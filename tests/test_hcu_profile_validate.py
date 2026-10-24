import hashlib
import json
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import ctag
import hcu_profile_chunks
import hcu_profile_validate
from hcu_profile_validate import ProfileValidationError, validate
from hcu_profile_import import import_profile


def fixture():
    image = bytearray(16)
    entry = SimpleNamespace(tag_id=7, path="levels\\bloodgulch\\bloodgulch",
                            group="scnr", data_address=0x1000)
    mapdata = SimpleNamespace(region=bytes(image), base=0x1000,
                              index=SimpleNamespace(entries=[entry]), by_id={7: entry})
    schema = {"format": "hcu-schema-manifest-v1", "elf_sha256": "synthetic",
              "groups": [{"group": "scnr", "definition": 1}],
              "definitions": {"1": {"name": "scenario", "size": 4, "fields": [
                  {"kind": "enum", "name": "x", "size": 4, "count": 1, "offset": 0}]}}}
    result = import_profile({"bloodgulch": mapdata}, [], schema,
                            scenario_root=("bloodgulch", "scnr", entry.path))
    sound = json.dumps({"format": "hcu-profile-sound-metadata-v1", "sources": {}},
                       sort_keys=True, separators=(",", ":")).encode()
    package = hcu_profile_chunks.encode(91, {"ce": result["ctag"], "media": {}, "sound_meta": sound})
    return package, result, schema, sound


def check(package, result, schema, scenario="levels\\bloodgulch\\bloodgulch", **extra):
    return validate(package, result["manifest"] | {"format": result["format"], "tags": result["tags"],
                    "resources": result["resources"], "chunk_bindings": []}, schema,
                    expected_package_sha256=hashlib.sha256(package).hexdigest(),
                    expected_profile_id=91, expected_scenario=scenario, **extra)


def test_valid_package_checks_hcp_ctag_schema_and_scenario():
    package, result, schema, _ = fixture()
    verified = check(package, result, schema)
    assert verified["tag_count"] == 1 and verified["profile_id"] == 91


def test_coherently_rehashed_invalid_ctag_is_rejected():
    package, result, schema, sound = fixture()
    damaged = bytearray(result["ctag"])
    damaged[-1] ^= 0x10
    package = hcu_profile_chunks.encode(91, {"ce": bytes(damaged), "media": {}, "sound_meta": sound})
    with pytest.raises(ProfileValidationError):
        check(package, result, schema)


def test_wrong_expected_scenario_and_package_identity_rejected():
    package, result, schema, _ = fixture()
    with pytest.raises(ProfileValidationError, match="scenario"):
        check(package, result, schema, "levels\\other\\other")
    with pytest.raises(ProfileValidationError, match="SHA-256"):
        validate(package, result["manifest"], schema, expected_package_sha256="0" * 64,
                 expected_profile_id=91, expected_scenario="levels\\bloodgulch\\bloodgulch")


def test_missing_resource_mapping_rejected():
    package, result, schema, _ = fixture()
    manifest = result["manifest"] | {"format": result["format"], "tags": result["tags"],
        "resources": [{"tag": "levels\\bloodgulch\\bloodgulch", "field": "samples", "bytes": 12}],
        "chunk_bindings": []}
    with pytest.raises(ProfileValidationError, match="resources"):
        validate(package, manifest, schema, expected_package_sha256=hashlib.sha256(package).hexdigest(),
                 expected_profile_id=91, expected_scenario="levels\\bloodgulch\\bloodgulch")


def test_arbitrary_rehashed_media_is_rejected_even_with_binding():
    package, result, schema, sound = fixture()
    media = b"test media"
    package = hcu_profile_chunks.encode(91, {"ce": result["ctag"], "media": {4: media}, "sound_meta": sound})
    manifest = result["manifest"] | {"format": result["format"], "tags": result["tags"], "resources": [],
        "media": {"chunks": [{"kind": "OPAQUE", "key": "opaque", "bytes": len(media),
                               "sha256": hashlib.sha256(media).hexdigest()}], "bindings": []}}
    with pytest.raises(ProfileValidationError, match="qualified parser"):
        validate(package, manifest, schema, expected_package_sha256=hashlib.sha256(package).hexdigest(),
                 expected_profile_id=91, expected_scenario="levels\\bloodgulch\\bloodgulch")


def test_dependency_reference_field_must_be_bounded_and_match_image():
    package, result, schema, _ = fixture()
    manifest = result["manifest"] | {"format": result["format"], "tags": result["tags"],
        "resources": [], "tag_relocations": [[0xffffffff, 0]]}
    with pytest.raises(ProfileValidationError, match="dependency slot"):
        validate(package, manifest, schema, expected_package_sha256=hashlib.sha256(package).hexdigest(),
                 expected_profile_id=91, expected_scenario="levels\\bloodgulch\\bloodgulch")


def test_schema_found_resources_cannot_be_omitted_from_manifest(monkeypatch):
    package, result, schema, _ = fixture()
    class WalkerWithResource:
        def __init__(self, *args, **kwargs): self.image = args[1]
        def run(self):
            from types import SimpleNamespace
            return SimpleNamespace(image=self.image, file_data_records=(("scenario", "samples", 8, 0, 0),))
    monkeypatch.setattr(hcu_profile_validate, "Walker", WalkerWithResource)
    manifest = result["manifest"] | {"format": result["format"], "tags": result["tags"],
        "resources": [], "schema_elf_sha256": schema["elf_sha256"]}
    with pytest.raises(ProfileValidationError, match="schema walk found"):
        validate(package, manifest, schema, expected_package_sha256=hashlib.sha256(package).hexdigest(),
                 expected_profile_id=91, expected_scenario="levels\\bloodgulch\\bloodgulch")



def test_actual_converted_gravity_and_animation_chunks_pass_engine_readers():
    import ctypes
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'submodules/halo-ps2/tools'))
    from halo2ps2 import texconv, modelconv, animconv
    path=Path(__file__).resolve().parents[1]/'build/retail-maps/decompressed/beavercreek.map'
    if not path.is_file(): pytest.skip('retained retail source map unavailable')
    source=texconv.MapData.open(path)
    model=next(e for e in source.index.entries if e.group=='mode' and e.path=='weapons\\gravity rifle\\gravity rifle')
    animation=next(e for e in source.index.entries if e.group=='antr' and e.path=='weapons\\pistol\\fp\\fp')
    converted=modelconv.convert_map(source,[model.tag_id])
    payloads=[(1,converted.modl),(3,converted.otex),(2,animconv.build_section(path,[animation.tag_id]))]
    reader=hcu_profile_validate._media_reader()
    for kind,payload,tag in [(1,converted.modl,model.tag_id),(2,payloads[2][1],animation.tag_id)]:
        buffer=ctypes.create_string_buffer(payload)
        assert reader.contains(kind,buffer,len(payload),tag)==1
        assert reader.contains(kind,buffer,len(payload),0xffffffff)==0
    for kind,payload in payloads:
        buf=ctypes.create_string_buffer(payload)
        assert reader(kind,buf,len(payload))==1
        bad=ctypes.create_string_buffer(b'bad!'+payload[4:])
        assert reader(kind,bad,len(payload))==0


def test_schema_dependency_cannot_be_hidden_by_omitting_manifest_edge():
    source=bytearray(64)
    source[:4]=b'paew'; struct.pack_into('<I',source,12,8)
    scenario=SimpleNamespace(tag_id=7,path='levels\\bloodgulch\\bloodgulch',group='scnr',data_address=0x1000)
    weapon=SimpleNamespace(tag_id=8,path='weapons\\one',group='weap',data_address=0x1020)
    md=SimpleNamespace(region=bytes(source),base=0x1000,index=SimpleNamespace(entries=[scenario,weapon]))
    schema={'format':'hcu-schema-manifest-v1','elf_sha256':'synthetic','groups':[
        {'group':'scnr','definition':1},{'group':'weap','definition':2}],
        'definitions':{'1':{'name':'scenario','size':16,'fields':[
            {'kind':'reference','name':'weapon','size':16,'count':1,'offset':0}]},
            '2':{'name':'weapon','size':4,'fields':[{'kind':'enum','name':'x','size':4,'count':1,'offset':0}]}}}
    result=import_profile({'bloodgulch':md},[],schema,scenario_root=('bloodgulch','scnr',scenario.path))
    sound=json.dumps({'format':'hcu-profile-sound-metadata-v1','sources':{}}).encode()
    package=hcu_profile_chunks.encode(91,{'ce':result['ctag'],'media':{},'sound_meta':sound})
    manifest={**result['manifest'],'format':result['format'],'tags':result['tags'],
              'resources':[],'tag_relocations':result['tag_relocations']}
    validate(package,manifest,schema,expected_package_sha256=hashlib.sha256(package).hexdigest(),
             expected_profile_id=91,expected_scenario=scenario.path)
    manifest['tag_relocations']=[]
    with pytest.raises(ProfileValidationError,match='omits or alters schema reference'):
        validate(package,manifest,schema,expected_package_sha256=hashlib.sha256(package).hexdigest(),
                 expected_profile_id=91,expected_scenario=scenario.path)


def test_dangling_media_binding_is_rejected():
    package,result,schema,_=fixture()
    manifest={**result['manifest'],'format':result['format'],'tags':result['tags'],
              'media':{'chunks':[],'bindings':[{'chunk_key':'missing'}]}}
    with pytest.raises(ProfileValidationError,match='missing chunk'):
        validate(package,manifest,schema,expected_package_sha256=hashlib.sha256(package).hexdigest(),
                 expected_profile_id=91,expected_scenario='levels\\bloodgulch\\bloodgulch')


def test_sound_sample_descriptors_are_bound_metadata_with_playback_unqualified(tmp_path):
    raw=bytearray(100); struct.pack_into('<iIiII',raw,32,4,0,96,0,0); raw[96:100]=b'SAMP'
    source_path=tmp_path/'source.map'; source_path.write_bytes(raw)
    scenario=SimpleNamespace(tag_id=7,path='levels\\bloodgulch\\bloodgulch',group='scnr',data_address=0x1000)
    sound=SimpleNamespace(tag_id=8,path='sound\\fire',group='snd!',data_address=0x1020)
    md=SimpleNamespace(region=bytes(raw),path=source_path,base=0x1000,index=SimpleNamespace(entries=[scenario,sound]))
    schema={'format':'hcu-schema-manifest-v1','elf_sha256':'synthetic','groups':[
        {'group':'scnr','definition':1},{'group':'snd!','definition':2}],
        'definitions':{'1':{'name':'scenario','size':4,'fields':[{'kind':'enum','name':'x','size':4,'count':1,'offset':0}]},
            '2':{'name':'sound_permutation','size':20,'fields':[
                {'kind':'file_data','name':'samples','size':20,'count':1,'offset':0,'maximum':100}]}}}
    result=import_profile({'bloodgulch':md},[('bloodgulch','snd!',sound.path)],schema,scenario_root=('bloodgulch','scnr',scenario.path))
    assert b'SAMP' not in result['ctag']
    metadata=json.dumps({'format':'hcu-profile-sound-metadata-v1','sources':{
        'bloodgulch':[{'datum':8,'path':sound.path}]}}).encode()
    package=hcu_profile_chunks.encode(91,{'ce':result['ctag'],'media':{},'sound_meta':metadata})
    manifest={**result['manifest'],'format':result['format'],'tags':result['tags'],
        'resources':result['resources'],'source_maps':{'bloodgulch':{'sha256':hashlib.sha256(raw).hexdigest()}},
        'resource_policy':{'sound_samples':'metadata_only_spu2_unqualified'}}
    args=dict(expected_package_sha256=hashlib.sha256(package).hexdigest(),expected_profile_id=91,expected_scenario=scenario.path)
    validate(package,manifest,schema,**args)
    manifest.pop('resource_policy')
    with pytest.raises(ProfileValidationError,match='unmapped file-backed'):
        validate(package,manifest,schema,**args)
    manifest['resource_policy']={'sound_samples':'metadata_only_spu2_unqualified'}
    manifest['resources'][0]['source_offset']+=1
    with pytest.raises(ProfileValidationError,match='descriptor does not match'):
        validate(package,manifest,schema,**args)


def test_real_ui_package_requires_every_bitmap_image_identity():
    import copy
    from hcu_schema_manifest import Elf32,SchemaManifest
    root=Path(__file__).resolve().parents[1]
    path=root/'build/m2-c1-ui-bsp-final/ui.hcp'
    if not path.is_file(): pytest.skip('C1 UI profile fixture not built')
    manifest=json.loads(path.with_suffix('.json').read_text())
    schema=SchemaManifest(Elf32(root/'build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf')).build()
    payload=path.read_bytes(); digest=hashlib.sha256(payload).hexdigest()
    args=dict(expected_package_sha256=digest,expected_profile_id=1,expected_scenario=r'levels\ui\ui')
    result=validate(payload,manifest,schema,**args)
    assert result['bitmap_coverage']=={'images':384,'serialized_images':368,'excluded_nonconsumer_images':16}
    modified=copy.deepcopy(manifest)
    binding=next(b for b in modified['media']['bindings'] if b['kind']=='BITM')
    binding['owner']['source_image_index']=99999; binding['source_image_index']=99999
    with pytest.raises(ProfileValidationError,match='image index'):
        validate(payload,modified,schema,**args)
    modified=copy.deepcopy(manifest)
    disposition=next(a['dispositions'][0] for a in modified['media']['bitmap_catalog'] if a['dispositions'])
    disposition['schema_consumers'][0]['field']='made_up_consumer'
    with pytest.raises(ProfileValidationError,match='consumers do not match'):
        validate(payload,modified,schema,**args)
