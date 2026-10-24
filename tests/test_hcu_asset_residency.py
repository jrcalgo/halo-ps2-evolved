"""Pin/lease/evict tests for the bounded HCP2 residency table.

Runs the C driver against real packages in build/m2-c2-hcp2-primary and checks
that every pinned chunk's SHA-256 equals the package's own logical digest."""
import hashlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "build/m2-c2-hcp2-primary"


def directory(data):
    count = struct.unpack_from("<I", data, 16)[0]
    rows = []
    for i in range(count):
        rows.append(struct.unpack_from("<IIIIIIII", data, 32 + i * 96))
        rows[-1] = rows[-1] + (data[32 + i * 96 + 64: 32 + i * 96 + 96].hex(),)
    return rows


class ResidencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.exe = Path(cls.tmp.name) / "residency_main"
        subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-I", str(ROOT / "src"),
                        str(ROOT / "tests/hcu_asset_residency_main.c"),
                        str(ROOT / "src/stream/hcu_asset_profile.c"),
                        str(ROOT / "src/stream/sha256.c"), "-o", str(cls.exe)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_driver(self, path, profile, chunks):
        return subprocess.run([str(self.exe), str(path), str(profile)] + chunks,
                              capture_output=True, text=True)

    def package(self, name):
        path = PKG / name
        if not path.exists():
            self.skipTest("missing HCP2 package %s" % name)
        return path

    def test_real_package_pin_evict_cycle(self):
        path = self.package("bots-bloodgulch.hcp")
        data = path.read_bytes()
        profile = struct.unpack_from("<I", data, 12)[0]
        rows = directory(data)
        ce = next(r for r in rows if r[0] == 1 and r[1] == 0)
        snd = next(r for r in rows if r[0] == 3 and r[1] == 0)
        result = self.run_driver(path, profile, ["1:0", "3:0"])
        self.assertEqual(result.returncode, 0, result.stderr)
        digests = dict()
        for line in result.stdout.splitlines():
            if line.startswith("PIN "):
                parts = dict(p.split("=") for p in line.split()[2:])
                digests[line.split()[1]] = parts["sha256"]
        self.assertEqual(digests["1:0"], ce[-1])
        self.assertEqual(digests["3:0"], snd[-1])
        # Residency is per segment: every segment is evicted twice (once in the
        # lifetime cycle, once after the whole-chunk pin) and refused three times.
        segments = sum(int(l.split("segments=")[1].split()[0])
                       for l in result.stdout.splitlines() if l.startswith("PIN "))
        self.assertEqual(segments, 74)
        self.assertIn("evictions %d " % (2 * segments), result.stdout)
        self.assertIn("verify_failures 0", result.stdout)
        self.assertIn("REFUSED %d " % (3 * segments), result.stdout)
        self.assertIn("refused_pins 0", result.stdout)

    def test_segments_are_bounded_to_64_KiB(self):
        path = self.package("bots-bloodgulch.hcp")
        data = path.read_bytes()
        profile = struct.unpack_from("<I", data, 12)[0]
        result = self.run_driver(path, profile, ["1:0"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("over 64 KiB", result.stderr)
        self.assertIn("PIN 1:0 bytes=4767713 segments=73", result.stdout)

    def test_media_chunk_is_pinnable_when_present(self):
        path = self.package("bots-bloodgulch.hcp")
        data = path.read_bytes()
        profile = struct.unpack_from("<I", data, 12)[0]
        media = [r for r in directory(data) if r[0] == 2]
        if not media:
            self.skipTest("no MEDIA resources in package")
        mid = media[0][1]
        result = self.run_driver(path, profile, ["2:%d" % mid])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PIN 2:%d" % mid, result.stdout)

    def test_corrupt_copy_is_refused_and_leaves_no_resident_state(self):
        path = self.package("bots-bloodgulch.hcp")
        data = bytearray(path.read_bytes())
        profile = struct.unpack_from("<I", data, 12)[0]
        # Flip one byte in the CE payload so segment hashing rejects the chunk.
        ce_offset = directory(bytes(data))[0][2]
        data[ce_offset] ^= 0x5A
        bad = Path(self.tmp.name) / "corrupt.hcp"
        bad.write_bytes(bytes(data))
        result = self.run_driver(bad, profile, ["1:0"])
        # Preflight rejects the corrupt chunk before any residency state exists.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL preflight rc=-5", result.stderr)
        self.assertNotIn("PIN", result.stdout)


if __name__ == "__main__":
    unittest.main()
