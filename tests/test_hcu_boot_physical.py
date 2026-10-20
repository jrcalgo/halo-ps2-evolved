import sys
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from test_hcu_boot import (failed_guest_evidence, linked_physical_evidence,
                           physical_memory_evidence)  # noqa: E402


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
            "high=0x1f80000 high_bytes=524288 reserve=0x1a00000 "
            "reserve_bytes=5767168")


def test_guest_placement_marker_proves_nonoverlap():
    boot = 0x004FC900
    end = boot + sum(CAPS.values())
    log = ("HALO_PS2_LOCAL memory-physical elf_end=0x4f0288 "
           f"boot=0x{boot:x} boot_end=0x{end:x} reserve=0x1a00000 "
           "allocator_gap=284\n" + arena_markers(boot) + "\n" +
           kernel_markers())
    evidence = physical_memory_evidence(log)
    assert evidence["nonoverlapping"] is True
    assert evidence["headroom_bytes"] == 0x1a00000 - end
    assert evidence["allocator_gap_bytes"] == 284
    assert evidence["arenas_complete_and_valid"]
    assert len(evidence["arenas"]) == 9


def test_guest_placement_marker_rejects_reserve_overlap():
    log = ("HALO_PS2_LOCAL memory-physical elf_end=0x4f0288 "
           "boot=0x4f04a0 boot_end=0x1a01000 reserve=0x1a00000 "
           "allocator_gap=100\n" + arena_markers(0x4f04a0) + "\n" +
           kernel_markers())
    assert physical_memory_evidence(log)["nonoverlapping"] is False
    assert physical_memory_evidence("no guest marker") is None


def test_guest_placement_rejects_missing_or_overlapping_arena_records():
    boot = 0x004FC900
    end = boot + sum(CAPS.values())
    marker = (f"HALO_PS2_LOCAL memory-physical elf_end=0x4f0288 "
              f"boot=0x{boot:x} boot_end=0x{end:x} reserve=0x1a00000 "
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
           f"boot=0x{boot:x} boot_end=0x{end:x} reserve=0x1a00000 "
           "allocator_gap=284\n" + arena_markers(boot) + "\n" + kernel_markers() + "\n"
           "HALO_PS2_LOCAL m1-ui-map-request\n"
           "HALO_PS2_LOCAL halt missing-bsp\n")
    result = failed_guest_evidence(log, "HALO_PS2_LOCAL m2-ui-map-loaded")
    assert result["reached_game_initialize_done"]
    assert result["reached_m1_boundary"]
    assert result["failure_after_m1_boundary"]
    assert not result["reached_success_marker"]
    assert result["physical_memory"]["nonoverlapping"]


def test_guest_physical_intervals_are_bound_to_exact_linked_image(tmp_path):
    boot = 0x004FC900
    end = boot + sum(CAPS.values())
    elf_end = 0x004FC800
    log = (f"HALO_PS2_LOCAL memory-physical elf_end=0x{elf_end:x} "
           f"boot=0x{boot:x} boot_end=0x{end:x} reserve=0x1a00000 "
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
    assert linked_physical_evidence(physical, elf, probe)["passed"]
    corrupted = dict(physical, boot_end=end + 16)
    assert not linked_physical_evidence(corrupted, elf, probe)["passed"]
    elf.write_bytes(b"different image")
    assert not linked_physical_evidence(physical, elf, probe)["passed"]
