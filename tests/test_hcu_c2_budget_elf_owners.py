#!/usr/bin/env python3
"""C2.3 checks for the ELF owner attribution (tools/audit_hcu_c2_budget_elf_owners.py).

These checks keep the attribution exact: each .bss byte is counted once, the
diagnostic bytes are a subset of the unowned .bss (not an addition to it), and
the elf_static reservation is read from config/memory-budget.json. The ELF
checks run only when the fresh gameplay probe ELF exists (build/ is not
committed). Runs under pytest or as a script.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_hcu_c2_budget_elf_owners as owners  # noqa: E402

FRESH_ELF = ROOT / "build/hcu-parent-link-probe/hcu-gameplay-machine.elf"
BUDGET = ROOT / "config/memory-budget.json"


def _reservation_from_budget():
    for region in json.loads(BUDGET.read_text())["regions"]:
        if region["name"] == "elf_static":
            return region["bytes"]
    raise KeyError("elf_static")


def test_reservation_is_read_from_budget():
    assert owners.elf_static_reservation() == _reservation_from_budget() == 2097152


def test_owner_rules_name_a_source_and_class():
    for name, (owner, cls, why) in owners.OWNER_RULES.items():
        assert owner and cls in ("owned", owners.DIAGNOSTIC), name
        assert owner == owners.ELF_STATIC if cls == owners.DIAGNOSTIC else owner != owners.ELF_STATIC, name
        assert why.strip(), name


def test_fresh_gameplay_elf_attribution_reconciles():
    if not FRESH_ELF.exists():
        return
    res = owners.attribute(FRESH_ELF, top=30)
    # Code and constants: text, rodata and the data sections, counted once.
    assert res["code_and_constant_bytes"] == res["text_bytes"] + res["rodata_bytes"] + res["data_bytes"]
    assert res["data_bytes"] == sum(res["sections"][s] for s in (".data", ".sdata", ".MIPS.abiflags"))
    # Owned plus unowned covers the .bss section exactly.
    assert res["owned_bss_total"] + res["unowned_bss_bytes"] == res["bss_bytes"]
    # Diagnostic bytes are inside the unowned .bss, never added to it.
    assert res["diagnostic_in_elf_static_total"] <= res["unowned_bss_bytes"]
    assert res["unowned_non_diagnostic_bss_bytes"] == \
        res["unowned_bss_bytes"] - res["diagnostic_in_elf_static_total"]
    # elf_static need is code plus unowned .bss, and the overflow is against the budget.
    assert res["elf_static_need_bytes"] == res["code_and_constant_bytes"] + res["unowned_bss_bytes"]
    assert res["elf_static_excess_bytes"] == max(0, res["elf_static_need_bytes"] - res["elf_static_reservation_bytes"])
    assert res["elf_static_fits"] == (res["elf_static_need_bytes"] <= res["elf_static_reservation_bytes"])


def test_top_tables_are_sorted_and_bounded():
    if not FRESH_ELF.exists():
        return
    res = owners.attribute(FRESH_ELF, top=12)
    for key in ("top_bss_symbols", "top_data_symbols", "top_text_symbols"):
        rows = res[key]
        assert len(rows) <= 12, key
        sizes = [r["bytes"] for r in rows]
        assert sizes == sorted(sizes, reverse=True), key
        assert all(r["source"] for r in rows), key


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("pass", name)
            except AssertionError as exc:
                failed += 1
                print("FAIL", name, exc)
    sys.exit(1 if failed else 0)
