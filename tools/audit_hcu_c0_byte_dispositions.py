#!/usr/bin/env python3
"""Build a byte-retention disposition for every serialized BSP inventory row."""
import argparse, hashlib, json
from pathlib import Path

DEFAULT_OUT = "docs/reports/m2-c0-byte-dispositions-2026-10-23.json"
INVENTORY = "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
LAYOUT = "docs/reports/m2-step7-bsp-range-member-layout-2026-10-22.json"
OPAQUE = "docs/reports/m2-step7-unclassified-range-dispositions-2026-10-22.json"
ROOTS = "docs/reports/m2-step7-open-root-bsp-dispositions-2026-10-22.json"
ROUNDTRIP = "docs/reports/retail-bsp-cbsp-audit-c0-2026-10-22.json"
EMPTY = "docs/reports/m2-step7-empty-bsp-fields-2026-10-22.json"

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def build(root=Path('.')):
    read=lambda p: json.loads((root/p).read_text())
    inv, layout, opaque, roots, roundtrip, empty = map(read,(INVENTORY,LAYOUT,OPAQUE,ROOTS,ROUNDTRIP,EMPTY))
    layouts={(d.get('definition'),d.get('schema_range',{}).get('offset'),d.get('schema_range',{}).get('size')):d for d in layout['ranges']}
    opaque_keys={(r.get('definition'),r.get('schema_range',{}).get('offset'),r.get('schema_range',{}).get('size')) for r in opaque['ranges']}
    root_members={r['inventory_path']:r for r in roots['rows']}
    root_paths=set(root_members)
    opaque_members={r['inventory_path']:r for r in opaque['ranges']}
    empty_paths=set(empty.get('empty_across_retail',[]))|set(empty.get('empty_in_any_retail',[]))
    rows=[]; problems=[]
    for report,label in ((roots,'root'),(opaque,'opaque')):
        if report['inventory_sha256'] != digest(root/INVENTORY): problems.append(f'{label} inventory pin mismatch')
    if inv['compiler_layout']['status'] != 'passed': problems.append('compiler layout did not pass')
    if roundtrip['schema_elf_sha256'] != inv['schema_elf_sha256']: problems.append('round-trip schema mismatch')
    if roundtrip['cbsp_round_trip_failure_count'] != 0: problems.append('CBSP round-trip failed')
    if len(empty['empty_in_any_retail']) != 41: problems.append('synthetic empty-field coverage changed')
    for m in inv['members']:
        name,path,kind=m['definition'],m['path'],m['kind']; off,size=m['offset_within_definition'],m['size']
        if size == 0 and kind == 'check':
            rows.append({'definition':name,'path':path,'offset':off,'size':size,'kind':kind,'classification':m['classification'],'disposition':'zero_byte_sentinel_check','evidence':EMPTY,'compiler_interval_covered':True,'empty_sentinel_check':True}); continue
        if size < 0: problems.append(f"invalid size {path}"); continue
        if m['classification'] in ('unclassified-range','unclassified'):
            disp='retain_opaque_unchanged'; evidence=OPAQUE
            if (name,off,size) not in opaque_keys: problems.append(f"opaque range not dispositioned {path}")
            typed=opaque_members.get(path,{})
            if typed.get('compiler_byte_interval_coverage',{}).get('status') != 'complete': problems.append(f'incomplete compiler coverage {path}')
            retained=typed.get('retained_byte_evidence',{})
            if not retained.get('path') or digest(root/retained['path']) != retained['sha256']: problems.append(f'missing/stale retention test {path}')
        elif m['classification']=='consumer-disposition-open' or m['kind']=='C-layout-member-omitted-from-validation-schema' or path in root_paths:
            disp='preserve_root_bytes'; evidence=ROOTS
            typed=root_members.get(path,{})
            if typed.get('offset_within_definition')!=off or typed.get('size')!=size: problems.append(f'root disposition extent mismatch {path}')
            if typed.get('fixture','!missing') not in (root/roots['fixture_path']).read_text(): problems.append(f'missing root fixture {path}')
        else:
            policies={'enum':'preserve_value','block_index':'preserve_value','tag_index':'preserve_value',
                      'struct':'recursive_member_policy','block':'preserve_count_and_elements_relocate_address_reset_definition',
                      'data':'preserve_size_and_content_relocate_address','reference':'preserve_identity_apply_named_reference_policy',
                      'long_block':'preserve_count_and_elements_relocate_address_reset_definition'}
            if kind=='check': disp='zero_byte_sentinel_check'
            elif kind=='reset': disp='documented_runtime_reset'
            elif kind not in policies: problems.append(f"unknown kind {kind}: {path}"); disp='unclassified'
            else: disp=policies[kind]
            evidence=INVENTORY
        compiler_exact=(name,off,size) in layouts
        if m['classification'] in ('unclassified-range','unclassified') and not compiler_exact: problems.append(f"missing compiler interval {path}")
        rows.append({'definition':name,'path':path,'offset':off,'size':size,'kind':kind,'classification':m['classification'],'disposition':disp,'evidence':evidence,'compiler_interval_covered':compiler_exact,'empty_sentinel_check': path in empty_paths,
                     'schema_metadata':{k:m[k] for k in ('count','maximum','flags','target_level','target_offset','child_definition_id') if k in m},
                     'runtime_semantics':'remain subject to Step 7 consumer qualification'})
    for definition in inv['definitions']:
        spans=sorted((r['offset'],r['offset']+r['size']) for r in rows if r['definition']==definition['name'] and r['size'])
        cursor=0
        for left,right in spans:
            if left!=cursor: problems.append(f"unexplained gap/overlap in {definition['name']} at {cursor}")
            cursor=max(cursor,right)
        if cursor!=definition['serialized_size']: problems.append(f"uncovered tail in {definition['name']}")
    pins=[INVENTORY,LAYOUT,OPAQUE,ROOTS,ROUNDTRIP,EMPTY,inv['schema_elf'],roots['fixture_path'],
          'tools/ctag_schema_walk.py','tests/test_step7_unmapped_bsp_range_retention.py','tests/test_step7_synthetic_empty_bsp_fields.py']
    if roots['fixture_sha256'] != digest(root/roots['fixture_path']): problems.append('root fixture source changed')
    report={'format':'hcu-c0-byte-dispositions-v1','purpose':'C0 byte disposition accounting; does not qualify C4/C7 target semantics','source_pins':{p:digest(root/p) for p in pins},'inventory_rows':len(inv['members']),'disposition_rows':len(rows),'unclassified_member_dispositions':sum(r['disposition'] in (None,'unclassified') for r in rows),'unexplained_removals':0 if {r['path'] for r in rows}=={m['path'] for m in inv['members']} else 1,'issues':problems,'semantic_open_statuses_preserved':True,'rows':rows}
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',default=DEFAULT_OUT); args=ap.parse_args()
    r=build(); out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'output':args.output,'rows':r['disposition_rows'],'issues':len(r['issues'])}))
    return bool(r['issues'] or r['disposition_rows']!=r['inventory_rows'])
if __name__=='__main__': raise SystemExit(main())
