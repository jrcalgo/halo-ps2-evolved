"""Link HCU diagnostics both beside the viewer and under the parent game entry.

The HCU-gameplay ELF proves compile/link reachability only; it is not a guest,
map-load, performance, or final-acceptance test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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


def load_segment_intervals(program_headers: str) -> list[dict[str, int]]:
    """Read every EE PT_LOAD range, including each NOBITS tail."""
    pattern = re.compile(
        r"^\s*LOAD\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+"
        r"(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+"
        r"(0x[0-9a-fA-F]+)\s+", re.M)
    matches = list(pattern.finditer(program_headers))
    if not matches:
        raise RuntimeError("linked probe ELF has no LOAD segment")
    intervals = []
    for match in matches:
        offset, virtual, physical, file_bytes, memory_bytes = (
            int(value, 16) for value in match.groups())
        if virtual != physical or file_bytes > memory_bytes:
            raise RuntimeError("unexpected EE PT_LOAD address or extent")
        intervals.append({"file_offset": offset, "start": physical,
                          "file_end": physical + file_bytes,
                          "memory_end": physical + memory_bytes,
                          "file_bytes": file_bytes, "memory_bytes": memory_bytes})
    return sorted(intervals, key=lambda item: item["start"])


def load_segment_interval(program_headers: str) -> dict[str, int]:
    """Compatibility view of the first EE PT_LOAD interval."""
    return load_segment_intervals(program_headers)[0]


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


def _budget_region_bytes(name: str) -> int:
    budget = json.loads((Path(__file__).resolve().parents[1] / "config/memory-budget.json").read_text())
    return next(r["bytes"] for r in budget["regions"] if r["name"] == name)


LOW_KERNEL_END = 0x00100000
HIGH_KERNEL_START = 0x01f80000
MEM_LAYOUT_V2_BYTES = 24_117_248  # submodules/halo-ps2/engine/src/core/mem.h


def physical_placement(segment: dict[str, int] | list[dict[str, int]], symbols: dict[str, int],
                       layout_bytes: int = 24_117_248) -> dict[str, object]:
    """Necessary physical-capacity proof; actual malloc placement is a guest check."""
    segments = segment if isinstance(segment, list) else [segment]
    first, last = segments[0], segments[-1]
    text, bss, end = (symbols[name] for name in ("_ftext", "_fbss", "_end"))
    static_end = LOW_KERNEL_END + _budget_region_bytes("elf_static")
    reserve_start = static_end + MEM_LAYOUT_V2_BYTES
    bss_bytes = end - bss
    backing_bytes = layout_bytes - bss_bytes
    stack_symbol = symbols.get("_stack")
    stack_size = symbols.get("_stack_size")
    heap_size_symbol = symbols.get("_heap_size")
    guarded_slack = (9 + 1) * (16 + 15)
    boot_request_bytes = backing_bytes + guarded_slack
    # The allocator may place the pointer *after* _end. This lower bound
    # intentionally excludes malloc metadata and must not be called a pass.
    minimum_boot_end = end + boot_request_bytes
    errors = []
    if text < 0x00100000 or first["start"] != text:
        errors.append("ELF load begins outside the 1 MiB user-image base")
    if not (last["file_end"] <= bss <= end == last["memory_end"]):
        errors.append("PT_LOAD file/BSS extents disagree with linker symbols")
    for left, right in zip(segments, segments[1:]):
        if left["memory_end"] > right["start"]:
            errors.append("PT_LOAD physical intervals overlap")
    if any(row["start"] < 0x00100000 or row["memory_end"] > 0x02000000
           for row in segments):
        errors.append("PT_LOAD interval escapes the EE user image range")
    if bss > static_end:
        errors.append("file-backed ELF exceeds elf_static physical boundary")
    if bss_bytes > _budget_region_bytes("resident_gameplay"):
        errors.append("ELF BSS exceeds resident_gameplay capacity")
    if backing_bytes < 0 or minimum_boot_end > reserve_start:
        errors.append("minimum boot backing overlaps untouched reserve")
    return {"load": first, "load_intervals": segments, "symbols": symbols,
            "nobits": {"start": bss, "end": end, "bytes": bss_bytes},
            "elf_static_end": static_end, "reserve_start": reserve_start,
            "bss_charged_to_resident": bss_bytes,
            "boot_backing_bytes_excluding_alignment_slack": backing_bytes,
            "guarded_alignment_slack_bytes": guarded_slack,
            "boot_malloc_request_bytes": boot_request_bytes,
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
                "budget_bytes": _budget_region_bytes("system_kernel"),
                "physical_intervals": [
                    {"start": 0x00000000, "end": 0x00100000,
                     "owner": "low EE kernel/communication reservation"},
                    {"start": 0x01f80000, "end": 0x02000000,
                     "owner": "high EE stack/kernel reservation"},
                ],
                "uncommitted_reserve_interval": {
                    "start": reserve_start, "end": HIGH_KERNEL_START,
                    "bytes": HIGH_KERNEL_START - reserve_start},
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
    parser.add_argument("--m2-ui-lifecycle-test", action="store_true",
                        help="build a distinct opt-in CE UI lifecycle guest ELF")
    parser.add_argument("--step8-mp-capacity-diagnostic", action="store_true",
                        help="build the isolated target-sized Sidewinder load/query ELF")
    parser.add_argument("--step8-mp-workload-only", action="store_true",
                        help="skip the 13 query maps and run only the CE local-player workload")
    parser.add_argument("--step8-mp-workload-players", type=int, choices=(2, 4), default=2,
                        help="local players for workload-only diagnostic (2 or CE maximum 4)")
    parser.add_argument("--m2-animation-trace", action="store_true",
                        help="build an opt-in guest ELF with budgeted CE animation tracing")
    parser.add_argument("--m3-render-clear-test", action="store_true",
                        help="build an isolated HCU ELF that presents a known GS clear")
    parser.add_argument("--tag-cache-bytes", type=int, default=2097152,
                        help=("boot-fixed diagnostic tag-cache span in bytes; "
                              "must be 16-byte aligned and smaller than current_bsp"))
    parser.add_argument("--partition-profile",
                        help="compile a generated C2 partition image row into the HCU main ELF")
    parser.add_argument("--profile-package-root", type=Path,
                        default=ROOT / "build/m2-c2-r3-selected-packages/pkg",
                        help="package row directory passed to the generated image-header builder")
    parser.add_argument("--headless-runtime-guest", action="store_true",
                        help="run CE's selected row scenario/BSP load and release before any render frame")
    parser.add_argument("--output-dir", type=Path,
                        help=("write every probe output under this directory (inside the build root) "
                              "instead of build/hcu-parent-link-probe; the shared HCU closure "
                              "directory is still rewritten, so hold the link lock around the run"))
    args = parser.parse_args()
    if args.m2_ui_lifecycle_test and args.m3_render_clear_test:
        parser.error("the M2 lifecycle and M3 render-clear diagnostics are separate ELF profiles")
    if args.m2_animation_trace and (args.m2_ui_lifecycle_test or args.m3_render_clear_test or args.step8_mp_capacity_diagnostic):
        parser.error("M2 animation trace, lifecycle, and render-clear profiles require separate ELFs")
    if args.step8_mp_capacity_diagnostic and args.m3_render_clear_test:
        parser.error("the Step 8 capacity and M3 render-clear diagnostics are separate ELF profiles")
    if args.step8_mp_workload_only and not args.step8_mp_capacity_diagnostic:
        parser.error("--step8-mp-workload-only requires --step8-mp-capacity-diagnostic")
    if not args.step8_mp_workload_only and args.step8_mp_workload_players != 2:
        parser.error("--step8-mp-workload-players requires --step8-mp-workload-only")
    if args.step8_mp_capacity_diagnostic:
        args.tag_cache_bytes = 4477120
    if args.asset_root and args.asset_profile != "host":
        parser.error("use either --asset-root or --asset-profile, not both")
    if args.partition_profile and not re.fullmatch(r"[a-z0-9_]+", args.partition_profile):
        parser.error("--partition-profile must be a lowercase row identifier")
    if args.headless_runtime_guest and not args.partition_profile:
        parser.error("--headless-runtime-guest requires a selected --partition-profile row")
    if args.headless_runtime_guest and (args.asset_profile != "host" or args.asset_root):
        parser.error("--headless-runtime-guest requires the host asset profile")
    if (args.tag_cache_bytes <= 0 or args.tag_cache_bytes >= 6291456 or
            args.tag_cache_bytes % 16 != 0):
        parser.error("--tag-cache-bytes must be positive, 16-byte aligned, and below 6291456")
    asset_profile = (next(name for name, root in profile_roots.items()
                          if root == args.asset_root) if args.asset_root
                     else args.asset_profile)
    asset_root = profile_roots[asset_profile]
    # The R5900 combined image is constrained by the configured elf_static window.
    # Use GCC's size-first mode for this probe, while retaining the HCU's
    # source-profile flags and verifying the exact image in PCSX2 afterward.
    optimization = "-Oz"
    build, prefix, env, _jobs = environment()
    output = build / "hcu-parent-link-probe"
    if args.output_dir:
        output = (args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir).resolve()
        if build not in output.parents:
            parser.error(f"--output-dir must be inside the build root {build}")
    output.mkdir(parents=True, exist_ok=True)
    profile_suffix = (f"-step8-mp-workload-{args.step8_mp_workload_players}p" if args.step8_mp_workload_only else
                      "-step8-mp-capacity" if args.step8_mp_capacity_diagnostic else
                      "-m2-ui-lifecycle" if args.m2_ui_lifecycle_test else
                      "-m2-animation-trace" if args.m2_animation_trace else
                      "-m3-render-clear" if args.m3_render_clear_test else "")
    if args.tag_cache_bytes != 2097152:
        profile_suffix += f"-tagcache-{args.tag_cache_bytes}"
    if args.partition_profile:
        profile_suffix += f"-partition-{args.partition_profile}"
    if args.headless_runtime_guest:
        profile_suffix += "-headless-runtime-guest"
    closure_suffix = (f"-step8-mp-workload-{args.step8_mp_workload_players}p" if args.step8_mp_workload_only else
                      "-step8-mp-capacity" if args.step8_mp_capacity_diagnostic else
                      "-m2-ui-lifecycle" if args.m2_ui_lifecycle_test else
                      "-m2-animation-trace" if args.m2_animation_trace else "")
    if args.headless_runtime_guest:
        closure_suffix += "-production-runtime-guest"
    # C3 (opt-in HCU_C3=1) reads its own closure directory, written by the closure and link scripts.
    hcu_c3 = os.environ.get("HCU_C3") == "1"
    if hcu_c3:
        closure_suffix += "-hcu-c3"
        if os.environ.get("HCU_C3_TELEMETRY") == "1":
            closure_suffix += "-telemetry"
        if os.environ.get("HCU_C3_TIMING") == "1" or os.environ.get("HCU_C3_TELEMETRY") == "1":
            closure_suffix += "-timing"
        if os.environ.get("HCU_C3_REALTIME_SCHEDULER") == "1":
            closure_suffix += "-realtime"
        if os.environ.get("HCU_C3_SNAPSHOT_INDEX") == "1":
            closure_suffix += "-snapshot-index"
        if os.environ.get("HCU_C3_MOVEMENT_TRACE") == "1":
            closure_suffix += "-movement-trace"
        fence_lag = (os.environ.get("HCU_C3_FENCE_LAG_KICKS") or "0").strip()
        if fence_lag not in ("", "0"):
            closure_suffix += f"-fence-lag{fence_lag}"
    # Must match hcu_ps2_closure.c3_workload_suffix(): CE main.c's player count is keyed on the workload header.
    for item in os.environ.get("C_INCLUDE_PATH", "").split(":"):
        workload_header = Path(item) / "hcu_c3_workload.h" if item else None
        if workload_header and workload_header.is_file():
            closure_suffix += "-workload-" + hashlib.sha256(workload_header.read_bytes()).hexdigest()[:12]
            break
    hcu_closure = build / "hcu-ps2-closure" / (
        "all-no-bootstrap-memory" + closure_suffix)
    parent_output = output / "parent-sections-os"
    parent_output.mkdir(parents=True, exist_ok=True)
    asset_root_id = hashlib.sha256(asset_root.encode("utf-8")).hexdigest()[:12]
    gameplay_output = output / f"parent-hcu-gameplay-{asset_root_id}{profile_suffix}"
    gameplay_output.mkdir(parents=True, exist_ok=True)
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    linker = prefix / "ee/bin/mips64r5900el-ps2-elf-ld"
    nm = prefix / "ee/bin/mips64r5900el-ps2-elf-nm"
    size = prefix / "ee/bin/mips64r5900el-ps2-elf-size"
    readelf = prefix / "ee/bin/mips64r5900el-ps2-elf-readelf"
    linkfile = prefix / "ps2sdk/ee/startup/linkfile"

    closure_command = [sys.executable, str(ROOT / "tools/hcu_ps2_closure.py"),
                       "--layer", "all", "--no-bootstrap-memory"]
    link_command = [sys.executable, str(ROOT / "tools/hcu_ps2_link.py"),
                    "--no-bootstrap-memory"]
    if args.m2_ui_lifecycle_test:
        closure_command.append("--m2-ui-lifecycle-test")
        link_command.append("--m2-ui-lifecycle-test")
    if args.step8_mp_capacity_diagnostic:
        closure_command.extend(("--m2-ui-lifecycle-test",
                                "--step8-mp-capacity-diagnostic"))
        link_command.extend(("--m2-ui-lifecycle-test",
                             "--step8-mp-capacity-diagnostic"))
    if args.step8_mp_workload_only:
        closure_command.extend(("--step8-mp-workload-only", "--step8-mp-workload-players",
                                str(args.step8_mp_workload_players)))
        link_command.extend(("--step8-mp-workload-only", "--step8-mp-workload-players",
                             str(args.step8_mp_workload_players)))
    if args.m2_animation_trace:
        closure_command.append("--m2-animation-trace")
        link_command.append("--m2-animation-trace")
    if args.headless_runtime_guest:
        closure_command.append("--production-runtime-guest")
        link_command.append("--production-runtime-guest")
    run(closure_command, env=env)
    if hcu_c3 and (os.environ.get("HCU_C3_TIMING") == "1" or
                   os.environ.get("HCU_C3_TELEMETRY") == "1"):
        closure_report = json.loads((hcu_closure / "result.json").read_text())
        if ("HALO_PS2_C3_TIMING" not in closure_report.get("profile_defines", []) or
                "-DHALO_PS2_C3_TIMING=1" not in closure_report.get("flags", [])):
            raise RuntimeError(
                "timed C3 guest requires HALO_PS2_C3_TIMING in the selected CE closure; "
                f"profile={hcu_closure}, defines={closure_report.get('profile_defines')}, "
                f"flags={closure_report.get('flags')}")
    run(link_command, env=env)
    parent_vis = "src/world/visibility.c"
    run(["make", "-B", "-f", "tools/ee-world.mk", f"WORLD_OUTPUT={parent_output}",
         f"WORLD_VIS_SOURCE={parent_vis}", "WORLD_STREAM_DIAGNOSTIC=0",
         "WORLD_PLAY=0", "WORLD_HCU_LINK_PROBE=1", "WORLD_HCU_MEMORY_BRIDGE=1",
         f"EE_OPTFLAGS={optimization}", "all"], env=env)
    # The link below globs every object under the output directory, so drop
    # objects a previous configuration built but this one no longer lists.
    for stale in gameplay_output.rglob("*.o"):
        stale.unlink()
    run(["make", "-B", "-f", "tools/ee-world.mk", f"WORLD_OUTPUT={gameplay_output}",
         f"WORLD_VIS_SOURCE={parent_vis}", "WORLD_STREAM_DIAGNOSTIC=0",
         "WORLD_PLAY=0", "WORLD_HCU_LINK_PROBE=1", "WORLD_HCU_GAMEPLAY=1",
         f"WORLD_HCU_ASSET_PROFILE={asset_profile}",
         f"WORLD_HCU_RENDER_CLEAR_TEST={1 if args.m3_render_clear_test else 0}",
         f"WORLD_HCU_ANIMATION_TRACE_TEST={1 if args.m2_animation_trace else 0}",
         f"WORLD_HCU_M2_UI_LIFECYCLE_TEST={1 if (args.m2_ui_lifecycle_test or args.step8_mp_capacity_diagnostic) else 0}",
         f"WORLD_HCU_STEP8_MP_CAPACITY_DIAGNOSTIC={1 if args.step8_mp_capacity_diagnostic else 0}",
         f"WORLD_HCU_STEP8_MP_WORKLOAD_PLAYERS={args.step8_mp_workload_players}",
         f"WORLD_HCU_TAG_CACHE_BYTES={args.tag_cache_bytes}",
         f"WORLD_HCU_PARTITION_PROFILE={args.partition_profile or ''}",
         f"WORLD_HCU_PROFILE_PACKAGE_ROOT={args.profile_package_root}",
         f"WORLD_HCU_HEADLESS_RUNTIME_GUEST={1 if args.headless_runtime_guest else 0}",
         f"EE_OPTFLAGS={optimization}", "parent-objects"], env=env)

    parent_objects = sorted(parent_output.rglob("*.o"))
    if not parent_objects:
        raise RuntimeError("parent build produced no object files")
    required_hcu = [
        "ps2_abi.o", "ps2_memory.o", "ps2_crt.o", "ps2_edge.o",
        "ps2_platform.o", "ps2_sound_playback_bind.o", "rooted.o",
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
    static_cap = _budget_region_bytes("elf_static")

    gameplay_objects = sorted(gameplay_output.rglob("*.o"))
    gameplay_entry = gameplay_output / "stream/hcu_main.o"
    input_bridge = gameplay_output / "stream/hcu_input_bridge.o"
    memory_bridge = gameplay_output / "stream/hcu_memory_bind.o"
    for path in (gameplay_entry, input_bridge, memory_bridge):
        if path not in gameplay_objects:
            raise RuntimeError(f"missing HCU gameplay machine input: {path}")
    headless_frame_state = None
    if args.headless_runtime_guest:
        rooted_object = hcu_closure / "rooted.o"
        rooted_report = json.loads((hcu_closure / "result.json").read_text())
        rooted_symbols = run([str(nm), "-g", str(rooted_object)], env=env)
        bitmap_roots = rooted_report.get("rooted_link", {}).get(
            "production_bitmap_provider_definition_counts", {})
        if not bitmap_roots or any(count != 1 for count in bitmap_roots.values()):
            raise RuntimeError("rooted CE image lacks exactly one real bitmap provider definition")
        headless_frame_state = {
            "rooted_object": str(rooted_object.relative_to(ROOT)),
            "rooted_object_sha256": sha256(rooted_object),
            "rooted_report_sha256": sha256(hcu_closure / "result.json"),
            "rooted_symbols": bitmap_roots,
            "registry_translation_unit": "port/ps2/src/ps2_render.c",
            "shared_singleton_with_render_frame": True,
        }
    gameplay_name = ("hcu-gameplay-machine" if asset_profile == "host"
                     else f"hcu-gameplay-machine-{asset_profile}") + profile_suffix
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
    c3_batch_profile_binding = None
    # CE calls hcu_c3_batch_profile only from its realtime-scheduler batch loop
    # (main.c, HALO_PS2_C3_REALTIME_SCHEDULER); a deterministic timed build has no
    # call site, so --gc-sections correctly drops both definitions.
    if hcu_c3 and os.environ.get("HCU_C3_REALTIME_SCHEDULER") == "1" and (
            os.environ.get("HCU_C3_TIMING") == "1" or
            os.environ.get("HCU_C3_TELEMETRY") == "1"):
        symbols = run([str(nm), "-g", str(gameplay_elf)], env=env).splitlines()
        matches = [line.split() for line in symbols
                   if line.split() and line.split()[-1] == "hcu_c3_batch_profile"]
        if len(matches) != 1 or len(matches[0]) < 2 or matches[0][-2] != "T":
            raise RuntimeError(
                "timed C3 guest must bind exactly one strong parent hcu_c3_batch_profile "
                "(CE weak no-op must not satisfy the call); nm entries=" + repr(matches))
        c3_batch_profile_binding = {"symbol": "hcu_c3_batch_profile", "nm_type": matches[0][-2],
                                    "source": "parent stream/hcu_main.c strong logger"}
    gameplay_undefined = run([str(nm), "-u", str(gameplay_elf)], env=env).splitlines()
    gameplay_sizes = section_sizes(run([str(size), "-A", str(gameplay_elf)], env=env))
    gameplay_program_headers = run([str(readelf), "-l", str(gameplay_elf)], env=env)
    gameplay_load_bytes, gameplay_load_memory_bytes = load_segment_sizes(
        gameplay_program_headers)
    gameplay_boundaries = named_symbols(
        run([str(nm), "-n", str(gameplay_elf)], env=env),
        {"_ftext", "_fbss", "_end", "_stack", "_stack_size", "_heap_size"})
    gameplay_physical = physical_placement(
        load_segment_intervals(gameplay_program_headers), gameplay_boundaries)
    gameplay_memory_audit = output / f"{gameplay_name}-memory-audit.json"
    run([sys.executable, str(ROOT / "tools/hcu_ps2_memory_audit.py"),
         "--elf", str(gameplay_elf), "--map", str(gameplay_map),
         "--output", str(gameplay_memory_audit)], env=env)
    gameplay_ledger = json.loads(gameplay_memory_audit.read_text())
    guest_scope = args.headless_runtime_guest
    gameplay_entrypoint = (
        "PS2 entry -> HCU selected partition/runtime -> CE main_setup_connection -> "
        "scenario+BSP load/release before first renderer frame"
        if guest_scope else "parent hcu_main -> parent v2 arena binder -> HCU shell")
    gameplay_map_service = (
        "selected HCP2 profile runtime with segmented source maps and guarded BSP residency"
        if guest_scope else "parent UI/bootstrap callback with HMAP preflight, CTAG/CRNG mount, and source verification")
    gameplay_limits = ([
        "The headless driver exercises CE initialization, selected Sidewinder scenario/BSP load, and owner release before rendering.",
        "This linked report alone is not runtime evidence; inspect the paired PCSX2 guest manifest and logs.",
        "No bitmap rendering, active-frame consumption, multiplayer bot behavior, or C3 draw proof is included.",
    ] if guest_scope else [
        "No guest execution or M1 startup marker has been observed for this linked image.",
        "Only the UI/bootstrap map callback is implemented; no CBSP residency or ordinary retail-map transaction is qualified.",
        "The default cache is deliberately too small to claim ordinary retail map support.",
    ])
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
            "entrypoint": gameplay_entrypoint,
            "input_bridge": "HCU input_frame_begin polls four parent logical pads before CE snapshot",
            "map_service": gameplay_map_service,
            "runtime_guest_mode": "headless-ce-map-load" if guest_scope else None,
            "asset_profile": asset_profile,
            "asset_root": asset_root,
            "partition_profile": args.partition_profile,
            "profile_package_root": str(args.profile_package_root),
            "headless_frame_state_object": headless_frame_state,
            "c3_batch_profile_binding": c3_batch_profile_binding,
            "tag_cache_bytes": args.tag_cache_bytes,
            "tag_cache_limit_note": ("partition-selected guest tuple; runtime qualification is in the paired guest result"
                                     if guest_scope else "UI/bootstrap diagnostic only; not a retail map capacity claim"),
            "limits": gameplay_limits,
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
            "hcu_compile": "python3 tools/hcu_ps2_closure.py --layer all --no-bootstrap-memory" +
                           (" --m2-ui-lifecycle-test" if args.m2_ui_lifecycle_test else
                            " --m2-animation-trace" if args.m2_animation_trace else ""),
            "hcu_link": "python3 tools/hcu_ps2_link.py --no-bootstrap-memory" +
                        (" --m2-ui-lifecycle-test" if args.m2_ui_lifecycle_test else
                         " --m2-animation-trace" if args.m2_animation_trace else ""),
            "parent_compile": f"make -B -f tools/ee-world.mk WORLD_PLAY=0 WORLD_HCU_LINK_PROBE=1 WORLD_HCU_MEMORY_BRIDGE=1 EE_OPTFLAGS={optimization} all",
            "hcu_gameplay_parent_compile": (
                "make -B -f tools/ee-world.mk WORLD_PLAY=0 WORLD_HCU_LINK_PROBE=1 "
                "WORLD_HCU_GAMEPLAY=1 WORLD_HCU_ASSET_PROFILE=" + asset_profile +
                " WORLD_HCU_RENDER_CLEAR_TEST=" +
                ("1" if args.m3_render_clear_test else "0") +
                " WORLD_HCU_ANIMATION_TRACE_TEST=" +
                ("1" if args.m2_animation_trace else "0") +
                " WORLD_HCU_M2_UI_LIFECYCLE_TEST=" +
                ("1" if args.m2_ui_lifecycle_test else "0") +
                f" WORLD_HCU_TAG_CACHE_BYTES={args.tag_cache_bytes} "
                f"WORLD_HCU_PARTITION_PROFILE={args.partition_profile or ''} "
                f"EE_OPTFLAGS={optimization} all"),
        },
    }
    report_path = output / ("result.json" if asset_profile == "host"
                            else f"result-{asset_profile}.json")
    if profile_suffix:
        report_path = report_path.with_name(report_path.stem + profile_suffix + report_path.suffix)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(report_path)
    print(f"ELF {elf}; LOAD file bytes {load_file_bytes}/{static_cap}; "
          f"undefined={len(undefined)}; acceptance=false")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"HCU-parent link probe failed: {error}")
