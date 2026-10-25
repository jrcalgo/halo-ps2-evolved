import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hcu_profile_consumer_exclusions as rules  # noqa: E402
import hcu_profile_package as package_builder  # noqa: E402

DECAL_ROW = {"class": "ce_world_particle_sprite_decal_lens_effect_source_only",
             "reason": "decal has no live PS2 consumer", "profile_kinds": ["bots"],
             "match": {"definition": "decal", "field": None, "owner_group": None, "role": None},
             "counts": {"bots-beavercreek": 1}}


def _ref(bitmap, owner_group="deca", field="shader.map", definition="decal", owner=1):
    return {"bitmap_output_datum": bitmap, "owner_group": owner_group, "field": field,
            "definition": definition, "owner_output_datum": owner, "owner_path": f"o{owner}",
            "source_key": "m", "bitmap_path": f"b{bitmap}"}


def test_loader_accepts_list_or_wrapper_and_pins_file_bytes(tmp_path):
    path = tmp_path / "x.json"
    path.write_text(json.dumps([DECAL_ROW]))
    loaded = rules.load_exclusions(path)
    assert loaded["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(loaded["rows"]) == 1
    wrapped = tmp_path / "w.json"
    wrapped.write_text(json.dumps({"required_profile_exclusions": [DECAL_ROW]}))
    assert rules.load_exclusions(wrapped)["rows"] == loaded["rows"]


@pytest.mark.parametrize("bad", [
    {"class": "c", "reason": "r", "profile_kinds": ["ui"], "match": {}, "counts": {}},
    dict(DECAL_ROW, profile_kinds=["bogus"]),
    dict(DECAL_ROW, match={"definition": None, "field": None, "owner_group": None}),
    dict(DECAL_ROW, extra=1),
])
def test_loader_rejects_malformed_rows(tmp_path, bad):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([bad]))
    with pytest.raises(ValueError):
        rules.load_exclusions(path)


def test_decide_requires_every_reference_to_be_excluded():
    rows = [rules._check_row(DECAL_ROW, 0)]
    refs = [_ref(5), _ref(5, owner_group="weap", field="x", definition="weapon")]
    assert rules.decide(refs, "ce_world_particle_sprite_decal_lens_effect_source_only", "bots", rows) is None
    assert rules.decide(refs[:1], "ce_world_particle_sprite_decal_lens_effect_source_only", "bots", rows) == rows


def test_decide_fails_closed_on_zero_refs_wrong_kind_and_unknown_role():
    rows = [rules._check_row(DECAL_ROW, 0)]
    role = "ce_world_particle_sprite_decal_lens_effect_source_only"
    assert rules.decide([], role, "bots", rows) is None
    assert rules.decide([_ref(5)], role, "ui", rows) is None
    assert rules.decide([_ref(5)], "unknown_owner_group_fail_closed", "bots", [
        rules._check_row(dict(DECAL_ROW, match={"definition": None, "field": None,
                                                "owner_group": None, "role": None}), 0)]) is None
    assert rules.decide([_ref(5)], "ps2_bsp_material_base_selected", "bots", [
        rules._check_row(dict(DECAL_ROW, match={"definition": None, "field": None,
                                                "owner_group": None, "role": None}), 0)]) is None


def test_role_field_must_equal_audit_role():
    row = rules._check_row(dict(DECAL_ROW, match={"definition": None, "field": None,
                                                  "owner_group": None, "role": "other"}), 0)
    assert rules.decide([_ref(5)], "ce_world_particle_sprite_decal_lens_effect_source_only", "bots", [row]) is None


def _fake_build_media(monkeypatch, covered_keys=()):
    def fake(sources, tags, *, conversion_cache=None, input_hashes=None, covered_out=None, object_profile=None):
        if covered_out is not None:
            covered_out.update({key: True for key in covered_keys})
        return {"chunks": [], "bindings": [], "memory": {}, "decisions": []}
    monkeypatch.setattr(package_builder, "build_media", fake)


_IMAGE_2D = SimpleNamespace(index=0, type=0, depth=1, format_name="a8", width=4, height=4,
                            mip_count=1, pixel_offset=0, pixel_size=3, is_2d=True)


def _sources(path, datums):
    by_id = {d: SimpleNamespace(group="bitm", path=f"bitmaps\\b{d}", data_address=0) for d in datums}
    return SimpleNamespace(path=path, by_id=by_id, region=b"", base=0,
                           pixels=lambda img: b"abc")


def _tag(datum, output):
    return {"source_key": "m", "source_datum": datum, "output_datum": output, "group": "bitm",
            "path": f"bitmaps\\b{datum}", "source_sha256": "a" * 64}


def _run(monkeypatch, tags, consumers, policy_rows, *, kind="bots", covered=()):
    _fake_build_media(monkeypatch, covered)
    monkeypatch.setattr(package_builder, "serialize_bitmap", lambda sources, owner, schema, **kw: {
        "source_sha256": "a" * 64, "sequences": [], "dispositions": [], "decision": "staged",
        "chunks": [{"key": f"BITM:{owner['source_datum']:x}", "kind": "BITM", "bytes": 3,
                    "data": b"abc", "sha256": "b" * 64,
                    "identity": {"source_image_index": 0}}]})
    monkeypatch.setattr(package_builder.bitmaps, "parse_images", lambda *a: [_IMAGE_2D])
    path = Path("/tmp/none.map")
    datums = [t["source_datum"] for t in tags]
    sources = {"m": _sources(path, datums)}
    policy = {"path": "x.json", "sha256": "c" * 64, "kind": kind,
              "rows": [rules._check_row(r, i) for i, r in enumerate(policy_rows)]}
    return package_builder.build_complete_media(sources, tags, {}, consumers,
                                                consumer_exclusions=policy)


def test_shared_bitmap_with_kept_consumer_stays(monkeypatch):
    tags = [_tag(1, 5), _tag(2, 6)]
    consumers = [_ref(5), _ref(5, owner_group="weap", field="x", definition="weapon"), _ref(6)]
    media = _run(monkeypatch, tags, consumers, [DECAL_ROW])
    # Bitmap 5 keeps a weapon consumer, so it stays; bitmap 6 is fully decal-excluded and drops.
    assert [r["output_datum"] for r in media["consumer_exclusions"]] == [6]
    assert [b["chunk_key"] for b in media["bindings"]] == ["BITM:1"]


def test_fully_excluded_bitmap_is_dropped_and_accounted(monkeypatch):
    tags = [_tag(1, 5), _tag(2, 6)]
    media = _run(monkeypatch, tags, [_ref(5), _ref(6, owner=2)], [DECAL_ROW])
    assert [r["output_datum"] for r in media["consumer_exclusions"]] == [5, 6]
    assert media["bindings"] == []
    assert media["chunks"] == []
    assert media["consumer_exclusion_policy"]["sha256"] == "c" * 64
    cat = next(c for c in media["bitmap_catalog"] if c["source_datum"] == 1)
    assert cat["dispositions"][0]["disposition"] == "excluded_by_consumer_exclusion"
    assert cat["dispositions"][0]["exclusion_sha256"] == "c" * 64
    assert cat["dispositions"][0]["exclusion_classes"] == [DECAL_ROW["class"]]


def test_zero_consumers_and_model_or_bsp_selection_keep_bitmap(monkeypatch):
    tags = [_tag(1, 5), _tag(2, 6), _tag(3, 7)]
    # 5: no references; 6: decal consumer but model-covered; 7: weapon consumer matches no rule.
    consumers = [_ref(6), _ref(7, owner_group="weap", field="x", definition="weapon")]
    media = _run(monkeypatch, tags, consumers, [DECAL_ROW], covered=[("m", 2)])
    assert media["consumer_exclusions"] == []
    assert {b["chunk_key"] for b in media["bindings"]} == {"BITM:1", "BITM:2", "BITM:3"}


def test_without_policy_output_has_no_consumer_keys(monkeypatch):
    _fake_build_media(monkeypatch)
    monkeypatch.setattr(package_builder.bitmaps, "parse_images", lambda *a: [])
    monkeypatch.setattr(package_builder, "serialize_bitmap", lambda *a, **k: {
        "source_sha256": "a" * 64, "sequences": [], "dispositions": [], "decision": "s", "chunks": []})
    sources = {"m": _sources(Path("/tmp/none.map"), [1])}
    media = package_builder.build_complete_media(sources, [_tag(1, 5)], {}, [_ref(5)])
    assert "consumer_exclusions" not in media
    assert "consumer_exclusion_policy" not in media


def test_decide_profile_matches_each_reference_and_keeps_guarded_bitmaps():
    rows = [rules._check_row(DECAL_ROW, 0)]
    policy = {"kind": "bots", "rows": rows, "sha256": "d" * 64, "path": "x.json"}
    manifest = {
        "dependencies": [
            {"group": "bitm", "source_key": "m", "source_datum": 1, "output_datum": 5, "path": "b1"},
            {"group": "bitm", "source_key": "m", "source_datum": 2, "output_datum": 6, "path": "b2"},
            {"group": "bitm", "source_key": "m", "source_datum": 3, "output_datum": 7, "path": "b3"},
        ],
        "bitmap_consumers": [
            # 5: a decal reference and a live weapon reference: the weapon reference keeps it.
            _ref(5), _ref(5, owner_group="weap", field="x", definition="weapon"),
            _ref(6),
            _ref(7),
        ],
        "tag_index_remaps": [],
    }
    decisions = rules.decide_profile(manifest, policy, guard_tags={("m", 3)})
    assert decisions[("m", 1)]["keep"] is True
    assert decisions[("m", 2)]["keep"] is False
    assert decisions[("m", 2)]["classes"] == [DECAL_ROW["class"]]
    assert decisions[("m", 3)]["keep"] is True
    assert decisions[("m", 3)]["reason"] == rules.GUARD_REASON


def test_decide_profile_without_policy_keeps_everything():
    manifest = {"dependencies": [{"group": "bitm", "source_key": "m", "source_datum": 1,
                                  "output_datum": 5, "path": "b1"}],
                "bitmap_consumers": [_ref(5)], "tag_index_remaps": []}
    decisions = rules.decide_profile(manifest, None)
    assert decisions[("m", 1)]["keep"] is True
    assert decisions[("m", 1)]["reason"] == "no_policy"
