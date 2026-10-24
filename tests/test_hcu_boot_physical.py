import sys
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from test_hcu_boot import (failed_guest_evidence, guest_fault_after_marker,
                           find_link_probe_report, host_asset_manifest,
                           linked_physical_evidence,
                           physical_memory_evidence,
                           required_physical_evidence,
                           validate_m2_ui_lifecycle_log)  # noqa: E402


CAPS = {
    "resident_gameplay": 6815744 - 2114532,
    "current_bsp": 6291456,
    "texture_cache": 4194304,
    "dynamic_simulation": 2621440,
    "dma_commands": 1179648,
    "streaming": 1572864,
    "checkpoint": 524288,
    "audio": 524288,
    "frame_scratch": 393216,
}


def arena_markers(start=0x004FC900, omit=None):
    lines = []
    cursor = start
    for name, cap in CAPS.items():
        if name == omit:
            continue
        lines.append(
            f"HALO_PS2_LOCAL arena name={name} base=0x{cursor:x} "
            f"cap={cap} used=0 high=0")
        cursor += cap
    return "\n".join(lines)


def kernel_markers(stack=0x01FE0000):
    return (f"HALO_PS2_LOCAL kernel-stack base=0x{stack:x} size=131072 "
            f"end=0x{stack + 131072:x}\n"
            "HALO_PS2_LOCAL kernel-reservation low=0x0 low_bytes=1048576 "
            "high=0x1f80000 high_bytes=524288 reserve=0x1a60000 "
            "reserve_bytes=5373952")


def test_guest_placement_marker_proves_nonoverlap():
    boot = 0x004FC900
    end = boot + sum(CAPS.values())
    log = ("HALO_PS2_LOCAL memory-physical elf_end=0x4f0288 "
           f"boot=0x{boot:x} boot_end=0x{end:x} reserve=0x1a60000 "
           "allocator_gap=284\n" + arena_markers(boot) + "\n" +
           kernel_markers())
    evidence = physical_memory_evidence(log)
    assert evidence["nonoverlapping"] is True
    assert evidence["headroom_bytes"] == 0x1a60000 - end
    assert evidence["allocator_gap_bytes"] == 284
    assert evidence["arenas_complete_and_valid"]
    assert len(evidence["arenas"]) == 9


def test_guest_placement_marker_rejects_reserve_overlap():
    log = ("HALO_PS2_LOCAL memory-physical elf_end=0x4f0288 "
           "boot=0x4f04a0 boot_end=0x1a61000 reserve=0x1a60000 "
           "allocator_gap=100\n" + arena_markers(0x4f04a0) + "\n" +
           kernel_markers())
    assert physical_memory_evidence(log)["nonoverlapping"] is False
    assert physical_memory_evidence("no guest marker") is None


def test_guest_placement_rejects_missing_or_overlapping_arena_records():
    boot = 0x004FC900
    end = boot + sum(CAPS.values())
    marker = (f"HALO_PS2_LOCAL memory-physical elf_end=0x4f0288 "
              f"boot=0x{boot:x} boot_end=0x{end:x} reserve=0x1a60000 "
              "allocator_gap=284\n")
    suffix = "\n" + kernel_markers()
    assert not physical_memory_evidence(
        marker + arena_markers(boot, omit="audio") + suffix)["nonoverlapping"]
    overlap = arena_markers(boot).replace(
        f"name=current_bsp base=0x{boot + CAPS['resident_gameplay']:x}",
        f"name=current_bsp base=0x{boot:x}")
    assert not physical_memory_evidence(marker + overlap + suffix)["nonoverlapping"]
    assert not physical_memory_evidence(
        marker + arena_markers(boot) + "\n" + kernel_markers(0x01F70000)
    )["kernel_stack_in_reserved_interval"]


def test_later_guest_halt_retains_m1_boundary_and_physical_evidence():
    boot = 0x004FC900
    end = boot + sum(CAPS.values())
    log = ("HALO_PS2_LOCAL game-initialize-done\n"
           f"HALO_PS2_LOCAL memory-physical elf_end=0x4f0288 "
           f"boot=0x{boot:x} boot_end=0x{end:x} reserve=0x1a60000 "
           "allocator_gap=284\n" + arena_markers(boot) + "\n" + kernel_markers() + "\n"
           "HALO_PS2_LOCAL m1-ui-map-request\n"
           "HALO_PS2_LOCAL halt missing-bsp\n")
    result = failed_guest_evidence(log, "HALO_PS2_LOCAL m2-ui-map-loaded")
    assert result["reached_game_initialize_done"]
    assert result["reached_m1_boundary"]
    assert result["failure_after_m1_boundary"]
    assert not result["reached_success_marker"]
    assert result["physical_memory"]["nonoverlapping"]


def test_guest_fault_detector_ignores_boot_noise_but_finds_post_marker_ee_faults():
    marker = "HALO_PS2_LOCAL m2-ui-map-loaded"
    log = ("Address Error, addr=0x1ff [store]\n" + marker + "\n"
           "Address Error, addr=0x7d2dc6 [load]")
    assert "0x7d2dc6" in guest_fault_after_marker(log, marker)


def test_guest_fault_detector_rejects_post_marker_branch_delay():
    marker = "HALO_PS2_LOCAL m2-ui-map-loaded"
    assert guest_fault_after_marker(
        marker + "\nEE: branch delay!!", marker) == "EE: branch delay!!"


def test_guest_fault_detector_requires_stage_marker():
    assert guest_fault_after_marker(
        "Address Error, addr=0x1ff [store]", "HALO_PS2_LOCAL m2-ui-map-loaded") is None


def test_host_asset_manifest_hashes_map_and_generated_hp2(tmp_path):
    root = tmp_path / "host-root"
    (root / "maps").mkdir(parents=True)
    (root / "maps/ui.map").write_bytes(b"map bytes")
    (root / "maps/ui.hp2").write_bytes(b"generated hp2")
    manifest = host_asset_manifest(root / "hcu.elf")
    assets = {row["relative_path"]: row for row in manifest["assets"]}
    assert manifest["host_root"] == str(root)
    assert assets["maps/ui.map"]["sha256"] == hashlib.sha256(b"map bytes").hexdigest()
    assert assets["maps/ui.hp2"]["sha256"] == hashlib.sha256(b"generated hp2").hexdigest()


def test_guest_physical_intervals_are_bound_to_exact_linked_image(tmp_path):
    boot = 0x004FC900
    end = boot + sum(CAPS.values())
    elf_end = 0x004FC800
    log = (f"HALO_PS2_LOCAL memory-physical elf_end=0x{elf_end:x} "
           f"boot=0x{boot:x} boot_end=0x{end:x} reserve=0x1a60000 "
           f"allocator_gap={boot - elf_end}\n" + arena_markers(boot) + "\n" +
           kernel_markers() + "\nHALO_PS2_LOCAL memory-ready canaries=10\n")
    physical = physical_memory_evidence(log)
    elf = tmp_path / "machine.elf"
    elf.write_bytes(b"synthetic ELF identity")
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps({"hcu_gameplay_machine": {
        "elf": {"sha256": hashlib.sha256(elf.read_bytes()).hexdigest()},
        "physical_placement": {
            "nobits": {"bytes": 2114532},
            "symbols": {"_end": elf_end},
            "boot_malloc_request_bytes": end - boot,
            "necessary_conditions_pass": True,
            "load_intervals": [{"memory_end": elf_end}],
        },
        "memory_ledger": {"map_sha256": "fixture"},
    }}))
    qualified, linked = required_physical_evidence(log, elf, True, probe)
    assert qualified == physical
    assert linked["passed"]
    assert required_physical_evidence("no placement markers", elf, False) == (None, None)
    try:
        required_physical_evidence("no placement markers", elf, True)
    except RuntimeError as error:
        assert "missing or invalid" in str(error)
    else:
        raise AssertionError("required physical placement accepted a markerless log")
    corrupted = dict(physical, boot_end=end + 16)
    assert not linked_physical_evidence(corrupted, elf, probe)["passed"]
    elf.write_bytes(b"different image")
    assert not linked_physical_evidence(physical, elf, probe)["passed"]


def test_custom_layout_probe_is_selected_by_exact_elf_hash(tmp_path):
    elf = tmp_path / "layout.elf"
    elf.write_bytes(b"layout-specific ELF")
    probe_dir = tmp_path / "probes"
    probe_dir.mkdir()
    (probe_dir / "result.json").write_text(json.dumps({
        "hcu_gameplay_machine": {"elf": {"sha256": "not-the-requested-elf"}}
    }))
    expected = probe_dir / "result-tagcache-4477120.json"
    expected.write_text(json.dumps({
        "hcu_gameplay_machine": {
            "elf": {"sha256": hashlib.sha256(elf.read_bytes()).hexdigest()}
        }
    }))
    assert find_link_probe_report(elf, probe_dir) == expected
    assert find_link_probe_report(elf, tmp_path / "missing") is None


def test_m2_ui_lifecycle_validator_requires_two_clean_owner_cycles():
    log = """HALO_PS2_LOCAL m2-ui-owner cycle=1 phase=ce-unpublished-owner-released base=0x81e200 cap=1572864 used=0 high=1550572 mount=0 source=0 descriptor=-1 preflight=0 reload=1 staged=ui
HALO_PS2_LOCAL m2-ui-lifecycle-ce-unpublished cycle=1 scenario=0x0 bsp=0x0 collision=0x0 bsp3d=0x0 game_globals=0x0 scenario_index=-1 bsp_index=-1 scenario_bsp_index=-1 tags=0x0 tag_count=0 cache=1
HALO_PS2_LOCAL m2-ui-lifecycle-owner-released cycle=1 scenario=0x0 bsp=0x0 collision=0x0 bsp3d=0x0 game_globals=0x0 scenario_index=-1 bsp_index=-1 scenario_bsp_index=-1 tags=0x0 tag_count=0 cache=0
HALO_PS2_LOCAL m2-ui-owner cycle=0 phase=before-preflight-fault base=0x81e200 cap=1572864 used=1550444 high=1550572 mount=1 source=1 descriptor=6 preflight=0 reload=0 staged=-
HALO_PS2_LOCAL m2-ui-lifecycle-injected preflight-before-unload
HALO_PS2_LOCAL m2-ui-owner cycle=0 phase=after-preflight-fault base=0x81e200 cap=1572864 used=1550444 high=1550572 mount=1 source=1 descriptor=6 preflight=0 reload=0 staged=-
HALO_PS2_LOCAL m2-ui-lifecycle-preunload-failure-preserved
HALO_PS2_LOCAL m2-ui-lifecycle-injected preflight-after-unload
HALO_PS2_LOCAL m2-ui-lifecycle-postunload-ce-preflight-refused
HALO_PS2_LOCAL m2-ui-owner cycle=0 phase=after-postunload-fault base=0x81e200 cap=1572864 used=0 high=1550572 mount=0 source=0 descriptor=-1 preflight=0 reload=0 staged=-
HALO_PS2_LOCAL m2-ui-lifecycle-postunload-failure-safe-empty
HALO_PS2_LOCAL m2-ui-owner cycle=0 phase=postunload-retry-loaded base=0x81e200 cap=1572864 used=1550444 high=1550572 mount=1 source=1 descriptor=7 preflight=0 reload=0 staged=-
HALO_PS2_LOCAL m2-ui-lifecycle-postunload-retry-complete
HALO_PS2_LOCAL m2-ui-owner cycle=1 phase=cycle-loaded base=0x81e200 cap=1572864 used=1550444 high=1550572 mount=1 source=1 descriptor=7 preflight=0 reload=0 staged=-
HALO_PS2_LOCAL m2-ui-lifecycle-cycle-complete cycle=1
HALO_PS2_LOCAL m2-ui-owner cycle=2 phase=ce-unpublished-owner-released base=0x81e200 cap=1572864 used=0 high=1550572 mount=0 source=0 descriptor=-1 preflight=0 reload=1 staged=ui
HALO_PS2_LOCAL m2-ui-lifecycle-ce-unpublished cycle=2 scenario=0x0 bsp=0x0 collision=0x0 bsp3d=0x0 game_globals=0x0 scenario_index=-1 bsp_index=-1 scenario_bsp_index=-1 tags=0x0 tag_count=0 cache=1
HALO_PS2_LOCAL m2-ui-lifecycle-owner-released cycle=2 scenario=0x0 bsp=0x0 collision=0x0 bsp3d=0x0 game_globals=0x0 scenario_index=-1 bsp_index=-1 scenario_bsp_index=-1 tags=0x0 tag_count=0 cache=0
HALO_PS2_LOCAL m2-ui-owner cycle=2 phase=cycle-loaded base=0x81e200 cap=1572864 used=1550444 high=1550572 mount=1 source=1 descriptor=8 preflight=0 reload=0 staged=-
HALO_PS2_LOCAL m2-ui-lifecycle-cycle-complete cycle=2
HALO_PS2_LOCAL m2-ui-lifecycle-complete cycles=2
"""
    result = validate_m2_ui_lifecycle_log(log)
    assert result["cycles"] == ["1", "2"]
    assert result["ce_globals_null"] == ["1", "2"]
    assert len(result["owner_release"]) == 2
    assert len(result["owner_loaded"]) == 2
    with_failure = log.replace(
        "HALO_PS2_LOCAL m2-ui-lifecycle-complete cycles=2",
        "HALO_PS2_LOCAL m2-ui-lifecycle-failed reason=negative-control\n"
        "HALO_PS2_LOCAL m2-ui-lifecycle-complete cycles=2")
    try:
        validate_m2_ui_lifecycle_log(with_failure)
    except RuntimeError as error:
        assert "failure marker" in str(error)
    else:
        raise AssertionError("lifecycle failure marker was accepted")
