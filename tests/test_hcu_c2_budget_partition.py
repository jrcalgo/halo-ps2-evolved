#!/usr/bin/env python3
"""C2 partition and ELF owner attribution checks (asset-free where possible).

Runs the partition audit into a scratch directory and checks that:
  - all 27 archived profiles have a row, and each row fills the 10 MiB backing;
  - the renderer terms leave a non-negative texture residual in every row;
  - the generated C table in src/stream/hcu_memory_profile.c matches the rows;
  - the ELF owner attribution counts every .bss symbol byte exactly once.
The ELF checks run only when the probe ELF exists (build/ is not committed).
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import audit_hcu_c2_budget_elf_owners as owners  # noqa: E402

PROBE = ROOT / "build/m2-c2-resume-budget-v3/hcu-gameplay-machine-partition-sidewinder_marine_shotgun_4p4bot.elf"
TABLE_C = ROOT / "src/stream/hcu_memory_profile.c"
MAP_RENDER = 6291456 + 6815744  # budget v6
RESERVE_PER_OUTER_GUARD = 16
_REGIONS = {r["name"]: r["bytes"] for r in json.loads((ROOT / "config/memory-budget.json").read_text())["regions"]}
COMMITTED = json.loads((ROOT / "config/memory-budget.json").read_text())["committed_bytes"]
ELF_STATIC = _REGIONS["elf_static"]


def run_audit(out, elfs=()):
    cmd = [sys.executable, "-I", str(TOOLS / "audit_hcu_c2_partition_budget.py"), "--out", str(out)]
    for e in elfs:
        cmd += ["--elf", str(e)]
    subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=str(ROOT))
    return json.loads((out / "partition-table-profile-v2.json").read_text()), \
        json.loads((out / "budget-audit.json").read_text())


def test_rows_cover_27_profiles_and_fill_backing():
    with tempfile.TemporaryDirectory() as d:
        table, audit = run_audit(Path(d))
    rows = table["profiles"]
    assert len(rows) == 27
    assert any(r["name"] == "ui" for r in rows)
    for r in rows:
        assert r["tag_cache_bytes"] % 16 == 0
        assert r["structure_bsp_bytes"] % 16 == 0
        assert r["tag_cache_bytes"] + RESERVE_PER_OUTER_GUARD + r["structure_bsp_bytes"] + \
            r["render_texture_bytes"] + RESERVE_PER_OUTER_GUARD + r["residency_bytes"] == MAP_RENDER
        assert r["fits_guarded_map_render_backing"] and r["resident_fits"]
        assert r["render_residual_after_renderer_terms_bytes"] >= 0
        assert r["texture_cache_pages_available"] == r["render_residual_after_renderer_terms_bytes"] // 8192
    assert audit["committed_budget"]["committed_bytes"] == COMMITTED
    assert audit["renderer_terms"]["packet_workspace_bytes"] == 5632
    assert audit["renderer_terms"]["reserved_texture_bytes"] == 139264
    assert audit["renderer_terms"]["staging_slot_bytes"] == 65536


def test_c_table_matches_generated_rows():
    with tempfile.TemporaryDirectory() as d:
        table, _ = run_audit(Path(d))
    text = TABLE_C.read_text()
    found = re.findall(r'\{ "([^"]+)", \{ HCU_MEMORY_PROFILE_VERSION_1, (\d+), (\d+), (\d+), (\d+) \} \}', text)
    generated = [row for row in found if row[0] != "bots_sidewinder"]
    assert len(found) == 28
    assert len(generated) == 27
    by_name = {r["name"]: r for r in table["profiles"]}
    for name, tag, bsp, render, residency in generated:
        r = by_name[name]
        assert (r["tag_cache_bytes"], r["structure_bsp_bytes"], r["render_texture_bytes"],
                r["residency_bytes"]) == (int(tag), int(bsp), int(render), int(residency)), name


def test_inc_is_byte_identical_to_c_rows():
    with tempfile.TemporaryDirectory() as d:
        run_audit(Path(d))
        inc = (Path(d) / "partition-table-profile-v2.inc").read_text()
    text = TABLE_C.read_text()
    start = "static const hcu_memory_partition_entry_t hcu_partition_table_v2[] = {\n"
    assert text.count(start) == 1
    body = text.split(start, 1)[1].split("\n};", 1)[0]
    body = re.sub(r'^\s*\{ "bots_sidewinder",[^\n]*\n', '', body, flags=re.MULTILINE)
    assert inc == body + "\n"


def test_renderer_residual_and_page_flags_are_consistent():
    with tempfile.TemporaryDirectory() as d:
        table, audit = run_audit(Path(d))
    for r in table["profiles"]:
        assert r["render_residual_matches_capacity_report"], r["name"]
        residual = r["render_texture_bytes"] - 5632 - 139264
        assert r["render_residual_after_renderer_terms_bytes"] == residual, r["name"]
        assert r["texture_cache_pages_available"] == residual // 8192, r["name"]
        assert r["residency_guard_bytes"] == 16
        if r["package_media_bytes"] is None:
            assert r["texture_pages_short_of_upper_bound"] is None, r["name"]
        else:
            needed = -(-r["package_media_bytes"] // 8192)
            assert r["texture_pages_needed_upper_bound"] == needed, r["name"]
            assert r["texture_pages_short_of_upper_bound"] == (r["texture_cache_pages_available"] < needed), r["name"]
    ui = next(r for r in table["profiles"] if r["name"] == "ui")
    assert ui["package_media_bytes"] is None
    assert audit["texture_pages"]["rows_without_package_media"] == ["ui"]


def test_elf_attribution_counts_each_bss_byte_once():
    if not PROBE.exists():
        return
    res = owners.attribute(PROBE)
    named = sum(res["owned_bss_by_region"].values())
    diag = res["diagnostic_in_elf_static_total"]
    assert named == res["owned_bss_total"]
    assert named + res["unowned_bss_bytes"] == res["bss_bytes"]
    assert res["elf_static_need_bytes"] == res["file_backed_load_bytes"]
    assert diag <= res["bss_bytes"]
    names = [s for s in res["owned_rows"]] + res["diagnostic_in_elf_static"]
    assert len({r.get("symbol", r.get("name")) for r in names}) == len(names)


def test_probe_elf_static_overflow_is_reported_not_hidden():
    if not PROBE.exists():
        return
    with tempfile.TemporaryDirectory() as d:
        _, audit = run_audit(Path(d), [PROBE])
    e = audit["elf"][0]
    assert e["elf_static_fits"] == (e["elf_static_need_bytes"] <= ELF_STATIC)
    assert e["elf_static_excess_bytes"] == e["elf_static_need_bytes"] - ELF_STATIC
    assert e["below_reserve"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
