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


STAGE_MARKERS = {
    "playable": "HALO_PS2_LOCAL playable",
    "m3-memory-ready": "HALO_PS2_LOCAL memory-ready",
    "m1-boundary": "HALO_PS2_LOCAL m1-ui-map-request",
    "m2-ui": "HALO_PS2_LOCAL m2-ui-map-loaded",
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


def linked_physical_evidence(physical, elf, probe_path=None):
    """Bind guest pointers to this exact linked image, not a prior guest log."""
    probe_path = probe_path or ROOT / "build/hcu-parent-link-probe/result.json"
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


def failed_guest_evidence(log_text, success_marker):
    """Retain completed startup gates even when a later stage halts."""
    m1_marker = "HALO_PS2_LOCAL m1-ui-map-request"
    m1_offset = log_text.find(m1_marker)
    return {
        "reached_game_initialize_done":
            "HALO_PS2_LOCAL game-initialize-done" in log_text,
        "reached_success_marker": success_marker in log_text,
        "reached_m1_boundary": m1_offset >= 0,
        "failure_after_m1_boundary": m1_offset >= 0 and any(
            token in log_text[m1_offset:]
            for token in ("HALO_PS2_LOCAL halt", "HALO_PS2_FAIL")),
        "physical_memory": physical_memory_evidence(log_text),
    }


def boot_once(config, elf, mode, display, timeout, stage, success_marker,
              disc=None, boot_from_disc=False, require_physical_placement=False):
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
        "elf_sha256": sha(elf) if elf is not None else None,
        "elf_path": str(elf) if elf is not None else None,
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
                physical = physical_memory_evidence(text)
                linked = (linked_physical_evidence(physical, elf)
                          if physical and require_physical_placement else None)
                if require_physical_placement and not (
                        physical and linked and linked["passed"]):
                    raise RuntimeError(
                        "guest physical memory/arena placement evidence missing or invalid")
                marker_offset = text.index(success_marker)
                result.update(
                    status=("passed" if stage == "m3-memory-ready" else "boundary-observed"),
                    outcome=("memory-placement-observed-not-playable"
                             if stage == "m3-memory-ready" else
                             "local-menu-request-reached-not-playable"),
                    reached_game_initialize_done="HALO_PS2_LOCAL game-initialize-done" in text,
                    reached_success_marker=True,
                    failure_after_boundary=any(
                        text.find(token, marker_offset) >= 0
                        for token in ("HALO_PS2_LOCAL halt", "HALO_PS2_FAIL")),
                    wall_seconds=time.monotonic() - started,
                    physical_memory=physical,
                    linked_physical=linked,
                    last_guest_log=text[-12000:],
                )
                save(result_path, result)
                return result
            if "HALO_PS2_LOCAL halt" in text or "HALO_PS2_FAIL" in text:
                marker = next((line for line in reversed(text.splitlines())
                               if "HALO_PS2_LOCAL halt" in line or "HALO_PS2_FAIL" in line), "guest failure")
                raise RuntimeError(marker)
            if "HALO_PS2_LOCAL game-initialize-done" in text:
                result["reached_game_initialize_done"] = True
                save(result_path, result)
            if success_marker in text and success_at is None:
                success_at = time.monotonic()
                result["reached_success_marker"] = True
                save(result_path, result)
            if success_at is not None and time.monotonic() - success_at >= 2.0:
                result.update(status="passed", outcome=f"{stage}-marker-stable",
                              wall_seconds=time.monotonic() - started,
                              stable_seconds=time.monotonic() - success_at)
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
                                     args.require_physical_placement))
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
