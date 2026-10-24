"""Host resource-accounting acceptance for the 32 MiB budget and audited arenas."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from host_abi32 import flags, sysroot
from memory_budget import (POOL_ROLES, BudgetError, Ledger, canonical_json, claim, load_budget,
                           scenario_result, validate_budget)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/resource_accounting.c"
INCLUDE = ROOT / "submodules/halo-ps2/engine/src"
MEM = ROOT / "submodules/halo-ps2/engine/src/core/mem.c"


def compile_and_run(extra):
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "resource-accounting"
        command = ["gcc", *extra, "-std=c11", "-Wall", "-Wextra", "-Werror",
                   "-I", str(INCLUDE), str(SOURCE), str(MEM), "-o", str(binary)]
        subprocess.run(command, check=True)
        completed = subprocess.run([str(binary)], capture_output=True, text=True)
        if completed.returncode == -31:
            return None
        if completed.returncode != 0:
            raise AssertionError(completed.stdout + completed.stderr)
    payload = json.loads(completed.stdout)
    checks = [item for item in payload["checks"] if item["check"] != "sentinel"]
    failed = [item["check"] for item in checks if not item["pass"]]
    if failed or payload["failures"] != 0:
        raise AssertionError(failed)
    return payload


class ResourceAccounting(unittest.TestCase):
    def test_compiled_profiler_cap_matches_configured_committed_budget(self):
        budget = load_budget()
        source = (ROOT / "src/game/play_ee.c").read_text()
        match = re.search(r"#define PLAY_EE_COMMITTED_BYTES (\d+)u", source)
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1)), budget["committed_bytes"])

    def test_audited_arena_on_host_abis(self):
        native = compile_and_run([])
        self.assertEqual(native["abi"]["pointer"], 8)
        expected_runtime_regions = [
            {"name": region["name"], "bytes": region["bytes"]}
            for region in load_budget()["regions"]
            if region["name"] not in {"system_kernel", "elf_static", "uncommitted_reserve"}
        ]
        self.assertEqual(native["layout_v2"], expected_runtime_regions)
        loader = sysroot() / "usr/lib32/ld-linux.so.2"
        self.assertTrue(loader.is_file(), "ILP32 sysroot is required for the ABI comparison")
        ilp32 = compile_and_run(flags())
        if ilp32 is None:
            self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")
        self.assertEqual(ilp32["abi"]["pointer"], 4)
        self.assertEqual(native["checks"], ilp32["checks"])
        self.assertEqual(canonical_json(native["checks"]), canonical_json(ilp32["checks"]))

    def test_budget_totals_and_double_count(self):
        budget = load_budget()
        spans = validate_budget(budget)
        self.assertEqual(spans[-1]["end"], 32 * 1024 * 1024)
        roles = {span["role"] for span in spans}
        self.assertTrue(set(POOL_ROLES).issubset(roles))
        elf = next(span for span in spans if span["name"] == "elf_static")
        system = next(span for span in spans if span["name"] == "system_kernel")
        self.assertEqual(claim(spans, "executable_sections", elf["start"], elf["end"] - elf["start"]), "elf_static")
        with self.assertRaisesRegex(BudgetError, "double-counts"):
            claim(spans, "stacks", elf["start"], 4096)
        with self.assertRaisesRegex(BudgetError, "crosses"):
            claim(spans, "overlap", system["end"] - 16, 32)

    def test_steady_state_and_exhaustion_are_observable(self):
        ledger = Ledger(load_budget())
        self.assertTrue(ledger.allocate("frame_scratch", 16)["ok"])
        ledger.steady = True
        failure = ledger.allocate("frame_scratch", ledger.pools["frame_scratch"].cap)
        self.assertFalse(failure["ok"])
        self.assertEqual(failure["reason"], "exhausted")
        self.assertEqual(ledger.steady_allocations, [
            {"role": "frame_scratch", "requested": ledger.pools["frame_scratch"].cap, "ok": False},
        ])
        result = scenario_result(
            {"fixture": "synthetic", "retail": False},
            seed=1,
            tick_count=30,
            outcome="steady-state-allocation",
            diagnostics=ledger.steady_allocations,
        )
        again = scenario_result(
            {"fixture": "synthetic", "retail": False},
            seed=1,
            tick_count=30,
            outcome="steady-state-allocation",
            diagnostics=list(ledger.steady_allocations),
        )
        self.assertEqual(canonical_json(result), canonical_json(again))
        self.assertNotIn("pointer", canonical_json(result))


if __name__ == "__main__":
    unittest.main()
