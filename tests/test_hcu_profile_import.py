import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from hcu_profile_import import import_profile, ImportError, SchemaWalkError


def fixture(name='map'):
    image=bytearray(64)
    struct.pack_into('<I',image,4,0x1010)
    image[0:4]=b'paew'; struct.pack_into('<I',image,12,22)
    image[16:20]=b'dep\0'; struct.pack_into('<I',image,40,77)
    struct.pack_into('<I',image,44,99)
    main=SimpleNamespace(tag_id=11,path='actors\\root',group='actv',data_address=0x1000)
    dep=SimpleNamespace(tag_id=22,path='weapons\\one',group='weap',data_address=0x1028)
    scn=SimpleNamespace(tag_id=33,path='levels\\bloodgulch\\bloodgulch',group='scnr',data_address=0x102c)
    entries=[main,dep,scn]
    md=SimpleNamespace(region=bytes(image),base=0x1000,index=SimpleNamespace(entries=entries),by_id={11:main,22:dep,33:scn})
    schema={'format':'hcu-schema-manifest-v1','elf_sha256':'schema','groups':[
        {'group':'actv','definition':1},{'group':'weap','definition':2},{'group':'scnr','definition':2}],
        'definitions':{'1':{'name':'variant','size':16,'fields':[{'kind':'reference','name':'weapon','size':16,'count':1,'offset':0}]},
                       '2':{'name':'weapon','size':4,'fields':[{'kind':'enum','name':'x','size':4,'count':1,'offset':0}]}}}
    return md,schema


def test_cross_tag_reference_remapped_and_order_stable():
    md,schema=fixture()
    md2,_=fixture(); md2.index.entries[0].tag_id=31; md2.index.entries[1].tag_id=42
    raw=bytearray(md2.region); struct.pack_into('<I',raw,12,42); md2.region=bytes(raw); md2.by_id={}
    result=import_profile({'m':md,'z':md2},[('z','actv','actors\\root'),('m','actv','actors\\root')],schema,source_priority=['m','z'])
    assert [x['path'] for x in result['tags']]==['actors\\root','weapons\\one']
    assert result['tags'][0]['source']=='m' and result['tags'][0]['source_aliases']==['m','z']
    assert result['tag_relocations'] and result['tag_relocations'][0][1]==1
    assert struct.unpack_from('<I',result['image'],result['tag_relocations'][0][0])[0]==1
    assert result['memory_needs']['image_bytes']==len(result['image'])
    reversed_result=import_profile({'m':md,'z':md2},[('m','actv','actors\\root'),('z','actv','actors\\root')],schema,source_priority=['m','z'])
    assert result['image']==reversed_result['image']


def test_missing_dependency_fails_closed():
    md,schema=fixture(); md.index.entries=md.index.entries[:1]; md.by_id={11:md.by_id[11]}
    with pytest.raises(ImportError): import_profile({'m':md},[{'source':'m','group':'actv','path':'actors\\root'}],schema)


def test_conflicting_dependency_variants_are_preserved():
    md,schema=fixture(); md2,_=fixture()
    md2.index.entries[0].tag_id=31; md2.index.entries[1].tag_id=42
    md2.index.entries[1].path='weapons\\two'
    raw=bytearray(md2.region); struct.pack_into('<I',raw,12,42); raw[16:29]=b'weapons\\two\0'; md2.region=bytes(raw)
    result=import_profile({'a':md,'b':md2},[('a','actv','actors\\root'),('b','actv','actors\\root')],schema)
    roots=[x for x in result['tags'] if x['group']=='actv']
    assert len(roots)==2 and all(x['conflicts'] for x in roots)


def test_corrupt_block_bounds_rejected():
    md,schema=fixture()
    schema['definitions']['1']['fields']=[{'kind':'block','name':'bad','size':12,'count':1,'offset':0,'definition':2}]
    schema['definitions']['1']['size']=16
    raw=bytearray(md.region); struct.pack_into('<iI',raw,0,1,0xfffffff0); md.region=bytes(raw)
    with pytest.raises((ImportError,SchemaWalkError)): import_profile({'m':md},[{'source':'m','group':'actv','path':'actors\\root'}],schema)


def test_scenario_root_emits_valid_ctag():
    import ctag
    md,schema=fixture()
    result=import_profile({'bloodgulch':md},[('bloodgulch','actv','actors\\root')],schema,
        scenario_root=('bloodgulch','scnr','levels\\bloodgulch\\bloodgulch'))
    assert result['ctag']
    decoded=ctag.decode(result['ctag'],max_image_size=len(result['image']))
    assert decoded.image==result['image']


def test_rootless_sbsp_kept_as_table_record_without_tag_root():
    md,schema=fixture()
    bsp=SimpleNamespace(tag_id=44,path='levels\\bloodgulch\\bsp0',group='sbsp',data_address=0)
    md.index.entries.append(bsp)
    schema['groups'].append({'group':'sbsp','definition':None})
    result=import_profile({'m':md},[('m','sbsp',bsp.path)],schema)
    row=next(x for x in result['tags'] if x['group']=='sbsp')
    assert row['root_offset'] is None


def test_stable_identities_are_content_hashes_and_conflicts_differ():
    md,schema=fixture(); other,_=fixture()
    raw=bytearray(other.region); struct.pack_into('<I',raw,40,88); other.region=bytes(raw)
    result=import_profile({'a':md,'b':other},[('a','actv','actors\\root'),('b','actv','actors\\root')],schema)
    roots=[r for r in result['tags'] if r['group']=='actv']
    assert len(roots)==2 and len({r['stable_key'] for r in roots})==2
    assert all(len(r['content_sha256'])==64 and r['stable_key'].endswith(r['content_sha256']) for r in roots)


def test_nonnull_pointer_to_first_retained_byte_survives():
    md,schema=fixture()
    # The nested block aliases its own scalar header, a legal schema pointer.
    schema['definitions']['1']={'name':'owner','size':12,'fields':[
        {'kind':'block','name':'items','size':12,'count':1,'offset':0,'definition':2,'maximum':2}]}
    raw=bytearray(md.region); struct.pack_into('<iII',raw,0,1,0x1000,0); md.region=bytes(raw)
    result=import_profile({'m':md},[('m','actv','actors\\root')],schema)
    root=result['tags'][0]['root_offset']+36+32
    assert struct.unpack_from('<I',result['image'],root+4)[0]==root


def test_pointer_topology_is_part_of_content_identity():
    md,schema=fixture(); other,_=fixture()
    schema['definitions']['1']={'name':'owner','size':24,'fields':[
        {'kind':'block','name':'left','size':12,'count':1,'offset':0,'definition':2,'maximum':2},
        {'kind':'block','name':'right','size':12,'count':1,'offset':12,'definition':2,'maximum':2}]}
    raw=bytearray(md.region); struct.pack_into('<iIIiII',raw,0,1,0x1028,0,1,0x102c,0); md.region=bytes(raw)
    raw=bytearray(raw); struct.pack_into('<I',raw,4,0x102c); struct.pack_into('<I',raw,16,0x1028); other.region=bytes(raw)
    result=import_profile({'a':md,'b':other},[('a','actv','actors\\root'),('b','actv','actors\\root')],schema)
    assert len([r for r in result['tags'] if r['group']=='actv'])==2


def test_each_source_occurrence_has_its_own_remap_even_when_deduplicated():
    md,schema=fixture(); other,_=fixture()
    other.index.entries[0].tag_id=31; other.index.entries[1].tag_id=42
    raw=bytearray(other.region); struct.pack_into('<I',raw,12,42); other.region=bytes(raw)
    result=import_profile({'a':md,'b':other},[('a','actv','actors\\root'),('b','actv','actors\\root')],schema)
    roots=[r for r in result['source_occurrence_remaps'] if r['group']=='actv']
    assert len(roots)==2 and {r['source_datum'] for r in roots}=={11,31}
    assert len({r['output_datum'] for r in roots})==1


def test_conflicting_name_lookup_uses_declared_source_priority():
    md,schema=fixture(); other,_=fixture()
    raw=bytearray(other.region); struct.pack_into('<I',raw,40,88); other.region=bytes(raw)
    result=import_profile({'a':md,'b':other},[('a','actv','actors\\root'),('b','actv','actors\\root')],schema,source_priority=['b','a'])
    roots=[r for r in result['tags'] if r['group']=='actv']
    assert [r['source_key'] for r in roots]==['b','a']


def test_equal_file_payloads_deduplicate_across_source_offsets(tmp_path):
    md,schema=fixture(); other,_=fixture()
    schema['definitions']['1']={'name':'sound_permutation','size':20,'fields':[
        {'kind':'file_data','name':'samples','size':20,'count':1,'offset':0,'maximum':100}]}
    for name,item,offset in [('one',md,40),('two',other,44)]:
        raw=bytearray(64); struct.pack_into('<iIiII',raw,0,4,0,offset,0,0)
        raw[offset:offset+4]=b'same'
        item.region=bytes(raw); item.path=tmp_path/f'{name}.map'; item.path.write_bytes(raw)
    result=import_profile({'a':md,'b':other},[('a','actv','actors\\root'),('b','actv','actors\\root')],schema)
    assert len(result['tags'])==1
    assert result['tags'][0]['source_aliases']==['a','b']
    resource=result['resources'][0]
    assert resource['source']=='a' and resource['source_offset']==40
    assert resource['output_descriptor_offset']>=36+32
    assert len(resource['payload_sha256'])==64
    raw=bytearray(other.region); raw[44:48]=b'diff'; other.region=bytes(raw); other.path.write_bytes(raw)
    different=import_profile({'a':md,'b':other},[('a','actv','actors\\root'),('b','actv','actors\\root')],schema)
    assert len(different['tags'])==2


def test_truncated_file_backed_payload_is_rejected(tmp_path):
    md,schema=fixture()
    schema['definitions']['1']={'name':'sound_permutation','size':20,'fields':[
        {'kind':'file_data','name':'samples','size':20,'count':1,'offset':0,'maximum':100}]}
    raw=bytearray(64); struct.pack_into('<iIiII',raw,0,8,0,60,0,0)
    md.region=bytes(raw); md.path=tmp_path/'short.map'; md.path.write_bytes(raw)
    with pytest.raises(ImportError,match='leaves source map'):
        import_profile({'a':md},[('a','actv','actors\\root')],schema)


def test_typed_tag_index_relocation_uses_final_image_offset():
    md,schema=fixture()
    for entry in md.index.entries: entry.index=entry.tag_id & 0xffff
    schema['definitions']['1']={'name':'predicted','size':8,'fields':[
        {'kind':'tag_index','name':'resource','size':4,'count':1,'offset':0,'groups':['weap']},
        {'kind':'block_index','name':'local','size':4,'count':1,'offset':4}]}
    raw=bytearray(md.region); struct.pack_into('<II',raw,0,22,777); md.region=bytes(raw)
    result=import_profile({'m':md},[('m','actv','actors\\root')],schema)
    remap=result['tag_index_remaps'][0]
    assert remap['field']>=36+32*len(result['tags'])
    assert struct.unpack_from('<I',result['image'],remap['field'])[0]==remap['output_index']
    assert struct.unpack_from('<I',result['image'],remap['field']+4)[0]==777


def test_sound_self_identity_is_remapped_and_does_not_defeat_content_dedup(tmp_path):
    def source(name,datum,offset):
        raw=bytearray(300)
        struct.pack_into('<II',raw,52,datum,0)
        struct.pack_into('<I',raw,60,datum)
        struct.pack_into('<iIiII',raw,64,4,0,offset,0,0)
        raw[offset:offset+4]=b'same'
        path=tmp_path/f'{name}.map';path.write_bytes(raw)
        entry=SimpleNamespace(tag_id=datum,path='sound\\same',group='snd!',data_address=0x1000)
        return SimpleNamespace(region=bytes(raw),base=0x1000,path=path,index=SimpleNamespace(entries=[entry]))
    schema={'format':'hcu-schema-manifest-v1','elf_sha256':'synthetic','groups':[{'group':'snd!','definition':1}],
        'runtime_normalization_layout':{'schema_elf_sha256':'synthetic','sound_permutation':{
            'size':124,'cache_tag_index_offset':52,'runtime_tag_index_offset':60}},
        'definitions':{'1':{'name':'sound_permutation','size':124,'fields':[
            {'kind':'file_data','name':'samples','size':20,'count':1,'offset':64,'maximum':100}]}}}
    result=import_profile({'a':source('a',17,128),'b':source('b',23,192)},
        [('a','snd!','sound\\same'),('b','snd!','sound\\same')],schema)
    assert len(result['tags'])==1 and result['tags'][0]['source_aliases']==['a','b']
    assert len(result['runtime_normalizations'])==2
    for field in result['runtime_normalizations']:
        assert field['source_value']==17 and field['output_datum']==0
        assert struct.unpack_from('<I',result['image'],field['field'])[0]==0
    schema['runtime_normalization_layout']['schema_elf_sha256']='wrong'
    with pytest.raises(ImportError,match='linked schema ELF'):
        import_profile({},[],schema)
