"""Validate source lock routing and refusal paths without acquiring compilers."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import shutil
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


locked = module("locked_source")
resolver = module("lock_toolchain")


class SourceLocks(unittest.TestCase):
    def test_sdk_links_are_idempotent_and_preserve_existing_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sdk = root / "sdk"
            sdk.mkdir()
            script = sdk / "download_dependencies.sh"
            shutil.copyfile(ROOT / "submodules/ps2sdk/download_dependencies.sh", script)
            helper = root / "fixture_helper.py"
            helper.write_text('import os,sys\nfrom pathlib import Path\nurl=sys.argv[sys.argv.index("--url")+1]\nprint(Path(os.environ["FIXTURE_SOURCE_ROOT"])/("lwip" if "lwip.git" in url else "fatfs"))\n')
            for name in ("lwip", "fatfs"):
                (root / name).mkdir()
            env = {**os.environ, "HALO_LOCKED_SOURCE_HELPER": str(helper),
                   "FIXTURE_SOURCE_ROOT": str(root)}
            command = ["bash", str(script), "locked"]
            subprocess.run(["bash", "-n", str(script)], check=True)
            for _ in range(2):
                subprocess.run(command, env=env, cwd=root, check=True)
            external = sdk / "common/external_deps"
            self.assertEqual((external / "lwip").resolve(), root / "lwip")
            self.assertEqual((external / "fatfs").resolve(), root / "fatfs")
            (external / "fatfs").unlink()
            (external / "fatfs").mkdir()
            marker = external / "fatfs/user-file"
            marker.write_text("keep")
            result = subprocess.run(command, env=env, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Preserving existing", result.stderr)
            self.assertEqual(marker.read_text(), "keep")
            (external / "lwip").unlink()
            result = subprocess.run(command, env=env, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((external / "lwip").exists(), "both destinations must be checked before linking")
            self.assertNotIn("git fetch", script.read_text())
            self.assertNotIn("reset --hard", script.read_text())

    def test_annotated_tag_and_ambiguity(self):
        item = {"id": "test", "url": "https://example.invalid/repo", "ref": "v1"}
        with patch.object(resolver.subprocess, "check_output", return_value=
                          "a" * 40 + "\trefs/tags/v1\n" + "b" * 40 + "\trefs/tags/v1^{}\n"):
            self.assertEqual(resolver.resolve(item)["commit"], "b" * 40)
        with patch.object(resolver.subprocess, "check_output", return_value=
                          "a" * 40 + "\trefs/heads/v1\n" + "b" * 40 + "\trefs/tags/v1\n"):
            with self.assertRaisesRegex(RuntimeError, "Ambiguous"):
                resolver.resolve(item)

    def test_staging_requires_exact_clean_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "staging/fixture"
            path.mkdir(parents=True)
            def git(*args):
                return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()
            git("init", "-q")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            (path / "file").write_text("source\n")
            git("add", "file")
            git("commit", "-qm", "Fixture")
            commit = git("rev-parse", "HEAD")
            (root / "config").mkdir()
            (root / "config/toolchain-sources.json").write_text(json.dumps({"sources": [
                {"id": "fixture", "url": "fixture-url", "ref": "fixture-ref", "commit": commit}]}))
            with patch.object(locked, "ROOT", root):
                self.assertEqual(locked.source_path("fixture-url", "fixture-ref", root / "staging"), path)
                with self.assertRaisesRegex(RuntimeError, "uniquely match"):
                    locked.source_path("other-url", "fixture-ref", root / "staging")
                (path / "file").write_text("user edit\n")
                with self.assertRaisesRegex(RuntimeError, "modified compiler source"):
                    locked.source_path("fixture-url", "fixture-ref", root / "staging")
                self.assertEqual((path / "file").read_text(), "user edit\n")
                git("checkout", "--", "file")
                git("commit", "--allow-empty", "-qm", "Different commit")
                with self.assertRaisesRegex(RuntimeError, "different commit"):
                    locked.source_path("fixture-url", "fixture-ref", root / "staging")

    def test_adapted_scripts_fail_without_explicit_source_helper(self):
        env = {key: value for key, value in os.environ.items()
               if key not in ("HALO_LOCKED_SOURCE_HELPER", "PS2DEV_CONFIG_OVERRIDE")}
        count = 0
        with tempfile.TemporaryDirectory() as cwd:
            for target in ("ee", "iop", "dvp"):
                for script in sorted((ROOT / "submodules" / ("ps2toolchain-" + target) / "scripts").glob("*.sh")):
                    text = script.read_text()
                    if "HALO_LOCKED_SOURCE_HELPER" not in text:
                        continue
                    count += 1
                    self.assertNotIn("git clone", text)
                    self.assertNotIn("git fetch", text)
                    subprocess.run(["bash", "-n", str(script)], check=True)
                    result = subprocess.run(["bash", str(script)], cwd=cwd, env=env, capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("HALO_LOCKED_SOURCE_HELPER", result.stderr)
            self.assertEqual(list(Path(cwd).iterdir()), [])
        self.assertEqual(count, 11)


if __name__ == "__main__":
    unittest.main()
