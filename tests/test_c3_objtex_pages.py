"""C3 objects: content-addressed OTEX texture pages (objtex.texture_pages / page_identity / shared_page_index).

Synthetic blobs are built with texconv.build_texs; the Blood Gulch case converts the Slayer needed set with the
C3 object profile from the retail map when it is staged (skipped otherwise)."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2 import objtex, texconv  # noqa: E402

MAP = ROOT / "build/retail-maps/decompressed/bloodgulch.map"
PACKAGE = ROOT / "build/m2-c2-r3-selected-packages/pkg/bloodgulch_mounted_gunner_4p4bot/bloodgulch_mounted_gunner_4p4bot.json"
SHA_BLOODGULCH = "9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1"


def _texture(source_id, fill, psm=texconv.PSMT8):
    clut = bytes([fill]) * 64                       # 16 entries * 4 bytes
    mip0 = bytes([fill ^ 0x5A]) * 256
    mip1 = bytes([fill ^ 0xA5]) * 64
    return texconv.Ps2Texture(source_id=source_id, width=16, height=16, psm=psm, flags=0, clut=clut,
                              clut_entries=16, mips=[mip0, mip1], avg_rgba=0x80402010)


def _blob(textures):
    shaders = []
    for i in range(len(textures)):
        s = texconv.ShaderInfo(100 + i, "soso", f"shader{i}")
        s.texture = i
        shaders.append(s)
    return texconv.build_texs(textures, shaders)


def test_identity_is_content_addressed_and_profile_scoped():
    blob = _blob([_texture(7, 1), _texture(8, 2)])
    pages = objtex.texture_pages(blob)
    assert [p["source_id"] for p in pages] == [7, 8]
    assert pages[0]["payload"] == bytes([1]) * 64 + bytes([1 ^ 0x5A]) * 256 + bytes([1 ^ 0xA5]) * 64
    same = objtex.texture_pages(_blob([_texture(7, 1)]))[0]
    a = objtex.page_identity("m" * 64, "c3-ps2-object-v1", pages[0])
    assert a == objtex.page_identity("m" * 64, "c3-ps2-object-v1", same)      # identical bytes: one identity
    assert a != objtex.page_identity("m" * 64, "other-profile", pages[0])     # profile is part of the key
    assert a != objtex.page_identity("n" * 64, "c3-ps2-object-v1", pages[0])  # map is part of the key
    flipped = dict(pages[0]); flipped["payload"] = b"\x00" + pages[0]["payload"][1:]
    assert a != objtex.page_identity("m" * 64, "c3-ps2-object-v1", flipped)  # one byte differs: other page
    other_id = dict(pages[0]); other_id["source_id"] = 99
    assert a != objtex.page_identity("m" * 64, "c3-ps2-object-v1", other_id)


def test_synthetic_entries_share_pages_once():
    e1 = _blob([_texture(7, 1), _texture(8, 2)])
    e2 = _blob([_texture(8, 2), _texture(9, 3)])     # shares bitmap 8 with e1
    idx = objtex.shared_page_index({"e1": e1, "e2": e2}, "m" * 64, "p")
    assert len(idx["pages"]) == 3
    assert idx["chunks"]["e1"][1] == idx["chunks"]["e2"][0]
    assert sorted(idx["pages"][idx["chunks"]["e1"][1]]["owners"]) == ["e1", "e2"]
    assert idx["referenced_bytes"] - idx["unique_bytes"] == idx["pages"][idx["chunks"]["e1"][1]]["bytes"]


def test_malformed_blob_is_refused():
    with pytest.raises(ValueError):
        objtex.texture_pages(b"TEXX" + bytes(60))


@pytest.mark.skipif(not (MAP.is_file() and PACKAGE.is_file()), reason="Blood Gulch map or package not staged")
def test_blood_gulch_needed_set_page_sharing():
    import json
    spec = importlib.util.spec_from_file_location("meas", ROOT / "tools/hcu_c3_objects_measure.py")
    meas = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(meas)
    from halo2ps2 import modelconv as mc
    man = json.loads(PACKAGE.read_text())
    m = texconv.MapData.open(MAP)
    import hashlib
    assert hashlib.sha256(MAP.read_bytes()).hexdigest() == SHA_BLOODGULCH   # the pinned map of the package
    needed = set(meas.SLAYER_NEEDED)
    rows = [b for b in man["chunk_bindings"] if b["kind"] == "MODL" and b["owner"]["group"] == "mode"
            and b["owner"]["path"] in needed]
    assert len(rows) == 28
    otex = {b["owner"]["path"]: mc.convert_map(m, [int(b["owner"]["source_datum"])],
                                              object_profile=mc.C3_OBJECT_PROFILE).otex for b in rows}
    idx = objtex.shared_page_index(otex, SHA_BLOODGULCH, mc.C3_OBJECT_PROFILE.name)
    # Measured on the v2 C3 object profile (c3-ps2-object-v2: per-class LOD, 64 px, 2 mips):
    # 261,824 B referenced per entry. The former 245,120 pinned the superseded single-LOD profile.
    assert idx["referenced_bytes"] == 261824
    assert idx["unique_bytes"] == 219712
    assert idx["referenced_bytes"] - idx["unique_bytes"] == 42112
