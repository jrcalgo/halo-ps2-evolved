"""Exercise exact offline acquisition and failure-aware build stage reporting."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from acquire_sources import acquire
from build_toolchain import environment, run_stages


class Workflow(unittest.TestCase):
    def test_offline_acquisition_is_exact_and_preserves_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            def git(*args):
                return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()
            git("init", "-q")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            (source / "file").write_text("pinned\n")
            git("add", "file")
            git("commit", "-qm", "Pinned fixture")
            commit = git("rev-parse", "HEAD")
            (source / "file").write_text("later upstream\n")
            git("commit", "-qam", "New upstream")
            item = {"id": "fixture", "url": "https://example.invalid/unreachable.git", "commit": commit}
            base = root / "staging"
            result = acquire(item, base, local=source, offline=True)
            self.assertEqual((result / "file").read_text(), "pinned\n")
            self.assertEqual(acquire(item, base, offline=True), result)
            (result / "file").write_text("user edit\n")
            with self.assertRaisesRegex(RuntimeError, "modified compiler source"):
                acquire(item, base, local=source, offline=True)
            self.assertEqual((result / "file").read_text(), "user edit\n")
            with self.assertRaisesRegex(RuntimeError, "explicit local"):
                acquire({**item, "id": "absent"}, base, offline=True)
            with self.assertRaises(subprocess.CalledProcessError):
                acquire({**item, "id": "bad-commit", "commit": "0" * 40}, base, local=source, offline=True)
            self.assertFalse((base / "bad-commit").exists())
            self.assertFalse(list(base.glob(".acquire-*-*")))
            (base / "linked").symlink_to(result, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "source symlink"):
                acquire({**item, "id": "linked"}, base, local=source, offline=True)

    def test_failed_stage_stops_and_retains_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "result.json"
            stages = [("failure", [sys.executable, "-c", 'print("failure details"); raise SystemExit(7)'], root),
                      ("must-not-run", [sys.executable, "-c", 'open("unexpected", "w").close()'], root)]
            with self.assertRaisesRegex(RuntimeError, "exit 7"):
                run_stages(stages, dict(os.environ), manifest, {"fixture": "identity"})
            report = json.loads(manifest.read_text())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(len(report["stages"]), 1)
            self.assertEqual(report["stages"][0]["exit_code"], 7)
            self.assertIn("failure details", Path(report["stages"][0]["log"]).read_text())
            self.assertFalse((root / "unexpected").exists())
            first_log = Path(report["stages"][0]["log"])
            with self.assertRaises(RuntimeError):
                run_stages(stages, dict(os.environ), manifest, {"fixture": "identity"})
            self.assertNotEqual(json.loads(manifest.read_text())["run_directory"], report["run_directory"])
            self.assertIn("failure details", first_log.read_text())

    def test_build_environment_is_bounded_and_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"HALO_BUILD_ROOT": directory, "HALO_BUILD_JOBS": "2",
                                         "PS2SDKSRC": "unwanted", "DESTDIR": "unwanted", "MAKEFLAGS": "unwanted"}):
                build, prefix, env, jobs = environment()
                self.assertEqual(build, Path(directory))
                self.assertEqual(prefix, build / "toolchain/install")
                self.assertEqual(jobs, 2)
                self.assertNotIn("PS2SDKSRC", env)
                self.assertNotIn("DESTDIR", env)
                self.assertNotIn("MAKEFLAGS", env)
                os.environ["HALO_BUILD_JOBS"] = "0"
                with self.assertRaisesRegex(RuntimeError, "between 1 and 64"):
                    environment()


if __name__ == "__main__":
    unittest.main()
