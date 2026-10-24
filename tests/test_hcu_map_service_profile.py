"""Host lifecycle regression for the HCP runtime in hcu_map_service.c.

The real map service translation unit runs with its CE hooks. The HCP envelope
and HCM1 metadata are real encoded blobs with pinned SHA-256 digests. Only the
profile mount seam is scripted by the C fixture."""
from __future__ import annotations

import hashlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
ENGINE = ROOT / "submodules/halo-ps2/engine/src"
PORT = HCU / "port/ps2"
PROFILE_ID = 7


def _hcm1(profile_id: int, ranges: list[tuple[int, int, int]], byte_count: int | None = None) -> bytes:
    body = b"".join(struct.pack("<III", *item) for item in ranges)
    total = 32 + len(body)
    header = struct.pack("<4sHHIIIIII", b"HCM1", 1, 32, total, profile_id,
                         0, 0, len(ranges), 0)
    return header + body


class MapServiceProfileLifecycleTest(unittest.TestCase):
    def test_runtime_lifecycle_preserves_owner_and_storage(self) -> None:
        sys.path.insert(0, str(ROOT / "tools"))
        import hcu_profile_chunks

        compiler = shutil.which("gcc-13") or shutil.which("gcc") or shutil.which("cc")
        if compiler is None:
            self.skipTest("no C compiler available")
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            package = hcu_profile_chunks.encode(PROFILE_ID, {
                "ce": bytes(range(256)) * 4,
                "media": b"media-chunk",
                "sound_meta": b"sound-meta-chunk",
            })
            package_path = tmp / "ui.hcp"
            package_path.write_bytes(package)
            meta_ok = _hcm1(PROFILE_ID, [])
            meta_big = _hcm1(PROFILE_ID, [(1, 0, 16)])
            ok_path = tmp / "meta-ok.hcm"
            big_path = tmp / "meta-big.hcm"
            ok_path.write_bytes(meta_ok)
            big_path.write_bytes(meta_big)
            exe = tmp / "hcu-map-service-profile"
            asset_root = tmp / "assets"
            asset_root.mkdir()
            cmd = [
                compiler, "-std=gnu11", "-D_EE", "-DHALO_FILE_USE_FILEXIO",
                "-Wall", "-Wextra", "-Werror", "-Wno-int-to-pointer-cast",
                "-no-pie",
                "-I" + str(ROOT / "tests/hcu_ctag_mount_shim"),
                "-I" + str(ROOT / "tests/hcu_ps2_cache_shim"),
                "-I" + str(ENGINE), "-I" + str(ROOT / "src"),
                "-I" + str(PORT / "include"),
                "-I" + str(ROOT / "submodules/ps2sdk/common/include"),
                "-I" + str(ROOT / "submodules/ps2sdk/ee/include"),
                "-I" + str(ROOT / "submodules/ps2sdk/ee/rpc/filexio/include"),
                str(ROOT / "tests/hcu_map_service_profile_main.c"),
                str(ROOT / "src/stream/ctag_mount.c"),
                str(ROOT / "src/stream/ctag_ps2_backend.c"),
                str(ROOT / "src/stream/cbsp_catalog.c"),
                str(ROOT / "src/stream/ctag_resource_index.c"),
                str(ROOT / "src/stream/ctag_map_source.c"),
                str(ROOT / "src/stream/sha256.c"),
                str(ROOT / "src/stream/hcu_asset_profile.c"),
                str(ROOT / "src/stream/hmap.c"),
                str(ROOT / "src/stream/hcu_map_catalog.c"),
                str(ROOT / "src/stream/hcu_profile_metadata.c"),
                str(ENGINE / "world/section.c"), str(ENGINE / "stream/hp2.c"),
                str(ENGINE / "stream/file.c"),
                str(ENGINE / "core/mem.c"),
                str(PORT / "src/ps2_cache.c"), str(PORT / "src/ps2_ctag.c"),
                str(PORT / "src/ps2_cbsp.c"),
                "-o", str(exe),
            ]
            built = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            run = subprocess.run([
                str(exe),
                str(package_path), hashlib.sha256(package).hexdigest(),
                str(ok_path), hashlib.sha256(meta_ok).hexdigest(),
                str(big_path), hashlib.sha256(meta_big).hexdigest(),
                str(asset_root) + "/",
            ], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertEqual(run.stdout.count("PASS "), 9, run.stdout)
            self.assertIn("reason=metadata", run.stdout)
            self.assertIn("map-service-profile-lifecycle passed", run.stdout)


if __name__ == "__main__":
    unittest.main()
