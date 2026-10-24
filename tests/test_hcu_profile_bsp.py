import hashlib
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import cbsp
from hcu_profile_bsp import ProfileBspError, bsp_profile_inputs, rebind_profile_bsp


def fixtures():
    source_key = "bloodgulch"
    datum = 0x12340001
    source_entry = SimpleNamespace(group="weap", path="weapons\\one", tag_id=datum,
                                   path_address=0x1000 + 200, index=1)
    source_map = SimpleNamespace(
        by_id={datum: source_entry},
        index=SimpleNamespace(entries=[source_entry],
                              header=SimpleNamespace(model_vertex_address=0x1800,
                                                     model_index_address=0x1800),
                              index_region=(0, 0)),
        base=0x1000, region=bytes(0x900), sha256="maphash")

    schema = {"format": "hcu-schema-manifest-v1", "elf_sha256": "schemahash",
              "groups": [{"group": "sbsp", "definition": 1}],
              "definitions": {"1": {"name": "bsp-root", "size": 16,
                                     "fields": [{"kind": "reference", "name": "mat",
                                                 "size": 16, "count": 1, "offset": 0,
                                                 "groups": ["shdr"]}]}}}
    outdatum = 0
    ctag = bytearray(36 + 32 + len(b"weapons\\one\0"))
    struct.pack_into("<I", ctag, 0, 36)
    struct.pack_into("<I", ctag, 12, 1)
    struct.pack_into("<I", ctag, 32, 0x74616773)
    row = 36
    ctag[row:row + 4] = b"paew"
    struct.pack_into("<II", ctag, row + 12, outdatum, 68)
    ctag[68:] = b"weapons\\one\0"
    import_result = {"format": "hcu-profile-image-v1", "image": bytes(ctag),
                     "source_occurrence_remaps": [{"source_key": source_key, "group": "weap",
                         "path": source_entry.path, "source_datum": datum, "output_datum": outdatum,
                         "stable_key": "weap:weapons\\one"}]}

    image = bytearray(64)
    struct.pack_into("<I", image, 0, 28)
    image[20:24] = b"psbs"
    image[28:32] = b"paew"
    struct.pack_into("<I", image, 32, 200)
    struct.pack_into("<I", image, 40, datum)
    raw_cbsp = cbsp.encode(bytes(image), (0,), ((32, 200),),
                           source_file_offset=0x2000, source_file_size=len(image))
    return raw_cbsp, schema, import_result, source_map, source_key


def test_rebinds_reference_name_and_datum_preserving_other_bsp_bytes():
    raw, schema, imported, source, key = fixtures()
    result = rebind_profile_bsp(raw, manifest=schema, import_result=imported,
                                source_map=source, source_key=key)
    decoded = cbsp.decode(result["payload"], max_image_size=1024)
    assert decoded.image[20:24] == b"psbs"
    assert struct.unpack_from("<I", decoded.image, 32)[0] == 68
    assert struct.unpack_from("<I", decoded.image, 40)[0] == 0
    before = bytearray(cbsp.decode(raw, max_image_size=1024).image)
    after = bytearray(decoded.image)
    for offset in (32, 40):
        before[offset:offset + 4] = after[offset:offset + 4]
    assert before == after
    assert decoded.relocations == (0,)
    assert decoded.source_file_offset == 0x2000 and decoded.source_file_size == 64
    assert result["ctag_image_sha256"] == hashlib.sha256(imported["image"]).hexdigest()


def test_missing_bsp_dependency_fails_closed():
    raw, schema, imported, source, key = fixtures()
    imported["source_occurrence_remaps"] = []
    with pytest.raises(ProfileBspError, match="does not retain BSP dependency"):
        rebind_profile_bsp(raw, manifest=schema, import_result=imported,
                           source_map=source, source_key=key)


def test_wrong_reference_group_or_source_name_is_rejected():
    raw, schema, imported, source, key = fixtures()
    image = bytearray(cbsp.decode(raw, max_image_size=1024).image)
    image[28:32] = b"pcsb"
    corrupt = cbsp.encode(bytes(image), (0,), ((32, 200),),
                          source_file_offset=0x2000, source_file_size=64)
    with pytest.raises(ProfileBspError, match="disagrees with source tuple"):
        rebind_profile_bsp(corrupt, manifest=schema, import_result=imported,
                           source_map=source, source_key=key)


def test_out_of_bounds_nested_schema_reference_rejected():
    raw, schema, imported, source, key = fixtures()
    schema["definitions"]["1"]["fields"][0]["offset"] = 4
    with pytest.raises(ProfileBspError, match="field exceeds"):
        rebind_profile_bsp(raw, manifest=schema, import_result=imported,
                           source_map=source, source_key=key)


def test_retail_ui_and_multiplayer_bsp_dependency_inventory():
    root = Path(__file__).resolve().parents[1]
    elf = root / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"
    names = ("ui", "beavercreek", "bloodgulch", "boardingaction", "carousel",
             "chillout", "damnation", "hangemhigh", "longest", "prisoner",
             "putput", "ratrace", "sidewinder", "wizard")
    map_paths = [root / "build/retail-maps/decompressed" / f"{name}.map" for name in names]
    if not elf.is_file() or any(not path.is_file() for path in map_paths):
        pytest.skip("retail C1 schema ELF and UI/MP map corpus are not available")
    ps2_tools = root / "submodules/halo-ps2/tools"
    if str(ps2_tools) not in sys.path:
        sys.path.insert(0, str(ps2_tools))
    from halo2ps2 import texconv
    from hcu_schema_manifest import Elf32, SchemaManifest

    schema = SchemaManifest(Elf32(elf)).build()
    all_rows = []
    per_map = {}
    for name, path in zip(names, map_paths):
        descriptors = bsp_profile_inputs(texconv.MapData.open(path), schema)
        per_map[name] = descriptors
        all_rows.extend(descriptors)
    assert len(per_map) == 14
    assert len(all_rows) == 14
    assert all(row["group"] == "sbsp" and row["payload"].startswith(b"CBSP")
               for row in all_rows)
    assert len(per_map["ui"][0]["tag_dependencies"]) == 0
    assert sum(len(row["tag_dependencies"]) for row in all_rows) == 609
    assert all(len(row["cbsp_sha256"]) == 64 and len(row["source_map_sha256"]) == 64
               for row in all_rows)
