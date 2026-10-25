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
        P + "kernel-reservation low=0x0 low_bytes=1048576 high=0x1f80000 high_bytes=524288 reserve=0x1ae0000 reserve_bytes=4849664",
        P + f"partition-selected name={row} version=1 tag=6913936 bsp=1993744 texture=529472 residency=1048576 qualified=1",
        P + "arena name=resident_gameplay base=0x48c1e0 cap=5059028 used=4541812 high=4541812 alloc_failures=0 resets=0 releases=0 invalid_releases=0",
        P + "memory-physical elf_end=0x48bfac boot=0x48c1d0 boot_end=0x19df4da reserve=0x1ae0000 allocator_gap=548",
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
    lines[4] = lines[4].replace("boot_end=0x19df4da", "boot_end=0x1ae0000")
    assert "boot_end_below_reserve" in parse(lines)["failing_checks"]


def test_wrong_reserve_and_canaries_fail():
    lines = good_log()
    lines[1] = lines[1].replace("reserve=0x1ae0000", "reserve=0x1a00000")
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
    assert plan["guest_package_root"] == "build/m2-c2-residual-packages/bots-tree"
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


def test_ui_row_is_in_profile_table_and_resolves_to_its_package_tree():
    assert "ui" in matrix.profile_rows()
    root = matrix.package_root_for("ui")
    if root is None:  # build artifact absent on this checkout
        return
    plan = matrix.stage_plan("ui", root)
    assert plan["map"] == "ui" and plan["scenario"] == "levels\\ui\\ui"
    assert plan["guest_package_root"].endswith("m2-c2-residual-packages/ui-tree")


def test_ui_log_passes_with_ui_map_and_scenario():
    lines = good_log(row="ui", map_name="ui")
    assert parse(lines, row="ui", map_name="ui")["failing_checks"] == []


# ---- --cycles: per-cycle parsing and storage reuse ----

def cycle_lines(cycles, map_name="sidewinder", ticks=0, used=3107696, high=(6913928, 6913928, 6913928),
                bsp_high=1984512, resets_step=1):
    lines = []
    for c in range(1, cycles + 1):
        r = c * resets_step
        h = high[min(c - 1, len(high) - 1)]
        lines += [
            P + f"m2-cycle-boundary phase=map-loaded cycle={c}",
            P + f"production-ce-map-loaded result=1 map={map_name} scenario=1 tag-table=1 tag-count=2901 "
                f"tag-bytes=6913928 bsp-bytes=1984512 cycle={c} cycles={cycles}",
        ]
        if ticks:
            lines.append(P + f"production-ce-ticks result=1 map={map_name} cycle={c} ticks={ticks} local-players=1")
            lines.append(P + f"production-ce-tick-allocations map={map_name} cycle={c} ticks={ticks} coverage=wrapped-compat-malloc "
                "malloc=3/3/0 calloc=0/0/0 realloc=0/0/0 free=3/3/0 requested=48 "
                "current-start=0 current-end=0 peak=64 sdk-malloc=0 sdk-realloc=0 sdk-free=0 refused-unbound=0")
        lines += [
            P + f"m2-cycle-boundary phase=map-released cycle={c}",
            P + f"owner-telemetry phase=map-released partition=x backing_cap=1 backing_used=3382400 backing_high=8335214 backing_failures=0 backing_resets={r}",
            P + f"owner-telemetry phase=map-released name=game_state kind=backing parent=- bound=1 cap=1 used={used} high={used} failures=0 resets={r}",
            P + f"owner-telemetry phase=map-released name=tags kind=backing parent=- bound=1 cap=1 used=0 high={h} failures=0 resets={r}",
            P + f"owner-telemetry phase=map-released name=bsp kind=backing parent=- bound=1 cap=1 used=0 high={bsp_high} failures=0 resets={r}",
            P + f"cache-owner phase=map-released name=tags current=0 peak={h} publications={c} failures=0 unmounts={r} resets={r}",
            P + f"cache-owner phase=map-released name=bsp current=0 peak={bsp_high} publications={c} failures=0 unmounts={r} resets={r} lease_failures=0",
            P + f"{'production-ce-map-released' if c == cycles else 'production-ce-map-released-cycle'} result=1 map={map_name} mounted=0 tag-bytes=0 bsp-bytes=0 cycle={c} cycles={cycles}",
        ]
    return lines


def test_three_cycles_with_reused_storage_pass():
    parsed = matrix.parse_cycles(cycle_lines(3), "sidewinder", 3)
    assert parsed["failing_checks"] == [], parsed["reasons"]
    assert [c["cycle"] for c in parsed["per_cycle"]] == [1, 2, 3]
    assert parsed["checks"]["storage_reused_cycles_2_to_n"]


def test_peak_growth_in_cycle_three_is_flagged():
    parsed = matrix.parse_cycles(cycle_lines(3, high=(6913928, 6913928, 6913984)), "sidewinder", 3)
    assert "storage_reused_cycles_2_to_n" in parsed["failing_checks"]
    assert any("owner:tags:high" in r for r in parsed["reasons"])


def test_cycle_one_difference_is_reported_not_failed():
    parsed = matrix.parse_cycles(cycle_lines(3, high=(6000000, 6913928, 6913928)), "sidewinder", 3)
    assert parsed["failing_checks"] == []
    assert any("tags" in key for key in parsed["cycle1_vs_cycle2_differences"])


def test_missing_cycle_or_stale_cycle_count_fails():
    lines = cycle_lines(2)
    assert "cycle_3_loaded" in matrix.parse_cycles(lines, "sidewinder", 3)["failing_checks"]
    stale = matrix.parse_cycles(cycle_lines(1), "sidewinder", 2)
    assert "cycle_2_loaded" in stale["failing_checks"]


def test_resets_must_increment_each_cycle():
    parsed = matrix.parse_cycles(cycle_lines(3, resets_step=0), "sidewinder", 3)
    assert any(name.startswith("resets_increment_") for name in parsed["failing_checks"])


def test_ticks_required_when_requested():
    assert matrix.parse_cycles(cycle_lines(2, ticks=300), "sidewinder", 2, 300)["failing_checks"] == []
    missing = matrix.parse_cycles(cycle_lines(2), "sidewinder", 2, 300)
    assert "cycle_1_ticks" in missing["failing_checks"]
    assert "cycle_1_tick_allocations" in missing["failing_checks"]


def test_postload_allocator_phase_is_reported_and_rejects_failures_or_fallbacks():
    lines = cycle_lines(1, ticks=300)
    parsed = matrix.parse_cycles(lines, "sidewinder", 1, 300)
    trace = parsed["per_cycle"][0]["tick_allocations"]
    assert trace["malloc"] == {"attempts": 3, "successes": 3, "failures": 0}
    assert trace["peak"] == 64
    lines = [line.replace("malloc=3/3/0", "malloc=3/2/1") if "production-ce-tick-allocations" in line else line
             for line in lines]
    parsed = matrix.parse_cycles(lines, "sidewinder", 1, 300)
    assert "cycle_1_tick_allocations" in parsed["failing_checks"]


def test_postload_allocator_growth_after_warmup_is_reported():
    lines = cycle_lines(3, ticks=300)
    lines = [line.replace("peak=64", "peak=80") if "production-ce-tick-allocations" in line
             and "cycle=3" in line else line for line in lines]
    parsed = matrix.parse_cycles(lines, "sidewinder", 3, 300)
    assert "postload_allocator_reused_cycles_2_to_n" in parsed["failing_checks"]
    assert parsed["postload_allocator_cycles_2_to_n_drift"]


def test_failed_cycle_marker_fails():
    lines = [l.replace("result=1", "result=0", 1)
             if "production-ce-map-released" in l and " cycle=2 " in l else l for l in cycle_lines(3)]
    assert "cycle_2_released" in matrix.parse_cycles(lines, "sidewinder", 3)["failing_checks"]


# ---- --successor: guest foreign replacement, failed preflight, fail-then-retry ----

A_ROW, A_MAP = "boardingaction_mounted_gunner_4p4bot", "boardingaction"
B_ROW, B_MAP = "damnation_mounted_gunner_4p4bot", "damnation"
A_TAG, A_BSP, B_TAG, B_BSP = 4673095, 1343488, 4662634, 1320960


def _step(step, result, old_m, new_m, tag, bsp, scenario=1, bsp_ok=1, fault=0, tag_failures=0,
          bsp_failures=0, mount_rejections=0):
    return (P + f"production-ce-successor-step step={step} result={result} old={A_MAP} old-mounted={old_m} "
                f"new={B_MAP} new-mounted={new_m} tag-bytes={tag} bsp-bytes={bsp} tag-failures={tag_failures} bsp-failures={bsp_failures} "
                f"mount-rejections={mount_rejections} tag-unmounts=0 bsp-unmounts=0 tag-resets=0 bsp-resets=0 scenario={scenario} "
                f"bsp={bsp_ok} fault-count={fault}")


def _boundary(phase, cycle, resets, pubs, used_tags=0, *, backing_failures=0,
              tag_failures=0, tag_resets=None, bsp_resets=None, tag_publications=None,
              tag_unmounts=None, bsp_publications=None, bsp_unmounts=None,
              game_state_resets=None):
    tag_resets = resets if tag_resets is None else tag_resets
    bsp_resets = resets if bsp_resets is None else bsp_resets
    tag_publications = pubs if tag_publications is None else tag_publications
    bsp_publications = pubs if bsp_publications is None else bsp_publications
    tag_unmounts = resets if tag_unmounts is None else tag_unmounts
    bsp_unmounts = resets if bsp_unmounts is None else bsp_unmounts
    game_state_resets = resets if game_state_resets is None else game_state_resets
    return [
        P + f"m2-cycle-boundary phase={phase} cycle={cycle}",
        P + f"owner-telemetry phase={phase} partition={A_ROW} backing_cap=1 backing_used=3382400 backing_high=8335214 backing_failures={backing_failures} backing_resets={resets} nested_within_parent=1 renderer_drained=1",
        P + f"owner-telemetry phase={phase} name=game_state kind=backing parent=- bound=1 cap=1 used=3107696 high=3107696 failures=0 resets={game_state_resets}",
        P + f"owner-telemetry phase={phase} name=tags kind=backing parent=- bound=1 cap=1 used={used_tags} high={A_TAG} failures={tag_failures} resets={tag_resets}",
        P + f"owner-telemetry phase={phase} name=bsp kind=backing parent=- bound=1 cap=1 used=0 high={A_BSP} failures=0 resets={bsp_resets}",
        P + f"cache-owner phase={phase} name=tags current=0 peak={A_TAG} publications={tag_publications} failures={tag_failures} unmounts={tag_unmounts} resets={tag_resets}",
        P + f"cache-owner phase={phase} name=bsp current=0 peak={A_BSP} publications={bsp_publications} failures=0 unmounts={bsp_unmounts} resets={bsp_resets} lease_failures=0",
        P + f"arena phase={phase} name=streaming_map_owner cap=1048576 used=300000 high=300000 alloc_failures=0 resets=0 releases=0 invalid_releases=0",
    ]


def _common_head(mode, ticks=30):
    lines = good_log(A_ROW, A_MAP)[:11]
    lines[2] = P + f"partition-selected name={A_ROW} version=1 tag=4673104 bsp=1354160 texture=529472 residency=1048576 qualified=1"
    lines[10] = (P + f"production-ce-map-loaded result=1 map={A_MAP} scenario=1 tag-table=1 tag-count=2901 "
                     f"tag-bytes={A_TAG} bsp-bytes={A_BSP} cycle=1 cycles=1")
    lines += _boundary("map-loaded", 1, 0, 1, used_tags=A_TAG)
    lines.insert(11, P + f"successor-runtime row={A_ROW} successor-row={B_ROW} map={B_MAP} profile=22 package-bytes=20000000 "
                       f"metadata-bytes=41148 metadata-storage=41116 relocation-bytes=81240 stream-scratch=65536 "
                       f"residency-bytes=524288 residency-entries=8")
    lines.append(P + f"production-ce-successor-begin mode={mode} old={A_MAP} new={B_MAP} old-tag-bytes={A_TAG} "
                     f"old-bsp-bytes={A_BSP} ticks={ticks}")
    return lines


def _released(map_name):
    return P + f"production-ce-map-released result=1 map={map_name} mounted=0 tag-bytes=0 bsp-bytes=0 cycle=1 cycles=1"


def _ok_attempt(fault=0, stage_passes=2):
    stage = P + f"profile-preflight result=1 map={B_MAP} successor=1"
    return ([_step("preflight", 1, 1, 0, A_TAG, A_BSP, fault=fault), stage,
             _step("dispose", 1, 1, 0, A_TAG, A_BSP, fault=fault)]
            + _boundary("map-released", 1, 1, 1)
            + [_step("unload", 1, 0, 0, 0, 0, fault=fault), stage,
               P + f"map-mount result=1 active=1 map={B_MAP} source=profile-runtime"]
            + _boundary("map-loaded", 2, 1, 2, used_tags=B_TAG)
            + [_step("load", 1, 0, 1, 0, 0, fault=fault),
               _step("new-map", 1, 0, 1, B_TAG, B_BSP, fault=fault)])


def _loaded_and_usable(ticks=30):
    return [P + f"production-ce-successor-loaded result=1 old={A_MAP} old-mounted=0 new={B_MAP} scenario=1 tag-table=1 "
                f"tag-count=2800 tag-bytes={B_TAG} bsp-bytes={B_BSP}",
            P + f"production-ce-successor-usable result=1 old={A_MAP} ticks={ticks} local-players=1 new={B_MAP}"]


def replace_log():
    lines = _common_head(1) + _ok_attempt() + _loaded_and_usable()
    return lines + _boundary("map-released", 2, 2, 2) + [_released(B_MAP)]


def failed_preflight_log():
    lines = _common_head(2)
    lines += [P + "successor-fault injected kind=package-read offset=0 size=64",
              P + f"profile-preflight rejected reason=successor-package-gate map={B_MAP}",
              _step("preflight", 0, 1, 0, A_TAG, A_BSP, fault=1),
              _step("after-failed-preflight", 1, 1, 0, A_TAG, A_BSP, fault=1),
              P + f"production-ce-successor-usable result=1 old={A_MAP} ticks=30 local-players=1"]
    return lines + _boundary("map-released", 1, 1, 1) + [_released(A_MAP)]


def retry_log():
    successor_stage = P + f"profile-preflight result=1 map={B_MAP} successor=1"
    lines = _common_head(3)
    lines += [_step("preflight", 1, 1, 0, A_TAG, A_BSP), successor_stage,
              _step("dispose", 1, 1, 0, A_TAG, A_BSP)]
    lines += _boundary("map-released", 1, 1, 1)
    lines += [_step("unload", 1, 0, 0, 0, 0), successor_stage,
              P + f"map-mount result=1 active=1 map={B_MAP} source=profile-runtime"]
    lines += _boundary("map-loaded", 2, 2, 1)
    lines += [P + "successor-fault injected kind=hcp-ctag-chunk-read callbacks=1 prior-bytes=67264 offset=44000 size=96",
              P + "cache-owner phase=map-released name=tags current=0 peak=4673095 publications=1 failures=1 unmounts=2 resets=2",
              P + "successor-fault-cleanup game-load=0 delayed-error-consumed=1 mounted=0 scenario=0"]
    lines += _boundary("map-released", 2, 2, 1, backing_failures=1, tag_failures=1,
                       tag_resets=2, bsp_resets=1, tag_publications=1, tag_unmounts=2,
                       bsp_publications=1, bsp_unmounts=1)
    lines += [_step("load", 0, 0, 0, 0, 0, scenario=0, bsp_ok=0, fault=1, tag_failures=1),
              _step("after-failed-load", 1, 0, 0, 0, 0, scenario=0, bsp_ok=0, fault=1, tag_failures=1),
              P + f"production-ce-successor-retry old={A_MAP} new={B_MAP}",
              _step("preflight", 1, 0, 0, 0, 0, fault=1, tag_failures=1),
              P + f"profile-preflight result=1 map={B_MAP}",
              _step("dispose", 1, 0, 0, 0, 0, fault=1, tag_failures=1),
              _step("unload", 1, 0, 0, 0, 0, fault=1, tag_failures=1),
              P + f"map-mount result=1 active=1 map={B_MAP} source=profile-runtime"]
    lines += _boundary("map-loaded", 3, 5, 1, tag_failures=1, tag_resets=2, bsp_resets=1)
    lines += [_step("load", 1, 0, 1, 0, 0, fault=1, tag_failures=1),
              _step("new-map", 1, 0, 1, B_TAG, B_BSP, fault=1, tag_failures=1)]
    lines += _loaded_and_usable()
    lines += _boundary("map-released", 3, 8, 2, backing_failures=1, tag_failures=1,
                       tag_resets=3, bsp_resets=2, tag_publications=2, tag_unmounts=3,
                       bsp_publications=2, bsp_unmounts=2, game_state_resets=2)
    return lines + [_released(B_MAP)]


def parse_succ(lines, mode, ticks=30):
    return matrix.parse_successor_log(lines, A_ROW, A_MAP, B_ROW, B_MAP, mode, ticks)


def test_successor_replacement_log_passes_with_full_evidence():
    parsed = parse_succ(replace_log(), 1)
    assert parsed["failing_checks"] == [], parsed["reasons"]
    assert parsed["values"]["steps"] == ["preflight", "dispose", "unload", "load", "new-map"]
    assert parsed["values"]["successor_tag_margin"] == 4673104 - B_TAG
    assert parsed["values"]["successor_bsp_margin"] == 1354160 - B_BSP
    assert parsed["values"]["boundary_sequence"] == [("map-loaded", 1), ("map-released", 1), ("map-loaded", 2), ("map-released", 2)]
    assert parsed["values"]["renderer_drained_at_boundaries"] == ["1"] * 4


def test_successor_replacement_requires_old_tags_live_at_dispose_and_released_at_unload():
    lines = replace_log()
    bad = [l.replace("step=dispose result=1 old=boardingaction old-mounted=1", "step=dispose result=1 old=boardingaction old-mounted=0")
           for l in lines]
    assert "step_1_dispose" in parse_succ(bad, 1)["failing_checks"]
    bad = [l.replace("step=unload result=1 old=boardingaction old-mounted=0 new=damnation new-mounted=0 tag-bytes=0",
                     f"step=unload result=1 old=boardingaction old-mounted=0 new=damnation new-mounted=0 tag-bytes={A_TAG}")
           for l in lines]
    assert "step_2_unload" in parse_succ(bad, 1)["failing_checks"]


def test_successor_replacement_fails_when_old_map_survives_or_successor_exceeds_caps():
    lines = [l.replace("old-mounted=0 new=damnation scenario=1", "old-mounted=1 new=damnation scenario=1")
             for l in replace_log()]
    assert "successor_loaded" in parse_succ(lines, 1)["failing_checks"]
    big = [l.replace(f"tag-bytes={B_TAG} bsp-bytes={B_BSP}", f"tag-bytes=4673105 bsp-bytes={B_BSP}")
           if "successor-loaded" in l else l for l in replace_log()]
    assert "successor_fits_row_caps" in parse_succ(big, 1)["failing_checks"]


def test_successor_replacement_rejects_a_fault_or_missing_boundary():
    lines = replace_log() + [P + "successor-fault injected kind=package-read offset=0 size=64"]
    assert "fault_gate" in parse_succ(lines, 1)["failing_checks"]
    lines = [l for l in replace_log() if "phase=map-loaded cycle=2" not in l]
    assert "boundary_sequence" in parse_succ(lines, 1)["failing_checks"]


def test_successor_replacement_requires_unpublish_before_successor_mount():
    lines = replace_log()
    mount = next(i for i, l in enumerate(lines) if "map-mount result=1 active=1 map=damnation" in l)
    unload = next(i for i, l in enumerate(lines) if "step=unload" in l)
    lines[mount], lines[unload] = lines[unload], lines[mount]
    assert "unpublish_before_successor_load" in parse_succ(lines, 1)["failing_checks"]


def test_failed_preflight_keeps_old_map_and_ends_on_old_release():
    parsed = parse_succ(failed_preflight_log(), 2)
    assert parsed["failing_checks"] == [], parsed["reasons"]
    assert parsed["values"]["successor_package_gate_rejections"] == 1
    assert parsed["values"]["boundary_sequence"] == [("map-loaded", 1), ("map-released", 1)]


def test_failed_preflight_fails_if_old_owner_changed_or_released_early():
    lines = [l.replace(f"step=after-failed-preflight result=1 old=boardingaction old-mounted=1 new=damnation new-mounted=0 tag-bytes={A_TAG}",
                       "step=after-failed-preflight result=1 old=boardingaction old-mounted=1 new=damnation new-mounted=0 tag-bytes=0")
             for l in failed_preflight_log()]
    assert "step_1_after-failed-preflight" in parse_succ(lines, 2)["failing_checks"]
    early = failed_preflight_log()
    early[-1:-1] = _boundary("map-released", 1, 1, 1)
    assert "boundary_sequence" in parse_succ(early, 2)["failing_checks"]
    # a preflight that unexpectedly passes is not a failed-preflight run
    passed = [l.replace("step=preflight result=0", "step=preflight result=1") for l in failed_preflight_log()]
    assert parse_succ(passed, 2)["failing_checks"]


def test_failed_preflight_requires_usable_old_map_and_the_injected_fault():
    lines = [l for l in failed_preflight_log() if "successor-usable" not in l]
    assert "usable_after_sequence" in parse_succ(lines, 2)["failing_checks"]
    lines = [l for l in failed_preflight_log() if "successor-fault" not in l]
    assert "fault_gate" in parse_succ(lines, 2)["failing_checks"]
    lines = failed_preflight_log()
    lines = [l.replace("scenario=1 bsp=1", "scenario=0 bsp=1") if "after-failed-preflight" in l else l for l in lines]
    assert "old_map_scenario_and_bsp_kept" in parse_succ(lines, 2)["failing_checks"]


def test_successor_mode_must_match_the_guest_begin_line():
    assert "successor_begin" in parse_succ(replace_log(), 2)["failing_checks"]
    assert "successor_begin" in parse_succ(replace_log(), 1, ticks=60)["failing_checks"]


def test_successor_counters_are_zero_on_every_line():
    lines = [l.replace("tag-failures=0", "tag-failures=1") if "step=load" in l else l for l in replace_log()]
    assert "step_owner_counters_zero" in parse_succ(lines, 1)["failing_checks"]
    lines = [l.replace("alloc_failures=0", "alloc_failures=2") if "phase=map-loaded cycle" not in l and l.startswith(P + "arena phase=map-loaded")
             else l for l in replace_log()]
    assert "failures_zero" in parse_succ(lines, 1)["failing_checks"]


def test_successor_header_renames_the_row_image_without_touching_content():
    root = matrix.package_root_for(B_ROW)
    if root is None:
        return
    text = matrix.successor_header_text(B_ROW, root)
    assert "HCU_C2_IMAGE_" not in text and "hcu_c2_image_" not in text
    assert f'#define HCU_C2_SUCC_MAP "{B_MAP}"' in text
    assert f'#define HCU_C2_SUCC_ROW "{B_ROW}"' in text
    assert "HCU_C2_SUCC_METADATA[HCU_C2_SUCC_METADATA_BYTES]" in text


def test_successor_includes_carry_mode_ticks_and_image(tmp_path):
    root = matrix.package_root_for(B_ROW)
    if root is None:
        return
    include = matrix.write_successor_includes(tmp_path, B_ROW, root, 3, 45)
    mode = (include / "hcu_c2_successor.h").read_text()
    assert "HALO_PS2_C2_SUCCESSOR_MODE 3" in mode and "HALO_PS2_C2_SUCCESSOR_TICKS 45" in mode
    assert (include / "hcu_c2_succ_image.h").read_text().startswith("/* Generated by tools/c2_profile_image_header.py")


def test_successor_stage_paths_add_only_files_outside_the_selected_tree():
    root = matrix.package_root_for(B_ROW)
    if root is None:
        return
    plan = {"stage_paths": [], "guest_package_root": "build/m2-c2-r3-selected-packages"}
    assert matrix.successor_stage_paths(plan, {"stage_paths": []}, B_ROW, root) == []
    ui_root = matrix.package_root_for("ui")
    if ui_root is not None:
        paths = matrix.successor_stage_paths(plan, {"stage_paths": []}, "ui", ui_root)
        assert paths == ["build/m2-c2-residual-packages/ui-tree/pkg/ui/ui.hcp"]


def test_successor_cli_validation_and_output_root(monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise AssertionError("must not run")
    monkeypatch.setattr(matrix, "run_successor", refuse)
    monkeypatch.setattr(matrix, "run_row", refuse)
    for argv in (["--successor", B_ROW], ["--rows", f"{A_ROW},{B_ROW}", "--successor", B_ROW],
                 ["--rows", A_ROW, "--successor", B_ROW, "--cycles", "2"],
                 ["--rows", A_ROW, "--successor", "not_a_row"], ["--successor-fault", "load"],
                 ["--rows", A_ROW, "--successor", B_ROW, "--successor-ticks", "0"]):
        try:
            matrix.main(argv)
        except SystemExit as stop:
            assert stop.code == 2, argv
        else:
            raise AssertionError(argv)
    assert matrix.FOREIGN_ROOT == ROOT / "build/m2-c2-foreign"
    assert matrix.FOREIGN_ROOT != matrix.MATRIX


def test_successor_run_never_rewrites_the_matrix_summary(monkeypatch, tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text("untouched")
    monkeypatch.setattr(matrix, "MATRIX", tmp_path)
    called = []
    monkeypatch.setattr(matrix, "run_successor",
                        lambda *a, **k: called.append(a) or {"pass": True, "reasons": [], "case": "replace"})
    assert matrix.main(["--rows", A_ROW, "--successor", B_ROW]) == 0
    assert called == [(A_ROW, B_ROW, "none", matrix.SUCCESSOR_TICKS)]
    assert summary.read_text() == "untouched"


def test_successor_rejects_same_row_and_same_map(monkeypatch, tmp_path):
    monkeypatch.setattr(matrix, "FOREIGN_ROOT", tmp_path)
    result = matrix.run_successor(A_ROW, A_ROW)
    assert not result["pass"] and "must differ" in result["reasons"][0]
    result = matrix.run_successor(A_ROW, "boardingaction_marine_shotgun_4p4bot")
    assert not result["pass"] and "foreign successor needs a different map" in result["reasons"][0]
    assert (tmp_path / A_ROW / f"{A_ROW}-replace/result.json").is_file()


def test_released_map_parameter_accepts_a_successor_terminal_release():
    lines = good_log()
    lines[-1] = lines[-1].replace("map=sidewinder", "map=damnation")
    assert "map_released" in parse(lines)["failing_checks"]
    assert "map_released" not in matrix.parse_guest_log(lines, ROW, "sidewinder", released_map="damnation")["failing_checks"]


def test_fail_then_retry_log_passes_with_empty_state_between_attempts():
    parsed = parse_succ(retry_log(), 3)
    assert parsed["failing_checks"] == [], parsed["reasons"]
    assert parsed["values"]["steps"] == ["preflight", "dispose", "unload", "load", "after-failed-load",
                                         "preflight", "dispose", "unload", "load", "new-map"]
    assert parsed["values"]["successor_stage_passes"] == 2
    assert parsed["values"]["successor_mounts"] == 2
    assert parsed["values"]["successor_package_gate_rejections"] == 0
    assert parsed["values"]["boundary_sequence"] == [
        ("map-loaded", 1), ("map-released", 1), ("map-loaded", 2),
        ("map-released", 2), ("map-loaded", 3), ("map-released", 3)]
    assert parsed["values"]["expected_failure_counter_lines"]
    assert parsed["values"]["fault_lines"][0].find("prior-bytes=67264") >= 0


def test_fail_then_retry_fails_without_a_retry_or_with_residue_after_failure():
    lines = [l for l in retry_log() if "production-ce-successor-loaded" not in l]
    assert "successor_loaded" in parse_succ(lines, 3)["failing_checks"]
    lines = [l.replace("step=after-failed-load result=1 old=boardingaction old-mounted=0 new=damnation new-mounted=0 tag-bytes=0",
                       f"step=after-failed-load result=1 old=boardingaction old-mounted=0 new=damnation new-mounted=0 tag-bytes={B_TAG}")
             for l in retry_log()]
    assert "step_4_after-failed-load" in parse_succ(lines, 3)["failing_checks"]
    # a log that never failed the first load is not a fail-then-retry run
    lines = replace_log()
    assert "step_sequence" in parse_succ(lines, 3)["failing_checks"]


def test_fail_then_retry_requires_two_mounts_and_two_preflight_stages_with_no_gate_rejection():
    lines = retry_log() + [P + f"profile-preflight rejected reason=successor-package-gate map={B_MAP}"]
    assert "fault_gate" in parse_succ(lines, 3)["failing_checks"]
    parsed = parse_succ(retry_log(), 3)
    assert parsed["values"]["successor_package_gate_rejections"] == 0
    assert parsed["values"]["successor_stage_passes"] == 2
    assert parsed["values"]["successor_mounts"] == 2
    first = next(i for i, l in enumerate(retry_log()) if l.endswith("successor=1"))
    lines = retry_log()
    del lines[first]
    assert "successor_stages_and_mount" in parse_succ(lines, 3)["failing_checks"]


def test_fail_then_retry_requires_active_partial_ctag_fault_and_one_exact_failure():
    original = retry_log()
    for old, new in (
        ("callbacks=1", "callbacks=0"),
        ("prior-bytes=67264", "prior-bytes=65535"),
    ):
        changed = [line.replace(old, new) if "successor-fault injected" in line else line for line in original]
        assert "fault_gate" in parse_succ(changed, 3)["failing_checks"]

    extra = [line.replace("tag-failures=1", "tag-failures=2", 1)
             if "step=load result=0" in line else line for line in original]
    assert "step_owner_counters_expected_once" in parse_succ(extra, 3)["failing_checks"]
    before_fault = [line.replace("step=preflight result=1", "step=preflight result=1", 1)
                    .replace("tag-failures=0", "tag-failures=1", 1)
                    if "step=preflight result=1" in line else line for line in original]
    assert "step_owner_counters_expected_once" in parse_succ(before_fault, 3)["failing_checks"]
    bsp = [line.replace("bsp-failures=0", "bsp-failures=1", 1)
           if "step=load result=0" in line else line for line in original]
    assert "step_owner_counters_expected_once" in parse_succ(bsp, 3)["failing_checks"]


def test_fail_then_retry_requires_safe_cleanup_before_valid_retry():
    lines = [line for line in retry_log() if "successor-fault-cleanup" not in line]
    assert "fault_gate" in parse_succ(lines, 3)["failing_checks"]
    duplicate = retry_log()
    duplicate.append(next(line for line in duplicate if "successor-fault injected" in line))
    assert "fault_gate" in parse_succ(duplicate, 3)["failing_checks"]
    failed_retry = [line.replace("step=new-map result=1", "step=new-map result=0", 1)
                    if "step=new-map result=1" in line else line for line in retry_log()]
    assert "step_9_new-map" in parse_succ(failed_retry, 3)["failing_checks"]
