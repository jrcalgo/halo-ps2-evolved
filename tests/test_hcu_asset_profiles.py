"""Check that named HCU source profiles resolve to fixed filesystem roots."""
from pathlib import Path
import subprocess
import unittest


class AssetProfileTests(unittest.TestCase):
    def test_profile_roots_are_explicit_and_reject_unknown_values(self):
        root = Path(__file__).resolve().parents[1]
        expected = {
            "host": "host:/",
            "optical": "cdrom:/",
            "opl-usb": "mass:/",
            "opl-smb": "smb0:/",
            "opl-hdd": "pfs0:/",
        }
        for profile, asset_root in expected.items():
            result = subprocess.run([
                "make", "-s", "-f", str(root / "tests/hcu_asset_profile.mk"),
                "print-root", f"WORLD_HCU_ASSET_PROFILE={profile}"],
                cwd=root, check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), asset_root)
        invalid = subprocess.run([
            "make", "-s", "-f", str(root / "tests/hcu_asset_profile.mk"),
            "print-root", "WORLD_HCU_ASSET_PROFILE=unknown"],
            cwd=root, capture_output=True, text=True)
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("Unsupported WORLD_HCU_ASSET_PROFILE", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
