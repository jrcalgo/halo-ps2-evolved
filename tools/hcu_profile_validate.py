"""Strict host validator for HCP1 HCU profile packages and their manifests."""
from __future__ import annotations

import hashlib
import json
import ctypes
import struct
import subprocess
import tempfile
from pathlib import Path

import ctag
from ctag_schema_walk import Walker
import hcu_profile_chunks as chunks

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine"


def _media_reader():
    """Use the production readers for both structure and owner identities."""
    sources=[ENGINE/'src/world'/f'{stem}.{suffix}'
             for suffix in ('c','h') for stem in ('model','anim','tex')]
    wrapper_source="""#include <stddef.h>
#include <stdint.h>
#include "world/model.h"
#include "world/anim.h"
#include "world/tex.h"
int hcu_read(unsigned kind,const uint8_t *p,size_t n){
 if(kind==1){model_section s;return model_open(&s,p,n)==MODEL_OK;}
 if(kind==2){anim_section s;return anim_open(&s,p,n)==ANIM_OK;}
 if(kind==3){tex_section s;return tex_open(&s,p,n)==TEX_OK;}
 return 0;
}
int hcu_contains(unsigned kind,const uint8_t *p,size_t n,uint32_t id){
 if(kind==1){model_section s;return model_open(&s,p,n)==MODEL_OK && model_find(&s,id)>=0;}
 if(kind==2){anim_section s;return anim_open(&s,p,n)==ANIM_OK && anim_find_graph(&s,id)>=0;}
 if(kind==3){tex_section s;if(tex_open(&s,p,n)!=TEX_OK)return 0;
  for(uint32_t i=0;i<s.texture_count;i++)if(tex_get(&s,i).source_id==id)return 1;}
 return 0;
}
"""
    key=hashlib.sha256(wrapper_source.encode()+b''.join(p.read_bytes() for p in sources)).hexdigest()
    cache=Path(tempfile.gettempdir())/'hcu-c1-validator'
    cache.mkdir(exist_ok=True)
    libpath=cache/f'reader-{key}.so'
    if not libpath.exists():
        wrapper=cache/f'reader-{key}.c'; wrapper.write_text(wrapper_source)
        command=['cc','-shared','-fPIC','-std=c11','-I',str(ENGINE/'src'),
                 str(wrapper),*(str(p) for p in sources[:3]),'-lm','-o',str(libpath)]
        try: subprocess.run(command,check=True,capture_output=True,text=True)
        except (OSError,subprocess.CalledProcessError) as error:
            raise ProfileValidationError(f'cannot build qualified media readers: {error}') from error
    library=ctypes.CDLL(str(libpath))
    library.hcu_read.argtypes=(ctypes.c_uint,ctypes.c_void_p,ctypes.c_size_t)
    library.hcu_read.restype=ctypes.c_int
    library.hcu_contains.argtypes=(ctypes.c_uint,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32)
    library.hcu_contains.restype=ctypes.c_int
    library.hcu_read.contains=library.hcu_contains
    library.hcu_read.source_sha256=key
    return library.hcu_read


def _pose_reader():
    sources = [ROOT / 'src/stream' / f'hcu_pose_asset.{suffix}' for suffix in ('c', 'h')]
    key = _sha(b''.join(path.read_bytes() for path in sources))
    cache = Path(tempfile.gettempdir()) / 'hcu-c1-validator'
    cache.mkdir(exist_ok=True)
    target = cache / f'pose-{key}.so'
    if not target.is_file():
        try:
            subprocess.run(['cc', '-shared', '-fPIC', '-std=c99', str(sources[0]),
                            '-o', str(target)], check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as error:
            raise ProfileValidationError(f'cannot build pose asset reader: {error}') from error
    library = ctypes.CDLL(str(target))
    reader = library.hcu_pose_asset_validate
    reader.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
    reader.restype = ctypes.c_int
    return reader


def _check_pose(blob, row, bindings, media, manifest, actual, expected_presentation, chunk_id):
    """Bind the independently sourced pose to its imported CE weapon owner."""
    key = f'POSE:{_sha(blob)}'
    matching = [binding for binding in bindings if binding.get('chunk_key') == key]
    catalog = [asset for asset in media.get('pose_catalog', []) if asset.get('key') == key]
    if row.get('key') != key or len(matching) != 1 or len(catalog) != 1:
        raise ProfileValidationError('POSE chunk lacks one exact binding and catalog entry')
    binding, asset = matching[0], catalog[0]
    if asset.get('chunk_id') != chunk_id:
        raise ProfileValidationError('POSE catalog physical chunk identity is incorrect')
    expected = [item for item in expected_presentation['bindings']
                if item['asset_id'] == asset.get('asset_id')]
    if len(expected) != 1:
        raise ProfileValidationError('POSE asset identity is unknown')
    expected = expected[0]
    provenance = expected_presentation['provenance'][expected['asset_id']]
    if blob != expected_presentation['chunks'][expected['chunk_id']]:
        raise ProfileValidationError('POSE payload differs from the pinned source adapter')
    owner = asset.get('owner', {})
    occurrence = [item for item in manifest.get('source_occurrence_remaps', []) if all(
        item.get(field) == owner.get(field) for field in (
            'source_key', 'source_datum', 'group', 'path', 'output_datum'))]
    target = [tag for tag in actual if tag.get('output_datum') == owner.get('output_datum')]
    if (len(occurrence) != 1 or len(target) != 1 or owner.get('group') != expected['tag_group'] or
            owner.get('path') != expected['tag_path'] or
            (target[0]['group'], target[0]['path']) != (expected['tag_group'], expected['tag_path'])):
        raise ProfileValidationError('POSE owner does not identify its imported weapon source occurrence')
    if (binding.get('owner') != owner or binding.get('kind') != 'POSE' or
            binding.get('asset_id') != expected['asset_id'] or
            binding.get('jmad') != expected['jmad'] or asset.get('jmad') != expected['jmad'] or
            binding.get('runtime_admitted') is not False or asset.get('runtime_admitted') is not False or
            row.get('runtime_admitted') is not False or row.get('owners') != [owner]):
        raise ProfileValidationError('POSE catalog and consumer binding disagree')
    for field, value in (
            ('source_map', provenance['source_map']),
            ('source_map_sha256', provenance['source_map_sha256']),
            ('source_pose', provenance['source_header']),
            ('source_pose_sha256', provenance['source_header_sha256']),
            ('bytes', len(blob)), ('sha256', _sha(blob))):
        if asset.get(field) != value:
            raise ProfileValidationError(f'POSE source provenance or extent mismatch: {field}')
    consumer = row.get('engine_consumer', {})
    if consumer != {'path': 'src/stream/hcu_pose_asset.c', 'function': 'hcu_pose_asset_sample',
                    'source_sha256': _sha((ROOT / 'src/stream/hcu_pose_asset.c').read_bytes())}:
        raise ProfileValidationError('POSE consumer source identity is missing or stale')
    reader = _pose_reader()
    buffer = ctypes.create_string_buffer(blob)
    if not reader(buffer, len(blob)):
        raise ProfileValidationError('production POSE reader rejected payload')
    return expected['asset_id']


class ProfileValidationError(ValueError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalized(value):
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _entries(image):
    """Read CE tag identities from an already schema-checked image."""
    if len(image) < 36:
        raise ProfileValidationError("short CE image")
    table, scenario, _, count, *_ = struct.unpack_from("<9I", image)
    if count > 65536 or table > len(image) or count * 32 > len(image) - table:
        raise ProfileValidationError("invalid CE tag table bounds")
    if scenario >= count:
        raise ProfileValidationError("invalid CE scenario index")
    rows = []
    for i in range(count):
        at = table + i * 32
        group = image[at:at + 4][::-1].decode("ascii", "strict")
        datum = struct.unpack_from("<I", image, at + 12)[0]
        name_at, root = struct.unpack_from("<II", image, at + 16)
        if datum != i or name_at >= len(image):
            raise ProfileValidationError("invalid CE tag identity fields")
        end = image.find(b"\0", name_at, min(len(image), name_at + 256))
        if end < 0:
            raise ProfileValidationError("unterminated CE tag path")
        path = image[name_at:end].decode("ascii", "strict")
        rows.append({"output_datum": datum, "group": group, "path": path,
                     "root_offset": root,"name_offset":name_at})
    return scenario, rows


def parse_package(data: bytes, *, expected_package_sha256: str,
                  expected_profile_id: int) -> dict:
    """Validate HCP1 structure, integrity, and exact package identity."""
    if _sha(data) != expected_package_sha256:
        raise ProfileValidationError("package SHA-256 mismatch")
    if len(data) < chunks.HEADER.size:
        raise ProfileValidationError("truncated HCP header")
    magic, version, hsize, profile_id, count, directory, dsize, total = chunks.HEADER.unpack_from(data)
    if magic != chunks.MAGIC or version != chunks.VERSION or hsize != chunks.HEADER.size:
        raise ProfileValidationError("unsupported HCP header")
    if profile_id != expected_profile_id or not profile_id:
        raise ProfileValidationError("profile id mismatch")
    if count < 2 or count > chunks.MAX_CHUNKS or directory != hsize or dsize != count * chunks.RECORD.size:
        raise ProfileValidationError("invalid HCP directory bounds")
    dir_end = directory + dsize
    if total != len(data) or dir_end > total:
        raise ProfileValidationError("invalid HCP total size")
    table, chunks_found = [], {}
    payload_end = dir_end
    previous = None
    for i in range(count):
        kind, cid, offset, size, digest = chunks.RECORD.unpack_from(data, directory + i * chunks.RECORD.size)
        key = (kind, cid)
        if previous is not None and key <= previous:
            raise ProfileValidationError("HCP entries are duplicated or out of order")
        previous = key
        if kind not in (1, 2, 3) or (kind != 2 and cid != 0) or not size:
            raise ProfileValidationError("invalid HCP chunk identity or size")
        if offset % chunks.ALIGNMENT or offset < dir_end or offset > total or size > total - offset:
            raise ProfileValidationError("HCP chunk bounds/alignment invalid")
        expected_offset = (payload_end + chunks.ALIGNMENT - 1) & ~(chunks.ALIGNMENT - 1)
        if offset != expected_offset or any(data[payload_end:offset]):
            raise ProfileValidationError("HCP payload ranges are not canonical or padding is nonzero")
        payload_end = offset + size
        blob = data[offset:offset + size]
        if hashlib.sha256(blob).digest() != digest:
            raise ProfileValidationError("HCP chunk hash mismatch")
        chunks_found[key] = blob
        table.append({"type": kind, "id": cid, "offset": offset, "size": size,
                      "sha256": digest.hex()})
    if (1, 0) not in chunks_found or (3, 0) not in chunks_found:
        raise ProfileValidationError("required CE or sound metadata chunk missing")
    if payload_end != total:
        raise ProfileValidationError("trailing bytes after final HCP payload")
    return {"profile_id": profile_id, "chunks": chunks_found, "directory": table}


def _schema_dependencies(image, schema, tags, *, roots=None):
    """Enumerate typed dependency slots; a manifest cannot hide an edge."""
    definitions=schema['definitions']
    groups={g['group']:g for g in schema['groups']}
    references={}; indexes={}; resources={}; bitmap_consumers=[]; visited=set()
    def visit(did,at,owner,field_path=()):
        key=(did,at)
        if key in visited: return
        visited.add(key)
        definition=definitions[str(did)]
        for field in definition['fields']:
            pos=at+field['offset']; width=field['size']
            for i in range(field['count']):
                offset=pos+i*width; kind=field['kind']
                if kind=='struct': visit(field['definition'],offset,owner,field_path+(field['name'],))
                elif kind=='block':
                    count,target=struct.unpack_from('<iI',image,offset)
                    stride=definitions[str(field['definition'])]['size']
                    for j in range(count): visit(field['definition'],target+j*stride,owner,field_path+(field['name'],))
                elif kind=='file_data':
                    size,flags,file_offset=struct.unpack_from('<iIi',image,offset)
                    if size:
                        resources[offset]={'definition':definition['name'],'field':field['name'],
                            'bytes':size,'flags':flags,'source_offset':file_offset,
                            'owner':owner}
                elif kind=='reference':
                    target=struct.unpack_from('<I',image,offset+12)[0]
                    if target==0xffffffff: continue
                    group=image[offset:offset+4][::-1].decode('ascii')
                    if target>=len(tags) or tags[target]['group']!=group:
                        raise ProfileValidationError('schema reference target group/datum is unresolved')
                    references[offset+12]=target
                    if group=='bitm':
                        bitmap_consumers.append({'owner_output_datum':owner['output_datum'],
                            'owner_group':owner['group'],'owner_path':owner['path'],
                            'definition':definition['name'],
                            'field':'.'.join(x for x in field_path+(field['name'],) if x),
                            'bitmap_output_datum':target,'bitmap_path':tags[target]['path']})
                elif kind=='tag_index':
                    target=int.from_bytes(image[offset:offset+width],'little')
                    if target in (0xffff,(1<<(width*8))-1): continue
                    if target>=len(tags) or (field.get('groups') and tags[target]['group'] not in field['groups']):
                        raise ProfileValidationError('schema typed tag index is unresolved')
                    indexes[offset]=(target,width)
    for tag in (tags if roots is None else roots):
        declaration=groups[tag['group']]
        if tag['root_offset'] and declaration.get('definition') is not None:
            visit(declaration['definition'],tag['root_offset'],tag)
    return references,indexes,resources,bitmap_consumers


def _bitmap_inventory(image, schema, tags):
    definitions=schema['definitions']
    group=next((g for g in schema['groups'] if g['group']=='bitm'),None)
    inventory={}
    if not group: return inventory
    definition=definitions[str(group['definition'])]
    field=next(f for f in definition['fields'] if f['name']=='bitmaps' and f['kind']=='block')
    element=definitions[str(field['definition'])]
    kind=next(f for f in element['fields'] if f['name']=='type')
    for tag in tags:
        if tag['group']!='bitm': continue
        count,address=struct.unpack_from('<iI',image,tag['root_offset']+field['offset'])
        if count<=0: raise ProfileValidationError('bitmap tag has no addressable image')
        for index in range(count):
            at=address+index*element['size']+kind['offset']
            inventory[(tag['output_datum'],index)]=int.from_bytes(image[at:at+kind['size']],'little')
    return inventory


CONSUMER_EXCLUSION_DISPOSITION='excluded_by_consumer_exclusion'
_SELECTED_BITMAP_ROLES=frozenset({'ps2_model_otex_base_selected','ps2_bsp_material_base_selected','ps2_bsp_lightmap_page_selected'})


def _check_consumer_exclusion(disposition,dependency,key,kind,consumers,media,profile_kind):
    """Re-derive a consumer-excluded image from the manifest's pinned exclusion rules."""
    import hcu_profile_consumer_exclusions as rules
    policy=media.get('consumer_exclusion_policy')
    if not isinstance(policy,dict) or profile_kind is None or policy.get('profile_kind')!=profile_kind:
        raise ProfileValidationError('consumer exclusion lacks a matching pinned policy')
    if disposition.get('exclusion_sha256')!=policy.get('sha256') or not isinstance(policy.get('rows'),list):
        raise ProfileValidationError('consumer exclusion does not match the pinned exclusion file')
    if kind not in (0,1,2):
        raise ProfileValidationError('consumer exclusion has an invalid image type')
    actual=[c for c in consumers if c['bitmap_output_datum']==key[0]]
    if not actual:
        raise ProfileValidationError('consumer exclusion has no consumer reference')
    for descriptor in media.get('bsp_catalog',[]):
        owner=descriptor.get('owner',{})
        if owner.get('source_key')!=dependency.get('source_key'):
            continue
        for remap in descriptor.get('tag_remaps',[]):
            if remap.get('group')=='bitm' and remap.get('source_datum')==dependency.get('source_datum'):
                raise ProfileValidationError('BSP-selected bitmap cannot be consumer-excluded')
    roles=[rules.reference_role(c) for c in actual]
    role='+'.join(sorted(set(roles)))
    if role!=disposition.get('role') or any(r in _SELECTED_BITMAP_ROLES for r in roles):
        raise ProfileValidationError('consumer exclusion role does not match the CTAG consumers')
    decision=rules.decide_references(actual,profile_kind,policy['rows'])
    if decision['keep'] or sorted({r['class'] for r in decision['rows']})!=sorted(disposition.get('exclusion_classes',[])):
        raise ProfileValidationError('consumer exclusion is not covered by the pinned rules')


def _check_bitmap_coverage(image,schema,tags,declared,media,bindings,consumers,profile_kind=None,typed=None):
    """Account for every image, deriving exclusions again from the linked schema."""
    inventory=_bitmap_inventory(image,schema,tags)
    lookup={(d.get('source_key'),d.get('source_datum'),d.get('path')):d for d in declared if d['group']=='bitm'}
    covered=set()
    for binding in bindings:
        if binding.get('kind')!='BITM': continue
        owner=binding.get('owner',{})
        dependency=lookup.get((owner.get('source_key'),owner.get('source_datum'),owner.get('path')))
        index=owner.get('source_image_index')
        if dependency is None or not isinstance(index,int) or index<0 or binding.get('source_image_index')!=index:
            raise ProfileValidationError('BITM binding lacks a precise source image identity')
        key=(dependency['output_datum'],index)
        if inventory.get(key)!=0 or key in covered:
            raise ProfileValidationError('BITM binding has an invalid or duplicated 2D image index')
        covered.add(key)
    excluded=set()
    declared_gates=set(media.get('disabled_features',[]))
    for asset in media.get('bitmap_catalog',[]):
        dependency=lookup.get((asset.get('source_key'),asset.get('source_datum'),asset.get('path')))
        if dependency is None: raise ProfileValidationError('bitmap catalog has an unknown owner')
        for disposition in asset.get('dispositions',[]):
            index=disposition.get('source_image_index')
            key=(dependency['output_datum'],index)
            kind=inventory.get(key)
            if disposition.get('disposition')==CONSUMER_EXCLUSION_DISPOSITION:
                if key in excluded:
                    raise ProfileValidationError('consumer exclusion has a duplicated image index')
                _check_consumer_exclusion(disposition,dependency,key,kind,
                    list(consumers)+[r for rows in (typed or {}).values() for r in rows],media,profile_kind)
                excluded.add(key)
                continue
            if kind not in (1,2) or key in excluded:
                raise ProfileValidationError('bitmap exclusion has an invalid or duplicated image index')
            from hcu_profile_package import classify_bitmap_role
            actual=[c for c in consumers if c['bitmap_output_datum']==key[0]]
            owners=[{'group':c['owner_group'],'field':c['field']} for c in actual]
            rule=classify_bitmap_role(dependency['path'],'cube' if kind==2 else '3d',owners)
            gate=rule.get('feature_gate')
            gates=[gate] if isinstance(gate,str) else gate
            recorded_gate=disposition.get('feature_gate')
            recorded_gates=[recorded_gate] if isinstance(recorded_gate,str) else recorded_gate
            if (not actual or not isinstance(gates,list) or not gates or
                    any(not isinstance(g,str) or g not in declared_gates for g in gates) or recorded_gates!=gates or
                    rule.get('payload_disposition')!='exclude_from_current_ps2_visual_profile_under_explicit_feature_gate'):
                raise ProfileValidationError('bitmap exclusion has no matching disabled consumer feature')
            recorded=disposition.get('schema_consumers',[])
            def owner_signature(c):
                return tuple(c.get(k) for k in ('owner_output_datum','owner_group','owner_path','definition','field','bitmap_output_datum','bitmap_path'))
            if sorted(map(owner_signature,recorded))!=sorted(map(owner_signature,actual)):
                raise ProfileValidationError('bitmap exclusion consumers do not match the CTAG schema')
            if disposition.get('source_sha256')!=asset.get('source_sha256'):
                raise ProfileValidationError('bitmap exclusion source identity mismatch')
            if not isinstance(disposition.get('source_pixel_sha256'),str) or len(disposition['source_pixel_sha256'])!=64:
                raise ProfileValidationError('bitmap exclusion has no source pixel integrity identity')
            excluded.add(key)
    if covered|excluded!=set(inventory) or covered&excluded:
        raise ProfileValidationError('profile has missing or incompatible bitmap image dependencies')
    return {'images':len(inventory),'serialized_images':len(covered),'excluded_nonconsumer_images':len(excluded)}


def _check_cbsp(blob,row,bindings,media,tag_image,tags,declared,schema,profile_manifest):
    import cbsp
    from ctag_schema_walk import walk_structure_bsp
    decoded=cbsp.decode(blob,max_image_size=len(blob))
    matching=[b for b in bindings if b.get('chunk_key')==row['key']]
    catalog=[b for b in media.get('bsp_catalog',[]) if b.get('chunk_key')==row['key']]
    if len(matching)!=1 or len(catalog)!=1:
        raise ProfileValidationError('CBSP chunk must have one exact owner and catalog entry')
    binding=matching[0]; descriptor=catalog[0]; owner=binding.get('owner',{})
    datum=owner.get('output_datum')
    if (not isinstance(datum,int) or datum>=len(tags) or datum<0 or tags[datum]['group']!='sbsp' or
            owner.get('group')!='sbsp' or owner.get('path')!=tags[datum]['path'] or descriptor.get('owner')!=owner):
        raise ProfileValidationError('CBSP owner is not the imported BSP tag identity')
    dependency=declared[datum]
    if any(owner.get(k)!=dependency.get(k) for k in ('source_key','source_datum','group','path','output_datum')):
        raise ProfileValidationError('CBSP owner source tuple mismatch')
    source=profile_manifest.get('source_maps',{}).get(owner['source_key'],{})
    if (descriptor.get('source_map_sha256')!=source.get('sha256') or
            descriptor.get('schema_elf_sha256')!=schema.get('elf_sha256') or
            descriptor.get('output_cbsp_sha256')!=row['sha256'] or
            descriptor.get('source_file_offset')!=decoded.source_file_offset or
            descriptor.get('source_file_size')!=decoded.source_file_size):
        raise ProfileValidationError('CBSP extent or source/schema identity mismatch')
    names={t['name_offset'] for t in tags}
    bsp_base=0x10000000; tag_base=0x20000000
    def map_name(pointer):
        offset=pointer-tag_base
        if offset not in names: raise ProfileValidationError('CBSP external name is not a CTAG tag name')
        return offset
    materialized=decoded.materialize(bsp_base,tag_base,tag_image)
    walked=walk_structure_bsp(schema,materialized,bsp_base,map_name,file_data_policy='reject')
    if (walked.image!=decoded.image or tuple(walked.relocations)!=tuple(decoded.relocations) or
            tuple(walked.tag_relocations)!=tuple(decoded.tag_relocations)):
        raise ProfileValidationError('CBSP pointer domains do not match linked BSP schema')
    root=struct.unpack_from('<I',decoded.image,0)[0]
    refs,indexes,resources,_=_schema_dependencies(decoded.image,schema,tags,
        roots=[dict(tags[datum],root_offset=root)])
    if resources: raise ProfileValidationError('CBSP has unsupported external resources')
    relocations=dict(decoded.tag_relocations)
    if set(relocations)!={field-8 for field in refs}:
        raise ProfileValidationError('CBSP tag-name relocation domain is incomplete')
    for field,target in refs.items():
        if relocations[field-8]!=tags[target]['name_offset']:
            raise ProfileValidationError('CBSP reference name and datum identify different CTAG tags')
    remaps=descriptor.get('tag_remaps',[])
    declared_refs={r['field']+12:r.get('output_datum') for r in remaps if r.get('kind')=='reference'}
    declared_indexes={r['field']:r.get('output_datum') for r in remaps if r.get('kind')=='tag_index'}
    if (declared_refs!=refs or len(declared_refs)!=sum(r.get('kind')=='reference' for r in remaps) or
            declared_indexes!={field:value[0] for field,value in indexes.items()}):
        raise ProfileValidationError('CBSP remap ledger omits or changes a typed dependency')
    occurrences={(r['source_key'],r['group'],r['path'],r['source_datum']):r['output_datum']
                 for r in profile_manifest.get('source_occurrence_remaps',[])}
    for remap in remaps:
        key=(owner['source_key'],remap.get('group'),remap.get('path'),remap.get('source_datum'))
        if occurrences.get(key)!=remap.get('output_datum'):
            raise ProfileValidationError('CBSP dependency does not match imported source occurrence')
    return datum


def validate(data: bytes, manifest: dict, schema_manifest: dict, *,
             expected_package_sha256: str, expected_profile_id: int,
             expected_scenario: str) -> dict:
    """Validate packaged CE closure against its manifest and real schema.

    Accepts the ``hcu-built-profile-v1`` builder manifest. Media chunks and
    file-backed resources fail closed until qualified readers are linked.
    """
    try:
        package = parse_package(data, expected_package_sha256=expected_package_sha256,
                                expected_profile_id=expected_profile_id)
        ctag_data = package["chunks"][(1, 0)]
        decoded = ctag.decode(ctag_data, max_image_size=len(ctag_data))
        walked = Walker(schema_manifest, decoded.image, 0, file_data_policy="inventory",
                        unknown_group_policy="reject").run()
    except (ValueError, KeyError, struct.error, UnicodeError) as error:
        raise ProfileValidationError(str(error)) from error
    if walked.image != decoded.image:
        raise ProfileValidationError("CE image is not schema-normalized")
    scenario_index, actual = _entries(decoded.image)
    if decoded.scenario_tag_index != scenario_index:
        raise ProfileValidationError("CTAG and CE scenario indices differ")
    scenarios = [r for r in actual if r["group"] == "scnr" and r["path"].lower() == expected_scenario.lower()]
    if len(scenarios) != 1 or scenarios[0]["output_datum"] != scenario_index:
        raise ProfileValidationError("expected real scenario tag is absent or not selected")
    if manifest.get("format") != "hcu-profile-image-v1":
        if manifest.get("format") != "hcu-built-profile-v1":
            raise ProfileValidationError("unsupported profile manifest")
    if manifest.get("schema_elf_sha256") != schema_manifest.get("elf_sha256"):
        raise ProfileValidationError("schema ELF SHA-256 mismatch")
    declared = _normalized(manifest.get("tags", manifest.get("dependencies", [])))
    identities = [{k: r[k] for k in ("output_datum", "group", "path")} for r in actual]
    declared_ids = [{k: r.get(k) for k in ("output_datum", "group", "path")} for r in declared]
    if _normalized(identities) != _normalized(declared_ids):
        raise ProfileValidationError("manifest tag identities do not match CTAG")
    by_datum = {r["output_datum"]: (r["group"], r["path"]) for r in actual}
    for field, target in manifest.get("tag_relocations", []):
        if (not isinstance(field, int) or field < 0 or field > len(decoded.image) - 4 or
                target not in by_datum or struct.unpack_from("<I", decoded.image, field)[0] != target):
            raise ProfileValidationError("manifest dependency slot/output datum does not match CTAG")
    for row in manifest.get("tag_index_remaps", []):
        target = row.get("output_index")
        identity = row.get("target", "").split(":", 1)
        if target not in by_datum or len(identity) != 2 or by_datum[target] != tuple(identity):
            raise ProfileValidationError("manifest index dependency does not match CTAG identity")
    actual_refs,actual_indexes,schema_resources,bitmap_consumers=_schema_dependencies(decoded.image,schema_manifest,actual)
    declared_refs=manifest.get('tag_relocations',[])
    if len(declared_refs)!=len(actual_refs) or dict(declared_refs)!=actual_refs:
        raise ProfileValidationError('manifest omits or alters schema reference dependency slots')
    declared_indexes=manifest.get('tag_index_remaps',[])
    if len(declared_indexes)!=len(actual_indexes):
        raise ProfileValidationError('manifest omits schema typed tag index dependency slots')
    for row in declared_indexes:
        if actual_indexes.get(row.get('field'))!=(row.get('output_index'),row.get('width')):
            raise ProfileValidationError('manifest typed tag index slot does not match schema')
    actual_resources = list(walked.file_data_records)
    declared_resources=manifest.get('resources',[])
    if len(actual_resources)!=len(schema_resources):
        raise ProfileValidationError('schema walk found unclassified file-backed resources')
    if len(declared_resources)!=len(schema_resources):
        raise ProfileValidationError('profile has unsupported unmapped file-backed resources')
    if schema_resources:
        if manifest.get('resource_policy')!={'sound_samples':'metadata_only_spu2_unqualified'}:
            raise ProfileValidationError('profile has unsupported unmapped file-backed resources')
        by_descriptor={r.get('output_descriptor_offset'):r for r in declared_resources}
        if len(by_descriptor)!=len(schema_resources):
            raise ProfileValidationError('duplicate resource descriptors')
        for offset,actual_resource in schema_resources.items():
            resource=by_descriptor.get(offset)
            owner=actual_resource['owner']
            if (resource is None or owner['group']!='snd!' or
                    actual_resource['definition']!='sound_permutation' or actual_resource['field']!='samples' or
                    actual_resource['flags']!=0 or actual_resource['source_offset']<0):
                raise ProfileValidationError('unqualified file-backed resource consumer')
            for field in ('definition','field','bytes','flags','source_offset'):
                if resource.get(field)!=actual_resource[field]:
                    raise ProfileValidationError('resource descriptor does not match schema bytes')
            declared_owner=declared[owner['output_datum']]
            source=resource.get('source')
            source_row=manifest.get('source_maps',{}).get(source,{})
            if (resource.get('tag')!=owner['path'] or declared_owner.get('source_key')!=source or
                    resource.get('source_sha256')!=source_row.get('sha256')):
                raise ProfileValidationError('resource source identity is not bound to its owner')
            for field in ('source_sha256','payload_sha256'):
                value=resource.get(field)
                if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
                    raise ProfileValidationError('resource provenance lacks an exact SHA-256')
    chunk_rows = sorted(((cid, blob) for (kind, cid), blob in package["chunks"].items() if kind == 2))
    media = manifest.get("media", {})
    declared_chunks = media.get("chunks", []) if isinstance(media, dict) else []
    bindings = media.get("bindings", []) if isinstance(media, dict) else []
    if len(declared_chunks) != len(chunk_rows):
        raise ProfileValidationError("media manifest/chunk count mismatch")
    known_chunk_keys={row.get('key') for row in declared_chunks}
    if any(not isinstance(binding,dict) or binding.get('chunk_key') not in known_chunk_keys for binding in bindings):
        raise ProfileValidationError('media binding refers to a missing chunk')
    media_read = _media_reader() if chunk_rows else None
    # BITM candidates use the production TEXS reader for structural validation.
    # This does not imply that a runtime bitmap packet/presentation consumer exists.
    bsp_owners=[]
    parsers = {"MODL": 1, "ANIM": 2, "OTEX": 3, "BITM": 3,"CBSP":4,'POSE':6}
    from hcu_profile_presentation import build_presentation
    presentation = build_presentation(ROOT)
    pose_assets = []
    for index, ((chunk_id, blob), row) in enumerate(zip(chunk_rows, declared_chunks), 1):
        kind = row.get("kind")
        if chunk_id != index or kind not in parsers:
            raise ProfileValidationError("media chunk has no qualified parser/consumer")
        if row.get("bytes") != len(blob) or row.get("sha256") != _sha(blob):
            raise ProfileValidationError("media chunk hash/size does not match manifest")
        if kind=='CBSP':
            try:
                bsp_owners.append(_check_cbsp(blob,row,bindings,media,decoded.image,actual,declared,schema_manifest,manifest))
            except (ValueError,KeyError,IndexError,struct.error) as error:
                raise ProfileValidationError(f'CBSP validation failed: {error}') from error
            continue
        if kind == 'POSE':
            try:
                pose_assets.append(_check_pose(blob, row, bindings, media, manifest, actual, presentation, chunk_id))
            except (ValueError, KeyError, IndexError, struct.error) as error:
                raise ProfileValidationError(f'POSE validation failed: {error}') from error
            continue
        buf = ctypes.create_string_buffer(blob)
        if not media_read(parsers[kind], buf, len(blob)):
            raise ProfileValidationError(f"production {kind} reader rejected media chunk")
        key = row.get("key")
        if key!=f"{kind}:{_sha(blob)}":
            raise ProfileValidationError('media stable key does not match payload identity')
        matching = [b for b in bindings if b.get("chunk_key") == key]
        if not matching:
            raise ProfileValidationError("media chunk has no declared tag binding")
        for binding in matching:
            owner = binding.get("owner", {})
            identity = (owner.get('source_key'),owner.get('group'),owner.get('path'),owner.get('source_datum'))
            if not any((d.get('source_key'),d.get('group'),d.get('path'),d.get('source_datum')) == identity and
                       d.get("output_datum") in by_datum for d in declared):
                raise ProfileValidationError("media binding owner is not a declared CTAG dependency")
            owner_group=owner.get('group')
            if (kind=='MODL' and owner_group!='mode') or (kind=='ANIM' and owner_group!='antr') or (kind=='BITM' and owner_group!='bitm'):
                raise ProfileValidationError('media kind does not match owner group')
            if kind=='BITM' and (owner_group!='bitm' or binding.get('runtime_admitted') is not False):
                raise ProfileValidationError('BITM candidate lacks an explicit non-admitted bitmap owner')
            if kind in ('MODL','ANIM') or owner_group=='bitm':
                if not media_read.contains(parsers[kind],buf,len(blob),owner['source_datum']):
                    raise ProfileValidationError('media payload does not contain declared owner source identity')
    expected_bsp={tag['output_datum'] for tag in actual if tag['group']=='sbsp'}
    if len(bsp_owners)!=len(expected_bsp) or set(bsp_owners)!=expected_bsp:
        raise ProfileValidationError('profile does not bind every BSP tag to a CBSP payload')
    expected_poses = {item['asset_id'] for item in (presentation or {}).get('bindings', [])
                      if any(tag['group'] == item['tag_group'] and tag['path'] == item['tag_path'] for tag in actual)}
    if len(pose_assets) != len(set(pose_assets)) or set(pose_assets) != expected_poses:
        raise ProfileValidationError('profile POSE payload coverage is incomplete or duplicated')
    import hcu_profile_consumer_exclusions as rules
    typed_refs=rules.typed_references(decoded.image,schema_manifest,manifest.get('tag_index_remaps',[]))
    bitmap_coverage=_check_bitmap_coverage(decoded.image,schema_manifest,actual,declared,media,bindings,bitmap_consumers,
        profile_kind=(manifest.get('profile') or {}).get('kind'),typed=typed_refs)
    sound = package["chunks"][(3, 0)]
    try:
        sound_obj = json.loads(sound)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ProfileValidationError("invalid sound metadata JSON") from error
    if (not isinstance(sound_obj, dict) or sound_obj.get("format") != "hcu-profile-sound-metadata-v1" or
            not isinstance(sound_obj.get("sources"), dict)):
        raise ProfileValidationError("unsupported sound metadata format")
    expected_sounds={(d.get('source_key'),d.get('source_datum'),d.get('path'))
                     for d in declared if d.get('group')=='snd!'}
    actual_sounds=[]
    for source,records in sound_obj['sources'].items():
        if not isinstance(records,list): raise ProfileValidationError('invalid sound source records')
        for record in records:
            if not isinstance(record,dict): raise ProfileValidationError('invalid sound identity record')
            actual_sounds.append((source,record.get('datum'),record.get('path')))
    if len(actual_sounds)!=len(expected_sounds) or set(actual_sounds)!=expected_sounds:
        raise ProfileValidationError('sound identity metadata does not match CE sound tags')
    return {"profile_id": expected_profile_id, "scenario": expected_scenario,
            "tag_count": len(actual), "media_chunk_count": len(chunk_rows),
            "bitmap_coverage":bitmap_coverage,"bsp_count":len(bsp_owners),
            "media_reader_source_sha256":media_read.source_sha256 if media_read else None,
            "package_sha256": _sha(data)}


def validate_files(package_path, manifest_path, schema_path, *, expected_package_sha256,
                   expected_profile_id, expected_scenario):
    manifest = json.loads(Path(manifest_path).read_text())
    schema = json.loads(Path(schema_path).read_text())
    return validate(Path(package_path).read_bytes(), manifest, schema,
                    expected_package_sha256=expected_package_sha256,
                    expected_profile_id=expected_profile_id,
                    expected_scenario=expected_scenario)
