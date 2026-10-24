import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("hcu_profile_presentation", ROOT / "tools/hcu_profile_presentation.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_weapon_pose_dependency_report_is_deterministic_and_pinned():
    first = MODULE.build_report(ROOT)
    second = MODULE.build_report(ROOT)
    assert first == second
    assert first["source_provenance"]["sha256"] == "6c0afbcf46ecd3a70ef5106e4f51d68414d5a389c1e0b1d14c47a2766abddfe0"
    assert first["source_pins"]["src/game/play_fp.c"]
    assert first["source_pins"]["plans/7.hcu-remake-m2-m4.md"]
    assert first["weapons"]["sword"]["consumer_reference"]
    assert first["weapons"]["gravity_rifle"]["consumer_reference"]
    assert first["weapons"]["sword"]["candidate_runtime_payload_bytes"] > 0
    assert first["weapons"]["gravity_rifle"]["candidate_runtime_payload_bytes"] > 0


def test_fuel_rod_pose_is_metadata_only_and_oracles_are_not_payload():
    report = MODULE.build_report(ROOT)
    fuel = report["weapons"]["fuel_rod"]
    assert fuel["candidate_runtime_payload_bytes"] == 0
    assert fuel["consumer_reference"] is True
    assert fuel["active_legacy_array_sampling"] is False
    assert fuel["oracle_fixture_only"]["included_in_runtime_payload"] is False
    assert "rocket-launcher" in fuel["limitation"]
    assert report["consumer_references"]["fuel_rod_active_pose"].startswith("rocket-launcher")
    for name in ("sword", "gravity_rifle"):
        assert report["weapons"][name]["oracle_fixture_only"]["present"]
        assert not report["weapons"][name]["oracle_fixture_only"]["included_in_runtime_payload"]


def test_chunk_policy_and_renderer_gap_are_explicit():
    assessment = MODULE.build_report(ROOT)["acceptance_assessment"]
    assert assessment["independent_chunks_required_by_policy"] is True
    assert assessment["legacy_compiled_assets_satisfy_independent_chunk_requirement"] is False
    assert assessment["qualified_hcu_target_consumer"] is False
    assert assessment["result"] == "partial"
    assert "No target renderer" in assessment["concrete_gap"]


def test_json_output_is_canonical(tmp_path):
    report = MODULE.build_report(ROOT)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    assert json.loads(path.read_text()) == report
    assert path.read_text().endswith("\n")


def test_pointer_free_chunks_match_live_header_sampler_and_reject_corruption(tmp_path):
    payload = MODULE.build_presentation(ROOT)
    sword, gravity = tmp_path / "sword.hpos", tmp_path / "gravity.hpos"
    sword.write_bytes(payload["chunks"][1])
    gravity.write_bytes(payload["chunks"][2])
    exe = tmp_path / "pose-fixture"
    subprocess.run([
        "cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-Isrc", "-Isubmodules/halo-ps2/engine/src", "tests/hcu_pose_asset_main.c",
        "src/stream/hcu_pose_asset.c", "-lm", "-o", str(exe),
    ], cwd=ROOT, check=True)
    result = subprocess.run([str(exe), str(sword), str(gravity)], cwd=ROOT,
                            check=True, text=True, capture_output=True)
    assert "pose-payload-parity" in result.stdout
    assert "result=passed" in result.stdout


def test_asset_chunk_catalog_is_separate_and_pins_sources():
    payload = MODULE.build_presentation(ROOT)
    assert set(payload["chunks"]) == {1, 2}
    assert [b["asset_id"] for b in payload["bindings"]] == ["sword", "gravity_rifle"]
    assert all(b["kind"] == "POSE" and b["runtime_admitted"] is False for b in payload["bindings"])
    assert all(len(b["chunk_sha256"]) == 64 for b in payload["bindings"])
    assert payload["memory"]["total_chunk_bytes"] == sum(map(len, payload["chunks"].values()))
    assert payload["provenance"]["sword"]["source_map_sha256"] == MODULE.SOURCE_SHA
    assert payload["presentation_provenance"]["source_animation_map"]["retained"] is False
    assert "src/game/carbine_idle.h" in payload["presentation_provenance"]["adapter_files"]


def test_durable_native_parity_artifact():
    payload = MODULE.build_presentation(ROOT)
    out = ROOT / "build/m2-c1-presentation-native"
    out.mkdir(parents=True, exist_ok=True)
    sword, gravity = out / "sword.hpos", out / "gravity.hpos"
    sword.write_bytes(payload["chunks"][1])
    gravity.write_bytes(payload["chunks"][2])
    exe = out / "hcu-pose-asset-fixture"
    command = ["cc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-Isrc",
               "-Isubmodules/halo-ps2/engine/src", "tests/hcu_pose_asset_main.c",
               "src/stream/hcu_pose_asset.c", "-lm", "-o", str(exe)]
    subprocess.run(command, cwd=ROOT, check=True)
    run = subprocess.run([str(exe), str(sword), str(gravity)], cwd=ROOT,
                         check=True, text=True, capture_output=True)
    (out / "execution.log").write_text(run.stdout + run.stderr)
    pins = ["tools/hcu_profile_presentation.py", "src/stream/hcu_pose_asset.c",
            "src/stream/hcu_pose_asset.h", "tests/hcu_pose_asset_main.c",
            "src/game/sword_idle.h", "src/game/carbine_idle.h", "src/game/hold_pose.h"]
    result = {"result": "passed", "command": command,
              "coverage": "all 89 frames plus wrap frames for all 37 sword and gravity nodes; Q/T/override/constants exact parity; truncation, counts, parent ordering, names, ranges and nonfinite rejection",
              "executable_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
              "chunk_sha256": {"1": hashlib.sha256(sword.read_bytes()).hexdigest(),
                               "2": hashlib.sha256(gravity.read_bytes()).hexdigest()},
              "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in pins},
              "stdout": run.stdout.strip()}
    (out / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
