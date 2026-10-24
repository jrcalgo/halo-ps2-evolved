"""Schema-validated import of selected retail tag roots and their dependencies.

This produces a normalized image plus tag records; resource payloads remain
source descriptors and are never silently stripped or copied into tag data.
"""
from __future__ import annotations

from collections import deque
from bisect import bisect_right
import hashlib
import json
from pathlib import Path
import struct

from ctag_schema_walk import Walker, SchemaWalkError


class ImportError(ValueError): pass


def _hash(data): return hashlib.sha256(data).hexdigest()


class Source:
    def __init__(self, source_id, map_data, *, source_sha256=None):
        self.id=str(source_id); self.map=map_data; self.image=bytes(map_data.region); self.base=map_data.base
        self.by_path={(e.group,e.path):e for e in map_data.index.entries}
        self.by_datum={e.tag_id:e for e in map_data.index.entries}
        self.by_handle={e.tag_id:e.group for e in map_data.index.entries}
        source_path=getattr(map_data,'path',None)
        if source_sha256 is not None:
            if len(source_sha256)!=64: raise ImportError('invalid source SHA-256')
            self.sha256=source_sha256
        elif source_path is not None:
            with Path(source_path).open('rb') as source_file:
                source_hash=hashlib.sha256()
                for block in iter(lambda:source_file.read(1<<20),b''): source_hash.update(block)
                self.sha256=source_hash.hexdigest()
        else: self.sha256=_hash(self.image)

    @classmethod
    def from_map(cls, path):
        from halo2ps2 import texconv
        return cls(Path(path).stem,texconv.MapData.open(path))


def _walk_root(src, entry, manifest):
    groups={g['group']:g for g in manifest['groups']}
    decl=groups.get(entry.group)
    if entry.group=='sbsp': return {'spans':[],'relocs':[],'refs':[],'indexes':[],'resources':[],'runtime_owner_slots':[],'edge_slots':{},
        'digest':_hash(entry.path.encode()),'span_data':[],'pointer_values':{}}
    if not decl or decl.get('definition') is None: raise ImportError(f"no schema for {entry.group}:{entry.path}")
    w=Walker(manifest,src.image,src.base,file_data_policy='inventory',unknown_group_policy='reject')
    w.tag_groups_by_handle=src.by_handle.copy()
    root=entry.data_address-src.base
    w.add_span(root,w.schema(decl['definition'])['size'],f"root {entry.group}:{entry.path}")
    w.walk_definition(decl['definition'],root)
    refs=[]; indexes=[]; names=[]; filedata=[]; runtime_slots=[]
    def visit(did,at,depth=0,field_path=()):
        if depth>32: raise ImportError('schema nesting exceeded')
        d=w.schema(did)
        layout=manifest.get('runtime_normalization_layout',{}).get('sound_permutation')
        if d['name']=='sound_permutation' and layout:
            if d['size']!=layout['size']:
                raise ImportError('sound permutation differs from the compiler-derived runtime layout')
            for member in ('cache_tag_index_offset','runtime_tag_index_offset'):
                offset=int(layout[member])
                if offset<0 or offset+4>d['size'] or offset&3:
                    raise ImportError('invalid compiler-derived sound owner field')
                runtime_slots.append({'offset':at+offset,'member':member})
        for f in d['fields']:
            pos=at+int(f['offset']); n=int(f['count']); size=int(f['size'])
            if f['kind']=='struct':
                for i in range(n): visit(f['definition'],pos+i*size,depth+1,field_path+(f['name'],))
            elif f['kind']=='block':
                for i in range(n):
                    p=pos+i*12; count=struct.unpack_from('<i',src.image,p)[0]
                    addr=struct.unpack_from('<I',src.image,p+4)[0]
                    if count:
                        nested=w.schema(f['definition']); target=addr-src.base
                        for j in range(count): visit(f['definition'],target+j*nested['size'],depth+1,field_path+(f['name'],))
            elif f['kind']=='reference':
                for i in range(n):
                    p=pos+i*16; group=src.image[p:p+4][::-1].decode('ascii','replace')
                    name_at=struct.unpack_from('<I',w.image,p+4)[0]
                    if name_at: names.append(name_at)
                    datum=struct.unpack_from('<I',src.image,p+12)[0]
                    if datum!=0xffffffff:
                        target=src.by_datum.get(datum)
                        refs.append({'offset':p+12,'definition':d['name'],'field':'.'.join(x for x in field_path+(f['name'],) if x),'group':group,'source_datum':datum,
                                     'path':target.path if target else None,'target_group':target.group if target else None})
            elif f['kind']=='file_data':
                for i in range(n):
                    p=pos+i*size
                    length,flags,offset=struct.unpack_from('<iIi',src.image,p)
                    if not length: continue
                    if flags!=0: raise ImportError(f'unsupported resource pointer domain {flags} in {entry.path}')
                    source_path=getattr(src.map,'path',None)
                    if source_path is None: raise ImportError(f'file-backed resource has no source file: {entry.path}')
                    if offset<0 or length>Path(source_path).stat().st_size-offset:
                        raise ImportError(f'file-backed resource leaves source map: {entry.path}')
                    cache=getattr(src,'resource_hashes',None)
                    if cache is None: src.resource_hashes=cache={}
                    key=(offset,length)
                    if key not in cache:
                        digest=hashlib.sha256()
                        with Path(source_path).open('rb') as stream:
                            stream.seek(offset); remaining=length
                            while remaining:
                                block=stream.read(min(remaining,1<<20))
                                if not block: raise ImportError(f'truncated resource in {entry.path}')
                                digest.update(block); remaining-=len(block)
                        cache[key]=digest.hexdigest()
                    filedata.append({'definition':d['name'],'field':f['name'],
                        'bytes':length,'flags':flags,'source_offset':offset,
                        'descriptor_offset':p,'payload_sha256':cache[key]})
            elif f['kind']=='tag_index':
                for i in range(n):
                    p=pos+i*size
                    width=size
                    value=int.from_bytes(src.image[p:p+width],'little')
                    if value not in (0xffff,0xffffffff):
                        index=value & 0xffff
                        target=next((x for x in src.map.index.entries if x.index==index and
                                     (not f.get('groups') or x.group in f['groups'])),None)
                        indexes.append({'offset':p,'width':width,'source_index':index,
                            'group':target.group if target else None,'path':target.path if target else None})
                        if target is None: raise ImportError(f"unresolved typed tag_index {value:#x} in {entry.path}.{f['name']}")
    visit(decl['definition'],root)
    spans=sorted((a,b) for a,b,_ in w.spans)
    # Tag-reference names are schema-typed pointers but are intentionally not
    # included in Walker spans; retain each bounded string as part of this tag.
    for name_at in names:
        end=src.image.find(b'\0',name_at,min(len(src.image),name_at+256))
        if end<0: raise ImportError(f"unterminated reference name in {entry.path}")
        spans.append((name_at,end+1))
    # Some engine schemas share tag-name storage through a pointer whose
    # owning reference is nested in a dynamically selected block. Retain only
    # bounded path strings for any otherwise-unowned schema pointer target.
    covered=lambda p:any(a<=p<b for a,b,_ in w.spans)
    for slot in w.relocations:
        target=struct.unpack_from('<I',w.image,slot)[0]
        if not target or covered(target) or any(a<=target<b for a,b in spans): continue
        end=src.image.find(b'\0',target,min(len(src.image),target+256))
        if end<0: raise ImportError(f"pointer target {target:#x} is outside retained spans in {entry.path}")
        raw=src.image[target:end]
        try: text=raw.decode('ascii')
        except UnicodeDecodeError as error: raise ImportError(f"unclassified pointer target in {entry.path}") from error
        if '\\' not in text: raise ImportError(f"unclassified pointer target {target:#x} in {entry.path}")
        spans.append((target,end+1))
    spans.sort()
    merged=[]
    for a,b in spans:
        if merged and a<=merged[-1][1]: merged[-1]=(merged[-1][0],max(merged[-1][1],b))
        else: merged.append((a,b))
    sig=bytearray(b''.join(w.image[a:b] for a,b in merged))
    relocs=sorted(w.relocations)
    # Source virtual addresses and retail datums are map-local. Canonicalize
    # those typed slots while preserving all other schema bytes for dedup.
    pos=0; ranges=[]; starts=[]
    for a,b in merged: starts.append(a); ranges.append((a,b,pos)); pos+=b-a
    def canonical_offset(source_offset):
        i=bisect_right(starts,source_offset)-1
        if i>=0:
            a,b,baseout=ranges[i]
            if source_offset<b: return baseout+source_offset-a
        return None
    for p in relocs:
        q=canonical_offset(p)
        if q is not None:
            value=struct.unpack_from('<I',w.image,p)[0]
            nonnull=struct.unpack_from('<I',src.image,p)[0]!=0
            target=canonical_offset(value) if nonnull else None
            if nonnull and target is None: raise ImportError(f'unretained canonical pointer in {entry.path}')
            struct.pack_into('<I',sig,q,0 if target is None else target+1)
    for ref in refs:
        q=canonical_offset(ref['offset'])
        if q is not None: sig[q:q+4]=bytes(4)
    for row in indexes:
        q=canonical_offset(row['offset'])
        if q is not None: sig[q:q+row['width']]=bytes(row['width'])
    for slot in runtime_slots:
        q=canonical_offset(slot['offset'])
        if q is None: raise ImportError('sound owner identity field not retained')
        sig[q:q+4]=bytes(4)
    for resource in filedata:
        # Source file offsets are addresses, not payload identity. Keep the
        # selected source descriptor in output, but deduplicate by actual bytes.
        q=canonical_offset(resource['descriptor_offset']+8)
        if q is None: raise ImportError('resource descriptor not retained')
        sig[q:q+4]=bytes(4)
    resource_identity=[(r['definition'],r['field'],r['bytes'],r['payload_sha256']) for r in filedata]
    return {'spans':merged,'relocs':relocs,'refs':refs,'indexes':indexes,
            'resources':filedata,'runtime_owner_slots':runtime_slots,
            # Equal payload bytes can deduplicate across source maps; provenance
            # remains attached to the deterministically selected descriptor.
            'digest':_hash(bytes(sig)+json.dumps(resource_identity,separators=(',',':')).encode()), 'span_data':[(a,bytes(w.image[a:b])) for a,b in merged],
            'pointer_values':{p:(struct.unpack_from('<I',w.image,p)[0] if struct.unpack_from('<I',src.image,p)[0] else None) for p in relocs},
            'edge_slots':{p:canonical_offset(p) for p in
                          [r['offset'] for r in refs]+[r['offset'] for r in indexes]}}


def import_profile(sources, roots, schema_manifest, *, source_priority=None, scenario_root=None):
    """Import roots as ``{source,group,path}``; dependencies resolve by source map.

    ``sources`` maps stable source names to halo2ps2 MapData objects. The return
    image is an append-only normalized tag-data image; table records expose
    stable sequential handles and root offsets for the caller's CTAG envelope.
    """
    if isinstance(schema_manifest,(str,Path)): schema_manifest=json.loads(Path(schema_manifest).read_text())
    if schema_manifest.get('format')!='hcu-schema-manifest-v1': raise ImportError('unsupported schema manifest')
    runtime_layout=schema_manifest.get('runtime_normalization_layout')
    if runtime_layout and runtime_layout.get('schema_elf_sha256')!=schema_manifest.get('elf_sha256'):
        raise ImportError('runtime normalization layout is not bound to the linked schema ELF')
    sources={str(k):v if isinstance(v,Source) else Source(k,v) for k,v in sources.items()}
    priority=list(source_priority or sorted(sources)); rank={x:i for i,x in enumerate(priority)}
    selected={}; queue=deque(); occurrences={}
    normalized_roots=[]
    for root in roots:
        if isinstance(root,(tuple,list)): root={'source':root[0],'group':root[1],'path':root[2]}
        normalized_roots.append(root)
    roots=normalized_roots
    if scenario_root is not None:
        if isinstance(scenario_root,(tuple,list)): scenario_root={'source':scenario_root[0],'group':scenario_root[1],'path':scenario_root[2]}
        roots.append(scenario_root)
    # The mounted map owns the only file-data extents a selected package can read.
    mounted_source=None if scenario_root is None else str(scenario_root['source'])
    roots.sort(key=lambda r:(rank.get(str(r['source']),len(rank)),str(r['source']),r['group'],r['path']))
    for root in roots:
        sid=str(root['source']); src=sources.get(sid)
        if src is None: raise ImportError(f"missing source {sid}")
        e=src.by_path.get((root['group'],root['path']))
        if e is None: raise ImportError(f"missing root {root['group']}:{root['path']} in {sid}")
        queue.append((src,e))
    processed=set()
    while queue:
        src,e=queue.popleft(); key=(e.group,e.path)
        proc=(src.id,e.group,e.path)
        if proc in processed: continue
        processed.add(proc)
        item=_walk_root(src,e,schema_manifest)
        occurrence=(src.id,e.group,e.path)
        occurrences[occurrence]={'source':src,'entry':e,'walk':item}
        for ref in item['refs']:
            if ref['path'] is None or ref['target_group']!=ref['group']:
                raise ImportError(f"unresolved dependency {ref['group']} datum {ref['source_datum']:#x} from {e.path}")
            target=src.by_path.get((ref['group'],ref['path']))
            if target is None: raise ImportError(f"missing dependency {ref['group']}:{ref['path']} in {src.id}")
            queue.append((src,target))
        for ref in item['indexes']:
            target=src.by_path.get((ref['group'],ref['path']))
            if target is None: raise ImportError(f"missing tag_index dependency {ref['group']}:{ref['path']} in {src.id}")
            queue.append((src,target))
    # A root signature includes every reachable dependency payload. The set is
    # cycle-safe and keeps same-path conflicting target content partitioned.
    occurrence_identity={}
    for occurrence,base_row in occurrences.items():
        srcid=occurrence[0]; todo=[occurrence]; visited=set(); closure=[]
        while todo:
            current=todo.pop()
            if current in visited: continue
            visited.add(current); row=occurrences[current]; wi=row['walk']; ce=current[1:]
            edges=sorted((wi['edge_slots'][edge['offset']], edge.get('width',4), edge['group'],edge['path'])
                         for edge in wi['refs']+wi['indexes'])
            # Retain edge ownership and slot order as well as payload hashes:
            # a reachable set alone cannot distinguish swapped dependencies.
            closure.append((ce[0],ce[1],wi['digest'],edges))
            for edge in wi['refs']+wi['indexes']:
                todo.append((srcid,edge['group'],edge['path']))
        signature=_hash(json.dumps({'local':base_row['walk']['digest'],'closure':sorted(closure)},sort_keys=True,separators=(',',':')).encode())
        occurrence_identity[occurrence]=(occurrence[1],occurrence[2],signature)
    for occurrence,identity in occurrence_identity.items():
        row=occurrences[occurrence]; prior=selected.get(identity)
        if prior is None: selected[identity]={**row,'aliases':{row['source'].id},'conflicts':[]}
        else: prior['aliases'].add(row['source'].id)
    by_logical={}
    for identity,row in selected.items(): by_logical.setdefault(identity[:2],[]).append(identity)
    for logical,variants in by_logical.items():
        if len(variants)>1:
            variants.sort(key=lambda ident:(rank.get(selected[ident]['source'].id,len(rank)),selected[ident]['source'].id,ident[2]))
            for ident in variants:
                selected[ident]['conflicts']=[{'stable_key':f'{v[0]}:{v[1]}#{v[2]}','source':selected[v]['source'].id} for v in variants if v!=ident]
    resolution={occurrence:identity for occurrence,identity in occurrence_identity.items()}
    identities=sorted(selected,key=lambda ident:(ident[0],ident[1],
        rank.get(selected[ident]['source'].id,len(rank)),selected[ident]['source'].id,ident[2]))
    handle={identity:i for i,identity in enumerate(identities)}
    out=bytearray(4); records=[]; reloc=[]; ref_reloc=[]; index_remaps=[]; resources=[]; bitmap_consumers=[]; runtime_normalizations=[]
    for identity in identities:
        row=selected[identity]; src,e,w=row['source'],row['entry'],row['walk']
        starts=[]; output_ranges=[]
        for a,data in w['span_data']:
            out.extend(bytes((-len(out)) & 3)); baseout=len(out)
            starts.append(a); output_ranges.append((a,a+len(data),baseout))
            out.extend(data)
        def output_offset(source_offset):
            i=bisect_right(starts,source_offset)-1
            if i>=0:
                a,b,baseout=output_ranges[i]
                if source_offset<b: return baseout+source_offset-a
            return None
        root_out=None if e.group=='sbsp' else output_offset(e.data_address-src.base)
        if e.group!='sbsp' and root_out is None: raise ImportError(f'root not retained: {e.path}')
        for p in w['relocs']:
            field=output_offset(p)
            if field is None: continue
            val=w['pointer_values'][p]
            target=output_offset(val) if val is not None else None
            if val is not None and target is None: raise ImportError(f"pointer target not retained for {e.path} at {p:#x}")
            struct.pack_into('<I',out,field,target or 0); reloc.append(field)
        for slot in w['runtime_owner_slots']:
            field=output_offset(slot['offset'])
            if field is None: raise ImportError('sound owner field not retained in output')
            previous=struct.unpack_from('<I',out,field)[0]
            struct.pack_into('<I',out,field,handle[identity])
            runtime_normalizations.append({'field':field,'definition':'sound_permutation',
                'member':slot['member'],'source_key':src.id,'source_datum':e.tag_id,
                'source_value':previous,'output_datum':handle[identity],
                'policy':'owning_sound_tag_identity_relocation'})
        records.append({'handle':handle[identity],'group':e.group,'path':e.path,'datum':handle[identity],
            'stable_key':f"{e.group}:{e.path}#{identity[2]}",'output_datum':handle[identity],
            'source':src.id,'source_key':src.id,'source_sha256':src.sha256,'source_datum':e.tag_id,'content_sha256':identity[2],'root_offset':root_out,
            'source_aliases':sorted(row['aliases']), 'conflicts':row['conflicts']})
        for r in w['resources']:
            field=output_offset(r['descriptor_offset'])
            if field is None: raise ImportError('resource descriptor not retained in output')
            if mounted_source is not None and src.id!=mounted_source:
                # Samples in another source map are not in the mounted map's
                # files. Keep identity in normalizations, not as an unbacked extent.
                struct.pack_into('<i',out,field,0); struct.pack_into('<i',out,field+8,0)
                runtime_normalizations.append({'field':field,'definition':'sound_permutation',
                    'member':r['field'],'source_key':src.id,'source_datum':e.tag_id,
                    'source_value':r['bytes'],'output_datum':handle[identity],
                    'source_offset':r['source_offset'],'payload_sha256':r['payload_sha256'],
                    'policy':'external_source_sample_metadata_only'})
                continue
            resources.append({'tag':e.path,'source':src.id,'source_sha256':src.sha256,**r,
                'output_descriptor_offset':field})
        for ref in w['refs']:
            if ref['path'] is None: raise ImportError('unresolved reference')
            target_key=(ref['group'],ref['path']); resolved=resolution.get((row['source'].id,*target_key))
            choices=[resolved] if resolved in handle else [x for x in identities if x[0]==target_key]
            if not choices: raise ImportError(f"dependency was not imported: {target_key}")
            chosen=choices[0]; field=output_offset(ref['offset'])
            if field is None: raise ImportError('tag reference field was not retained')
            struct.pack_into('<I',out,field,handle[chosen]); ref_reloc.append((field,handle[chosen]))
            if ref['group']=='bitm':
                bitmap_consumers.append({'owner_output_datum':handle[identity],
                    'owner_group':e.group,'owner_path':e.path,'source_key':src.id,
                    'definition':ref['definition'],'field':ref['field'],
                    'bitmap_output_datum':handle[chosen], 'bitmap_path':ref['path']})
        for idx in w['indexes']:
            target_key=(idx['group'],idx['path']); chosen=resolution[(src.id,*target_key)]
            field=output_offset(idx['offset'])
            if field is None: raise ImportError('tag_index field was not retained')
            struct.pack_into('<H' if idx['width']==2 else '<I',out,field,handle[chosen])
            index_remaps.append({'field':field,'width':idx['width'],'source_index':idx['source_index'],'output_index':handle[chosen],
                                 'target':f"{idx['group']}:{idx['path']}"})
    # Build a CE-compatible header/table around the selected roots. Tag names
    # are emitted in the image and every table pointer is an explicit relocation.
    scenario_key=None
    if scenario_root is not None:
        sr={'source':str(scenario_root['source']),'group':scenario_root['group'],'path':scenario_root['path']}
        if sr['group']!='scnr': raise ImportError('scenario_root must be a scenario tag')
        if sr['source'].lower() not in {'ui','beavercreek','bloodgulch','boardingaction','carousel','chillout','damnation','hangemhigh','longest','prisoner','putput','ratrace','sidewinder','wizard'}:
            raise ImportError(f"scenario source {sr['source']} is not an admitted UI/MP map")
        se=sources[sr['source']].by_path.get(('scnr',sr['path']))
        if se is None: raise ImportError(f"missing scenario root {sr['path']}")
        scenario_key=occurrence_identity.get((sr['source'],'scnr',se.path))
        if scenario_key not in handle: raise ImportError('scenario root must be included in roots')
    table_at=36; body_at=table_at+32*len(records)
    final=bytearray(body_at)+out
    for resource in resources: resource['output_descriptor_offset']+=body_at
    for index in index_remaps: index['field']+=body_at
    for normalization in runtime_normalizations: normalization['field']+=body_at
    for p in set(reloc):
        value=struct.unpack_from('<I',final,body_at+p)[0]
        if value: struct.pack_into('<I',final,body_at+p,body_at+value)
    table_reloc=[0,20,28]
    struct.pack_into('<9I',final,0,table_at,handle.get(scenario_key,0),0,len(records),0,0,0,0,0x74616773)
    for rec in records:
        i=rec['handle']; e=selected[identities[i]]['entry']; src=selected[identities[i]]['source']; off=table_at+i*32
        final[off:off+4]=e.group.encode('ascii')[::-1]
        parent=getattr(e,'parent',None); grandparent=getattr(e,'grandparent',None)
        struct.pack_into('<I',final,off+4,0xffffffff if not parent else int.from_bytes(parent.encode('ascii'),'big'))
        struct.pack_into('<I',final,off+8,0xffffffff if not grandparent else int.from_bytes(grandparent.encode('ascii'),'big'))
        struct.pack_into('<I',final,off+12,i)
        nameptr=len(final); final.extend(e.path.encode('ascii')+b'\0')
        struct.pack_into('<I',final,off+16,nameptr); table_reloc.append(off+16)
        rootptr=body_at+rec['root_offset'] if rec['group']!='sbsp' else 0
        struct.pack_into('<I',final,off+20,rootptr); table_reloc.append(off+20)
    final_reloc=tuple(sorted(set(table_reloc+[x+body_at for x in reloc])))
    final_tag_reloc=tuple(sorted((x+body_at,t) for x,t in ref_reloc))
    ctag_bytes=None
    if scenario_key is not None:
        from ctag import encode
        ctag_bytes=encode(bytes(final),final_reloc,scenario_tag_index=handle[scenario_key])
        validation=Walker(schema_manifest,bytes(final),0,file_data_policy='inventory',unknown_group_policy='reject').run()
        if validation.image!=bytes(final): raise ImportError('final schema validation unexpectedly normalized imported image')
    decisions=[]
    for rec in records:
        decisions.append({'stable_key':rec['stable_key'],'output_datum':rec['output_datum'],
            'canonical_source':rec['source'],'source_aliases':rec['source_aliases'],
            'decision':'content_deduplicated' if len(rec['source_aliases'])>1 else ('conflict_variant_preserved' if rec['conflicts'] else 'retained'),
            'conflicts':rec['conflicts']})
    return {'format':'hcu-profile-image-v1','image':bytes(final),'ctag':ctag_bytes,'relocations':final_reloc,
            'tag_relocations':final_tag_reloc,'tags':records,'resources':resources,
            'decisions':decisions,'tag_index_remaps':index_remaps,'bitmap_consumers':bitmap_consumers,'runtime_normalizations':runtime_normalizations,
            'memory_needs':{'image_bytes':len(final),'resident_ce_bytes':len(final),'pointer_relocations':len(final_reloc),'tag_relocations':len(final_tag_reloc)},
            'manifest':{'schema_elf_sha256':schema_manifest.get('elf_sha256'),'tag_count':len(records),
                        'source_priority':priority},
            'source_occurrence_remaps':[
                {'source_key':key[0],'group':key[1],'path':key[2],
                 'source_datum':occurrences[key]['entry'].tag_id,
                 'output_datum':handle[resolution[key]],
                 'stable_key':records[handle[resolution[key]]]['stable_key']}
                for key in sorted(resolution)]}
