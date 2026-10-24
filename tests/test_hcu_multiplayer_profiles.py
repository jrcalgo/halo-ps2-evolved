import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import hcu_multiplayer_profiles as profiles
import hcu_profile_package as package_builder


def test_specs_cover_all_27_and_keep_each_actor_occurrence(tmp_path,monkeypatch):
    roster={'source_roots':[],'variants':[]}
    maps=profiles.MP_MAPS+('ui','a10')
    for name in sorted(set(maps)):
        p=tmp_path/f'{name}.map'; p.write_bytes(name.encode())
        roster['source_roots'].append({'map':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    roster['variants']=[
        {'map':'a10','group':'actv','path':'actors\\one','disposition':'combat','recipe':{'actor':{}},'mounted_recipes':[]},
        {'map':'a10','group':'actv','path':'actors\\mounted','disposition':'mounted_occupant','recipe':None,
         'mounted_recipes':[{'parent_vehicle':{'group':'vehi','path':'vehicle','datum':2},'seat_index':3}]},
    ]
    source_hash=hashlib.sha256((tmp_path/'a10.map').read_bytes()).hexdigest()
    weapon={'weapon_roots':{key:{'source_map':'a10.map','source_map_sha256':source_hash,
        'root_tag':{'group':'weap','path':f'weapons\\{key}'}} for key in ('fuel_rod','gravity_rifle','energy_sword')}}
    fake_entries=[SimpleNamespace(group='scnr',path='levels\\test\\map'),
                  SimpleNamespace(group='matg',path='globals\\globals'),
                  SimpleNamespace(group='hudg',path='ui\\hud'),
                  SimpleNamespace(group='bipd',path='characters\\cyborg_mp\\cyborg_mp'),
                  SimpleNamespace(group='weap',path='weapons\\assault rifle\\assault rifle'),
                  SimpleNamespace(group='weap',path='weapons\\pistol\\pistol'),
                  SimpleNamespace(group='weap',path='weapons\\plasma pistol\\plasma pistol')]
    monkeypatch.setattr(profiles.texconv.MapData,'open',lambda _p:SimpleNamespace(index=SimpleNamespace(entries=fake_entries)))
    specs=profiles.build_specs(roster,weapon,tmp_path)
    assert len(specs['profiles'])==27
    bots=next(x for x in specs['profiles'] if x['name']=='bots-beavercreek')
    survival=next(x for x in specs['profiles'] if x['name']=='survival-beavercreek')
    assert not bots['actor_roots']
    assert sum(x['role']=='spartan_asset' for x in bots['roots'])==4
    assert any(x['role']=='matg_global' for x in specs['profiles'][0]['roots'])
    assert any(x['role']=='hudg_global' for x in specs['profiles'][0]['roots'])
    assert sum(x['role'].startswith('special_weapon:') for x in bots['roots'])==3
    assert sum(x['role']=='combat_variant' for x in survival['roots'])==1
    assert sum(x['role']=='mounted_variant' for x in survival['roots'])==1


def test_special_roots_require_source_hashes(tmp_path,monkeypatch):
    for name in (*profiles.MP_MAPS,'ui','a10'):
        (tmp_path/f'{name}.map').write_bytes(name.encode())
    roster={'source_roots':[], 'variants':[{'map':'a10','path':'actors\\test',
        'disposition':'combat','recipe':{'actor':{}},'mounted_recipes':[]}]}
    for name in (*profiles.MP_MAPS,'ui','a10'):
        path=tmp_path/f'{name}.map'
        roster['source_roots'].append({'map':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    weapon={'weapon_roots':{key:{'source_map':'a10.map','root_tag':{'group':'weap','path':key}}
        for key in ('fuel_rod','gravity_rifle','energy_sword')}}
    fake_entries=[SimpleNamespace(group='scnr',path='levels\\test\\map'),
        SimpleNamespace(group='matg',path='globals\\globals'), SimpleNamespace(group='hudg',path='ui\\hud'),
        SimpleNamespace(group='bipd',path='characters\\cyborg_mp\\cyborg_mp'),
        SimpleNamespace(group='weap',path='weapons\\assault rifle\\assault rifle'),
        SimpleNamespace(group='weap',path='weapons\\pistol\\pistol'),
        SimpleNamespace(group='weap',path='weapons\\plasma pistol\\plasma pistol')]
    monkeypatch.setattr(profiles.texconv.MapData,'open',lambda _p:SimpleNamespace(index=SimpleNamespace(entries=fake_entries)))
    try:
        profiles.build_specs(roster,weapon,tmp_path)
    except ValueError as exc:
        assert 'mandatory source_map_sha256' in str(exc)
    else:
        raise AssertionError('special roots without source hashes must be rejected')


def test_actor_bindings_resolve_all_source_occurrences():
    spec={'actor_roots':[{'source':'a10','group':'actv','path':'actors\\one','role':'combat_variant',
        'placement_recipe':{'vehicle':{'group':'vehi','path':'vehicles\\warthog'}}}]}
    result={'source_occurrence_remaps':[
        {'source_key':'a10','group':'actv','path':'actors\\one','output_datum':7,'stable_key':'actv:key'},
        {'source_key':'a10','group':'vehi','path':'vehicles\\warthog','output_datum':8,'stable_key':'vehi:key'}]}
    rows=profiles.actor_bindings(spec,result)
    assert rows==[{'source_key':'a10','path':'actors\\one','role':'combat_variant','output_datum':7,
        'stable_key':'actv:key','recipe':{'vehicle':{'group':'vehi','path':'vehicles\\warthog',
        'output_datum':8,'stable_key':'vehi:key'}}}]


def test_complete_media_records_every_bitmap_image_without_runtime_admission(monkeypatch):
    from hcu_profile_media import media_json_summary
    monkeypatch.setattr(package_builder,'build_media',lambda sources,tags,**kwargs:{'chunks':[],'bindings':[],
        'memory':{},'decisions':[]})
    monkeypatch.setattr(package_builder,'serialize_bitmap',lambda sources,owner,schema,**kwargs:{
        'source_sha256':'a'*64,'chunks':[
            {'key':'BITM:'+'b'*64,'kind':'BITM','bytes':4,'data':b'one!','sha256':'b'*64,
             'identity':{'source_image_index':0}},
            {'key':'BITM:'+'c'*64,'kind':'BITM','bytes':4,'data':b'two!','sha256':'c'*64,
            'identity':{'source_image_index':1}}], 'sequences':[], 'dispositions':[],
        'decision':'staged only'})
    entry=SimpleNamespace(group='bitm',path='textures\\two',data_address=0)
    source=SimpleNamespace(path=Path('/tmp/map.map'),by_id={4:entry},region=b'',base=0)
    monkeypatch.setattr(package_builder.bitmaps,'parse_images',lambda *_args:[])
    media=package_builder.build_complete_media({'m':source},[
        {'source_key':'m','source_datum':4,'source_sha256':'a'*64,'output_datum':5,
         'group':'bitm','path':'textures\\two'}],{})
    assert [b['source_image_index'] for b in media['bindings']]==[0,1]
    assert all(b['runtime_admitted'] is False for b in media['bindings'])
    assert all(c['runtime_consumer'] is None for c in media['chunks'])
    assert all('data' not in c for c in media_json_summary(media)['chunks'])


def test_non2d_disposition_requires_exact_imported_owner_field(monkeypatch):
    from halo2ps2 import bitmaps
    image=SimpleNamespace(is_2d=False,type=bitmaps.TYPE_CUBE,index=0)
    entry=SimpleNamespace(group='bitm',path=r'characters\cyborg\bitmaps\cyborg reflection armor',data_address=0)
    source=SimpleNamespace(by_id={12:entry},region=b'',base=0,path=Path(__file__),
                           pixels=lambda _image:b'cube-pixels')
    monkeypatch.setattr(package_builder.bitmaps,'parse_images',lambda *_args:[image])
    tag={'group':'bitm','source_key':'a10','source_datum':12,'output_datum':23,'path':entry.path}
    consumer={'owner_output_datum':4,'owner_group':'soso','owner_path':'characters\\cyborg\\fp\\shaders\\armor hands',
        'source_key':'a10','definition':'shader_environment','field':'reflection_cube_map',
        'bitmap_output_datum':23,'bitmap_path':entry.path}
    decisions=package_builder.classify_profile_non2d({'a10':source},[tag],[consumer])
    row=decisions[23][0]
    assert row['feature_gate']==['ps2_model_reflection_cube_consumer_absent']
    assert row['schema_consumers'][0]['field']=='reflection_cube_map'
    assert row['source_pixel_sha256']==hashlib.sha256(b'cube-pixels').hexdigest()
    with pytest.raises(ValueError,match='unclassified required non-2D'):
        package_builder.classify_profile_non2d({'a10':source},[tag],[{**consumer,'field':'unknown_field'}])


def test_generic_model_reflection_rule_is_limited_to_named_schema_field():
    owners=[{'group':'senv','field':'reflection_cube_map'}]
    decision=package_builder.classify_bitmap_role(r'levels\\custom\\bitmap','cube',owners)
    assert decision['feature_gate']==['ps2_environment_reflection_consumer_absent']
    blocked=package_builder.classify_bitmap_role(r'levels\\custom\\bitmap','cube',
        [{'group':'soso','field':'base_map'}])
    assert blocked['classification']=='unknown_fail_closed'


def test_path_specific_matg_rule_requires_expected_nested_field():
    decision=package_builder.classify_bitmap_role(r'rasterizer\default cube map','cube',
        [{'group':'matg','field':'rasterizer_data.default_textures.bitmap'}])
    assert decision['classification']=='role_gated_no_current_ps2_payload_consumer'
    blocked=package_builder.classify_bitmap_role(r'rasterizer\default cube map','cube',
        [{'group':'matg','field':'render_globals.bitmap'}])
    assert blocked['classification']=='unknown_fail_closed'


def test_disabled_features_flattens_per_image_gate_lists():
    assert package_builder._all_feature_gates([
        {'feature_gate':['ps2_model_reflection_cube_consumer_absent']},
        {'feature_gate':['ps2_projected_gel_consumer_absent','ps2_model_reflection_cube_consumer_absent']}]) == [
            'ps2_model_reflection_cube_consumer_absent','ps2_projected_gel_consumer_absent']


def test_package_limit_failure_retains_ctag_and_media_chunk_count(tmp_path,monkeypatch):
    source_map=tmp_path/'m.map'; source_map.write_bytes(b'map')
    source=SimpleNamespace(map=SimpleNamespace(path=source_map))
    monkeypatch.setattr(profiles,'_source_set',lambda *_args,**_kwargs:{'m':source})
    monkeypatch.setattr(profiles,'import_profile',lambda *_args,**_kwargs:{
        'ctag':b'ctag','image':b'image','tags':[],'resources':[],'memory_needs':{},
        'decisions':[],'source_occurrence_remaps':[],'bitmap_consumers':[]})
    monkeypatch.setattr(profiles,'_profile_memory',lambda _result:{'resident_recipe_bytes':5})
    monkeypatch.setattr(profiles,'prepare_profile_bsp_roots',lambda *_args,**_kwargs:[])
    monkeypatch.setattr(profiles,'build_complete_media',lambda *_args,**_kwargs:{
        'chunks':[{'key':'BITM:'+'a'*64,'kind':'BITM','bytes':4,'data':b'data','sha256':'a'*64}],
        'bindings':[],'sound_metadata':{}})
    monkeypatch.setattr(profiles,'encode_hcp',lambda *_args,**_kwargs:(_ for _ in ()).throw(ValueError('HCP media chunk limit')))
    spec={'id':2,'name':'survival-test','scenario':{'source':'m','path':'levels\\test\\map'},'roots':[],'actor_roots':[]}
    package,diagnostic,artifacts=profiles.build_one(spec,tmp_path,{'elf_sha256':'schema'},
        {'builder':'pin'},report_failures=True)
    assert package is None and diagnostic['failure_stage']=='package'
    assert diagnostic['media_chunk_count']==1
    assert artifacts=={'unadmitted.ctag':b'ctag'}


def test_bitmap_conversion_cache_reuses_only_identical_source_and_policy(monkeypatch):
    monkeypatch.setattr(package_builder,'build_media',lambda sources,tags,**kwargs:{'chunks':[],
        'bindings':[],'memory':{},'decisions':[]})
    calls=[]
    asset={'source_sha256':'a'*64,'chunks':[],'sequences':[],'dispositions':[],
           'decision':'staged only'}
    def serialize(*args,**kwargs):
        calls.append(kwargs['source_sha256'])
        return asset
    monkeypatch.setattr(package_builder,'serialize_bitmap',serialize)
    entry=SimpleNamespace(group='bitm',path='textures\\two',data_address=0)
    source=SimpleNamespace(path=Path('/tmp/map.map'),by_id={4:entry},region=b'',base=0)
    monkeypatch.setattr(package_builder.bitmaps,'parse_images',lambda *_args:[])
    tags=[{'source_key':'m','source_datum':4,'source_sha256':'a'*64,'output_datum':5,
           'group':'bitm','path':'textures\\two'}]
    cache={}
    for _ in range(2):
        package_builder.build_complete_media({'m':source},tags,{},bitmap_cache=cache,
                                             input_hashes={'m':'a'*64})
    package_builder.build_complete_media({'m':source},[{**tags[0],'source_sha256':'d'*64}],{},
                                         bitmap_cache=cache,input_hashes={'m':'d'*64})
    assert calls==['a'*64,'d'*64]
    assert len(cache)==2


def test_prepare_profile_bsp_roots_adds_owner_and_typed_dependency_closure(tmp_path,monkeypatch):
    path=tmp_path/'beavercreek.map'; path.write_bytes(b'map')
    fake_map=SimpleNamespace(path=path)
    cache=profiles.BuildCache()
    monkeypatch.setattr(cache,'map',lambda _path:fake_map)
    monkeypatch.setattr(cache,'sha',lambda _path:'a'*64)
    monkeypatch.setattr(profiles,'bsp_profile_inputs',lambda *_args,**kwargs:[{
        'source_key':kwargs['source_key'],'group':'sbsp','path':'levels\\test\\structure',
        'source_datum':17,'source_file_offset':100,'source_file_size':20,'payload':b'cbsp',
        'tag_dependencies':[
            {'source_key':'beavercreek','group':'bitm','path':'levels\\test\\lightmap'},
            {'source_key':'beavercreek','group':'mode','path':'levels\\test\\model'}]}])
    spec={'name':'bots-beavercreek','scenario':{'source':'beavercreek'},'roots':[
        {'source':'beavercreek','group':'scnr','path':'levels\\test\\scenario','role':'scenario'}]}
    rows=profiles.prepare_profile_bsp_roots(spec,tmp_path,{'elf_sha256':'schema'},cache)
    assert len(rows)==1
    assert {(r['group'],r['path'],r['role']) for r in spec['roots']} >= {
        ('sbsp','levels\\test\\structure','structure_bsp'),
        ('bitm','levels\\test\\lightmap','bsp_dependency'),
        ('mode','levels\\test\\model','bsp_dependency')}
    assert spec['bsp_roots'][0]['payload_bytes']==4
    profiles.prepare_profile_bsp_roots(spec,tmp_path,{'elf_sha256':'schema'},cache)
    assert len([r for r in spec['roots'] if r['role']=='bsp_dependency'])==2


def test_append_cbsp_chunks_records_binding_and_nonadmission():
    payload=b'cbsp payload'
    digest=hashlib.sha256(payload).hexdigest()
    media={'chunks':[],'bindings':[],'memory':{},'decisions':[]}
    asset={'source_key':'beavercreek','group':'sbsp','path':'levels\\test\\structure',
        'source_datum':17,'output_datum':2,'payload':payload,'output_cbsp_sha256':digest,
        'source_cbsp_sha256':'a'*64,'source_file_offset':100,'source_file_size':20,
        'source_xbox_base':0x1000,'source_map_sha256':'b'*64,'schema_elf_sha256':'c'*64,
        'tag_dependencies':[{'group':'bitm','path':'levels\\test\\lightmap','source_datum':3}],
        'tag_remaps':[{'field':12,'kind':'reference','group':'bitm','path':'levels\\test\\lightmap',
                       'source_datum':3,'output_datum':8}]}
    package_builder.append_cbsp_chunks(media,[asset])
    assert media['chunks'][0]['key']==f'CBSP:{digest}'
    assert media['bindings'][0]['kind']=='CBSP'
    assert media['bindings'][0]['owner']['output_datum']==2
    assert media['bindings'][0]['runtime_admitted'] is False
    assert media['bsp_catalog'][0]['tag_remaps']==asset['tag_remaps']
    assert media['memory']['independently_addressable_converted_bytes']==len(payload)


def test_append_presentation_chunks_joins_exact_weapon_roots_and_preserves_provenance():
    presentation=profiles.build_presentation()
    media={'chunks':[],'bindings':[],'memory':{'independently_addressable_converted_bytes':0,
        'maximum_selected_transient_asset_requirement_bytes':0},'decisions':[]}
    roots=[{'source':'c40','group':'weap','path':row['tag_path'],
        'role':f"special_weapon:{'energy_sword' if row['asset_id']=='sword' else 'gravity_rifle'}"}
        for row in presentation['bindings']]
    remaps=[]
    for index,root in enumerate(roots,10):
        remaps.append({'source_key':root['source'],'group':root['group'],'path':root['path'],
            'source_datum':index,'output_datum':index+100})
    evidence=package_builder.append_presentation_chunks(media,presentation,{'roots':roots},remaps)
    assert set(evidence['assets'])=={'sword','gravity_rifle'}
    assert set(evidence['adapter_files']) >= {'src/game/sword_idle.h','src/game/carbine_idle.h'}
    assert evidence['source_animation_map'] == presentation['presentation_provenance']['source_animation_map']
    assert evidence['source_animation_map']['sha256']
    assert len(media['chunks'])==2 and all(row['kind']=='POSE' for row in media['chunks'])
    assert all(row['runtime_admitted'] is False for row in media['bindings'])
    assert {row['owner']['output_datum'] for row in media['bindings']}=={110,111}
    assert {row['asset_id'] for row in media['pose_catalog']}=={'sword','gravity_rifle'}


