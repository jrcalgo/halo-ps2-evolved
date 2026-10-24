#!/usr/bin/env python3
"""Add C1 requirement evidence without replacing the historical C0 baseline."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / 'docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json'
QUALIFICATION = Path('docs/reports/m2-c1-qualification-2026-10-23.json')
ROLE_AUDIT = Path('docs/reports/m2-c1-bitmap-consumer-roles-2026-10-23.json')
REPORTS = {
 'roster':'docs/reports/m2-c1-actor-roster-2026-10-23.json',
 'weapons':'docs/reports/m2-c1-special-weapons-2026-10-23.json',
 'media':'docs/reports/m2-c1-media-coverage-2026-10-23.json',
 'preflight':'docs/reports/m2-c1-preflight-2026-10-23.json',
 'ui_failure':'build/m2-c1-profiles-ui/ui.failure.json',
 'survival_failure':'build/m2-c1-survival-dedup/survival-beavercreek.failure.json',
}
CASES = [
 ('Deterministic UI, multiplayer-bot and survival profiles',
  'profile builder', ('roster','weapons','media','ui_failure','survival_failure'),
  'Deterministic manifests/packages identify roots, dependencies, hashes, decisions and per-profile memory.',
  '27 specifications exist; no complete admitted package or clean-build package reproducibility is proved.'),
 ('Every resolved combat actor and placement recipe',
  'actor roster and schema importer', ('roster','survival_failure'),
  'Import each resolved combat variant and complete dependency closure; retain real mounted/secondary recipes; explicitly classify noncombat/hollow data.',
  'Source recipes are inventoried; complete per-variant output bindings and imported runtime placement remain unqualified.'),
 ('Schema-driven import, remapping and deterministic identities',
  'schema importer', ('roster','ui_failure','survival_failure'),
  'Schema-derived reference remapping, stable identities, identical-dependency deduplication and deterministic conflict source choice; no synthesized MP actor references.',
  'Host importer tests and UI diagnostic do not establish complete admitted profiles or every resource binding.'),
 ('CE pointer lifetime and independently addressable media',
  'HCP storage and media consumers', ('media','preflight','ui_failure','survival_failure'),
  'Retain CE data for pointer lifetime; integrity-check independent media chunks and include only payloads with proven live consumers.',
  'Chunk envelope exists; uncovered UI/effect assets have no qualified consumer and imported HCP CE data is not mounted by production.'),
 ('Sword, gravity rifle and CE fuel rod with presentation provenance',
  'weapon closure and presentation converters', ('weapons',),
  'Complete three weapon closures, resolve both fuel-rod bitmap metadata records before visual admission, and retain custom presentation provenance.',
  'Cube layouts are classified and base/diffuse policy is recorded; full profile media admission and presentation bindings remain incomplete.'),
 ('Dependency compatibility rejection before map teardown',
  'profile validator and map service', ('preflight','ui_failure'),
  'Reject missing, corrupt and profile-incompatible dependencies before teardown; preserve sound identities/request metadata with SPU2 playback separate.',
  'Envelope/hash rejection is tested; production imported-profile dependency compatibility and resource routing are not wired.'),
]

def sha(path):
 digest=hashlib.sha256()
 with path.open('rb') as source:
  for block in iter(lambda:source.read(1<<20),b''): digest.update(block)
 return digest.hexdigest()

def nested_artifact_pins(value):
 """Retain file identities embedded in native evidence, including executables."""
 if isinstance(value,dict):
  if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str):
   yield {'path':value['path'],'sha256':value['sha256']}
  for name in ('implementation_source_pins','source_pins'):
   for path,digest in value.get(name,{}).items():
    # Some reports keep member identities (e.g. ui_ctag_chunk_sha256)
    # beside file pins. Those are artifact members, not missing file names.
    if (isinstance(path,str) and isinstance(digest,str) and len(digest)==64 and
        ('/' in path or Path(path).suffix)):
     yield {'path':path,'sha256':digest}
  for path_key,digest_key in (('serialized_texs_path','serialized_texs_file_sha256'),
                             ('source_map','source_map_sha256'),
                             ('schema_elf','schema_elf_sha256'),
                             ('stage_catalog','stage_catalog_sha256')):
   if isinstance(value.get(path_key),str) and isinstance(value.get(digest_key),str):
    yield {'path':value[path_key],'sha256':value[digest_key]}
  if value.get('format')=='hcu-c1-native-ce-corpus-v1':
   for row in value.get('profiles',[]):
    command=row.get('target',{}).get('command',[])
    if len(command)>1 and row.get('ctag_sha256'):
     yield {'path':command[1],'sha256':row['ctag_sha256']}
  for item in value.values(): yield from nested_artifact_pins(item)
 elif isinstance(value,list):
  for item in value: yield from nested_artifact_pins(item)

def qualification_rows(root, report_path):
 """Import exact requirement results while retaining their dependency pins."""
 report_file=root/report_path
 report=json.loads(report_file.read_text())
 requirements=report.get('requirements',[])
 if report.get('format')!='hcu-c1-qualification-v1' or len(requirements)!=6 or {
     row.get('id') for row in requirements}!={f'C1.{i}' for i in range(1,7)}:
  raise ValueError('C1 qualification must name all six exact acceptance requirements')
 producer=report.get('producer',{})
 inputs=[{'path':str(report_path),'sha256':sha(report_file)}]
 inputs.extend(report.get('verification_inputs',[]))
 if producer: inputs.append(producer)
 # The qualification report pins its child reports. Preserve their exact
 # executable, generated-source, log and journal file identities in each row
 # as well, rather than making fixture hashes terminate at another JSON file.
 child_reports=[]
 for key in ('native_ce_corpus','native_corpus','native_bitmap_dispatch','bitmap_dispatch',
             'real_ce_preflight_report','preflight_report'):
  name=report.get('inputs',{}).get(key)
  if name and (root/name).is_file(): child_reports.append(root/name)
 for evidence_name in ('bitmap_native_evidence',):
  name=report.get('inputs',{}).get(evidence_name)
  if name and (root/name).is_dir():
   child_reports.extend((root/name).rglob('case-metadata.json'))
 for child in child_reports:
  inputs.extend(nested_artifact_pins(json.loads(child.read_text())))
 cache={}
 pins=[]
 stale=[]
 executables=[]
 seen=set()
 for item in inputs:
  relative=item.get('path')
  expected=item.get('sha256')
  if not relative: raise ValueError('qualification input pin lacks a file path')
  path=root/relative
  if (relative,expected) in seen: continue
  seen.add((relative,expected))
  if relative not in cache:
   cache[relative]=sha(path) if path.is_file() else None
  exists=cache[relative] is not None
  pins.append({'path':relative,'sha256':expected,'exists':exists})
  if not exists or not expected or cache[relative]!=expected: stale.append(relative)
  if exists:
   with path.open('rb') as stream:
    if stream.read(4)==b'\x7fELF': executables.append(dict(pins[-1]))
 if not producer or not report.get('verification_inputs'):
  stale.append('qualification producer or verification input pins are missing')
 result=[]
 by_id={row['id']:row for row in requirements}
 for i,(behavior,owner,_,requirement,old_limit) in enumerate(CASES,1):
  check=by_id[f'C1.{i}']
  passed=check.get('status')=='pass' and check.get('evidence_grade')=='verified'
  status='stale' if stale else ('passed' if passed else 'partial')
  findings='; '.join(item.get('message','') for item in check.get('findings',[]))
  limitation='; '.join(check.get('limitations',[])) if passed else (findings or old_limit)
  result.append({'step':8,'subcheck':f'c1-{i}','behavior_or_member':behavior,
   'owner':owner,'evidence':str(report_path),'evidence_files':pins,
   'evidence_level':'host execution',
   'execution_results':[{'mode':'host execution','result':status,
     'scope':report.get('scope'),'evidence_files':[pins[0]]}],
   'fixture_input_hashes':{'status':'partial' if stale else 'complete',
     'executable_hashes':executables,'fixture_hashes':[pins[0]],
     'harness_hashes':[producer] if producer else [],'input_hashes':pins[1:]},
   'measurements':check.get('measurements',{}),'result':status,
   'acceptance_requirement':requirement,'remaining_limitation':limitation,
   'source_report_hashes':{pin['path']:pin['sha256'] for pin in pins},
   **({'stale_dependencies':stale} if stale else {})})
  if i==4 and (root/ROLE_AUDIT).is_file():
   audit=json.loads((root/ROLE_AUDIT).read_text())
   role_pin={'path':str(ROLE_AUDIT),'sha256':sha(root/ROLE_AUDIT),'exists':True}
   entry=result[-1]
   role_pins=[role_pin]
   for name,expected in audit.get('source_pins',{}).items():
    dependency=root/name
    if name not in cache: cache[name]=sha(dependency) if dependency.is_file() else None
    role_pins.append({'path':name,'sha256':expected,'exists':cache[name] is not None})
    if cache[name]!=expected:
     entry['result']='stale'
     entry.setdefault('stale_dependencies',[]).append(name)
     entry['fixture_input_hashes']['status']='partial'
   entry['evidence_files']=[*entry['evidence_files'],*role_pins]
   entry['fixture_input_hashes']['input_hashes'].extend(role_pins)
   entry['source_report_hashes'].update({pin['path']:pin['sha256'] for pin in role_pins})
   entry['measurements']={**entry['measurements'],
     'bitmap_payload_role_inventory':audit.get('totals',{}),
     'bitmap_consumer_scope':audit.get('c1_4_scope',{})}
   undecided=((audit.get('totals') or {}).get('disposition_occurrence_counts') or {}).get('undecided')
   decided=audit.get('result')=='all_occurrences_decided' and undecided==0
   if check.get('deferred_to'):
    entry['deferred_to']=check['deferred_to']
   if audit.get('result') not in ('pass','passed','complete') and not decided and entry['result']!='stale':
    entry['result']='partial'
    entry['remaining_limitation']=('Production frame registration and complete consumer-class coverage remain open; '
      'the linked role inventory separately records unclassified owners and shader/helper payloads without enabled consumers.')
   entry['execution_results'].append({'mode':'host execution','result':entry['result'],
     'scope':'Bitmap consumer-role inventory across the complete 27-profile corpus',
     'evidence_files':role_pins})
 return result

def rows(root=ROOT, qualification_report=QUALIFICATION):
 if qualification_report is not None and (root/qualification_report).is_file():
  return qualification_rows(root,qualification_report)
 result=[]
 file_info={}
 for name,relative in REPORTS.items():
  path=root/relative
  file_info[name]={'path':relative,'exists':path.is_file(),
                   'sha256':sha(path) if path.is_file() else None}
 documents={}
 def document(name):
  if name not in documents:
   documents[name]=json.loads((root/REPORTS[name]).read_text())
  return documents[name]
 for i,(behavior,owner,names,requirement,limit) in enumerate(CASES,1):
  evidence=[]
  for name in names:
   evidence.append(file_info[name])
  metrics={}
  if i==2 and (root/REPORTS['roster']).is_file():
   roster=document('roster')
   metrics={'source_variant_occurrences':len(roster['variants']),
            'logical_recipes':len(roster['unique_recipes'])}
  if i in (1,3,4) and (root/REPORTS['ui_failure']).is_file():
   diagnostic=document('ui_failure')
   metrics['ui_diagnostic']={k:diagnostic.get(k) for k in ('tag_count','memory','failure_stage','error')}
  executions=[]
  if 'survival_failure' in names and (root/REPORTS['survival_failure']).is_file():
   survival=document('survival_failure')
   metrics['survival_diagnostic']={k:survival.get(k) for k in
    ('tag_count','memory','failure_stage','error','reproducibility')}
   metrics['survival_diagnostic']['actor_bindings']=len(survival.get('actor_bindings',[]))
   executions.append({'mode':'host execution','result':'partial',
    'scope':'Independent imports and unadmitted CTAG only; no HCP admission or runtime placement',
    'evidence_files':[e for e in evidence if e['path']==REPORTS['survival_failure']]})
  result.append({'step':8,'subcheck':f'c1-{i}','behavior_or_member':behavior,
   'owner':owner,'evidence':'; '.join(e['path'] for e in evidence),
   'evidence_files':evidence,'evidence_level':'source inspection',
   'execution_results':executions,
   'fixture_input_hashes':{'status':'partial','executable_hashes':[],
     'fixture_hashes':[], 'harness_hashes':[],
     'input_hashes':[dict(e,role='report') for e in evidence]},
   'measurements':metrics,'result':'partial',
   'acceptance_requirement':requirement,'remaining_limitation':limit,
   'source_report_hashes':{e['path']:e['sha256'] for e in evidence}})
 return result

def invalidate(ledger, root=ROOT):
 """Preserve original pins; changed report bytes cannot pass their rows."""
 for row in ledger['evidence']:
  if not row.get('subcheck','').startswith('c1-'): continue
  stale=[]
  for rel,digest in row.get('source_report_hashes',{}).items():
   path=root/rel
   if not path.is_file() or not digest or sha(path)!=digest: stale.append(rel)
  if stale:
   row['result']='stale'; row['stale_dependencies']=stale
 return ledger

def update(path=LEDGER, *, qualification_report=QUALIFICATION):
 d=json.loads(path.read_text())
 d['evidence']=[x for x in d['evidence'] if not x.get('subcheck','').startswith('c1-')]+rows(qualification_report=qualification_report)
 d.setdefault('additional_pins',{})['c1_evidence_updater']={
  'path':'tools/update_hcu_c1_evidence.py','sha256':sha(Path(__file__).resolve())}
 # Recompute counters from actual rows; never decrement unrun work on append.
 for step in (7,8):
  records=[x for x in d['evidence'] if x['step']==step]
  st=d['step_status'][f'step{step}']
  st['partial_rows']=sum(x['result'] in ('partial','stale') for x in records)
  st['qualified_rows']=sum(x['result'] in ('passed','pass','qualified') for x in records)
  st['unrun_rows']=sum(x['result'] in ('not_run','blocked','missing') for x in records)
  st['status']='open'
 path.write_text(json.dumps(d,indent=2)+'\n')
 return d

if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('--ledger',type=Path,default=LEDGER)
 a=p.parse_args(); update(a.ledger)
