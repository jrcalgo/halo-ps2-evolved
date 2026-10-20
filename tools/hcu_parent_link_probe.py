"""Link HCU diagnostics both beside the viewer and under the parent game entry.

The HCU-gameplay ELF proves compile/link reachability only; it is not a guest,
map-load, performance, or final-acceptance test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from build_toolchain import ROOT, environment


def run(command: list[str], *, env: dict[str, str], cwd: Path = ROOT) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, text=True,
                            capture_output=True)
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result.stdout + result.stderr


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section_sizes(size_output: str) -> dict[str, int]:
    sections: dict[str, int] = {}
    for line in size_output.splitlines():
        match = re.match(r"^(\.[^\s]+)\s+(\d+)\s+", line.strip())
        if match:
            sections[match.group(1)] = int(match.group(2))
    return sections


def load_segment_sizes(program_headers: str) -> tuple[int, int]:
    """Return LOAD p_filesz and p_memsz, the latter including .bss."""
    match = re.search(
        r"^\s*LOAD\s+\S+\s+\S+\s+\S+\s+(0x[0-9a-fA-F]+)\s+"
        r"(0x[0-9a-fA-F]+)\s+", program_headers, re.M)
    if not match:
        raise RuntimeError("linked probe ELF has no LOAD segment")
    return int(match.group(1), 16), int(match.group(2), 16)


def load_segment_interval(program_headers: str) -> dict[str, int]:
    """Read the actual EE PT_LOAD range, including its NOBITS tail."""
    match = re.search(
        r"^\s*LOAD\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+"
        r"(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+"
        r"(0x[0-9a-fA-F]+)\s+", program_headers, re.M)
    if not match:
        raise RuntimeError("linked probe ELF has no LOAD segment")
    offset, virtual, physical, file_bytes, memory_bytes = (
        int(value, 16) for value in match.groups())
    if virtual != physical or file_bytes > memory_bytes:
        raise RuntimeError("unexpected EE PT_LOAD address or extent")
    return {"file_offset": offset, "start": physical,
            "file_end": physical + file_bytes,
            "memory_end": physical + memory_bytes,
            "file_bytes": file_bytes, "memory_bytes": memory_bytes}


def named_symbols(nm_output: str, names: set[str]) -> dict[str, int]:
    found = {}
    for line in nm_output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[-1] in names:
            found[fields[-1]] = int(fields[0], 16)
    if set(found) != names:
        raise RuntimeError("missing EE linker boundary symbols: " +
                           ", ".join(sorted(names - set(found))))
    return found


def physical_placement(segment: dict[str, int], symbols: dict[str, int],
                       layout_bytes: int = 24_117_248) -> dict[str, object]:
    """Necessary physical-capacity proof; actual malloc placement is a guest check."""
    text, bss, end = (symbols[name] for name in ("_ftext", "_fbss", "_end"))
    static_end = 0x00300000
    reserve_start = 0x01a00000
    bss_bytes = end - bss
    backing_bytes = layout_bytes - bss_bytes
    stack_symbol = symbols.get("_stack")
    stack_size = symbols.get("_stack_size")
    heap_size_symbol = symbols.get("_heap_size")
    # The allocator may place the pointer *after* _end. This lower bound
    # intentionally excludes malloc metadata and must not be called a pass.
    minimum_boot_end = end + backing_bytes + 15
    errors = []
    if text < 0x00100000 or segment["start"] != text:
        errors.append("ELF load begins outside the 1 MiB user-image base")
    if not (segment["file_end"] <= bss <= end == segment["memory_end"]):
        errors.append("PT_LOAD file/BSS extents disagree with linker symbols")
    if bss > static_end:
        errors.append("file-backed ELF exceeds elf_static physical boundary")
    if bss_bytes > 6_815_744:
        errors.append("ELF BSS exceeds resident_gameplay capacity")
    if backing_bytes < 0 or minimum_boot_end > reserve_start:
        errors.append("minimum boot backing overlaps untouched reserve")
    return {"load": segment, "symbols": symbols,
            "nobits": {"start": bss, "end": end, "bytes": bss_bytes},
            "elf_static_end": static_end, "reserve_start": reserve_start,
            "bss_charged_to_resident": bss_bytes,
            "boot_backing_bytes_excluding_alignment_slack": backing_bytes,
            "minimum_boot_end_excluding_allocator_metadata": minimum_boot_end,
            "minimum_headroom_before_reserve": reserve_start - minimum_boot_end,
            "crt_heap": {"base": end, "size_symbol": heap_size_symbol,
                         "size_is_runtime_dynamic": heap_size_symbol == 0xffffffff,
                         "actual_boot_pointer_guest_verified": False},
            "thread_stack": {"base_symbol": stack_symbol,
                             "size_bytes": stack_size,
                             "kernel_assigned": stack_symbol == 0xffffffff,
                             "physical_bounds_guest_verified": False},
            "system_kernel_reservation": {
                "budget_bytes": 1_572_864,
                "physical_intervals": [
                    {"start": 0x00000000, "end": 0x00100000,
                     "owner": "low EE kernel/communication reservation"},
                    {"start": 0x01f80000, "end": 0x02000000,
                     "owner": "high EE stack/kernel reservation"},
                ],
                "uncommitted_reserve_interval": {
                    "start": reserve_start, "end": 0x01f80000,
                    "bytes": 5_767_168},
                "source": "config/memory-budget.json",
                "layout_basis": "docs/memory.md:122-139",
                "physical_bounds_guest_verified_for_this_image": False},
            "necessary_conditions_pass": not errors, "errors": errors,
            "actual_boot_pointer_guest_verified": False,
            "remaining_physical_proof": [
                "observe the runtime malloc pointer and allocated extent in the guest",
                "run this exact image and verify ReferThreadStatus stack bounds",
                "confirm the configured system_kernel intervals on target hardware",
            ]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    profile_roots = {
        "host": "host:/", "optical": "cdrom:/", "opl-usb": "mass:/",
        "opl-smb": "smb0:/", "opl-hdd": "pfs0:/",
    }
    parser.add_argument("--asset-profile", choices=tuple(profile_roots), default="host",
                        help="deterministic filesystem profile compiled into HCU")
    parser.add_argument("--asset-root", choices=tuple(profile_roots.values()),
                        help="deprecated exact-root alias; prefer --asset-profile")
    args = parser.parse_args()
    if args.asset_root and args.asset_profile != "host":
        parser.error("use either --asset-root or --asset-profile, not both")
    asset_profile = (next(name for name, root in profile_roots.items()
                          if root == args.asset_root) if args.asset_root
                     else args.asset_profile)
    asset_root = profile_roots[asset_profile]
    build, prefix, env, _jobs = environment()
    output = build / "hcu-parent-link-probe"
    output.mkdir(parents=True, exist_ok=True)
    hcu_closure = build / "hcu-ps2-closure" / "all-no-bootstrap-memory"
    parent_output = output / "parent-sections-os"
    parent_output.mkdir(parents=True, exist_ok=True)
    asset_root_id = hashlib.sha256(asset_root.encode("utf-8")).hexdigest()[:12]
    gameplay_output = output / f"parent-hcu-gameplay-{asset_root_id}"
    gameplay_output.mkdir(parents=True, exist_ok=True)
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    linker = prefix / "ee/bin/mips64r5900el-ps2-elf-ld"
    nm = prefix / "ee/bin/mips64r5900el-ps2-elf-nm"
    size = prefix / "ee/bin/mips64r5900el-ps2-elf-size"
    readelf = prefix / "ee/bin/mips64r5900el-ps2-elf-readelf"
    linkfile = prefix / "ps2sdk/ee/startup/linkfile"

    run([sys.executable, str(ROOT / "tools/hcu_ps2_closure.py"), "--layer", "all",
         "--no-bootstrap-memory"], env=env)
    run([sys.executable, str(ROOT / "tools/hcu_ps2_link.py"),
         "--no-bootstrap-memory"], env=env)
    parent_vis = "src/world/visibility.c"
    run(["make", "-f", "tools/ee-world.mk", f"WORLD_OUTPUT={parent_output}",
         f"WORLD_VIS_SOURCE={parent_vis}", "WORLD_STREAM_DIAGNOSTIC=0",
         "WORLD_PLAY=0", "WORLD_HCU_LINK_PROBE=1", "WORLD_HCU_MEMORY_BRIDGE=1",
         "EE_OPTFLAGS=-Os", "all"], env=env)
    run(["make", "-f", "tools/ee-world.mk", f"WORLD_OUTPUT={gameplay_output}",
         f"WORLD_VIS_SOURCE={parent_vis}", "WORLD_STREAM_DIAGNOSTIC=0",
         "WORLD_PLAY=0", "WORLD_HCU_LINK_PROBE=1", "WORLD_HCU_GAMEPLAY=1",
         f"WORLD_HCU_ASSET_PROFILE={asset_profile}",
         "WORLD_HCU_TAG_CACHE_BYTES=2097152", "EE_OPTFLAGS=-Os", "parent-objects"], env=env)

    parent_objects = sorted(parent_output.rglob("*.o"))
    if not parent_objects:
        raise RuntimeError("parent build produced no object files")
    required_hcu = [
        "ps2_abi.o", "ps2_memory.o", "ps2_crt.o", "ps2_edge.o",
        "ps2_platform.o", "rooted.o",
    ]
    hcu_objects = [hcu_closure / name for name in required_hcu]
    missing = [str(path) for path in hcu_objects if not path.is_file()]
    if missing:
        raise RuntimeError("missing HCU joint-link inputs: " + ", ".join(missing))

    elf = output / "hcu-parent-link.elf"
    map_file = output / "hcu-parent-link.map"
    link_command = [
        str(compiler), "-mabi=n32", "-G0", "-T", str(linkfile),
        "-Wl,--gc-sections", "-Wl,--wrap,malloc", "-Wl,--wrap,free",
        "-Wl,--wrap,calloc", "-Wl,--wrap,realloc", "-Wl,-u,halo_shell_main",
        "-Wl,-u,hcu_memory_bind_parent_v2",
        "-Wl,-Map," + str(map_file), "-Wl,-zmax-page-size=128",
        "-L" + str(prefix / "ps2sdk/ee/lib"), "-o", str(elf),
        *[str(path) for path in parent_objects], *[str(path) for path in hcu_objects],
        "-ldraw", "-lgraph", "-lpacket2", "-ldma", "-ldebug", "-lpad",
        "-lmtap", "-lm",
    ]
    run(link_command, env=env)
    undefined = run([str(nm), "-u", str(elf)], env=env).splitlines()
    sizes = section_sizes(run([str(size), "-A", str(elf)], env=env))
    cpu_file_backed = sum(sizes.get(name, 0) for name in
                          (".text", ".rodata", ".data", ".sdata", ".ctors", ".dtors"))
    vu_program_bytes = sizes.get(".vutext", 0)
    program_headers = run([str(readelf), "-l", str(elf)], env=env)
    load_file_bytes, load_memory_bytes = load_segment_sizes(program_headers)
    static_cap = 2_097_152

    gameplay_objects = sorted(gameplay_output.rglob("*.o"))
    gameplay_entry = gameplay_output / "stream/hcu_main.o"
    input_bridge = gameplay_output / "stream/hcu_input_bridge.o"
    memory_bridge = gameplay_output / "stream/hcu_memory_bind.o"
    for path in (gameplay_entry, input_bridge, memory_bridge):
        if path not in gameplay_objects:
            raise RuntimeError(f"missing HCU gameplay machine input: {path}")
    gameplay_name = ("hcu-gameplay-machine" if asset_profile == "host"
                     else f"hcu-gameplay-machine-{asset_profile}")
    gameplay_elf = output / f"{gameplay_name}.elf"
    gameplay_map = output / f"{gameplay_name}.map"
    gameplay_command = [
        str(compiler), "-mabi=n32", "-G0", "-T", str(linkfile),
        "-Wl,--gc-sections", "-Wl,--wrap,malloc", "-Wl,--wrap,free",
        "-Wl,--wrap,calloc", "-Wl,--wrap,realloc", "-Wl,-u,halo_shell_main",
        "-Wl,-Map," + str(gameplay_map), "-Wl,-zmax-page-size=128",
        "-L" + str(prefix / "ps2sdk/ee/lib"), "-o", str(gameplay_elf),
        *[str(path) for path in gameplay_objects], *[str(path) for path in hcu_objects],
        "-ldraw", "-lgraph", "-lpacket2", "-ldma", "-ldebug", "-lpad",
        "-lmtap", "-lfileXio", "-lpatches", "-lm",
    ]
    run(gameplay_command, env=env)
    gameplay_undefined = run([str(nm), "-u", str(gameplay_elf)], env=env).splitlines()
    gameplay_sizes = section_sizes(run([str(size), "-A", str(gameplay_elf)], env=env))
    gameplay_program_headers = run([str(readelf), "-l", str(gameplay_elf)], env=env)
    gameplay_load_bytes, gameplay_load_memory_bytes = load_segment_sizes(
        gameplay_program_headers)
    gameplay_boundaries = named_symbols(
        run([str(nm), "-n", str(gameplay_elf)], env=env),
        {"_ftext", "_fbss", "_end", "_stack", "_stack_size", "_heap_size"})
    gameplay_physical = physical_placement(
        load_segment_interval(gameplay_program_headers), gameplay_boundaries)
    gameplay_memory_audit = output / f"{gameplay_name}-memory-audit.json"
    run([sys.executable, str(ROOT / "tools/hcu_ps2_memory_audit.py"),
         "--elf", str(gameplay_elf), "--map", str(gameplay_map),
         "--output", str(gameplay_memory_audit)], env=env)
    gameplay_ledger = json.loads(gameplay_memory_audit.read_text())
    report = {
        "status": "linked-diagnostic",
        "acceptance": False,
        "entrypoint": "parent main; HCU shell is force-retained but not called",
        "limits": [
            "No runtime CE tick, map load, arena binding, or render snapshot is exercised.",
            "The parent-to-HCU binder is compiled and retained, but is not called by the parent entry.",
            "The probe does not qualify the 20 MiB parent viewer malloc against budget v2.",
            "A linked ELF that exceeds elf_static is diagnostic only, never accepted.",
        ],
        "source_inputs": {
            "hcu_profile": str(hcu_closure.relative_to(ROOT)),
            "hcu_rooted_sha256": sha256(hcu_closure / "rooted.o"),
            "hcu_closure_report_sha256": sha256(hcu_closure / "result.json"),
            "hcu_object_sha256": {
                str(path.relative_to(ROOT)): sha256(path) for path in hcu_objects
            },
            "parent_object_count": len(parent_objects),
            "parent_object_sha256": {
                str(path.relative_to(ROOT)): sha256(path) for path in parent_objects
            },
            "parent_source_root": "submodules/halo-ps2/engine/src + src/world/visibility.c",
            "halo_ps2_head": run(["git", "-C", str(ROOT / "submodules/halo-ps2"),
                                   "rev-parse", "HEAD"], env=env).strip(),
            "halo_ce_universal_head": run(["git", "-C", str(ROOT / "submodules/halo-ce-universal"),
                                            "rev-parse", "HEAD"], env=env).strip(),
            "memory_map_sha256": sha256(ROOT / "config/hcu-ps2-memory-map.json"),
        },
        "elf": {
            "path": str(elf.relative_to(ROOT)),
            "sha256": sha256(elf),
            "sections": sizes,
            "cpu_sections_file_backed_bytes": cpu_file_backed,
            "vu_program_bytes": vu_program_bytes,
            "file_backed_bytes": load_file_bytes,
            "load_segment_file_bytes": load_file_bytes,
            "load_segment_memory_bytes_including_bss": load_memory_bytes,
            "elf_static_capacity": static_cap,
            "elf_static_overage": max(0, load_file_bytes - static_cap),
            "elf_static_memory_overage_including_bss": max(
                0, load_memory_bytes - static_cap),
            "bss_bytes": sizes.get(".bss", 0),
            "undefined_symbol_count": len(undefined),
            "undefined_symbols": undefined,
        },
        "hcu_gameplay_machine": {
            "status": "linked-diagnostic",
            "acceptance": False,
            "entrypoint": "parent hcu_main -> parent v2 arena binder -> HCU shell",
            "input_bridge": "HCU input_frame_begin polls four parent logical pads before CE snapshot",
            "map_service": "parent UI-only callback with HMAP preflight, CTAG/CRNG mount, and source verification",
            "asset_profile": asset_profile,
            "asset_root": asset_root,
            "tag_cache_bytes": 2097152,
            "tag_cache_limit_note": "UI/bootstrap diagnostic only; not a retail map capacity claim",
            "limits": [
                "No guest execution or M1 startup marker has been observed for this linked image.",
                "Only the UI/bootstrap map callback is implemented; no CBSP residency or ordinary retail-map transaction is qualified.",
                "The default cache is deliberately too small to claim ordinary retail map support.",
            ],
            "elf": {
                "path": str(gameplay_elf.relative_to(ROOT)),
                "sha256": sha256(gameplay_elf),
                "sections": gameplay_sizes,
                "load_segment_file_bytes": gameplay_load_bytes,
                "load_segment_memory_bytes_including_bss": gameplay_load_memory_bytes,
                "elf_static_capacity": static_cap,
                "elf_static_overage": max(0, gameplay_load_bytes - static_cap),
                "elf_static_memory_overage_including_bss": max(
                    0, gameplay_load_memory_bytes - static_cap),
                "bss_bytes": gameplay_sizes.get(".bss", 0),
                "undefined_symbol_count": len(gameplay_undefined),
                "undefined_symbols": gameplay_undefined,
            },
            "memory_ledger": {
                "report": str(gameplay_memory_audit.relative_to(ROOT)),
                "report_sha256": sha256(gameplay_memory_audit),
                "elf_sha256": sha256(gameplay_elf),
                "map": str(gameplay_map.relative_to(ROOT)),
                "map_sha256": sha256(gameplay_map),
                "memory_map_sha256": sha256(ROOT / "config/hcu-ps2-memory-map.json"),
                "candidate_allocated_bytes_by_region": gameplay_ledger[
                    "candidate_allocated_bytes_by_region"],
                "candidate_regions_over_capacity": gameplay_ledger[
                    "candidate_regions_over_capacity"],
                "unassigned_owners": gameplay_ledger["unassigned_owners"],
                "bss_bytes_by_input_object": gameplay_ledger[
                    "bss_bytes_by_input_object"],
                "warning": gameplay_ledger["warning"],
            },
            "physical_placement": gameplay_physical,
            "parent_object_count": len(gameplay_objects),
            "parent_object_sha256": {
                str(path.relative_to(ROOT)): sha256(path) for path in gameplay_objects
            },
        },
        "commands": {
            "hcu_compile": "python3 tools/hcu_ps2_closure.py --layer all --no-bootstrap-memory",
            "hcu_link": "python3 tools/hcu_ps2_link.py --no-bootstrap-memory",
            "parent_compile": "make -f tools/ee-world.mk WORLD_PLAY=0 WORLD_HCU_LINK_PROBE=1 WORLD_HCU_MEMORY_BRIDGE=1 EE_OPTFLAGS=-Os all",
            "hcu_gameplay_parent_compile": (
                "make -f tools/ee-world.mk WORLD_PLAY=0 WORLD_HCU_LINK_PROBE=1 "
                "WORLD_HCU_GAMEPLAY=1 WORLD_HCU_ASSET_PROFILE=" + asset_profile +
                " WORLD_HCU_TAG_CACHE_BYTES=2097152 EE_OPTFLAGS=-Os all"),
        },
    }
    report_path = output / ("result.json" if asset_profile == "host"
                            else f"result-{asset_profile}.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(report_path)
    print(f"ELF {elf}; LOAD file bytes {load_file_bytes}/{static_cap}; "
          f"undefined={len(undefined)}; acceptance=false")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"HCU-parent link probe failed: {error}")
