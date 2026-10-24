from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hcu_profile_chunks as profile


class ProfileChunksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.exe = Path(cls.tmp.name) / "fixture"
        subprocess.run(["cc", "-std=c99", "-I", str(ROOT / "src"),
                        str(ROOT / "tests/hcu_asset_profile_main.c"),
                        str(ROOT / "src/stream/hcu_asset_profile.c"),
                        str(ROOT / "src/stream/sha256.c"), "-o", str(cls.exe)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_image(self, data, profile_id=7):
        path = Path(self.tmp.name) / "profile.hcp"
        path.write_bytes(data)
        return subprocess.run([str(self.exe), str(path), str(profile_id)],
                              capture_output=True, text=True, check=True).stdout.strip()

    def sample(self):
        return profile.encode(7, {"ce": b"resident-tag-cache", "media": {1: b"texture-one", 9: b"texture-nine"},
                                  "sound_meta": b"sound-index"})

    def test_deterministic_and_multi_media(self):
        a = self.sample()
        self.assertEqual(a, self.sample())
        self.assertEqual(self.run_image(a), "OK 7 4 18")

    def test_rejects_corruption_wrong_profile_and_truncation(self):
        data = self.sample()
        self.assertIn("ERR -3", self.run_image(data, 8))
        self.assertIn("ERR", self.run_image(data[:-1]))
        changed = bytearray(data); changed[-1] ^= 1
        self.assertIn("ERR -5", self.run_image(changed))

    def test_rejects_overlapping_extent(self):
        import struct
        data = bytearray(self.sample())
        # Second directory entry offset aliases the first payload.
        first_offset = struct.unpack_from("<I", data, 32 + 8)[0]
        struct.pack_into("<I", data, profile.HEADER.size + profile.RECORD.size + 8, first_offset)
        self.assertIn("ERR -4", self.run_image(data))

    def test_media_chunk_limit_at_boundary(self):
        import hashlib
        import struct
        exact = profile.encode(7, {(1, 0): b'c', (3, 0): b's', (2, 1): b'x' * 65536}, version=1)
        self.assertIn("OK 7 3 1", self.run_image(exact))
        with self.assertRaises(profile.ProfileError):
            profile.encode(7, {(1, 0): b'c', (3, 0): b's', (2, 1): b'x' * 65537}, version=1)
        # Construct a structurally valid oversized wire package to exercise C preflight.
        payloads = [b'c', b'x' * 65537, b's']
        rows = bytearray(); body = bytearray(); offset = 32 + 3 * 48
        for kind, blob in zip((1, 2, 3), payloads):
            offset = (offset + 15) & ~15
            body.extend(b'\0' * (offset - (32 + 3 * 48 + len(body))))
            rows.extend(struct.pack('<4I32s', kind, 1 if kind == 2 else 0,
                                    offset, len(blob), hashlib.sha256(blob).digest()))
            body.extend(blob); offset += len(blob)
        total = 32 + len(rows) + len(body)
        header = struct.pack('<4s7I', b'HCP1', 1, 32, 7, 3, 32, len(rows), total)
        self.assertIn("ERR -4", self.run_image(header + rows + body))

    def test_many_roster_entries_and_invalid_ids(self):
        chunks = {(1, 0): b"ce", (3, 0): b"sound"}
        chunks.update({(2, i): f"asset-{i}".encode() for i in range(5000)})
        data = profile.encode(7, chunks)
        self.assertIn("OK 7 5002 2", self.run_image(data))
        with self.assertRaises(profile.ProfileError):
            profile.encode(7, {(1, 0): b"ce", (3, 0): b"s", (2, -1): b"bad"})
        with self.assertRaises(profile.ProfileError):
            profile.encode(7, {(1, 0): b"ce", (3, 0): b"s", (2, 0x1_0000_0000): b"bad"})


if __name__ == "__main__":
    unittest.main()


def test_directory_limit_is_bounded_and_streamable():
    import hashlib
    import struct
    from hcu_profile_validate import parse_package,ProfileValidationError
    chunks={(1,0):b'ce',(3,0):b'sound'}
    chunks.update({(2,i):b'x' for i in range(profile.MAX_CHUNKS-2)})
    data=profile.encode(7,chunks)
    parsed=parse_package(data,expected_package_sha256=hashlib.sha256(data).hexdigest(),expected_profile_id=7)
    assert len(parsed['directory'])==profile.MAX_CHUNKS
    chunks[(2,profile.MAX_CHUNKS)]=b'too many'
    try: profile.encode(7,chunks)
    except profile.ProfileError: pass
    else: raise AssertionError('directory count limit was bypassed')
    malformed=bytearray(data);struct.pack_into('<I',malformed,16,profile.MAX_CHUNKS+1)
    try: parse_package(bytes(malformed),expected_package_sha256=hashlib.sha256(malformed).hexdigest(),expected_profile_id=7)
    except ProfileValidationError: pass
    else: raise AssertionError('oversized directory accepted')
