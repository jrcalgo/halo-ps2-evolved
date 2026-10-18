"""Exercise restoration of a fork-only commit and preservation of user edits."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("bootstrap", Path(__file__).resolve().parents[1] / "tools/bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


class Restoration(unittest.TestCase):
    def test_fork_only_restore_and_refusals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            git(source, "init", "-q")
            git(source, "config", "user.name", "Fixture")
            git(source, "config", "user.email", "fixture@example.invalid")
            (source / "file").write_text("upstream\n")
            git(source, "add", "file")
            git(source, "commit", "-qm", "Upstream fixture")
            upstream = git(source, "rev-parse", "HEAD")
            (source / "file").write_text("fork-only\n")
            git(source, "commit", "-qam", "Fork fixture")
            commit = git(source, "rev-parse", "HEAD")
            parent = root / "parent"
            parent.mkdir()
            git(parent, "init", "-q")
            bundles = parent / ".local/bundles"
            bundles.mkdir(parents=True)
            bundle = bundles / "fixture.bundle"
            git(source, "bundle", "create", str(bundle), "--all")
            git(source, "reset", "--hard", upstream)
            (parent / ".gitmodules").write_text('[submodule "fixture"]\n path = submodules/fixture\n url = https://example.invalid/unreachable.git\n')
            git(parent, "update-index", "--add", "--cacheinfo", "160000," + commit + ",submodules/fixture")
            (parent / "config").mkdir()
            (parent / "config/dependencies.json").write_text(json.dumps({"dependencies": [{
                "name": "fixture", "path": "submodules/fixture", "commit": commit,
                "upstream": "https://example.invalid/unreachable.git",
                "bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest()}]}))
            old_root = bootstrap.ROOT
            bootstrap.ROOT = parent
            try:
                bootstrap.bootstrap()
                bootstrap.bootstrap()
                work = parent / "submodules/fixture"
                self.assertEqual(git(work, "rev-parse", "HEAD"), commit)
                self.assertEqual((work / "file").read_text(), "fork-only\n")
                (work / "file").write_text("user edit\n")
                with self.assertRaisesRegex(RuntimeError, "dirty worktree"):
                    bootstrap.bootstrap()
                self.assertEqual((work / "file").read_text(), "user edit\n")
                bundle.unlink()
                with self.assertRaisesRegex(RuntimeError, "Missing or changed"):
                    bootstrap.bootstrap()
            finally:
                bootstrap.ROOT = old_root


if __name__ == "__main__":
    unittest.main()
