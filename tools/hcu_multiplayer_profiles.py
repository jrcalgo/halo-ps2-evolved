#!/usr/bin/env python3
"""Build deterministic UI, multiplayer bot, and survival HCP profiles."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'tools'
sys.path[:0]=[str(TOOLS),str(ROOT/'submodules/halo-ps2/tools')]
from hcu_profile_import import Source, import_profile  # noqa: E402
from hcu_profile_media import build_media, media_json_summary  # noqa: E402
from hcu_profile_package import build_complete_media
from hcu_profile_package import append_cbsp_chunks, append_presentation_chunks
from hcu_profile_bsp import bsp_profile_inputs, rebind_profile_bsp
from hcu_profile_validate import validate
from hcu_profile_chunks import encode as encode_hcp  # noqa: E402
from hcu_schema_manifest import Elf32, SchemaManifest  # noqa: E402
from hcu_profile_runtime_layout import run_probe as run_runtime_layout_probe  # noqa: E402
from hcu_profile_presentation import build_presentation
import ctag  # noqa: E402
from halo2ps2 import texconv  # noqa: E402

MP_MAPS=('beavercreek','bloodgulch','boardingaction','carousel','chillout','damnation',
         'hangemhigh','longest','prisoner','putput','ratrace','sidewinder','wizard')
DEFAULT_MAPS=ROOT/'build/retail-maps/decompressed'
DEFAULT_ROSTER=ROOT/'docs/reports/m2-c1-actor-roster-2026-10-23.json'
DEFAULT_WEAPONS=ROOT/'docs/reports/m2-c1-special-weapons-2026-10-23.json'
DEFAULT_ELF=ROOT/'build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf'


class BuildCache:
    """Read each map and its bytes once during a build invocation."""
    def __init__(self):
        self.maps={}; self.hashes={}; self.sources={}
        self.media_conversions={}; self.bitmap_conversions={}; self.bsp_inputs={}
        self.presentation=None

    def map(self, path):
        path=Path(path).resolve()
        if path not in self.maps:
            self.maps[path]=texconv.MapData.open(path)
        return self.maps[path]

    def sha(self, path):
        path=Path(path).resolve()
        if path not in self.hashes:
            self.hashes[path]=sha_file(path)
        return self.hashes[path]

    def source(self, path):
        path=Path(path).resolve()
        if path not in self.sources:
            self.sources[path]=Source(path.stem,self.map(path),source_sha256=self.sha(path))
        return self.sources[path]


def sha_bytes(data): return hashlib.sha256(data).hexdigest()
def sha_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''): digest.update(block)
    return digest.hexdigest()


def _scenario(path, cache=None):
    md=cache.map(path) if cache else texconv.MapData.open(path)
    rows=[e for e in md.index.entries if e.group=='scnr']
    if len(rows)!=1: raise ValueError(f"{path}: expected one scenario root, found {len(rows)}")
    return rows[0].path


def build_specs(roster:dict, weapon_report:dict, maps_dir:Path=DEFAULT_MAPS, cache=None) -> dict:
    """Return canonical 27 profile specs, retaining all real actor occurrences."""
    source_rows={r['map']:r for r in roster['source_roots']}
    for map_name,row in source_rows.items():
        path=maps_dir/f'{map_name}.map'
        actual=cache.sha(path) if cache and path.is_file() else (sha_file(path) if path.is_file() else None)
        if not path.is_file() or actual!=row.get('sha256'):
            raise ValueError(f"missing/changed actor source map {path}")
    if weapon_report.get('source_map_sha256'):
        base=maps_dir/Path(weapon_report.get('source_map','c40.map')).name
        actual=cache.sha(base) if cache and base.is_file() else (sha_file(base) if base.is_file() else None)
        if not base.is_file() or actual!=weapon_report['source_map_sha256']:
            raise ValueError(f"special weapon report source map hash mismatch: {base}")
    actor_roots=[]
    for row in roster['variants']:
        if row.get('disposition')=='combat' and row.get('recipe'):
            actor_roots.append({'source':row['map'],'group':'actv','path':row['path'],'role':'combat_variant','placement_recipe':row['recipe']})
        for mounted in row.get('mounted_recipes',[]):
            actor_roots.append({'source':row['map'],'group':'actv','path':row['path'],'role':'mounted_variant',
                                'parent_vehicle':mounted['parent_vehicle'],'seat_index':mounted['seat_index'],'placement_recipe':mounted})
    actor_roots.sort(key=lambda x:(x['source'],x['group'],x['path'],x['role']))
    if not actor_roots: raise ValueError('actor roster contains no valid combat/mounted source occurrences')
    profiles=[]
    ui_path=maps_dir/'ui.map'
    if not ui_path.is_file(): raise ValueError(f'missing UI map {ui_path}')
    ui_md=cache.map(ui_path) if cache else texconv.MapData.open(ui_path)
    ui_scenario=_scenario(ui_path,cache)
    ui_roots=[{'source':'ui','group':'scnr','path':ui_scenario,'role':'scenario'}]
    for group in ('matg','hudg'):
        rows=[e for e in ui_md.index.entries if e.group==group]
        if len(rows)!=1: raise ValueError(f"ui: expected one {group} root, found {len(rows)}")
        ui_roots.append({'source':'ui','group':group,'path':rows[0].path,'role':f'{group}_global'})
    profiles.append({'id':1,'name':'ui','kind':'ui','map':'ui','scenario':{'source':'ui','group':'scnr','path':ui_scenario},
                     'actor_roots':[],'roots':ui_roots})
    special=[]
    weapon_rows=weapon_report.get('weapon_roots',{})
    if len(weapon_rows)!=3: raise ValueError(f"special weapon report must contain exactly 3 roots, found {len(weapon_rows)}")
    for key,row in sorted(weapon_rows.items()):
        source=Path(row['source_map']).stem
        if source not in source_rows: raise ValueError(f"special weapon source {source} absent from actor corpus")
        if not row.get('source_map_sha256'):
            raise ValueError(f"special weapon source {source} lacks mandatory source_map_sha256")
        special_map=maps_dir/f'{source}.map'
        actual=cache.sha(special_map) if cache else sha_file(special_map)
        if actual!=row['source_map_sha256']:
            raise ValueError(f"special weapon source hash mismatch for {source}")
        if row.get('root_tag',{}).get('group')!='weap' or not row.get('root_tag',{}).get('path'):
            raise ValueError(f"special weapon {key} has invalid root identity")
        special.append({'source':source,'group':row['root_tag']['group'],'path':row['root_tag']['path'],'role':f'special_weapon:{key}'})
    for kind in ('bots','survival'):
        for map_name in MP_MAPS:
            p=maps_dir/f'{map_name}.map'
            if not p.is_file(): raise ValueError(f'missing multiplayer source {p}')
            md=cache.map(p) if cache else texconv.MapData.open(p)
            spartan=[]
            for group,path in (('bipd','characters\\cyborg_mp\\cyborg_mp'),
                               ('weap','weapons\\assault rifle\\assault rifle'),
                               ('weap','weapons\\pistol\\pistol'),
                               ('weap','weapons\\plasma pistol\\plasma pistol')):
                if not any(e.group==group and e.path.casefold()==path.casefold() for e in md.index.entries):
                    raise ValueError(f"{map_name}: missing authentic Spartan root {group}:{path}")
                spartan.append({'source':map_name,'group':group,'path':path,'role':'spartan_asset'})
            scenario={'source':map_name,'group':'scnr','path':_scenario(p,cache)}
            profile_actors=actor_roots if kind=='survival' else []
            roots=[{'source':map_name,**{k:v for k,v in scenario.items() if k!='source'},'role':'scenario'}]
            for group in ('matg','hudg'):
                rows=[e for e in md.index.entries if e.group==group]
                if len(rows)!=1: raise ValueError(f"{map_name}: expected one {group} global, found {len(rows)}")
                roots.append({'source':map_name,'group':group,'path':rows[0].path,'role':f'{group}_global'})
            roots.extend(spartan); roots.extend(profile_actors); roots.extend(special)
            for actor in profile_actors:
                parent=actor.get('parent_vehicle')
                if parent:
                    roots.append({'source':actor['source'],'group':parent['group'],
                                  'path':parent['path'],'role':'mounted_parent_vehicle'})
            profiles.append({'id':len(profiles)+1,'name':f'{kind}-{map_name}','kind':kind,'map':map_name,
                             'scenario':scenario,'spartan_roots':spartan,'actor_roots':profile_actors,
                             'roots':roots})
    return {'format':'hcu-multiplayer-profile-specs-v1','roster_sha256':sha_bytes(json.dumps(roster,sort_keys=True,separators=(',',':')).encode()),
            'weapon_report_sha256':sha_bytes(json.dumps(weapon_report,sort_keys=True,separators=(',',':')).encode()),
            'profiles':profiles}


def _source_set(spec, maps_dir, cache=None):
    names=sorted({r['source'] for r in spec['roots']})
    out={}
    for name in names:
        path=maps_dir/f'{name}.map'
        if not path.is_file(): raise ValueError(f"missing required source map {path}")
        out[name]=cache.source(path) if cache else Source.from_map(path)
    return out


def _provenance_path(path):
    path=Path(path).resolve()
    try: return path.relative_to(ROOT).as_posix()
    except ValueError: return path.as_posix()


def prepare_profile_bsp_roots(spec:dict, maps_dir:Path, manifest:dict, cache=None):
    """Enumerate selected scenario-map BSPs and add their typed closure roots."""
    source_key=spec['scenario']['source']
    map_path=maps_dir/f'{source_key}.map'
    if not map_path.is_file(): raise ValueError(f'missing scenario source map for BSPs: {map_path}')
    source_map=cache.map(map_path) if cache else texconv.MapData.open(map_path)
    source_hash=cache.sha(map_path) if cache else sha_file(map_path)
    cache_key=(source_hash,manifest.get('elf_sha256'))
    if cache is not None and cache_key in cache.bsp_inputs:
        descriptors=cache.bsp_inputs[cache_key]
    else:
        descriptors=bsp_profile_inputs(source_map,manifest,source_key=source_key)
        if cache is not None: cache.bsp_inputs[cache_key]=descriptors
    descriptors=sorted(descriptors,key=lambda row:(row['path'],row['source_datum']))
    existing={(row['source'],row['group'],row['path']) for row in spec['roots']}
    for bsp_row in descriptors:
        owner=(bsp_row['source_key'],'sbsp',bsp_row['path'])
        if owner not in existing:
            spec['roots'].append({'source':owner[0],'group':owner[1],'path':owner[2],
                                  'role':'structure_bsp'})
            existing.add(owner)
        for dep in sorted(bsp_row['tag_dependencies'],key=lambda row:(row['source_key'],row['group'],row['path'])):
            identity=(dep['source_key'],dep['group'],dep['path'])
            if identity not in existing:
                spec['roots'].append({'source':identity[0],'group':identity[1],'path':identity[2],
                                      'role':'bsp_dependency'})
                existing.add(identity)
    summaries=[]
    for row in descriptors:
        summaries.append({k:v for k,v in row.items() if k!='payload'} | {
            'payload_bytes':len(row['payload'])})
    if spec.get('bsp_roots') is not None and spec['bsp_roots']!=summaries:
        raise ValueError(f"{spec['name']}: BSP dependency roots changed during independent rebuild")
    spec['bsp_roots']=summaries
    return descriptors


def actor_bindings(spec, result):
    remaps={(r['source_key'],r['group'],r['path']):r for r in result['source_occurrence_remaps']}
    def resolve(value,source):
        if isinstance(value,list): return [resolve(v,source) for v in value]
        if not isinstance(value,dict): return value
        answer={k:resolve(v,source) for k,v in value.items()}
        if value.get('group') and value.get('path'):
            ref=remaps.get((source,value['group'],value['path']))
            if ref is None: raise ValueError(f"placement dependency missing: {source}:{value['group']}:{value['path']}")
            answer.update(output_datum=ref['output_datum'],stable_key=ref['stable_key'])
        return answer
    bindings=[]
    for root in spec.get('actor_roots',[]):
        key=(root['source'],root['group'],root['path'])
        if key not in remaps: raise ValueError(f'actor root not imported: {key}')
        bindings.append({'source_key':root['source'],'path':root['path'],
            'role':root['role'],'output_datum':remaps[key]['output_datum'],
            'stable_key':remaps[key]['stable_key'],
            'recipe':resolve(root.get('placement_recipe',{}),root['source'])})
    return bindings


def _profile_memory(result):
    decoded=ctag.decode(result['ctag'],max_image_size=len(result['image']))
    return {**result['memory_needs'],
        'normalized_ctag_bytes':len(result['ctag']),
        'resident_recipe_bytes':len(decoded.image),
        'ctag_relocation_entries':len(decoded.relocations),
        'ctag_relocation_table_bytes':len(decoded.relocations)*4,
        'relocation_table_residency':'loader staging; excluded from resident_recipe_bytes'}


def _ctag_decode(ctag_bytes):
    import ctag as _ctag  # noqa: E402
    return _ctag.decode(ctag_bytes, max_image_size=64*1024*1024)


def build_one(spec, maps_dir:Path, manifest:dict, producers:dict, *, report_failures=False, cache=None,
              source_inputs=None, runtime_layout_probe=None, presentation=None,
              consumer_exclusions=None, render_bsp=None, object_profile=None) -> tuple[bytes|None,dict,dict]:
    bsp_inputs=prepare_profile_bsp_roots(spec,maps_dir,manifest,cache)
    sources=_source_set(spec,maps_dir,cache)
    scenario=spec['scenario']
    try:
        result=import_profile(sources,spec['roots'],manifest,source_priority=sorted(sources),scenario_root=scenario)
    except (ValueError,OSError,KeyError,IndexError,struct.error) as exc:
        if not report_failures: raise
        return (None,{'format':'hcu-profile-diagnostic-v1','profile':spec['name'],'roots':spec['roots'],
            'producers':producers,'schema_elf_sha256':manifest.get('elf_sha256'),'failure_stage':'import','error':str(exc),
            'source_inputs':source_inputs or {},'runtime_layout_probe':runtime_layout_probe,
            'source_maps':{k:{'path':_provenance_path(v.map.path),'sha256':cache.sha(v.map.path) if cache else sha_file(v.map.path)} for k,v in sorted(sources.items())}}, {})
    placements=actor_bindings(spec,result)
    memory=_profile_memory(result)
    presentation_provenance=None  # the media-failure diagnostic reports it even if media failed first
    if not result.get('ctag'): raise ValueError(f"{spec['name']}: scenario import did not produce CTAG")
    try:
        bsp_assets=[]
        remaps={(row['source_key'],row['group'],row['path'],row['source_datum']):row
                for row in result['source_occurrence_remaps']}
        for item in bsp_inputs:
            source_key=item['source_key']
            source_map=sources[source_key].map
            rebound=rebind_profile_bsp(item['payload'],manifest=manifest,import_result=result,
                                       source_map=source_map,source_key=source_key)
            owner=remaps.get((source_key,'sbsp',item['path'],item['source_datum']))
            if owner is None:
                raise ValueError(f"imported CTAG lacks BSP owner {source_key}:{item['path']}")
            bsp_assets.append({**{k:item[k] for k in ('source_key','group','path','source_datum',
                'source_file_offset','source_file_size','source_xbox_base','source_map_sha256',
                'schema_elf_sha256','cbsp_sha256','tag_dependencies')},
                'output_datum':owner['output_datum'],'payload':rebound['payload'],
                'output_cbsp_sha256':rebound['output_cbsp_sha256'],'source_cbsp_sha256':rebound['source_cbsp_sha256'],
                'tag_remaps':rebound['remaps']})
        input_hashes={k:(cache.sha(v.map.path) if cache else sha_file(v.map.path))
                      for k,v in sources.items()}
        # BSP-selected bitmaps (CBSP tag remaps) are never consumer-dropped.
        bsp_selected={(asset_key,int(row['source_datum']))
            for asset_key,asset_rows in ((i['source_key'],i['tag_remaps']) for i in bsp_assets)
            for row in asset_rows if row.get('group')=='bitm'} if consumer_exclusions else None
        if consumer_exclusions:
            # Bitmaps the pinned source BSPs select through shaders or lightmap pages are parent-reader live.
            import hcu_profile_consumer_exclusions as _guard_rules  # noqa: E402
            scanned_tags,scanned_lightmaps,_=_guard_rules.selected_bsp_bitmaps(
                [(i['source_key'],int(i['source_file_offset'])) for i in bsp_inputs],
                lambda key: sources[key].map)
            bsp_selected|={(k,d) for k,d in scanned_tags}|{(k,d) for k,d,_page in scanned_lightmaps}
        media=build_complete_media({k:v.map for k,v in sources.items()},result['tags'],manifest,
            result.get('bitmap_consumers',[]),
            conversion_cache=cache.media_conversions if cache else None,
            bitmap_cache=cache.bitmap_conversions if cache else None,
            input_hashes=input_hashes,
            consumer_exclusions=({**consumer_exclusions,'kind':spec['kind']} if consumer_exclusions else None),
            bsp_selected=bsp_selected,
            ctag_image=(_ctag_decode(result['ctag']).image if consumer_exclusions else None),
            schema=(manifest if consumer_exclusions else None),
            tag_index_remaps=(result['tag_index_remaps'] if consumer_exclusions else None),
            object_profile=object_profile)
        append_cbsp_chunks(media,bsp_assets)
        presentation_provenance=append_presentation_chunks(media,presentation,spec,
            result['source_occurrence_remaps']) if presentation is not None else None
    except (ValueError,OSError,KeyError,IndexError,struct.error) as exc:
        if not report_failures: raise
        return (None,{'format':'hcu-profile-diagnostic-v1','profile':spec['name'],'roots':spec['roots'],
            'producers':producers,'schema_elf_sha256':manifest.get('elf_sha256'),'failure_stage':'media','error':str(exc),
            'tag_count':len(result['tags']),'dependencies':result['tags'],'resources':result['resources'],
            'memory':memory,'decisions':result['decisions'],
            'source_occurrence_remaps':result['source_occurrence_remaps'],'actor_bindings':placements,
            'bitmap_consumers':result.get('bitmap_consumers',[]),
            'runtime_normalizations':result.get('runtime_normalizations',[]),
            'source_inputs':source_inputs or {},'runtime_layout_probe':runtime_layout_probe,
            'presentation_provenance':presentation_provenance,
            'unadmitted_ctag_sha256':sha_bytes(result['ctag']),
            'source_maps':{k:{'path':_provenance_path(v.map.path),'sha256':cache.sha(v.map.path) if cache else sha_file(v.map.path)} for k,v in sorted(sources.items())}},
            {'unadmitted.ctag':result['ctag']})
    media_chunks={i+1:bytes(c['data']) for i,c in enumerate(media['chunks'])}
    sound_meta=json.dumps({'format':'hcu-profile-sound-metadata-v1','sources':media['sound_metadata']},sort_keys=True,separators=(',',':')).encode()
    render=None
    if render_bsp is not None:
        # Opt-in C3 render chunks (BSPS/TEXS/LMn) for one scenario-map BSP index.
        import hcu_render_media as _render_media  # noqa: E402
        render=_render_media.build(maps_dir/f"{spec['scenario']['source']}.map",int(render_bsp))
    try:
        if render is None:
            package=encode_hcp(spec['id'],{'ce':result['ctag'],'media':media_chunks,'sound_meta':sound_meta})
        else:
            typed={(1,0):result['ctag'],(3,0):sound_meta}
            typed.update({(2,cid):blob for cid,blob in media_chunks.items()})
            typed.update(render['chunks'])
            package=encode_hcp(spec['id'],typed)
    except (ValueError,OSError,KeyError,IndexError,struct.error) as exc:
        if not report_failures: raise
        return (None,{'format':'hcu-profile-diagnostic-v1','profile':spec['name'],'roots':spec['roots'],
            'producers':producers,'schema_elf_sha256':manifest.get('elf_sha256'),
            'failure_stage':'package','error':str(exc),'tag_count':len(result['tags']),
            'dependencies':result['tags'],'resources':result['resources'],'memory':memory,
            'decisions':result['decisions'],'source_occurrence_remaps':result['source_occurrence_remaps'],
            'actor_bindings':placements,'bitmap_consumers':result.get('bitmap_consumers',[]),
            'runtime_normalizations':result.get('runtime_normalizations',[]),
            'source_inputs':source_inputs or {},'runtime_layout_probe':runtime_layout_probe,
            'presentation_provenance':presentation_provenance,
            'unadmitted_ctag_sha256':sha_bytes(result['ctag']),
            'media':media_json_summary(media),'media_chunk_count':len(media['chunks']),
            'source_maps':{k:{'path':_provenance_path(v.map.path),'sha256':cache.sha(v.map.path) if cache else sha_file(v.map.path)} for k,v in sorted(sources.items())}},
            {'unadmitted.ctag':result['ctag']})
    chunk_ids={c['key']:i+1 for i,c in enumerate(media['chunks'])}
    remaps={(r['source_key'],r['source_datum']):r for r in result['source_occurrence_remaps']}
    chunk_bindings=[]
    for binding in media['bindings']:
        original=binding['owner']; owner=remaps.get((original['source_key'],original['source_datum']))
        if owner is None: raise ValueError('media owner lacks imported source binding')
        chunk_bindings.append({'chunk_id':chunk_ids[binding['chunk_key']],
            'sha256':binding['chunk_key'].split(':',1)[1],
            **{k:binding[k] for k in ('kind','asset_id','presentation_chunk_id','jmad') if k in binding},
            'owner':{**{k:owner[k] for k in ('source_key','source_datum','group','path','output_datum')},
                     **({'source_image_index':binding['source_image_index']}
                        if 'source_image_index' in binding else {})},
            **({'source_image_index':binding['source_image_index']}
               if 'source_image_index' in binding else {})})
    profile_manifest={'format':'hcu-built-profile-v1','profile':{k:v for k,v in spec.items() if k not in ('roots','actor_roots','spartan_roots')},
        'source_maps':{k:{'path':_provenance_path(v.map.path),'sha256':cache.sha(v.map.path) if cache else sha_file(v.map.path)} for k,v in sorted(sources.items())},
        'producers':producers,'schema_elf_sha256':manifest.get('elf_sha256'),
        'roots':spec['roots'],'dependencies':[{'stable_key':t['stable_key'],'group':t['group'],'path':t['path'],
            'source_key':t['source_key'],'source_datum':t['source_datum'],'output_datum':t['output_datum'],
            'content_sha256':t['content_sha256'],'source_aliases':t['source_aliases'],'conflicts':t['conflicts']} for t in result['tags']],
        'decisions':result['decisions'],'resources':result['resources'],
        'resource_policy':{'sound_samples':'metadata_only_spu2_unqualified'},'memory':memory,
        'source_occurrence_remaps':result['source_occurrence_remaps'],'actor_bindings':placements,
        'bitmap_consumers':result.get('bitmap_consumers',[]),
        'runtime_normalizations':result.get('runtime_normalizations',[]),
        'source_inputs':source_inputs or {},'runtime_layout_probe':runtime_layout_probe,
        'presentation_provenance':presentation_provenance,
        'chunk_bindings':chunk_bindings,'tag_relocations':result['tag_relocations'],
        'tag_index_remaps':result['tag_index_remaps'],
        'media':media_json_summary(media),'package_sha256':sha_bytes(package),
        'reproducibility':{'sha256':sha_bytes(package)}}
    if render is not None:
        profile_manifest['render_media']=render['manifest']
    if object_profile is not None:
        # Opt-in lower-detail object packing (C3); recorded so the package's provenance names it.
        profile_manifest['object_profile']={'name':object_profile.name,'max_tex':object_profile.max_tex,
            'max_levels':object_profile.max_levels,
            'classes':{c:{'slots':list(l.slots),'cluster_fraction':l.cluster_fraction} for c,l in object_profile.classes}}
    profile_manifest['memory'].update({
        'package_file_bytes':len(package),
        'independently_addressable_media_bytes':media['memory']['independently_addressable_converted_bytes'],
        'media_bytes_residency':'on-disk independent chunks; excluded from resident_recipe_bytes'})
    profile_manifest['validation']=validate(package,profile_manifest,manifest,
        expected_package_sha256=sha_bytes(package),expected_profile_id=spec['id'],
        expected_scenario=scenario['path'])
    return package,profile_manifest,{}


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    mode=ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--spec-only',action='store_true')
    mode.add_argument('--all',action='store_true')
    mode.add_argument('--profile',action='append',default=[],help='profile name; repeat to build a subset')
    mode.add_argument('--session-selection',type=Path,
        help='build one complete HCP2 package from a hcu-session-roster-selection-v1 JSON')
    ap.add_argument('--report-failures',action='store_true',help='write diagnostics without emitting HCP packages for failures')
    ap.add_argument('--verify-rebuild',action='store_true',help='run a second independent import/conversion and compare outputs')
    ap.add_argument('--maps',type=Path,default=DEFAULT_MAPS)
    ap.add_argument('--roster',type=Path,default=DEFAULT_ROSTER)
    ap.add_argument('--weapon-report',type=Path,default=DEFAULT_WEAPONS)
    ap.add_argument('--schema-elf',type=Path,default=DEFAULT_ELF)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--render-media',action='store_true',
        help='opt-in: append BSPS/TEXS/LMn render chunks for the selected BSP index (C3)')
    ap.add_argument('--render-bsp',type=int,default=0,help='structure BSP index for --render-media')
    ap.add_argument('--c3-object-profile',action='store_true',
        help='opt-in C3 lower-detail object packing (modelconv.C3_OBJECT_PROFILE): one clustered LOD, 64 px textures')
    ap.add_argument('--consumer-exclusions',type=Path,default=None,
        help='pinned exclusion rows; bitmap media with only excluded live consumers is omitted and recorded')
    args=ap.parse_args(argv)
    roster=json.loads(args.roster.read_text()); weapon_report=json.loads(args.weapon_report.read_text())
    cache=BuildCache()
    specs=build_specs(roster,weapon_report,args.maps,cache)
    if args.spec_only:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(specs,sort_keys=True,indent=2)+'\n'); return 0
    selected=specs['profiles'] if args.all else [p for p in specs['profiles'] if p['name'] in set(args.profile)]
    if args.session_selection:
        selection=json.loads(args.session_selection.read_text())
        if selection.get('format')!='hcu-session-roster-selection-v1':
            raise ValueError('unsupported session selection format')
        base=next((p for p in specs['profiles'] if p['name']==selection.get('scenario_profile')),None)
        if base is None or base.get('kind')!='survival':
            raise ValueError('session selection must name a retained C1 survival profile')
        source_hashes={row['map']:row['sha256'] for row in roster.get('source_roots',[])}
        available={(row['map'].casefold(),str(row['datum']),row['path'].casefold()):row
                   for row in roster.get('variants',[])
                   if (row.get('disposition')=='combat' and row.get('recipe')) or
                      (row.get('disposition')=='mounted_occupant' and row.get('mounted_recipes'))}
        selected_ids=set()
        for identity in selection.get('selected_variants',[]):
            key=(str(identity.get('source_map','')).casefold(),str(identity.get('source_datum')),
                 str(identity.get('path','')).casefold())
            row=available.get(key)
            if row is None or identity.get('source_map_sha256')!=source_hashes.get(row['map']):
                raise ValueError('session selection contains a missing or stale exact catalog identity')
            selected_ids.add((row['map'].casefold(),row['path'].casefold()))
        if not selected_ids:
            raise ValueError('session selection has no selected variants')
        actor_roots=[r for r in base.get('actor_roots',[]) if
                     (r['source'].casefold(),r['path'].casefold()) in selected_ids]
        if not actor_roots:
            raise ValueError('session selection resolves to no profile actor roots')
        parents={(r['source'].casefold(),r['parent_vehicle']['group'],r['parent_vehicle']['path'].casefold())
                 for r in actor_roots if r.get('parent_vehicle')}
        roots=[]
        for root in base['roots']:
            role=root.get('role','')
            if role in ('combat_variant','mounted_variant'):
                if (root['source'].casefold(),root['path'].casefold()) in selected_ids: roots.append(root)
            elif role=='mounted_parent_vehicle':
                if (root['source'].casefold(),root['group'],root['path'].casefold()) in parents: roots.append(root)
            else: roots.append(root)
        base=copy.deepcopy(base)
        base['name']=str(selection.get('name',''))
        if not base['name'] or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in base['name']):
            raise ValueError('session selection name must be filename-safe')
        base['actor_roots']=actor_roots; base['roots']=roots
        selected=[base]
    if args.profile and len(selected)!=len(set(args.profile)): raise ValueError('unknown profile name in --profile')
    if not selected: raise ValueError('no profiles selected')
    manifest=SchemaManifest(Elf32(args.schema_elf)).build()
    probe=run_runtime_layout_probe(args.output/'runtime-layout-probe',args.schema_elf)
    if probe.get('status')!='passed' or probe.get('inputs',{}).get('schema_elf_sha256')!=manifest.get('elf_sha256'):
        raise ValueError('target runtime-layout probe does not match the selected schema ELF')
    manifest['runtime_normalization_layout']={**probe['layout'],
        'schema_elf_sha256':manifest.get('elf_sha256')}
    runtime_layout_evidence={k:probe[k] for k in
        ('format','cache_key','inputs','layout','object_sha256','layout_section_sha256','limits')}
    source_inputs={
        'roster':{'path':_provenance_path(args.roster),'sha256':sha_file(args.roster)},
        'weapon_report':{'path':_provenance_path(args.weapon_report),'sha256':sha_file(args.weapon_report)},
        'schema_elf':{'path':_provenance_path(args.schema_elf),'sha256':sha_file(args.schema_elf)},
    }
    if args.session_selection:
        source_inputs['session_selection']={'path':_provenance_path(args.session_selection),
                                           'sha256':sha_file(args.session_selection)}
    consumer_exclusions=None
    if args.consumer_exclusions is not None:
        import hcu_profile_consumer_exclusions as _exclusion_rules  # noqa: E402
        consumer_exclusions=_exclusion_rules.load_exclusions(args.consumer_exclusions)
        source_inputs['consumer_exclusions']={'path':consumer_exclusions['path'],'sha256':consumer_exclusions['sha256']}
    # BSP schema normalization imports these lazily; load them before taking the
    # producer snapshot so every dependency is pinned on the first profile too.
    from halo2ps2 import bsp as _bsp, mapinfo as _mapinfo  # noqa: F401
    import ctag_schema_walk as _ctag_schema_walk  # noqa: F401
    import convert_retail_bsp as _convert_retail_bsp  # noqa: F401
    producer_paths=set()
    for module in tuple(sys.modules.values()):
        filename=getattr(module,'__file__',None)
        if not filename: continue
        path=Path(filename).resolve()
        if path.suffix=='.py' and (TOOLS in path.parents or ROOT/'submodules/halo-ps2/tools' in path.parents):
            producer_paths.add(path)
    producer_paths.add(Path(__file__).resolve())
    producers={str(path.relative_to(ROOT)):sha_file(path) for path in sorted(producer_paths)}
    args.output.mkdir(parents=True,exist_ok=True)
    failed=False
    object_profile=None
    if args.c3_object_profile:
        from halo2ps2 import modelconv as _modelconv  # noqa: E402
        object_profile=_modelconv.C3_OBJECT_PROFILE
    for spec in selected:
        stem=spec['name']
        # A failed rebuild must never leave a package from an earlier invocation.
        for suffix in ('.hcp','.json','.failure.json','.unadmitted.ctag'):
            stale=args.output/f'{stem}{suffix}'
            if stale.exists(): stale.unlink()
        if cache.presentation is None:
            cache.presentation=build_presentation(ROOT)
        package,profile_manifest,artifacts=build_one(spec,args.maps,manifest,producers,
            report_failures=args.report_failures,cache=cache,source_inputs=source_inputs,
            runtime_layout_probe=runtime_layout_evidence,presentation=cache.presentation,
            consumer_exclusions=consumer_exclusions,
            render_bsp=(args.render_bsp if args.render_media else None),
            object_profile=object_profile)
        if args.session_selection and package is not None:
            catalog_rows=[r for r in roster.get('variants',[]) if
                (r.get('disposition')=='combat' and r.get('recipe')) or
                (r.get('disposition')=='mounted_occupant' and r.get('mounted_recipes'))]
            if len(catalog_rows)!=255:
                raise ValueError(f'retained selectable catalog must remain complete (255 occurrences), found {len(catalog_rows)}')
            profile_manifest['selected_session_catalog']={
                'selection_sha256':sha_file(args.session_selection),
                'retained_roster_sha256':sha_file(args.roster),
                'selectable_catalog_occurrences':len(catalog_rows),
                'complete_catalog_availability_preserved':True,
                'selected_variants':json.loads(args.session_selection.read_text())['selected_variants'],
            }
        if args.verify_rebuild:
            package2,manifest2,artifacts2=build_one(spec,args.maps,manifest,producers,
                report_failures=args.report_failures,cache=BuildCache(),source_inputs=source_inputs,
                runtime_layout_probe=runtime_layout_evidence,presentation=cache.presentation,
                consumer_exclusions=consumer_exclusions,
                render_bsp=(args.render_bsp if args.render_media else None),
                object_profile=object_profile)
            if (package2,manifest2,artifacts2)!=(package,profile_manifest,artifacts):
                raise ValueError(f'{stem}: independent rebuild differs')
            profile_manifest.setdefault('reproducibility',{})['independent_rebuild_equal']=True
            profile_manifest['reproducibility']['scope']='complete package' if package else 'unadmitted diagnostic only'
        if package is None:
            failed=True
            for name,data in artifacts.items(): (args.output/f'{stem}.{name}').write_bytes(data)
            (args.output/f'{stem}.failure.json').write_text(json.dumps(profile_manifest,sort_keys=True,indent=2)+'\n')
        else:
            (args.output/f'{stem}.hcp').write_bytes(package)
            (args.output/f'{stem}.json').write_text(json.dumps(profile_manifest,sort_keys=True,indent=2)+'\n')
    (args.output/'specs.json').write_text(json.dumps(specs,sort_keys=True,indent=2)+'\n')
    return 1 if failed else 0


if __name__=='__main__':
    try: raise SystemExit(main())
    except (OSError,ValueError,KeyError) as exc: raise SystemExit(f"profile build failed: {exc}")
