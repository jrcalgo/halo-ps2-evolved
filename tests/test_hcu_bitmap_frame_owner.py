"""Bounded bitmap frame-owner lifecycle, independent of product-frame qualification."""
import shutil
import subprocess
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine"
HCU = ROOT / "submodules/halo-ce-universal"


def test_frame_owner_lifecycle(tmp_path):
    compiler = shutil.which("gcc")
    if not compiler:
        import pytest
        pytest.skip("GCC unavailable")
    includes = [ROOT / "src", ENGINE / "src", HCU / "port/ps2/include"]
    cmd = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror"]
    for include in includes:
        cmd += ["-I", str(include)]
    sources = [ROOT / "tests/hcu_bitmap_frame_owner_main.c",
               ROOT / "src/stream/hcu_bitmap_frame.c", ROOT / "src/stream/sha256.c"]
    hud_provider = HCU / "source/interface/interface.c"
    hud_text = hud_provider.read_text()
    marker = "halo_ps2_real_producer_descriptor_instance = {"
    assert marker in hud_text
    descriptor_body = hud_text.split(marker, 1)[1].split("};", 1)[0]
    assert "HALO_PS2_BITMAP_FRAME_PRODUCER_INTERFACE" in descriptor_body
    assert "HALO_PS2_BITMAP_FRAME_PRODUCER_WIDGETS" not in descriptor_body
    artifact_dir = ROOT / "build/m2-c1-bitmap-frame-owner"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    version = subprocess.run([compiler, "--version"], capture_output=True, text=True)
    cases = []
    for name, caps in (("both", 3), ("hud-only", 1)):
        exe = artifact_dir / f"frame-owner-{name}"
        build_cmd = cmd + ["-DHALO_PS2_BITMAP_FRAME_TEST_CAPS=" + str(caps)] + \
            [str(source) for source in sources] + ["-o", str(exe)]
        built = subprocess.run(build_cmd, capture_output=True, text=True)
        assert built.returncode == 0, built.stdout + built.stderr
        run = subprocess.run([str(exe)], capture_output=True, text=True)
        assert run.returncode == 0, run.stdout + run.stderr
        assert "FRAME_OWNER_OK" in run.stdout
        (artifact_dir / f"{name}.log").write_text(
            "compile stdout:\n" + built.stdout + "\ncompile stderr:\n" + built.stderr +
            "\nrun stdout:\n" + run.stdout + "\nrun stderr:\n" + run.stderr)
        cases.append({"name": name, "capabilities": caps,
                      "compile_command": build_cmd, "compile_returncode": built.returncode,
                      "compile_stdout": built.stdout, "compile_stderr": built.stderr,
                      "executable": str(exe.relative_to(ROOT)),
                      "executable_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
                      "run_returncode": run.returncode, "run_stdout": run.stdout,
                      "run_stderr": run.stderr})
    pins = {}
    for source in sources + [HCU / "port/ps2/include/halo_ps2_bitmap_frame.h",
                             HCU / "port/ps2/include/halo_ps2_bitmap_requests.h",
                             HCU / "port/ps2/src/ps2_bitmap_requests.c",
                             HCU / "port/ps2/src/ps2_render.c",
                             ROOT / "src/stream/hcu_bitmap_frame.h",
                             ROOT / "src/stream/hcu_bitmap_dispatch.h",
                             ROOT / "src/stream/hcu_asset_profile.h",
                             ROOT / "src/stream/sha256.h",
                             ROOT / "tests/test_hcu_bitmap_frame_owner.py",
                             hud_provider]:
        pins[str(source.relative_to(ROOT))] = hashlib.sha256(source.read_bytes()).hexdigest()
    report = {"schema": "hcu-bitmap-frame-owner-fixture-v1",
              "status": "fixture_lifecycle_passed",
              "actual_ce_frame_bound": False, "actual_gs_fence_observed": False,
              "product_frame_qualification": False, "host_only": True,
              "real_hud_descriptor_source": {
                  "path": str(hud_provider.relative_to(ROOT)),
                  "sha256": pins[str(hud_provider.relative_to(ROOT))],
                  "advertised_capability": "HALO_PS2_BITMAP_FRAME_PRODUCER_INTERFACE",
                  "widgets_advertised": False,
                  "linked_into_fixture": False},
              "compiler": shutil.which("gcc"), "compiler_version": version.stdout,
              "compiler_version_returncode": version.returncode,
              "source_sha256": pins,
              "cases": cases}
    (artifact_dir / "result.json").write_text(json.dumps(report, indent=2) + "\n")
