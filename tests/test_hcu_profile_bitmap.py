import ctypes
import hashlib
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from hcu_profile_bitmap import (BitmapProfileError, SOURCE_RESOLUTION_HUD_BITMAPS,
                                NATIVE_RESOLUTION_HUD_BITMAPS,
                                _engine_tex_reader,
                                _convert_scope_mask, serialize_bitmap, serialize_bitmaps)


def fixture(tmp_path, second_type=0):
    path = tmp_path / "tiny.map"
    path.write_bytes(b"synthetic retail map bytes")
    base = 0x1000
    region = bytearray(0x300)
    # Compiler schema fixture: bitmap_group.sequences at 0 and .bitmaps at +0x60.
    struct.pack_into("<iII", region, 0, 1, base + 0xB0, 0)
    struct.pack_into("<iII", region, 0x60, 2, base + 0x180, 0)
    # One sequence with two sprite frames. Schema field offsets match the CE compiler definition.
    region[0xB0:0xB0 + 8] = b"frames\0\0"
    struct.pack_into("<hh", region, 0xB0 + 32, 0, 2)
    struct.pack_into("<iII", region, 0xB0 + 52, 2, base + 0xF0, 0)
    struct.pack_into("<h", region, 0xF0, 0)
    struct.pack_into("<h", region, 0x110, 1)
    pixels = {}
    for i, typ in enumerate((0, second_type)):
        offset = 0x2000 + i * 0x100
        at = 0x180 + i * 48
        struct.pack_into("<4sHHHHHHhhHHII", region, at, b"mtib", 8, 8, 1, typ, 6, 16,
                         0, 0, 0, 0, offset, 128)
        pixels[offset] = bytes([0x1F, 0xF8] * 64)  # 8x8 linear R5G6B5
    entry = SimpleNamespace(tag_id=5, path="ui\\test\\bitmap", group="bitm", data_address=base)
    class MapData:
        def __init__(self):
            self.path, self.base, self.region = path, base, bytes(region)
            self.by_id = {5: entry}
        def pixels(self, img): return pixels[img.pixel_offset]
    m = MapData()
    schema = {"format": "hcu-schema-manifest-v1", "elf_sha256": "tiny", "groups": [
        {"group": "bitm", "definition": 1}], "definitions": {
            "1": {"name": "bitmap_group", "size": 108, "fields": [
                {"kind": "block", "name": "sequences", "offset": 0, "size": 12,
                 "definition": 2, "maximum": 16},
                {"kind": "block", "name": "bitmaps", "offset": 96, "size": 12,
                 "definition": 4, "maximum": 16}]},
            "2": {"name": "bitmap_sequence", "size": 64, "fields": [
                {"kind": "string", "name": "name", "offset": 0, "size": 32},
                {"kind": "block", "name": "sprites", "offset": 52, "size": 12,
                 "definition": 3, "maximum": 16}]},
            "3": {"name": "bitmap_sprite", "size": 32, "fields": [
                {"kind": "tag_index", "name": "bitmap_index", "offset": 0, "size": 2}]},
            "4": {"name": "bitmap_data", "size": 48, "fields": []}}}
    owner = {"source_key": "source", "group": "bitm", "path": entry.path, "source_datum": 5}
    return {"source": m}, owner, schema


def test_all_images_are_independent_and_sequence_frames_preserved(tmp_path):
    sources, owner, schema = fixture(tmp_path)
    result = serialize_bitmap(sources, owner, schema)
    assert len(result["chunks"]) == 2
    assert [c["identity"]["source_image_index"] for c in result["chunks"]] == [0, 1]
    assert [f["bitmap_index"] for f in result["sequences"][0]["frames"]] == [0, 1]
    assert all(c["kind"] == "BITM" and len(c["sha256"]) == 64 for c in result["chunks"])
    assert result["runtime_consumer"] is None


def test_serialization_is_deterministic_and_source_hash_is_shared(tmp_path):
    sources, owner, schema = fixture(tmp_path)
    a = serialize_bitmaps(sources, [owner, owner], schema)
    assert a[0]["source_sha256"] == a[1]["source_sha256"]
    assert [x["sha256"] for x in a[0]["chunks"]] == [x["sha256"] for x in a[1]["chunks"]]
    assert hashlib.sha256(a[0]["chunks"][0]["data"]).hexdigest() == a[0]["chunks"][0]["sha256"]


def test_unsupported_3d_images_fail_closed(tmp_path):
    sources, owner, schema = fixture(tmp_path, second_type=1)
    with pytest.raises(BitmapProfileError, match="unsupported required bitmap image"):
        serialize_bitmap(sources, owner, schema)


def test_retail_sniper_masks_preserve_native_mip_zero():
    """The zoom mask must reach dispatch at its retail dimensions, not half size."""
    root = Path(__file__).resolve().parents[1]
    source_path = root / "build/retail-maps/decompressed/bloodgulch.map"
    if not source_path.is_file():
        pytest.skip("retail Blood Gulch source map unavailable")
    sys.path[:0] = [str(root / "submodules/halo-ps2/tools"),
                    str(root / "submodules/halo-ps2/tools/halo2ps2")]
    from halo2ps2 import bitmaps, texconv
    source = texconv.MapData.open(source_path)
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == (
        "9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1")
    expected = {
        3861513398: (r"ui\hud\bitmaps\sniper\sniper_scope_mask2", 512, 256, 65536),
        3861578935: (r"ui\hud\bitmaps\sniper\sniper_scope_mask_sm", 256, 256, 32768),
    }
    assert {row[0].casefold() for row in expected.values()} <= SOURCE_RESOLUTION_HUD_BITMAPS
    for datum, (path, width, height, pixel_bytes) in expected.items():
        entry = source.by_id[datum]
        image = bitmaps.parse_images(source.region, source.base, entry.data_address)[0]
        assert entry.path == path
        texture = _convert_scope_mask(source, image, datum)
        assert (texture.width, texture.height) == (width, height)
        expected_bytes = width * height
        assert texture.psm == texconv.PSMT8 and texture.clut_entries == 256
        assert len(texture.mips[0]) == expected_bytes and len(texture.clut) == 1024
        # Validate the serialized TEXS representation, including CSM1 CLUT
        # ordering. Compare post-conversion values to GS channel normalization.
        payload = texconv.build_texs([texture], [])
        c_payload = ctypes.create_string_buffer(payload)
        assert _engine_tex_reader()(c_payload, len(payload))
        section = texconv.parse_texs(payload)
        tex = section.textures[0]
        assert (tex["width"], tex["height"], tex["psm"], tex["mips"]) == (
            width, height, texconv.PSMT8, 1)
        indices = section.mip(tex, 0)[2][:expected_bytes]
        palette = texconv.parse_clut(payload[tex["clut_offset"]:tex["clut_offset"] + 1024], 256)
        _w, _h, rgba = bitmaps.decode_level(image, source.pixels(image), 0)
        expected = [(rgba[i], rgba[i + 1], rgba[i + 2], texconv.ps2_alpha(rgba[i + 3]))
                    for i in range(0, len(rgba), 4)]
        reconstructed = [palette[index] for index in indices]
        assert reconstructed == expected



def test_sprite_frame_cannot_reference_a_missing_image(tmp_path):
    sources,owner,schema=fixture(tmp_path)
    md=sources['source']; raw=bytearray(md.region); struct.pack_into('<h',raw,0x110,99); md.region=bytes(raw)
    with pytest.raises(BitmapProfileError,match='sprite frame bitmap index'):
        serialize_bitmap(sources,owner,schema)


def test_retail_health_ammo_radar_hud_keep_native_resolution():
    """Health, ammo and motion-sensor art is drawn 1:1, so it must not be halved."""
    root = Path(__file__).resolve().parents[1]
    source_path = root / "build/retail-maps/decompressed/bloodgulch.map"
    if not source_path.is_file():
        pytest.skip("retail Blood Gulch source map unavailable")
    sys.path[:0] = [str(root / "submodules/halo-ps2/tools"),
                    str(root / "submodules/halo-ps2/tools/halo2ps2")]
    from halo2ps2 import bitmaps, texconv
    source = texconv.MapData.open(source_path)
    seen = set()
    for entry in source.index.entries:
        path = entry.path.casefold()
        if entry.group != "bitm" or path not in NATIVE_RESOLUTION_HUD_BITMAPS:
            continue
        seen.add(path)
        for image in bitmaps.parse_images(source.region, source.base, entry.data_address):
            texture = texconv.convert_texture(source, image, entry.tag_id, texconv.CLASS_BLEND,
                                              preserve_source_resolution=True)
            assert (texture.width, texture.height) == (image.width, image.height)
    assert seen == NATIVE_RESOLUTION_HUD_BITMAPS
