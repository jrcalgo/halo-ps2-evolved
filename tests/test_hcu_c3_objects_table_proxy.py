"""The C3 objects table generator pairs each low-detail stand-in with its full model."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
_spec = importlib.util.spec_from_file_location("hcu_c3_objects_table", ROOT / "tools/hcu_c3_objects_table.py")
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def _binding(kind, chunk, path, datum, sha, variant=None):
    row = {"kind": kind, "chunk_id": chunk, "sha256": sha,
           "owner": {"group": "mode", "path": path, "output_datum": datum, "source_datum": datum + 1000}}
    if variant:
        row["variant"] = variant
    return row


def _manifest():
    h = lambda c: c * 64
    return {"chunk_bindings": [
        _binding("MODL", 1, "vehicles\\ghost\\ghost", 7, h("a")),
        _binding("OTEX", 2, "vehicles\\ghost\\ghost", 7, h("b")),
        _binding("MODL", 3, "vehicles\\ghost\\ghost", 7, h("c"), "proxy"),
        _binding("OTEX", 4, "vehicles\\ghost\\ghost", 7, h("d"), "proxy"),
        _binding("MODL", 5, "scenery\\rock\\rock", 9, h("e")),
    ]}


def test_full_rows_ignore_the_proxy_variant():
    rows = gen.select(_manifest())
    assert [(r["path"], r["model_chunk"], r["texture_chunk"]) for r in rows] == [
        ("vehicles\\ghost\\ghost", 1, 2), ("scenery\\rock\\rock", 5, 0)]


def test_proxy_rows_follow_their_full_model_with_their_own_chunks():
    manifest = _manifest()
    rows = gen.select(manifest)
    proxies = gen.select_proxies(manifest, rows)
    assert len(proxies) == 1                      # the rock has no stand-in
    p = proxies[0]
    assert (p["model_chunk"], p["texture_chunk"], p["proxy"]) == (3, 4, 1)
    assert p["source_datum"] == rows[0]["source_datum"] and p["tag_datum"] == rows[0]["tag_datum"]
    assert p["model_sha256"] == "c" * 64 and p["texture_sha256"] == "d" * 64


def test_rendered_table_flags_the_proxy_and_carries_key_counts(tmp_path):
    manifest = _manifest()
    rows = gen.select(manifest)
    rows[0]["tex_keys"] = 6
    rows += gen.select_proxies(manifest, rows)
    rows[-1]["tex_keys"] = 2                      # the stand-in counts its own OTEX textures
    pj = tmp_path / "m.json"
    pj.write_text("{}")
    text = gen.render(rows, pj)
    assert "HCU_C3_OBJECTS_TABLE_COUNT 3u" in text
    assert text.count('", 0u, 6u }') == 1         # the ghost: full, six texture keys
    assert text.count('", 1u, 2u }') == 1         # its stand-in
