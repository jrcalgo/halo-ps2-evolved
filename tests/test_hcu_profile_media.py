import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
import hcu_profile_media as media  # noqa: E402


class FakeMap:
    path = Path(__file__)
    by_id = {1: SimpleNamespace(group="mode"), 2: SimpleNamespace(group="mode"),
             8: SimpleNamespace(group="bitm"), 3: SimpleNamespace(group="snd!")}


def test_build_media_is_order_independent_and_deduplicates(monkeypatch):
    monkeypatch.setattr(media, "_verify_consumer", lambda group: {"path": "verified", "function": group,
                                                                     "source_sha256": "consumer-hash"})
    monkeypatch.setattr(media.modelconv, "convert_map", lambda m, ids, object_profile=None:
                        SimpleNamespace(modl=b"same-modl", otex=b"same-otex",
                                        otex_result=SimpleNamespace(textures=[])))
    rows = [dict(source_key="m", source_datum=1, group="mode", path="one"),
            dict(source_key="m", source_datum=2, group="mode", path="two")]
    a = media.build_media({"m": FakeMap()}, rows)
    b = media.build_media({"m": FakeMap()}, list(reversed(rows)))
    assert a == b
    assert len(a["chunks"]) == 2
    assert len(a["chunks"][0]["owners"]) == 2
    assert isinstance(a["chunks"][0]["data"], bytes)
    assert a["chunks"][0]["bytes"] == len(a["chunks"][0]["data"])
    assert a["memory"]["decoded_resident_ce_bytes"] == 0
    assert media.media_json_summary(a)["chunks"][0]["sha256"] == a["chunks"][0]["sha256"]


def test_build_media_rejects_absent_model_root():
    with pytest.raises(ValueError, match="missing mode source datum"):
        media.build_media({"m": FakeMap()},
                          [dict(source_key="m", source_datum=9, group="mode", path="missing")])


def test_build_media_rejects_unsupported_required_bitmap():
    with pytest.raises(ValueError, match="no model-generated OTEX binding"):
        media.build_media({"m": FakeMap()},
                          [dict(source_key="m", source_datum=8, group="bitm", path="texture")])


def test_sound_identity_is_metadata_only():
    rows = [dict(source_key="m", source_datum=3, group="snd!", path="sound\\fire")]
    result = media.build_media({"m": FakeMap()}, rows)
    assert result["chunks"] == []
    assert result["sound_metadata"]["m"][0]["datum"] == 3


def test_nonmedia_closure_tags_are_ignored():
    assert media.build_media({"m": FakeMap()},
                             [dict(source_key="m", source_datum=99, group="proj", path="projectile")])[
        "chunks"] == []


def test_model_covered_bitmap_binds_existing_otex(monkeypatch):
    monkeypatch.setattr(media, "_verify_consumer", lambda group: {"path": "verified", "function": group,
                                                                     "source_sha256": "consumer-hash"})
    monkeypatch.setattr(media.modelconv, "convert_map", lambda m, ids, object_profile=None:
                        SimpleNamespace(modl=b"m", otex=b"o",
                                        otex_result=SimpleNamespace(textures=[SimpleNamespace(source_id=8)])))
    rows = [dict(source_key="m", source_datum=1, group="mode", path="model"),
            dict(source_key="m", source_datum=8, group="bitm", path="bitmap")]
    result = media.build_media({"m": FakeMap()}, rows)
    assert len(result["chunks"]) == 2
    binding = next(b for b in result["bindings"] if b["owner"]["group"] == "bitm")
    assert binding["covered_by_model"] is True
    assert binding["kind"] == "OTEX"


def test_unknown_sound_identity_is_rejected():
    with pytest.raises(ValueError,match='missing snd! source datum'):
        media.build_media({'m':FakeMap()},[dict(source_key='m',source_datum=999,group='snd!',path='missing')])


def test_identical_cross_profile_inputs_convert_once(monkeypatch):
    calls=[]
    monkeypatch.setattr(media,'_verify_consumer',lambda _g:{'path':'qualified','function':'open','source_sha256':'pin'})
    monkeypatch.setattr(media.modelconv,'convert_map',lambda m,ids,object_profile=None:(calls.append(tuple(ids)) or
        SimpleNamespace(modl=b'model',otex=b'texture',otex_result=SimpleNamespace(textures=[]))))
    cache={}; tags=[dict(source_key='m',source_datum=1,group='mode',path='model')]
    one=media.build_media({'m':FakeMap()},tags,conversion_cache=cache,input_hashes={'m':'a'*64})
    two=media.build_media({'m':FakeMap()},tags,conversion_cache=cache,input_hashes={'m':'a'*64})
    assert one==two and calls==[(1,)]
    media.build_media({'m':FakeMap()},tags,conversion_cache=cache,input_hashes={'m':'b'*64})
    assert calls==[(1,),(1,)]
