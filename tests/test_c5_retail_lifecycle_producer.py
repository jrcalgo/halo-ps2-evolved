"""Host tests for the C5 retail lifecycle producer (tools/c5_retail_lifecycle_producer.py).

The producer compiles the real CE actors.c and memory/data.c (ILP32) and runs one harness per
C1 recipe. These tests check the evidence it writes: retail stages only from executed code,
exact blockers for the rest, bot counters never sampled, and that the ledger accepts the output.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import c5_retail_actor_lifecycle as c5  # noqa: E402
import c5_retail_lifecycle_producer as producer  # noqa: E402

ROSTER = ROOT / "docs/reports/m2-c1-actor-roster-2026-10-23.json"


@unittest.skipUnless(shutil.which("clang"), "clang -m32 required for the ILP32 host closure")
class ProducerRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="c5-producer-test-")
        cls.addClassCleanup(cls.tmp.cleanup)
        work = Path(cls.tmp.name)
        cls.evidence_path = work / "evidence.json"
        result = subprocess.run([sys.executable, "-I", str(ROOT / "tools/c5_retail_lifecycle_producer.py"),
                                 "--limit", "3", "--output", str(cls.evidence_path),
                                 "--work", str(work / "build")], capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        cls.evidence = json.loads(cls.evidence_path.read_text())

    def test_format_pins_the_roster(self):
        self.assertEqual(self.evidence["format"], c5.EVIDENCE_FORMAT)
        self.assertEqual(self.evidence["roster_sha256"], c5.sha256_file(ROSTER))
        self.assertEqual(len(self.evidence["records"]), 3)

    def test_real_ce_units_and_stub_closure_are_recorded(self):
        host = self.evidence["host"]
        self.assertIn("submodules/halo-ce-universal/source/ai/actors.c", host["real_units"])
        self.assertIn("submodules/halo-ce-universal/source/memory/data.c", host["real_units"])
        self.assertIn("submodules/halo-ce-universal/source/objects/objects.c", host["real_units"])
        self.assertTrue(any(item.startswith("submodules/halo-ce-universal/source/cache/cache_files.c") for item in host["generated_from"]))
        self.assertGreater(host["blocked_function_stubs"], 0)

    def test_no_stage_is_retail_passed_without_executed_code(self):
        for record in self.evidence["records"]:
            self.assertEqual(record["kind"], "blocked")
            for name in c5.STAGES:
                self.assertIn(name, record["stages"])
                self.assertNotEqual(record["stages"][name]["status"], "passed", record["variant"])
                self.assertNotEqual(record["stages"][name].get("kind"), "retail", record["variant"])

    def test_blockers_are_exact_and_name_the_first_stub_reached(self):
        for record in self.evidence["records"]:
            placement = record["stages"]["placement"]
            self.assertEqual(placement["status"], "blocked")
            self.assertEqual(placement["blocker"],
                             "not reached: setup stopped at game_state_allocate_buffer before the placement stage")
            self.assertEqual(record["harness_exit"], 3)
            self.assertNotIn("without a blocker record", placement["blocker"])

    def test_bots_are_not_measured_and_not_claimed(self):
        bots = self.evidence["metrics"]["spartan_bots"]
        self.assertEqual(bots["status"], "not-measured")
        self.assertEqual(bots["samples"], 0)
        self.assertEqual(self.evidence["metrics"]["retail_actors"]["recipes_placed"], 0)

    def test_ledger_accepts_the_output_and_passes_nothing(self):
        result = c5.build(ROSTER, ROOT / "build/retail-maps/decompressed", self.evidence_path, limit=3)
        self.assertEqual(result["stages_passed"], 0)
        self.assertEqual(result["stages_failed"], 0)
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["retail_actor_records"])
        self.assertIsNone(result["spartan_bots"])


class ParserTest(unittest.TestCase):
    def _run(self, lines, exit_code=0):
        return {"exit": exit_code, "timeout": False, "lines": lines, "stderr": ""}

    def test_checked_stages_are_retail(self):
        run = self._run(["C5 begin stage=placement", "C5 end stage=placement result=7",
                         "C5 check stage=placement ok=1 detail=pool counts one",
                         "C5 begin stage=death", "C5 end stage=death result=7",
                         "C5 begin stage=cleanup", "C5 end stage=cleanup result=7",
                         "C5 check stage=cleanup ok=1 detail=pool empty",
                         "C5 metrics retail_samples=2 retail_peak=1 retail_failures=0 bot_samples=0"])
        parsed = producer.parse_run(run)
        stages, kind = producer.stage_rows(parsed, run)
        self.assertEqual(stages["placement"]["status"], "passed")
        self.assertEqual(stages["placement"]["kind"], "retail")
        self.assertEqual(stages["cleanup"]["status"], "passed")
        # death ran but has no observable-state check: it stays blocked, with the reason
        self.assertEqual(stages["death"]["status"], "blocked")
        self.assertIn("no observable-state check", stages["death"]["blocker"])
        self.assertEqual(stages["update"]["status"], "blocked")
        self.assertEqual(kind, "retail")

    def test_failed_check_is_a_real_failure(self):
        run = self._run(["C5 begin stage=placement", "C5 end stage=placement result=-1",
                         "C5 check stage=placement ok=0 detail=placed actor is a live datum"])
        stages, _ = producer.stage_rows(producer.parse_run(run), run)
        self.assertEqual(stages["placement"]["status"], "failed")
        self.assertEqual(stages["placement"]["kind"], "retail")
        self.assertEqual(stages["death"]["status"], "blocked")
        self.assertIn("not reached", stages["death"]["blocker"])

    def test_open_stage_with_stub_is_blocked_with_symbol(self):
        run = self._run(["C5 begin stage=placement", "C5 blocked symbol=tag_get"], exit_code=3)
        stages, _ = producer.stage_rows(producer.parse_run(run), run)
        self.assertEqual(stages["placement"]["status"], "blocked")
        self.assertIn("tag_get", stages["placement"]["blocker"])

    def test_ce_assertion_is_the_blocker(self):
        run = self._run(["C5 begin stage=setup", "C5 assert file=c:\\halo\\SOURCE\\memory\\data.c line=67 expr=data",
                         "C5 exit system_exit=-1"], exit_code=3)
        parsed = producer.parse_run(run)
        self.assertIn("CE assertion failed at line 67", parsed["blocker"])
        stages, kind = producer.stage_rows(parsed, run)
        self.assertEqual(kind, "blocked")
        self.assertEqual(stages["placement"]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
