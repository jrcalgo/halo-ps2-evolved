import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import c2_profile_boot_matrix as matrix

ROW = "sidewinder_marine_shotgun_4p4bot"
P = "HALO_PS2_LOCAL "


def good_log(row=ROW, map_name="sidewinder"):
    return [
        P + "machine entry",
        P + "kernel-reservation low=0x0 low_bytes=1048576 high=0x1f80000 high_bytes=524288 reserve=0x1a40000 reserve_bytes=5505024",
        P + f"partition-selected name={row} version=1 tag=6913936 bsp=1993744 texture=529472 residency=1048576 qualified=1",
        P + "arena name=resident_gameplay base=0x48c1e0 cap=5059028 used=4541812 high=4541812 alloc_failures=0 resets=0 releases=0 invalid_releases=0",
        P + "memory-physical elf_end=0x48bfac boot=0x48c1d0 boot_end=0x19df4da reserve=0x1a40000 allocator_gap=548",
        P + "memory-ready canaries=10",
        P + f"owner-telemetry phase=bound name=game_state kind=backing parent=- bound=0 cap=0 used=3000 high=3107656 failures=0 resets=0",
        P + f"profile-runtime row={row} map={map_name} profile=26 package-bytes=29531846 metadata-bytes=51124",
        P + f"profile-preflight result=1 map={map_name}",
        P + f"map-mount result=1 active=1 map={map_name} source=profile-runtime",
        P + f"production-ce-map-loaded result=1 map={map_name} scenario=1 tag-table=1 tag-count=2901 tag-bytes=6913928 bsp-bytes=1984512",
        P + "cache-owner phase=map-released name=tags current=0 peak=6913928 publications=1 failures=0 unmounts=1 resets=1",
        P + "cache-owner phase=map-released name=bsp current=0 peak=1984512 publications=1 failures=0 unmounts=1 resets=1 lease_failures=0 readers_drained=1 mount_rejections=0",
        P + f"production-ce-map-released result=1 map={map_name} mounted=0 tag-bytes=0 bsp-bytes=0",
    ]


def parse(lines, row=ROW, map_name="sidewinder"):
    return matrix.parse_guest_log(lines, row, map_name)


def test_complete_log_passes_and_records_values_and_peaks():
    parsed = parse(good_log())
    assert parsed["failing_checks"] == [], parsed["reasons"]
    assert parsed["values"]["tag_bytes"] == 6913928
    assert parsed["values"]["bsp_bytes"] == 1984512
    assert parsed["values"]["tag_count"] == 2901
    assert parsed["values"]["boot_end"] == 0x19DF4DA
    assert parsed["peaks"]["game_state_peak"] == 3107656
    assert parsed["peaks"]["tag_peak"] == 6913928
    assert parsed["peaks"]["bsp_peak"] == 1984512


def test_boot_end_at_or_above_reserve_fails():
    lines = good_log()
    lines[4] = lines[4].replace("boot_end=0x19df4da", "boot_end=0x1a40000")
    assert "boot_end_below_reserve" in parse(lines)["failing_checks"]


def test_wrong_reserve_and_canaries_fail():
    lines = good_log()
    lines[1] = lines[1].replace("reserve=0x1a40000", "reserve=0x1a00000")
    lines[5] = P + "memory-ready canaries=9"
    failing = parse(lines)["failing_checks"]
    assert "kernel_reservation" in failing and "memory_ready" in failing


def test_unqualified_or_other_row_fails():
    lines = good_log()
    lines[2] = lines[2].replace("qualified=1", "qualified=0")
    assert "partition_selected" in parse(lines)["failing_checks"]
    assert "partition_selected" in parse(good_log("other_row"))["failing_checks"]


def test_map_mount_requires_profile_runtime_source():
    lines = good_log()
    lines[9] = lines[9].replace("source=profile-runtime", "source=legacy")
    assert "map_mount" in parse(lines)["failing_checks"]


def test_missing_or_failed_load_and_release_fail():
    lines = good_log()
    assert "map_loaded" in parse(lines[:10] + lines[11:])["failing_checks"]
    assert "map_released" in parse(lines[:-1])["failing_checks"]
    lines[10] = lines[10].replace("result=1", "result=0")
    assert "map_loaded" in parse(lines)["failing_checks"]


def test_marker_order_is_checked():
    lines = good_log()
    lines[8], lines[9] = lines[9], lines[8]
    assert "marker_order" in parse(lines)["failing_checks"]


def test_nonzero_failure_counters_fail_on_each_line_kind():
    for index, old, new in ((3, "alloc_failures=0", "alloc_failures=1"),
                            (6, "failures=0", "failures=2"),
                            (11, "failures=0", "failures=1"),
                            (12, "mount_rejections=0", "mount_rejections=1")):
        lines = good_log()
        lines[index] = lines[index].replace(old, new)
        parsed = parse(lines)
        assert "failures_zero" in parsed["failing_checks"], index


def test_guest_fault_after_entry_fails_but_boot_noise_does_not():
    lines = good_log()
    assert "no_guest_faults" not in parse(["Address Error, addr=0x1ff [store]"] + lines)["failing_checks"]
    assert "no_guest_faults" in parse(lines + ["[err] late failure"])["failing_checks"]
    assert "no_guest_faults" in parse(lines + ["HALO_PS2_FAIL production-ce-map-loaded map=sidewinder"])["failing_checks"]


def test_row_discovery_requires_selected_package(tmp_path):
    source = tmp_path / "profiles.c"
    source.write_text('\t{ "a_row", { HCU_MEMORY_PROFILE_VERSION_1, 1, 2, 3, 4 } },\n'
                      '\t{ "b_row", { HCU_MEMORY_PROFILE_VERSION_1, 1, 2, 3, 4 } },\n')
    assert matrix.profile_rows(source) == ["a_row", "b_row"]
    root = tmp_path / "pkg"
    (root / "b_row").mkdir(parents=True)
    (root / "b_row/b_row.hcp").write_bytes(b"x")
    (root / "b_row/b_row.json").write_text("{}")
    assert matrix.default_rows(source, root) == ["b_row"]


def test_real_profile_table_lists_the_corpus_rows():
    rows = matrix.profile_rows()
    assert ROW in rows and "bots_sidewinder" in rows and len(rows) == len(set(rows))


def test_stage_plan_mounts_the_tree_at_the_header_pinned_path():
    root = matrix.EXTRA_PACKAGE_ROOTS["bots_sidewinder"]
    if not (root / "bots_sidewinder/bots_sidewinder.json").is_file():
        return
    plan = matrix.stage_plan("bots_sidewinder", root)
    manifest = json.loads((root / "bots_sidewinder/bots_sidewinder.json").read_text())
    assert plan["map"] == manifest["profile"]["map"]
    assert plan["guest_package_root"] == "build/m2-c2-resume-runtime-guest/bots-package-tree-v2"
    assert plan["stage_paths"] == []


def test_read_guest_lines_strips_timestamps(tmp_path):
    log = tmp_path / "log.txt"
    log.write_text("[ 12.5] HALO_PS2_LOCAL memory-ready canaries=10\n\nplain\n")
    assert matrix.read_guest_lines(log) == ["HALO_PS2_LOCAL memory-ready canaries=10", "plain"]


def test_guest_halt_line_after_entry_is_a_fault():
    lines = good_log() + [P + "halt 0x1aca50 file_create('z:saved') error 0x00000005"]
    assert "no_guest_faults" in parse(lines)["failing_checks"]


def test_ce_failure_lines_come_from_the_emulator_log(tmp_path):
    log = tmp_path / "emu.txt"
    log.write_text("[ 1.0] Unknown device 'd'\n[ 168.4] game_load() failed.\n[ 168.5] failed to find/create 'z:saved' directory\n")
    assert matrix.ce_failure_lines(log) == ["game_load() failed."]
    assert matrix.ce_failure_lines(tmp_path / "missing.txt") == []
