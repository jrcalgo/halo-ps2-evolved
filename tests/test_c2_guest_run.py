import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import c2_guest_run


def test_guest_log_keeps_errors_and_address_errors():
    lines = c2_guest_run.halo_lines(
        "[12.3] [err] cannot bind drain gate\n"
        "[13.0] Address Error exception\n"
        "[14.0] ordinary emulator noise\n")
    assert lines == ["[err] cannot bind drain gate", "Address Error exception"]


def test_lifecycle_requires_both_release_and_completion_markers():
    release = c2_guest_run.LIFECYCLE_EXTRA[0]
    complete = c2_guest_run.LIFECYCLE_EXTRA[1]
    assert c2_guest_run.check_markers([release], lifecycle=True)[
        "lifecycle-owner-released"]
    assert not c2_guest_run.check_markers([release], lifecycle=True)[
        "lifecycle-complete"]
    assert c2_guest_run.check_markers([release, complete], lifecycle=True)[
        "lifecycle-complete"]


def test_production_qualification_requires_ordered_ce_mount_and_release():
    sequence = [
        "HALO_PS2_LOCAL partition-selected name=bots_sidewinder qualified=1",
        "HALO_PS2_LOCAL profile-runtime row=bots_sidewinder map=sidewinder profile=13 package-bytes=19484677",
        "HALO_PS2_LOCAL map-mount result=1 active=1 map=sidewinder source=profile-runtime",
        "HALO_PS2_LOCAL production-ce-map-loaded result=1 map=sidewinder scenario=1 tag-table=1 tag-count=1830 tag-bytes=4584878 bsp-bytes=1993740",
        "HALO_PS2_LOCAL production-ce-map-released result=1 map=sidewinder mounted=0 tag-bytes=0 bsp-bytes=0",
    ]
    complete_lines = ["HALO_PS2_LOCAL machine entry", *sequence]
    assert c2_guest_run.production_guest_qualification(complete_lines)["guest_completed"]
    assert not c2_guest_run.production_guest_qualification(complete_lines[:3])["guest_completed"]
    assert not c2_guest_run.production_guest_qualification(
        [complete_lines[0], sequence[0], sequence[1], sequence[3], sequence[2], sequence[4]])[
            "guest_completed"]
    assert not c2_guest_run.production_guest_qualification(
        complete_lines + ["[err] late runtime failure"])["guest_completed"]
    exact = c2_guest_run.production_tuple_qualification(
        complete_lines, "bots_sidewinder", "sidewinder", 13, 19484677)
    assert exact["guest_completed"]
    assert all(exact["tuple_checks"].values())
    mismatch = c2_guest_run.production_tuple_qualification(
        complete_lines, "other_row", "sidewinder", 13, 19484677)
    assert not mismatch["guest_completed"]
    assert not mismatch["tuple_checks"]["partition_row_matches"]


def test_diagnostic_terminal_markers_and_errors(tmp_path):
    log = tmp_path / "guest.log"
    log.write_text("HALO_PS2_LOCAL step8-mp-capacity-complete maps=13 query_only=1\n")
    assert c2_guest_run._run_terminal("capacity", log) == "completion-marker"
    log.write_text("HALO_PS2_LOCAL step8-mp-workload map=sidewinder local_players=4 units=4 "
                    "unit_indices=0,1,2,3 ticks=3 objects=94 active_objects=88 "
                    "game_state_used=3107656 game_state_peak=3107656 game_state_fail=0 "
                    "object_pool_used=92768 object_pool_peak=92768 object_pool_fail=0 "
                    "dynamic_simulation=separate workload=local-splitscreen-only bots=not-exercised\n"
                    "HALO_PS2_LOCAL step8-mp-workload-complete local_players=4 ticks=3 teardown=clean\n")
    assert c2_guest_run._run_terminal("workload4p", log) == "completion-marker"
    log.write_text("HALO_PS2_LOCAL step8-mp-workload map=sidewinder local_players=4\n"
                    "HALO_PS2_LOCAL step8-mp-workload-complete local_players=4 ticks=3 teardown=clean\n")
    assert c2_guest_run._run_terminal("workload4p", log) is None
    log.write_text("HALO_PS2_LOCAL step8-mp-workload map=sidewinder local_players=4 "
                    "bots=not-exercised\n"
                    "HALO_PS2_LOCAL step8-mp-workload-complete local_players=4 ticks=3 teardown=clean\n")
    assert c2_guest_run._run_terminal("workload2p", log) is None
    log.write_text("HALO_PS2_LOCAL machine entry\n[err] cache map load failed\n")
    assert c2_guest_run._run_terminal("lifecycle", log) == "guest-error"
    log.write_text("Address Error, addr=0x1ff [store]\nHALO_PS2_LOCAL machine entry\n")
    assert c2_guest_run._run_terminal("lifecycle", log) is None
    log.write_text("HALO_PS2_LOCAL machine entry\nHALO_PS2_LOCAL halt reason=0x1\n")
    assert c2_guest_run._run_terminal("lifecycle", log) == "guest-error"


def test_guest_run_records_config_switches_and_selected_bios_hash(tmp_path):
    config = tmp_path / "PCSX2/inis/PCSX2.ini"
    config.parent.mkdir(parents=True)
    config.write_text("[EmuCore/CPU/Recompiler]\nEnableEE = false\nEnableIOP = false\n"
                      "EnableVU0 = false\nEnableVU1 = false\n[Filenames]\nBIOS = sample.bin\n")
    bios = tmp_path / "PCSX2/bios/sample.bin"
    bios.parent.mkdir(parents=True)
    bios.write_bytes(b"test-bios-image")
    identity = c2_guest_run.pcsx2_config_identity(tmp_path)
    assert identity["config_sha256"]
    assert identity["execution_backend"] == "interpreter-configured"
    assert identity["recompiler_switches"] == {
        "EnableEE": "false", "EnableIOP": "false",
        "EnableVU0": "false", "EnableVU1": "false"}
    assert identity["selected_bios"] == "sample.bin"
    assert identity["bios_files"][0]["sha256"]


def test_package_tree_mount_uses_build_time_guest_host_path(tmp_path):
    package_tree = tmp_path / "package-tree"
    (package_tree / "pkg/bots_sidewinder").mkdir(parents=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    c2_guest_run.mount_guest_package_tree(
        run_dir, package_tree, "build/m2-c2-resume-runtime-guest/bots-package-tree-v2")
    mounted = run_dir / "build/m2-c2-resume-runtime-guest/bots-package-tree-v2"
    assert mounted.is_symlink()
    assert (mounted / "pkg/bots_sidewinder").is_dir()
    try:
        c2_guest_run.mount_guest_package_tree(run_dir, package_tree, "../escape")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe host: package mount path was accepted")


def test_stage_host_paths_symlinks_repo_files_and_rejects_escapes(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    rel = "tools/c2_guest_run.py"
    assert c2_guest_run.stage_host_paths(run_dir, [rel]) == [rel]
    assert (run_dir / rel).is_symlink() and (run_dir / rel).is_file()
    assert c2_guest_run.stage_host_paths(run_dir, [rel]) == []
    for bad in ("../escape", "/etc/passwd"):
        try:
            c2_guest_run.stage_host_paths(run_dir, [bad])
        except ValueError:
            continue
        raise AssertionError(f"unsafe staging path accepted: {bad}")
