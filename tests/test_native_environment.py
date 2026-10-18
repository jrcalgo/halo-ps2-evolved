"""Check the native package trust boundary and container mount isolation."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import host_prerequisites
import container_run


class NativeEnvironment(unittest.TestCase):
    def test_all_package_checksums_are_verified_before_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packages = root / "build/host-prerequisites/packages"
            packages.mkdir(parents=True)
            (root / "config").mkdir()
            (packages / "first.deb").write_bytes(b"first")
            (packages / "second.deb").write_bytes(b"changed")
            (root / "config/native-prerequisites.json").write_text(json.dumps({"packages": [
                {"file": "first.deb", "sha256": hashlib.sha256(b"first").hexdigest()},
                {"file": "second.deb", "sha256": "0" * 64}]}))
            with patch.object(host_prerequisites, "ROOT", root), patch.dict(os.environ, {
                "HALO_BUILD_ROOT": str(root / "build"),
                "HALO_HOST_PREREQUISITE_PREFIX": str(root / "build/host-prerequisites/install"),
            }), patch.object(host_prerequisites.subprocess, "run") as process:
                with self.assertRaisesRegex(RuntimeError, "checksum differs"):
                    host_prerequisites.prepare()
                process.assert_not_called()
            self.assertFalse((packages.parent / "root").exists())

    def test_container_only_writes_its_own_output(self):
        output = container_run.ROOT / "build/container"
        command = container_run.command("host-tools", "sha256:fixture", output)
        mounts = [command[index + 1] for index, word in enumerate(command) if word == "--mount"]
        self.assertEqual(len(mounts), 2)
        self.assertTrue(mounts[0].endswith(",readonly"))
        self.assertIn(f"src={output},dst={output}", mounts[1])
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertIn("HALO_EXECUTION_ENV=container", command)
        for bad in (container_run.ROOT, container_run.ROOT / ".git/output", container_run.ROOT / "submodules/output", container_run.ROOT / "build"):
            with self.assertRaises(RuntimeError):
                container_run.command("host-tools", "sha256:fixture", bad)


if __name__ == "__main__":
    unittest.main()
