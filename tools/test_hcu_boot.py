"""Boot the HCU local-game ELF in PCSX2 and retain startup evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

from test_emulator import ROOT, prepare, save, sha


OUTPUT = ROOT / "build/hcu-ps2-closure"
ELF = OUTPUT / "all/halo-local.elf"


def git_revision(path):
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def host_asset_manifest(elf):
    """Hash UI inputs under the HLE host root associated with the ELF."""
    if elf is None:
        return None
    root = Path(elf).resolve().parent
    assets = []
    for relative in ("maps/ui.map", "maps/ui.hp2"):
        path = root / relative
        if path.is_file():
            assets.append({"relative_path": relative, "path": str(path),
                           "bytes": path.stat().st_size, "sha256": sha(path)})
        else:
            assets.append({"relative_path": relative, "path": str(path),
                           "missing": True})
    return {"host_root": str(root),
            "basis": "HLE host:/ root observed in PCSX2 guest log",
            "assets": assets}


STAGE_MARKERS = {
    "playable": "HALO_PS2_LOCAL playable",
    "m3-memory-ready": "HALO_PS2_LOCAL memory-ready",
    "m1-boundary": "HALO_PS2_LOCAL m1-ui-map-request",
    "m2-ui": "HALO_PS2_LOCAL m2-ui-map-loaded",
    "m2-ui-lifecycle": "HALO_PS2_LOCAL m2-ui-lifecycle-complete cycles=2",
    "m3-render-clear": "HALO_PS2_LOCAL m3-render-clear-presented",
}

PHYSICAL_MEMORY = re.compile(
    r"HALO_PS2_LOCAL memory-physical elf_end=0x([0-9a-fA-F]+) "
    r"boot=0x([0-9a-fA-F]+) boot_end=0x([0-9a-fA-F]+) "
    r"reserve=0x([0-9a-fA-F]+)(?: allocator_gap=(\d+))?")
PHYSICAL_ARENA = re.compile(
    r"HALO_PS2_LOCAL arena name=([a-z_]+) base=0x([0-9a-fA-F]+) "
    r"cap=(\d+) used=(\d+) high=(\d+)")
KERNEL_STACK = re.compile(
    r"HALO_PS2_LOCAL kernel-stack base=0x([0-9a-fA-F]+) "
    r"size=(\d+) end=0x([0-9a-fA-F]+)")
KERNEL_RESERVATION = re.compile(
    r"HALO_PS2_LOCAL kernel-reservation low=0x0 low_bytes=(\d+) "
    r"high=0x([0-9a-fA-F]+) high_bytes=(\d+) "
    r"reserve=0x([0-9a-fA-F]+) reserve_bytes=(\d+)")
MEMORY_READY = re.compile(r"HALO_PS2_LOCAL memory-ready canaries=(\d+)")
EXPECTED_ARENAS = {
    "resident_gameplay", "current_bsp", "texture_cache",
    "dynamic_simulation", "dma_commands", "streaming", "checkpoint",
    "audio", "frame_scratch",
}

GUEST_FAULT_MARKERS = (
    "HALO_PS2_LOCAL halt",
    "HALO_PS2_FAIL",
    "Address Error,",
    "branch delay!!",
    "EXCEPTION halt",
)


def guest_fault_after_marker(log_text, success_marker):
    """Return the first guest-fault line after this stage's success boundary."""
    marker_offset = log_text.find(success_marker)
    if marker_offset < 0:
        return None
    for line in log_text[marker_offset:].splitlines():
        if any(marker in line for marker in GUEST_FAULT_MARKERS):
            return line
    return None


def validate_m2_ui_lifecycle_log(log_text):
    """Require live-owner fault preservation, post-unload retry, and two reloads."""
    if "HALO_PS2_LOCAL m2-ui-lifecycle-failed" in log_text:
        raise RuntimeError("CE UI lifecycle diagnostic emitted a failure marker")
    required_fault_markers = (
        "m2-ui-lifecycle-injected preflight-before-unload",
        "m2-ui-lifecycle-preunload-failure-preserved",
        "m2-ui-lifecycle-injected preflight-after-unload",
		"m2-ui-lifecycle-postunload-ce-preflight-refused",
        "m2-ui-lifecycle-postunload-failure-safe-empty",
        "m2-ui-lifecycle-postunload-retry-complete",
    )
    for marker in required_fault_markers:
        if f"HALO_PS2_LOCAL {marker}" not in log_text:
            raise RuntimeError(f"missing CE lifecycle fault/retry evidence: {marker}")
    if not (log_text.index("m2-ui-lifecycle-preunload-failure-preserved") <
            log_text.index("m2-ui-lifecycle-injected preflight-after-unload") <
            log_text.index("m2-ui-lifecycle-postunload-ce-preflight-refused") <
            log_text.index("m2-ui-lifecycle-postunload-failure-safe-empty") <
            log_text.index("m2-ui-lifecycle-postunload-retry-complete")):
        raise RuntimeError("CE lifecycle fault/retry evidence is out of order")
    trace = re.compile(
        r"HALO_PS2_LOCAL m2-ui-owner cycle=0 phase=([^ ]+) base=(0x[0-9a-fA-F]+) "
        r"cap=(\d+) used=(\d+) high=(\d+) mount=(\d+) source=(\d+) "
        r"descriptor=(-?\d+) preflight=(\d+) reload=(\d+) staged=([^\s]+)")
    states = {row[0]: row[1:] for row in trace.findall(log_text)}
    before = states.get("before-preflight-fault")
    after = states.get("after-preflight-fault")
    if before is None or after is None or before != after:
        raise RuntimeError("pre-unload preflight refusal changed the live owner snapshot")
    empty = states.get("after-postunload-fault")
    if (empty is None or empty[0:2] != before[0:2] or empty[2] != "0" or
            empty[3] != before[3] or empty[4:9] != ("0", "0", "-1", "0", "0") or
            empty[9] != "-"):
        raise RuntimeError("post-unload fault did not return parent owner to empty baseline")
    recovered = states.get("postunload-retry-loaded")
    if (recovered is None or recovered[2] == "0" or recovered[4] != "1" or
            recovered[5] != "1" or recovered[6] == "-1" or
            recovered[7] != "0" or recovered[8] != "0" or
            recovered[9] != "-"):
        raise RuntimeError("post-unload same-process retry did not remount the UI owner")
    completed = re.findall(
        r"HALO_PS2_LOCAL m2-ui-lifecycle-cycle-complete cycle=(\d+)", log_text)
    if completed != ["1", "2"]:
        raise RuntimeError(f"expected lifecycle cycle completions [1, 2], got {completed}")
    ce_released = re.findall(
        r"HALO_PS2_LOCAL m2-ui-lifecycle-owner-released cycle=(\d+) "
        r"scenario=(?:\(nil\)|0x0+|0+) bsp=(?:\(nil\)|0x0+|0+) "
        r"collision=(?:\(nil\)|0x0+|0+) bsp3d=(?:\(nil\)|0x0+|0+) "
        r"game_globals=(?:\(nil\)|0x0+|0+) scenario_index=-1 bsp_index=-1 "
        r"scenario_bsp_index=-1 tags=(?:\(nil\)|0x0+|0+) tag_count=0 cache=0",
        log_text)
    if ce_released != ["1", "2"]:
        raise RuntimeError("CE scenario/collision/tag/index globals were not null at owner release")
    ce_unpublished = re.findall(
        r"HALO_PS2_LOCAL m2-ui-lifecycle-ce-unpublished cycle=(\d+) "
        r"scenario=(?:\(nil\)|0x0+|0+) bsp=(?:\(nil\)|0x0+|0+) "
        r"collision=(?:\(nil\)|0x0+|0+) bsp3d=(?:\(nil\)|0x0+|0+) "
        r"game_globals=(?:\(nil\)|0x0+|0+) scenario_index=-1 bsp_index=-1 "
        r"scenario_bsp_index=-1 tags=(?:\(nil\)|0x0+|0+) tag_count=0 cache=1",
        log_text)
    if ce_unpublished != ["1", "2"]:
        raise RuntimeError("CE globals were not unpublished before owner release")
    if not (log_text.index("m2-ui-lifecycle-ce-unpublished cycle=1") <
            log_text.index("m2-ui-lifecycle-owner-released cycle=1") <
            log_text.index("m2-ui-lifecycle-cycle-complete cycle=1") <
            log_text.index("m2-ui-lifecycle-ce-unpublished cycle=2") <
            log_text.index("m2-ui-lifecycle-owner-released cycle=2") <
            log_text.index("m2-ui-lifecycle-cycle-complete cycle=2")):
        raise RuntimeError("CE unpublish/release/reload cycles are not ordered")
    owner_released = re.findall(
        r"HALO_PS2_LOCAL m2-ui-owner cycle=(\d+) phase=ce-unpublished-owner-released "
        r"base=(0x[0-9a-fA-F]+) cap=(\d+) used=0 high=(\d+) mount=0 source=0 "
        r"descriptor=-1 preflight=0 reload=1 staged=ui",
        log_text)
    owner_released = [row for row in owner_released if row[0] in ("1", "2")]
    if [(cycle, cap) for cycle, _base, cap, _high in owner_released] != [
            ("1", "1572864"), ("2", "1572864")]:
        raise RuntimeError("parent owner did not return to its fixed UI-unload baseline")
    loaded = re.findall(
        r"HALO_PS2_LOCAL m2-ui-owner cycle=(\d+) phase=cycle-loaded "
        r"base=(0x[0-9a-fA-F]+) cap=(\d+) used=(\d+) high=(\d+) mount=1 source=1 "
        r"descriptor=(\d+) preflight=0 reload=0 staged=-",
        log_text)
    if [row[0] for row in loaded] != ["1", "2"]:
        raise RuntimeError("parent owner state missing after one or more UI reloads")
    if loaded[0][1:5] != loaded[1][1:5]:
        raise RuntimeError("identical UI reload changed fixed owner footprint/high-water")
    return {"cycles": completed, "owner_release": owner_released,
            "owner_loaded": loaded, "ce_globals_null": ce_released,
            "ce_globals_unpublished": ce_unpublished}


def physical_memory_evidence(log_text):
    match = PHYSICAL_MEMORY.search(log_text)
    if not match:
        return None
    elf_end, boot, boot_end, reserve = (
        int(value, 16) for value in match.groups()[:4])
    allocator_gap = int(match.group(5)) if match.group(5) is not None else None
    arenas = []
    seen = set()
    for row in PHYSICAL_ARENA.finditer(log_text):
        name, base, cap, used, high = row.groups()
        if name in seen:
            return {"nonoverlapping": False, "error": f"duplicate arena {name}"}
        seen.add(name)
        base, cap, used, high = int(base, 16), int(cap), int(used), int(high)
        arenas.append({"name": name, "base": base, "cap": cap,
                       "used": used, "high": high, "end": base + cap})
    ranges = sorted(arenas, key=lambda row: row["base"])
    arena_valid = seen == EXPECTED_ARENAS and all(
        row["cap"] > 0 and row["used"] <= row["cap"] and
        row["high"] <= row["cap"] and boot <= row["base"] < row["end"] <= boot_end
        for row in ranges)
    arena_valid = arena_valid and all(
        left["end"] <= right["base"] for left, right in zip(ranges, ranges[1:]))
    stack_match = KERNEL_STACK.search(log_text)
    kernel_match = KERNEL_RESERVATION.search(log_text)
    ready_match = MEMORY_READY.search(log_text)
    stack_valid = False
    stack = None
    kernel = None
    if stack_match:
        stack_start, stack_bytes, stack_end = (
            int(stack_match.group(1), 16), int(stack_match.group(2)),
            int(stack_match.group(3), 16))
        stack = {"base": stack_start, "bytes": stack_bytes, "end": stack_end}
        stack_valid = stack_bytes > 0 and stack_start + stack_bytes == stack_end
    if kernel_match:
        low_bytes, high, high_bytes, reserve, reserve_bytes = (
            int(kernel_match.group(1)), int(kernel_match.group(2), 16),
            int(kernel_match.group(3)), int(kernel_match.group(4), 16),
            int(kernel_match.group(5)))
        kernel = {"low_start": 0, "low_end": low_bytes,
                  "high_start": high, "high_end": high + high_bytes,
                  "reserve_start": reserve, "reserve_end": reserve + reserve_bytes}
        stack_valid = stack_valid and (
            (stack["base"] >= kernel["low_start"] and stack["end"] <= kernel["low_end"]) or
            (stack["base"] >= kernel["high_start"] and stack["end"] <= kernel["high_end"]))
        stack_valid = stack_valid and kernel["reserve_end"] == kernel["high_start"]
    return {"elf_end": elf_end, "boot_start": boot,
            "boot_end": boot_end, "reserve_start": reserve,
            "headroom_bytes": reserve - boot_end,
            "allocator_gap_bytes": allocator_gap,
            "arenas": arenas,
            "arenas_complete_and_valid": arena_valid,
            "kernel_stack": stack,
            "kernel_reservation": kernel,
            "kernel_stack_in_reserved_interval": stack_valid,
            "boundary_canaries_verified": (int(ready_match.group(1)) == 10
                                           if ready_match else False),
            "nonoverlapping": 0x00100000 <= elf_end <= boot < boot_end <= reserve
                and arena_valid and stack_valid}


def find_link_probe_report(elf, probe_directory=None):
    """Find the link-probe report whose embedded ELF hash matches `elf`.

    Diagnostic profiles write isolated result-<profile>.json files. Selecting
    the default result.json unconditionally can compare a real guest run against
    the wrong tag-cache/layout profile, so identity is the selection key.
    """
    probe_directory = (Path(probe_directory) if probe_directory is not None
                       else ROOT / "build/hcu-parent-link-probe")
    wanted = sha(elf)
    candidates = [probe_directory / "result.json"]
    candidates.extend(sorted(probe_directory.glob("result-*.json")))
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            report = json.loads(candidate.read_text())
            machine = report["hcu_gameplay_machine"]
            if machine["elf"]["sha256"] == wanted:
                return candidate
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def linked_physical_evidence(physical, elf, probe_path=None):
    """Bind guest pointers to this exact linked image, not a prior guest log."""
    if probe_path is None:
        probe_path = find_link_probe_report(elf)
    if probe_path is None:
        return {"checks": {"matching_link_probe_report": False}, "passed": False,
                "machine_elf_sha256": sha(elf), "link_map_sha256": None}
    probe = json.loads(probe_path.read_text())
    machine = probe["hcu_gameplay_machine"]
    placement = machine["physical_placement"]
    expected = {"resident_gameplay": 6_815_744 - placement["nobits"]["bytes"],
                "current_bsp": 6_291_456, "texture_cache": 4_194_304,
                "dynamic_simulation": 2_621_440, "dma_commands": 1_179_648,
                "streaming": 1_572_864, "checkpoint": 524_288,
                "audio": 524_288, "frame_scratch": 393_216}
    actual = {row["name"]: row["cap"] for row in physical["arenas"]}
    checks = {
        "exact_elf": sha(elf) == machine["elf"]["sha256"],
        "crt_end": physical["elf_end"] == placement["symbols"]["_end"],
        "malloc_request": physical["boot_end"] - physical["boot_start"] ==
            placement["boot_malloc_request_bytes"],
        "allocator_gap": physical["allocator_gap_bytes"] ==
            physical["boot_start"] - physical["elf_end"],
        "arena_capacities": actual == expected,
        "physical_nonoverlap": physical["nonoverlapping"],
        "load_intervals": placement["necessary_conditions_pass"] and all(
            row["memory_end"] <= physical["boot_start"]
            for row in placement["load_intervals"]),
        "boundary_canaries": physical["boundary_canaries_verified"],
    }
    return {"checks": checks, "passed": all(checks.values()),
            "machine_elf_sha256": machine["elf"]["sha256"],
            "link_map_sha256": machine["memory_ledger"]["map_sha256"]}


def required_physical_evidence(log_text, elf, required, probe_path=None):
    """Parse runtime placement and bind it to the exact linked image."""
    physical = physical_memory_evidence(log_text)
    linked = (linked_physical_evidence(physical, elf, probe_path)
              if physical is not None and elf is not None else None)
    if required and not (physical and linked and linked["passed"]):
        raise RuntimeError(
            "guest physical memory/arena placement evidence missing or invalid")
    return physical, linked


def failed_guest_evidence(log_text, success_marker):
    """Retain completed startup gates even when a later stage halts."""
    m1_marker = "HALO_PS2_LOCAL m1-ui-map-request"
    m1_offset = log_text.find(m1_marker)
    return {
        "reached_game_initialize_done":
            "HALO_PS2_LOCAL game-initialize-done" in log_text,
        "reached_success_marker": success_marker in log_text,
        "reached_m1_boundary": m1_offset >= 0,
        "failure_after_m1_boundary": m1_offset >= 0 and
            guest_fault_after_marker(log_text[m1_offset:], m1_marker) is not None,
        "physical_memory": physical_memory_evidence(log_text),
    }


def boot_once(config, elf, mode, display, timeout, stage, success_marker,
              disc=None, boot_from_disc=False, require_physical_placement=False,
              stable_seconds=2.0):
    run = OUTPUT / f"emulator-m1-{mode}-{uuid.uuid4().hex}"
    run.mkdir(parents=True)
    ini = prepare(config, run, mode)
    log = run / "emulog.txt"
    command = [config["binary"], "-datapath", str(run / "data"),
               "-nofullscreen", "-logfile", str(log)]
    if not boot_from_disc:
        command.extend(("-elf", str(elf)))
    # A normal boot uses the ISO as PCSX2's positional boot filename. In the
    # alternate dev case, -elf overrides the executable while retaining that
    # disc as CDVD data source. -disc is for physical host DVD drives.
    if disc is not None:
        command.extend(("--", str(disc)))
    result = {
        "status": "running",
        "scenario": "hcu-local-game-startup",
        "stage": stage,
        "required_success_marker": success_marker,
        "mode": mode,
        "command": command,
        "display": display,
        "parent_commit": git_revision(ROOT),
        "hcu_commit": git_revision(ROOT / "submodules/halo-ce-universal"),
        "halo_ps2_commit": git_revision(ROOT / "submodules/halo-ps2"),
        "boot_from_disc": boot_from_disc,
        "require_physical_placement": require_physical_placement,
        "required_stable_seconds": stable_seconds,
        "elf_sha256": sha(elf) if elf is not None else None,
        "elf_path": str(elf) if elf is not None else None,
        "host_asset_manifest_before": host_asset_manifest(elf),
        "disc_path": str(disc) if disc is not None else None,
        "disc_sha256": sha(disc) if disc is not None else None,
        "bios_sha256": sha(config["bios"]),
        "emulator_sha256": sha(Path(config["binary"]).resolve()),
        "settings_sha256": sha(ini),
        "run_directory": str(run),
        "log": str(log),
    }
    result_path = run / "result.json"
    save(result_path, result)
    env = {**os.environ, "DISPLAY": display,
           "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM", "xcb"),
           "APPIMAGE_EXTRACT_AND_RUN": "1"}
    launcher = (run / "launcher.log").open("w")
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=launcher,
                               stderr=subprocess.STDOUT, start_new_session=True)
    started = last_progress = time.monotonic()
    success_at = None
    previous_size = 0
    try:
        while time.monotonic() - started < timeout:
            text = log.read_text(errors="replace") if log.exists() else ""
            if len(text) != previous_size:
                previous_size = len(text)
                last_progress = time.monotonic()
            if (stage in ("m1-boundary", "m3-memory-ready") and
                    success_marker in text and
                    (stage == "m3-memory-ready" or
                     "HALO_PS2_LOCAL game-initialize-done" in text)):
                guest_fault = guest_fault_after_marker(text, success_marker)
                if guest_fault:
                    raise RuntimeError(guest_fault)
                physical, linked = required_physical_evidence(
                    text, elf, require_physical_placement)
                marker_offset = text.index(success_marker)
                result.update(
                    status=("passed" if stage == "m3-memory-ready" else "boundary-observed"),
                    outcome=("memory-placement-observed-not-playable"
                             if stage == "m3-memory-ready" else
                             "local-menu-request-reached-not-playable"),
                    reached_game_initialize_done="HALO_PS2_LOCAL game-initialize-done" in text,
                    reached_success_marker=True,
                    failure_after_boundary=guest_fault_after_marker(
                        text[marker_offset:], success_marker) is not None,
                    wall_seconds=time.monotonic() - started,
                    physical_memory=physical,
                    linked_physical=linked,
                    last_guest_log=text[-12000:],
                )
                result["host_asset_manifest_after"] = host_asset_manifest(elf)
                result["host_assets_unchanged"] = (
                    result["host_asset_manifest_before"] ==
                    result["host_asset_manifest_after"])
                save(result_path, result)
                return result
            if "HALO_PS2_LOCAL game-initialize-done" in text:
                result["reached_game_initialize_done"] = True
                save(result_path, result)
            if success_marker in text and success_at is None:
                if stage == "m2-ui-lifecycle":
                    result["lifecycle_evidence"] = validate_m2_ui_lifecycle_log(text)
                    if require_physical_placement:
                        physical, linked = required_physical_evidence(
                            text, elf, True)
                        result["physical_memory"] = physical
                        result["linked_physical"] = linked
                success_at = time.monotonic()
                result["reached_success_marker"] = True
                save(result_path, result)
            if success_at is not None:
                guest_fault = guest_fault_after_marker(text, success_marker)
                if guest_fault:
                    raise RuntimeError(guest_fault)
            elif "HALO_PS2_LOCAL halt" in text or "HALO_PS2_FAIL" in text:
                marker = next((line for line in reversed(text.splitlines())
                               if "HALO_PS2_LOCAL halt" in line or "HALO_PS2_FAIL" in line), "guest failure")
                raise RuntimeError(marker)
            if (success_at is not None and
                    time.monotonic() - success_at >= stable_seconds):
                guest_fault = guest_fault_after_marker(text, success_marker)
                if guest_fault:
                    raise RuntimeError(guest_fault)
                result.update(status="passed", outcome=f"{stage}-marker-stable",
                              wall_seconds=time.monotonic() - started,
                              stable_seconds=time.monotonic() - success_at)
                result["host_asset_manifest_after"] = host_asset_manifest(elf)
                result["host_assets_unchanged"] = (
                    result["host_asset_manifest_before"] ==
                    result["host_asset_manifest_after"])
                save(result_path, result)
                return result
            if process.poll() is not None:
                raise RuntimeError(
                    f"PCSX2 exited with status {process.returncode} before the {stage} marker")
            if time.monotonic() - last_progress > 90:
                raise RuntimeError("PCSX2 log stopped progressing for 90 seconds")
            time.sleep(0.25)
        raise RuntimeError(
            f"{stage} marker {success_marker!r} was not stable before timeout {timeout}s")
    except Exception as error:
        text = log.read_text(errors="replace") if log.exists() else ""
        result.update(status="failed", error=str(error),
                      **failed_guest_evidence(text, success_marker),
                      last_guest_log=text[-12000:])
        result["host_asset_manifest_after"] = host_asset_manifest(elf)
        result["host_assets_unchanged"] = (
            result["host_asset_manifest_before"] ==
            result["host_asset_manifest_after"])
        save(result_path, result)
        raise
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        launcher.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("interpreter", "recompiler", "both"), default="recompiler")
    parser.add_argument("--stage", choices=tuple(STAGE_MARKERS), default="playable",
                        help="playable is the acceptance default; m1-boundary is diagnostic only")
    parser.add_argument("--display", default=os.environ.get("DISPLAY"))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--stable-seconds", type=float, default=2.0,
                        help="fault-free observation time after the requested marker")
    parser.add_argument("--elf", type=Path, default=ELF,
                        help="ELF to qualify (default: standalone HCU closure)")
    parser.add_argument("--disc", type=Path, default=None,
                        help="optional ISO mounted as the guest DVD source")
    parser.add_argument("--boot-from-disc", action="store_true",
                        help="boot the PS2 executable named by the ISO SYSTEM.CNF")
    parser.add_argument("--require-physical-placement", action="store_true",
                        help="require the combined-image runtime ELF/boot/reserve address marker")
    parser.add_argument("--success-marker", default=None,
                        help="override the selected stage marker (normally avoid this)")
    args = parser.parse_args()
    if args.stable_seconds <= 0:
        parser.error("--stable-seconds must be positive")
    elf = args.elf.resolve() if not args.boot_from_disc else None
    if elf is not None and not elf.is_file():
        raise RuntimeError(f"ELF does not exist: {elf}")
    disc = args.disc.resolve() if args.disc is not None else None
    if disc is not None and not disc.is_file():
        raise RuntimeError(f"disc image does not exist: {disc}")
    if args.boot_from_disc and disc is None:
        raise RuntimeError("--boot-from-disc requires --disc")
    config = json.loads((ROOT / ".local/emulator.json").read_text())
    display = args.display or config["display"]
    success_marker = args.success_marker or STAGE_MARKERS[args.stage]
    modes = ("interpreter", "recompiler") if args.mode == "both" else (args.mode,)
    results = []
    latest_report = OUTPUT / "emulator-m1-latest.json"
    for mode in modes:
        try:
            results.append(boot_once(config, elf, mode, display, args.timeout,
                                     args.stage, success_marker, disc,
                                     args.boot_from_disc,
                                     args.require_physical_placement,
                                     args.stable_seconds))
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            # boot_once persists the exact failed run before raising. Keep the
            # aggregate pointer truthful too; otherwise a failed current ELF
            # can leave a prior successful diagnostic (or unrelated smoke
            # marker) looking like the latest HCU result.
            candidates = sorted(
                OUTPUT.glob(f"emulator-m1-{mode}-*/result.json"),
                key=lambda path: path.stat().st_mtime_ns,
                reverse=True)
            if candidates:
                results.append(json.loads(candidates[0].read_text()))
            report = {"status": "failed", "scenario": "hcu-local-game-startup",
                      "stage": args.stage, "results": results,
                      "error": str(error)}
            latest_report.write_text(json.dumps(report, indent=2) + "\n")
            raise
    report_status = "passed" if all(result["status"] == "passed" for result in results) else "boundary-observed"
    report = {"status": report_status, "scenario": "hcu-local-game-startup",
              "stage": args.stage, "results": results}
    latest_report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError, KeyError) as error:
        sys.exit(f"HCU boot probe failed: {error}")
