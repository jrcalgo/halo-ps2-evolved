import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import stage_hcu_profile_bitmaps as stage  # noqa: E402


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixture(tmp_path, monkeypatch, serializer=None):
    source = tmp_path / "ui.map"
    source.write_bytes(b"pinned-retail-map")
    ctag = tmp_path / "ui.unadmitted.ctag"
    ctag.write_bytes(b"exact-unadmitted-ctag")
    elf = tmp_path / "schema.elf"
    elf.write_bytes(b"pinned-schema-elf")
    diagnostic = {
        "format": "hcu-profile-diagnostic-v1", "profile": "ui", "failure_stage": "media",
        "error": "bitmap has no model-generated OTEX binding/qualified consumer", "tag_count": 2,
        "schema_elf_sha256": sha(elf.read_bytes()), "unadmitted_ctag_sha256": sha(ctag.read_bytes()),
        "source_maps": {"ui": {"path": str(source), "sha256": sha(source.read_bytes())}},
        "roots": [{"group": "hudg", "path": "ui\\hud\\default", "source": "ui"}],
        "dependencies": [
            {"group": "bitm", "source": "ui", "source_datum": 1, "path": "ui\\first",
             "source_sha256": sha(source.read_bytes())},
            {"group": "bitm", "source": "ui", "source_datum": 2, "path": "ui\\second",
             "source_sha256": sha(source.read_bytes())},
            {"group": "soso", "source": "ui", "source_datum": 3, "path": "ignored",
             "source_sha256": sha(source.read_bytes())},
        ],
    }
    diagnostic_path = tmp_path / "ui.failure.json"
    diagnostic_path.write_text(json.dumps(diagnostic))

    class FakeManifest:
        def __init__(self, elf32):
            self.elf32 = elf32
        def build(self):
            return {"elf_sha256": sha(elf.read_bytes()), "groups": [], "definitions": {}}

    monkeypatch.setattr(stage, "Elf32", lambda path: path)
    monkeypatch.setattr(stage, "SchemaManifest", FakeManifest)
    monkeypatch.setattr(stage.texconv.MapData, "open", staticmethod(
        lambda path: SimpleNamespace(path=path)))
    if serializer is not None:
        monkeypatch.setattr(stage, "serialize_bitmap", serializer)
    return diagnostic_path, elf, ctag, source


def fake_asset(sources, owner, schema):
    payload = b"same-serialized-bitmap"
    return {
        "format": "hcu-bitmap-assets-v1", "source_sha256": sha(b"pinned-retail-map"),
        "decision": "serialized for independently addressable staging; not admitted to live UI/effect presentation",
        "sequences": [{"sequence_index": 0, "name": "default", "frames": []}],
        "dispositions": [],
        "chunks": [{"key": f"BITM:{sha(payload)}", "kind": "BITM", "bytes": len(payload),
                    "sha256": sha(payload), "data": payload, "texture_source_id": owner["source_datum"],
                    "width": 8, "height": 4, "psm": 19, "image_format": "r5g6b5",
                    "source_pixel_offset": 128, "source_pixel_bytes": 64,
                    "source_pixel_sha256": sha(b"source pixels")}],
    }


def test_stages_and_deduplicates_chunks_deterministically(tmp_path, monkeypatch):
    diagnostic, elf, _, _ = fixture(tmp_path, monkeypatch, fake_asset)
    out_a, out_b = tmp_path / "stage-a", tmp_path / "stage-b"
    assert stage.stage_profile_bitmaps(diagnostic, elf, out_a) == 0
    assert stage.stage_profile_bitmaps(diagnostic, elf, out_b) == 0
    catalog_a = (out_a / "catalog.json").read_bytes()
    catalog_b = (out_b / "catalog.json").read_bytes()
    assert catalog_a == catalog_b
    catalog = json.loads(catalog_a)
    assert catalog["status"] == "staged"
    assert catalog["runtime_admitted"] is False
    assert len(catalog["assets"]) == 2
    assert catalog["storage"]["unique_chunk_count"] == 1
    assert catalog["storage"]["unique_chunk_bytes"] == len(b"same-serialized-bitmap")
    assert catalog["storage"]["max_selected_decoded_bytes"] == 8 * 4 * 4
    assert [x["sha256"] for x in catalog["chunks"]] == [x["sha256"] for x in json.loads(catalog_b)["chunks"]]
    chunk = out_a / catalog["chunks"][0]["path"]
    assert chunk.read_bytes() == b"same-serialized-bitmap"


def test_source_pin_failure_replaces_old_catalog_before_conversion(tmp_path, monkeypatch):
    called = []
    diagnostic, elf, _, source = fixture(
        tmp_path, monkeypatch, lambda *args: called.append(True))
    source.write_bytes(b"changed after diagnostic")
    output = tmp_path / "stage"
    output.mkdir()
    (output / "catalog.json").write_text('{"status":"staged"}')
    assert stage.stage_profile_bitmaps(diagnostic, elf, output) == 2
    catalog = json.loads((output / "catalog.json").read_text())
    assert catalog["status"] == "incomplete"
    assert catalog["runtime_admitted"] is False
    assert not called
    assert "SHA-256 does not match" in catalog["failures"][0]["failure"]


def test_failed_owner_records_image_and_continues(tmp_path, monkeypatch):
    def serializer(sources, owner, schema):
        if owner["source_datum"] == 1:
            raise ValueError("unsupported required bitmap image ui\\first[3] type=1")
        return fake_asset(sources, owner, schema)

    diagnostic, elf, _, _ = fixture(tmp_path, monkeypatch, serializer)
    output = tmp_path / "partial"
    assert stage.stage_profile_bitmaps(diagnostic, elf, output) == 2
    catalog = json.loads((output / "catalog.json").read_text())
    assert catalog["status"] == "incomplete"
    assert catalog["failures"][0]["source_datum"] == 1
    assert catalog["failures"][0]["image_index"] == 3
    assert [a["source_datum"] for a in catalog["assets"]] == [2]
