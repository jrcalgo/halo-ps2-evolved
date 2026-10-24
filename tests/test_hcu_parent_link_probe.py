import sys
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from hcu_parent_link_probe import (load_segment_interval, load_segment_intervals,
                                   load_segment_sizes,
                                   named_symbols, physical_placement,
                                   section_sizes)  # noqa: E402


def test_size_parser_collects_sections_without_treating_the_header_as_data():
    sample = """probe.elf :

section size addr
.text 1024 0x1000
.vutext 128 0x2000
.bss 4096 0x3000
Total 5248
"""
    assert section_sizes(sample) == {
        ".text": 1024,
        ".vutext": 128,
        ".bss": 4096,
    }


def test_load_segment_parser_distinguishes_file_bytes_from_bss_memory():
    sample = """Program Headers:
  Type           Offset   VirtAddr   PhysAddr   FileSiz MemSiz  Flg Align
  LOAD           0x000080 0x00100000 0x00100000 0x1f9404 0x3ee530 RWE 0x80
"""
    assert load_segment_sizes(sample) == (2069508, 4121904)
    assert load_segment_interval(sample) == {
        "file_offset": 128, "start": 0x100000,
        "file_end": 0x100000 + 2069508,
        "memory_end": 0x100000 + 4121904,
        "file_bytes": 2069508, "memory_bytes": 4121904,
    }
    assert load_segment_intervals(sample) == [load_segment_interval(sample)]


def test_physical_placement_rejects_overlapping_load_intervals():
    segments = [
        {"start": 0x100000, "file_end": 0x180000, "memory_end": 0x210000},
        {"start": 0x200000, "file_end": 0x280000, "memory_end": 0x300000},
    ]
    symbols = {"_ftext": 0x100000, "_fbss": 0x280000, "_end": 0x300000}
    report = physical_placement(segments, symbols)
    assert not report["necessary_conditions_pass"]
    assert "PT_LOAD physical intervals overlap" in report["errors"]


def test_physical_placement_rejects_file_overage_and_reserve_overlap():
    segment = {"start": 0x100000, "file_end": 0x340880,
               "memory_end": 0x4f6888}
    symbols = named_symbols(
        "00100000 T _ftext\n00340880 D _fbss\n004f6888 B _end\n",
        {"_ftext", "_fbss", "_end"})
    report = physical_placement(segment, symbols)
    assert report["necessary_conditions_pass"] is False
    assert any("elf_static" in error for error in report["errors"])
    assert report["actual_boot_pointer_guest_verified"] is False


def test_file_backed_fit_cannot_hide_boot_backing_reserve_overlap():
    segment = {"start": 0x100000, "file_end": 0x200000,
               "memory_end": 0x300000}
    symbols = {"_ftext": 0x100000, "_fbss": 0x200000,
               "_end": 0x300000, "_stack": 0xffffffff,
               "_stack_size": 131072, "_heap_size": 0xffffffff}
    report = physical_placement(segment, symbols, layout_bytes=25 * 1024 * 1024)
    assert segment["file_end"] <= report["elf_static_end"]
    assert not report["necessary_conditions_pass"]
    assert "minimum boot backing overlaps untouched reserve" in report["errors"]


def test_physical_placement_keeps_dynamic_crt_heap_and_kernel_stack_unresolved():
    segment = {"start": 0x100000, "file_end": 0x200000,
               "memory_end": 0x300000}
    symbols = {"_ftext": 0x100000, "_fbss": 0x200000, "_end": 0x300000,
               "_stack": 0xffffffff, "_stack_size": 128 * 1024,
               "_heap_size": 0xffffffff}
    report = physical_placement(segment, symbols)
    assert report["nobits"] == {"start": 0x200000, "end": 0x300000,
                                 "bytes": 0x100000}
    assert report["guarded_alignment_slack_bytes"] == 310
    assert report["boot_malloc_request_bytes"] == 24_117_248 - 0x100000 + 310
    assert report["crt_heap"]["size_is_runtime_dynamic"]
    assert report["thread_stack"]["kernel_assigned"]
    assert not report["thread_stack"]["physical_bounds_guest_verified"]
    assert report["system_kernel_reservation"]["budget_bytes"] == 1_572_864
    assert report["system_kernel_reservation"]["physical_intervals"] == [
        {"start": 0, "end": 0x100000,
         "owner": "low EE kernel/communication reservation"},
        {"start": 0x1f80000, "end": 0x2000000,
         "owner": "high EE stack/kernel reservation"},
    ]
    assert not report["system_kernel_reservation"][
        "physical_bounds_guest_verified_for_this_image"]


def test_joint_probe_retains_parent_memory_bridge_without_claiming_runtime_acceptance():
    result = json.loads((ROOT / "build/hcu-parent-link-probe/result.json").read_text())
    parent_sources = result["source_inputs"]["parent_object_sha256"]
    bridge = "build/hcu-parent-link-probe/parent-sections-os/stream/hcu_memory_bind.o"
    assert result["status"] == "linked-diagnostic"
    assert result["acceptance"] is False
    assert parent_sources[bridge]
    assert result["elf"]["undefined_symbol_count"] == 0
    assert result["elf"]["elf_static_overage"] > 0
    assert any("binder is compiled and retained" in limit
               for limit in result["limits"])
    assert result["entrypoint"].startswith("parent main;")


def test_joint_probe_links_optional_hcu_machine_entry_and_input_owner():
    result = json.loads((ROOT / "build/m2-c2-resume-budget-v3/result-partition-sidewinder_marine_shotgun_4p4bot.json").read_text())
    gameplay = result["hcu_gameplay_machine"]
    parent_objects = gameplay["parent_object_sha256"]
    assert gameplay["status"] == "linked-diagnostic"
    assert gameplay["acceptance"] is False
    assert gameplay["entrypoint"].startswith("parent hcu_main")
    assert "hcu_main.o" in " ".join(parent_objects)
    assert "hcu_input_bridge.o" in " ".join(parent_objects)
    assert "hcu_file_bridge.o" in " ".join(parent_objects)
    assert "hcu_map_service.o" in " ".join(parent_objects)
    assert "ctag_ps2_backend.o" in " ".join(parent_objects)
    assert gameplay["elf"]["undefined_symbol_count"] == 0
    assert gameplay["elf"]["elf_static_capacity"] == 2359296
    assert gameplay["elf"]["elf_static_overage"] == 0
    assert gameplay["elf"]["load_segment_file_bytes"] == 2250500
    assert gameplay["elf"]["bss_bytes"] > 0
    assert gameplay["elf"]["load_segment_memory_bytes_including_bss"] > gameplay["elf"]["elf_static_capacity"]
    assert gameplay["elf"]["elf_static_memory_overage_including_bss"] > 0
    ledger = gameplay["memory_ledger"]
    assert ledger["unassigned_owners"] == []
    assert ledger["candidate_regions_over_capacity"] == {}
    assert ledger["candidate_allocated_bytes_by_region"]["elf_static"] == 2250500
    assert ledger["candidate_allocated_bytes_by_region"]["resident_gameplay"] == 1811648
    assert "does not prove physical" in ledger["warning"]
    assert gameplay["partition_profile"] == "sidewinder_marine_shotgun_4p4bot"
    assert gameplay["tag_cache_bytes"] == 2 * 1024 * 1024
    assert gameplay["physical_placement"]["necessary_conditions_pass"] is True
    assert gameplay["physical_placement"]["actual_boot_pointer_guest_verified"] is False
    assert gameplay["physical_placement"]["thread_stack"]["kernel_assigned"]
    assert gameplay["physical_placement"]["system_kernel_reservation"][
        "physical_bounds_guest_verified_for_this_image"] is False


def test_optical_profile_keeps_separate_elf_and_report_from_host():
    host = json.loads((ROOT / "build/hcu-parent-link-probe/result.json").read_text())
    optical = json.loads((ROOT / "build/hcu-parent-link-probe/result-optical.json").read_text())
    host_game = host["hcu_gameplay_machine"]
    optical_game = optical["hcu_gameplay_machine"]
    assert host_game["asset_root"] == "host:/"
    assert optical_game["asset_root"] == "cdrom:/"
    assert host_game["elf"]["path"] != optical_game["elf"]["path"]
    assert host_game["elf"]["sha256"] != optical_game["elf"]["sha256"]


def test_combined_screen_width_is_parent_machine_owned():
    result = json.loads((ROOT / "build/hcu-parent-link-probe/result.json").read_text())
    elf = ROOT / result["hcu_gameplay_machine"]["elf"]["path"]
    nm = ROOT / "build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-nm"
    symbols = subprocess.check_output([str(nm), str(elf)], text=True)
    assert any(line.endswith(" T halo_screen_width") for line in symbols.splitlines())
    assert "long halo_screen_width(void) { return VIDEO_WIDTH; }" in (
        ROOT / "src/stream/hcu_main.c").read_text()
    assert "halo_screen_width" not in (
        ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/ps2_platform.c").read_text()


def test_nondefault_tag_cache_profile_is_validated_before_building():
    script = ROOT / "tools/hcu_parent_link_probe.py"
    for value in ("0", "4477121", "6291456", "-16"):
        result = subprocess.run(
            [sys.executable, str(script), "--tag-cache-bytes", value],
            cwd=ROOT, text=True, capture_output=True, check=False)
        assert result.returncode == 2
        assert "16-byte aligned" in result.stderr


def test_partition_profile_identifier_is_validated_before_building():
    script = ROOT / "tools/hcu_parent_link_probe.py"
    result = subprocess.run(
        [sys.executable, str(script), "--partition-profile", "Bad-Row"],
        cwd=ROOT, text=True, capture_output=True, check=False)
    assert result.returncode == 2
    assert "lowercase row identifier" in result.stderr


def test_partition_profile_option_is_forwarded_and_artifacts_are_scoped():
    script = (ROOT / "tools/hcu_parent_link_probe.py").read_text()
    assert 'parser.add_argument("--partition-profile"' in script
    assert 'f"-partition-{args.partition_profile}"' in script
    assert 'f"WORLD_HCU_PARTITION_PROFILE={args.partition_profile or \'\'}"' in script


def test_c3_sound_playback_provider_is_a_distinct_combined_link_input():
    manifest = json.loads((ROOT / "submodules/halo-ce-universal/port/ps2/port.json").read_text())
    assert "port/ps2/src/ps2_sound_playback.c" in manifest["port_sources"]
    linker = (ROOT / "tools/hcu_ps2_link.py").read_text()
    assert '"halo_ps2_sound_playback_note"' in linker
    assert '"halo_ps2_sound_playback_bind_sink"' in linker
    assert 'HCU / "port/ps2/src/ps2_sound_playback_bind.c"' in linker
    probe = (ROOT / "tools/hcu_parent_link_probe.py").read_text()
    assert '"ps2_sound_playback_bind.o"' in probe


def test_nondefault_tag_cache_profile_artifact_is_isolated_and_diagnostic():
    result = json.loads((ROOT /
        "build/hcu-parent-link-probe/result-tagcache-4477120.json").read_text())
    gameplay = result["hcu_gameplay_machine"]
    assert gameplay["tag_cache_bytes"] == 4_477_120
    assert gameplay["status"] == "linked-diagnostic"
    assert gameplay["acceptance"] is False
    assert gameplay["elf"]["path"].endswith(
        "hcu-gameplay-machine-tagcache-4477120.elf")
