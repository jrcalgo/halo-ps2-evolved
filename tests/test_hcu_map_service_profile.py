"""Host lifecycle regression for the HCP runtime in hcu_map_service.c.

The real map service translation unit runs with its CE hooks. The HCP envelope
and HCM1 metadata are real encoded blobs with pinned SHA-256 digests. Only the
profile mount seam is scripted by the C fixture."""
from __future__ import annotations

import hashlib
import json
import os
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
    @staticmethod
    def _command(compiler: str, exe: Path, asset_root: Path, defines: tuple[str, ...] = ()) -> list[str]:
        return [
            compiler, "-std=gnu11", "-D_EE", "-DHALO_FILE_USE_FILEXIO",
            "-DHCU_M2_MP_HOST_ORACLE",  # host-only admission of ui, beavercreek and two more; never in the EE build
            *defines,
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

    def test_headless_admission_accepts_a_registered_foreign_successor(self) -> None:
        """The headless runtime guest admits the C2.8 successor under its own runtime."""
        sys.path.insert(0, str(ROOT / "tools"))
        import hcu_profile_chunks

        compiler = shutil.which("gcc-13") or shutil.which("gcc") or shutil.which("cc")
        if compiler is None:
            self.skipTest("no C compiler available")
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            package = hcu_profile_chunks.encode(PROFILE_ID, {
                "ce": bytes(range(256)) * 4, "media": b"media-chunk", "sound_meta": b"sound-meta-chunk"})
            meta_ok, meta_big = _hcm1(PROFILE_ID, []), _hcm1(PROFILE_ID, [(1, 0, 16)])
            (tmp / "ui.hcp").write_bytes(package)
            (tmp / "meta-ok.hcm").write_bytes(meta_ok)
            (tmp / "meta-big.hcm").write_bytes(meta_big)
            asset_root = tmp / "assets"
            asset_root.mkdir()
            exe = tmp / "hcu-map-service-profile-headless"
            built = subprocess.run(self._command(compiler, exe, asset_root, ("-DHALO_HCU_HEADLESS_RUNTIME_GUEST",)),
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            run = subprocess.run([
                str(exe), str(tmp / "ui.hcp"), hashlib.sha256(package).hexdigest(),
                str(tmp / "meta-ok.hcm"), hashlib.sha256(meta_ok).hexdigest(),
                str(tmp / "meta-big.hcm"), hashlib.sha256(meta_big).hexdigest(), str(asset_root) + "/"],
                capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("PASS headless admission accepts a registered foreign successor under its own runtime", run.stdout)
            self.assertIn("PASS headless admission refuses a successor of another partition row", run.stdout)
            self.assertEqual(run.stdout.count("PASS "), 28, run.stdout)
            self.assertIn("map-preflight rejected reason=headless-candidate-capacity map=carousel", run.stdout)
            self.assertIn("map-service-profile-lifecycle passed", run.stdout)

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
            cmd = self._command(compiler, exe, asset_root)
            built = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            run_command = [
                str(exe),
                str(package_path), hashlib.sha256(package).hexdigest(),
                str(ok_path), hashlib.sha256(meta_ok).hexdigest(),
                str(big_path), hashlib.sha256(meta_big).hexdigest(),
                str(asset_root) + "/",
            ]
            run = subprocess.run(run_command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertEqual(run.stdout.count("PASS "), 26, run.stdout)
            self.assertIn("corrupt package, metadata and bindings rejected before live teardown", run.stdout)
            self.assertIn("repeated preflight revalidates and discards a corrupted empty stage", run.stdout)
            self.assertIn("reason=metadata", run.stdout)
            self.assertIn("map-service-profile-lifecycle passed", run.stdout)
            retained = Path(os.environ.get("HCU_MAP_SERVICE_PROFILE_ARTIFACTS",
                                           ROOT / "build/m2-c2-map-service-profile")).resolve()
            shutil.copytree(tmp, retained, dirs_exist_ok=True)
            def artifact(path):
                return {"path": str(path.relative_to(ROOT)),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            sources = [Path(value) for value in cmd if value.endswith(".c")]
            sources += [ROOT / "src/stream/hcu_asset_profile.h",
                        ROOT / "src/stream/hcu_profile_mount.h",
                        ROOT / "src/stream/hcu_map_service.h", Path(__file__)]
            report = {
                "format": "hcu-c2-map-service-profile-host-v1",
                "evidence_level": "host execution", "result": "passed",
                "scope": "real map-service control flow with scripted CE mount seam",
                "limitation": "CE dispose, the renderer drain predicate and the mount seam are scripted; no GS/DMA fence, target run, or real CE simulation is exercised.",
                "passing_checks": run.stdout.count("PASS "),
                "compile_command": cmd, "run_command": run_command,
                "compile_returncode": built.returncode, "returncode": run.returncode,
                "inputs": [artifact(retained / name) for name in
                           ("ui.hcp", "meta-ok.hcm", "meta-big.hcm")],
                "executable": artifact(retained / exe.name),
                "source_pins": {str(path.relative_to(ROOT)): artifact(path)["sha256"]
                                for path in sources},
                "stdout": run.stdout, "stderr": run.stderr,
            }
            (retained / "result.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    unittest.main()
