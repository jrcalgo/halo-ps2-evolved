import importlib.util, json, shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('c1e',ROOT/'tools/update_hcu_c1_evidence.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def test_updater_adds_six_partial_rows_and_preserves_other_rows(tmp_path):
 original=json.loads(mod.LEDGER.read_text()); other=[x for x in original['evidence'] if not x.get('subcheck','').startswith('c1-')]
 path=tmp_path/'ledger.json'; shutil.copyfile(mod.LEDGER,path)
 d=mod.update(path,qualification_report=None)
 c1=[x for x in d['evidence'] if x.get('subcheck','').startswith('c1-')]
 assert [x['subcheck'] for x in c1]==[f'c1-{i}' for i in range(1,7)]
 assert all(x['step']==8 and x['result']=='partial' for x in c1)
 assert [x for x in d['evidence'] if not x.get('subcheck','').startswith('c1-')]==other
 assert d['step_status']['step8']['status']=='open'

def test_source_report_hash_change_invalidates_only_dependent_rows(tmp_path):
 for rel in mod.REPORTS.values():
  destination=tmp_path/rel; destination.parent.mkdir(parents=True,exist_ok=True)
  if rel==mod.REPORTS['roster']:
   value={'variants':[],'unique_recipes':[]}
  else: value={}
  destination.write_text(json.dumps(value))
 ledger={'evidence':mod.rows(tmp_path)}
 (tmp_path/mod.REPORTS['preflight']).write_text('{"changed":true}')
 mod.invalidate(ledger,tmp_path)
 indexed={r['subcheck']:r for r in ledger['evidence']}
 assert indexed['c1-4']['result']=='stale'
 assert indexed['c1-2']['result']=='partial'
 assert indexed['c1-2'].get('stale_dependencies') is None


def test_updates_do_not_erase_unrun_acceptance(tmp_path):
 original=json.loads(mod.LEDGER.read_text())
 path=tmp_path/'ledger.json'; path.write_text(json.dumps(original))
 first=mod.update(path,qualification_report=None); second=mod.update(path,qualification_report=None)
 assert first==second
 assert second['step_status']['step8']['unrun_rows']==sum(
  r['result'] in ('not_run','blocked','missing') for r in second['evidence'] if r['step']==8)
 assert second['step_status']['step8']['unrun_rows']==4


def test_current_qualified_report_imports_only_its_six_rows(tmp_path):
 fixture=tmp_path/'fixture.json'; fixture.write_text('{"input":true}')
 producer=tmp_path/'gate.py'; producer.write_text('# exact gate')
 report={'format':'hcu-c1-qualification-v1','scope':'C1 host asset qualification',
  'producer':{'path':'gate.py','sha256':mod.sha(producer)},
  'verification_inputs':[{'path':'fixture.json','sha256':mod.sha(fixture)}],
  'requirements':[{'id':f'C1.{i}','status':'pass','evidence_grade':'verified',
   'measurements':{'profiles':27},'limitations':['C2 ownership remains separate']} for i in range(1,7)]}
 path=tmp_path/mod.QUALIFICATION; path.parent.mkdir(parents=True); path.write_text(json.dumps(report))
 rows=mod.rows(tmp_path)
 assert len(rows)==6 and all(row['result']=='passed' for row in rows)
 assert all(row['fixture_input_hashes']['status']=='complete' for row in rows)
 fixture.write_text('{"input":"changed"}')
 changed=mod.rows(tmp_path)
 assert [row['subcheck'] for row in changed if row['result']=='stale']==[f'c1-{i}' for i in range(1,7)]


def test_unverified_report_cannot_promote_requirement(tmp_path):
 path=tmp_path/mod.QUALIFICATION; path.parent.mkdir(parents=True)
 path.write_text(json.dumps({'format':'hcu-c1-qualification-v1',
  'requirements':[{'id':f'C1.{i}','status':'pass','evidence_grade':'verified'} for i in range(1,7)]}))
 assert all(row['result']=='stale' for row in mod.rows(tmp_path))

def test_malformed_unclassified_verification_input_is_rejected(tmp_path):
 gate=tmp_path/'gate.py'; gate.write_text('gate')
 path=tmp_path/mod.QUALIFICATION; path.parent.mkdir(parents=True)
 path.write_text(json.dumps({'format':'hcu-c1-qualification-v1',
  'producer':{'path':'gate.py','sha256':mod.sha(gate)},
  'verification_inputs':[{'role':'unclassified'}],
  'requirements':[{'id':f'C1.{i}','status':'pass','evidence_grade':'verified'} for i in range(1,7)]}))
 try:
  mod.rows(tmp_path)
 except ValueError as exc:
  assert 'lacks a file path' in str(exc)
 else:
  raise AssertionError('malformed global input pin must not be ignored')

def test_requirement_evidence_hash_invalidates_only_that_requirement(tmp_path):
 report_path=tmp_path/mod.QUALIFICATION; report_path.parent.mkdir(parents=True)
 a=tmp_path/'c14.json'; b=tmp_path/'c15.json'; a.write_text('a'); b.write_text('b')
 gate=tmp_path/'gate.py'; gate.write_text('gate'); schema=tmp_path/'schema.elf'; schema.write_bytes(b'ELF!')
 requirements=[]
 for i in range(1,7):
  requirements.append({'id':f'C1.{i}','status':'pass','evidence_grade':'verified',
   'evidence':[{'path':str(a if i==4 else b),'sha256':mod.sha(a if i==4 else b)}]})
 report_path.write_text(json.dumps({'format':'hcu-c1-qualification-v1','scope':'test',
  'producer':{'path':'gate.py','sha256':mod.sha(gate)},
  'inputs':{'schema_elf':'schema.elf'},
  'verification_inputs':[{'path':'schema.elf','sha256':mod.sha(schema)}],
  'requirements':requirements}))
 a.write_text('changed')
 rows=mod.rows(tmp_path); stale=[r['subcheck'] for r in rows if r['result']=='stale']
 assert stale==['c1-4']
 assert rows[3]['stale_dependencies']==[str(a)]
 assert all(r['result']=='passed' for r in rows if r['subcheck']!='c1-4')

def test_package_hash_invalidates_only_rows_that_pin_package(tmp_path):
 report_path=tmp_path/mod.QUALIFICATION; report_path.parent.mkdir(parents=True)
 gate=tmp_path/'gate.py'; gate.write_text('gate'); schema=tmp_path/'schema.elf'; schema.write_bytes(b'ELF!')
 pkg=tmp_path/'package.hcp'; pkg.write_text('package')
 requirements=[]
 for i in range(1,7):
  evidence=[]
  if i in (2,4,6): evidence=[{'package_path':str(pkg),'package_sha256':mod.sha(pkg)}]
  requirements.append({'id':f'C1.{i}','status':'pass','evidence_grade':'verified','evidence':evidence})
 report_path.write_text(json.dumps({'format':'hcu-c1-qualification-v1','scope':'test',
  'producer':{'path':'gate.py','sha256':mod.sha(gate)},'inputs':{'schema_elf':'schema.elf'},
  'verification_inputs':[{'path':'schema.elf','sha256':mod.sha(schema)}], 'requirements':requirements}))
 pkg.write_text('changed')
 rows=mod.rows(tmp_path)
 assert [r['subcheck'] for r in rows if r['result']=='stale']==['c1-2','c1-4','c1-6']

def test_requirement_producer_pins_invalidate_only_declaring_requirement(tmp_path):
 report_path=tmp_path/mod.QUALIFICATION; report_path.parent.mkdir(parents=True)
 gate=tmp_path/'gate.py'; gate.write_text('gate')
 schema=tmp_path/'schema.elf'; schema.write_bytes(b'ELF!')
 source=tmp_path/'tools'/'hcu_profile_chunks.py'; source.parent.mkdir(); source.write_text('source')
 requirements=[]
 for i in range(1,7):
  evidence=[]
  if i==1:
   evidence=[{'path':'manifest.json','sha256':'manifest-pin','details':{
    'producer_pins':{'tools/hcu_profile_chunks.py':mod.sha(source)}}}]
  requirements.append({'id':f'C1.{i}','status':'pass','evidence_grade':'verified','evidence':evidence})
 report_path.write_text(json.dumps({'format':'hcu-c1-qualification-v1','scope':'test',
  'producer':{'path':'gate.py','sha256':mod.sha(gate)},'inputs':{'schema_elf':'schema.elf'},
  'verification_inputs':[{'path':'schema.elf','sha256':mod.sha(schema)}],
  'requirements':requirements}))
 source.write_text('changed source')
 rows=mod.rows(tmp_path)
 assert [r['subcheck'] for r in rows if r['result']=='stale']==['c1-1']
 assert 'tools/hcu_profile_chunks.py' in rows[0]['stale_dependencies']


def test_role_dependency_invalidation_preserves_independent_requirements(tmp_path):
 producer=tmp_path/'gate.py'; producer.write_text('# gate')
 fixture=tmp_path/'fixture'; fixture.write_text('inputs')
 report={'format':'hcu-c1-qualification-v1',
  'producer':{'path':'gate.py','sha256':mod.sha(producer)},
 'verification_inputs':[{'path':'fixture','sha256':mod.sha(fixture)}],
 'inputs':{'consumer_roles':str(mod.ROLE_AUDIT)},
  'requirements':[{'id':f'C1.{i}','status':'pass','evidence_grade':'verified'} for i in range(1,7)]}
 path=tmp_path/mod.QUALIFICATION; path.parent.mkdir(parents=True); path.write_text(json.dumps(report))
 consumer=tmp_path/'consumer.c'; consumer.write_text('/* runtime consumer */')
 role_path=tmp_path/mod.ROLE_AUDIT
 role_path.write_text(json.dumps({'result':'inventory_complete_runtime_bitmap_consumers_unqualified',
  'source_pins':{'consumer.c':mod.sha(consumer)},'totals':{'unclassified':1}}))
 rows=mod.rows(tmp_path)
 assert rows[3]['result']=='partial'
 assert all(row['result']=='passed' for i,row in enumerate(rows) if i!=3)
 consumer.write_text('/* changed */')
 rows=mod.rows(tmp_path)
 assert rows[3]['result']=='stale'
 assert all(row['result']=='passed' for i,row in enumerate(rows) if i!=3)
