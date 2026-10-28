#!/usr/bin/env python3
"""C5 guest qualification runner (skeleton): bots, coop modes and survival waves in PCSX2.

The runner launches one PCSX2 instance per run with its own copied data directory and its own Xvfb display, and
supervises it. The run ends when the process exits on its own, when the terminal marker 'HALO_PS2_C5 boot done' is
logged, or when the bounded timeout passes. In the last two cases the runner stops ONLY its own child, through the
child's process group (SIGTERM, then SIGKILL after a grace period). No other PID, no name-based kill and no
pkill/killall is used, and the user's window and other PCSX2 processes are never touched. A run stopped by the
runner counts as terminated_ok only when the terminal marker was logged before the stop (stopped_by_runner=true in
the manifest and the evidence). A run without the marker, stopped by the timeout, is refused.

A row is claimed only when the log of a run that exited normally contains the row's marker lines, in the
session the marker belongs to. Nothing is claimed from the manifest, from a dry run or from a log that was not
written by PCSX2.

A MEASURE run (the setup's intent is measure) prints status=measuring on its session-start line. A log with any
session-start whose status is not "qualified" (measuring, or no status at all) claims no row. The rows of
docs/reports/c5-guest-*.json, which tools/c5_local_setup_rows.py reads, come only from qualified runs.

Markers (the lines are printed by the guest through hcu_c5_session's ops->emit; each starts with HALO_PS2_C5):
  session-start mode=<coop|survival|none> coop=<CE coop mode number, -1 for survival> humans=N bots=N qualified=N map=M difficulty=D status=<qualified|measuring>
  session-refused reason=<setup reason name>                       a refused setup (never a claimed row)
  bot-event tick=T kind=<nav|fight|kill|death|respawn|score> bot=B arg=A
  survival-wave tick=T wave=W batch=N humans=H units=U
  survival-over tick=T wave=W waves-cleared=C
  session-hash tick=T hash=<16 hex digits>                          the final hash of the run

Rows and their evidence:
  bots-navigate, bots-fight, bots-score, bots-die, bots-respawn
      a coop session with bots>=1 (any coop mode) and at least one bot-event of the row's kind.
  coop-<mode>  (team-slayer 1, team-oddball 3, team-king 5, ctf 6, team-race 8)
      a session-start with mode=coop and that coop number, then a session-hash.
  survival-waves
      a survival session-start, at least one survival-wave with wave>=2, a survival-over, then a session-hash.

Each claimed row also needs the boot line HALO_PS2_LOCAL (the guest ran) and the session-hash line of the same run.

Usage:
    python3 -I tools/c5_guest_qualification.py --elf PATH --data-template PATH [--timeout SECONDS]
                                               [--display :NN] [--run-name NAME] [--dry-run]
    python3 -I tools/c5_guest_qualification.py --evaluate-log PATH --run-name NAME
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build/m4-c5-qualification"
PCSX2 = Path(os.environ.get("PCSX2_BIN", "/home/ai/.local/bin/pcsx2"))
# The user's own PCSX2 window. Never used, never signalled; a run whose pid collides with it is refused.
PROTECTED_PIDS = frozenset({183707})
MARKER = "HALO_PS2_C5 "
BOOT_MARKER = "HALO_PS2_LOCAL "
TERMINAL_MARKER = "HALO_PS2_C5 boot done"
STOP_GRACE_SECONDS = 10.0

COOP_MODES = {
    "team-slayer": 1,
    "team-oddball": 3,
    "team-king": 5,
    "ctf": 6,
    "team-race": 8,
}
BOT_KINDS = ("nav", "fight", "kill", "death", "respawn", "score")
ROW_NAMES = (
    ["bots-navigate", "bots-fight", "bots-score", "bots-die", "bots-respawn"]
    + ["coop-" + name for name in COOP_MODES]
    + ["survival-waves"]
)

SESSION_START = re.compile(r"HALO_PS2_C5 session-start mode=(\w+) coop=(-?\d+) humans=(\d+) bots=(\d+)")
SESSION_LINE = re.compile(r"HALO_PS2_C5 session-start ([^\n]*)")
EVIDENCE_FORMAT = "hcu-c5-guest-evidence-v1"
EVIDENCE_DIR = ROOT / "docs/reports"
BOT_EVENT = re.compile(r"HALO_PS2_C5 bot-event tick=\d+ kind=(\w+) bot=\d+ arg=-?\d+")
SURVIVAL_WAVE = re.compile(r"HALO_PS2_C5 survival-wave tick=\d+ wave=(\d+)")
SURVIVAL_OVER = re.compile(r"HALO_PS2_C5 survival-over ")
SESSION_HASH = re.compile(r"HALO_PS2_C5 session-hash tick=\d+ hash=([0-9a-f]{16})")
REFUSED = re.compile(r"HALO_PS2_C5 session-refused reason=(\S+)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_log(text: str, terminated_ok: bool) -> dict:
    """Decide the rows one run's log supports. Only a normally terminated run with the boot line can claim.

    A log whose sessions are measuring (status=measuring) claims nothing; a row whose markers are in such a log is
    reported as "measuring" with its marker evidence, so a measurement can be published without a qualification.
    """
    result = {row: {"status": "not-claimed", "evidence": []} for row in ROW_NAMES}
    sessions = [parse_session_line(m.group(1)) for m in SESSION_LINE.finditer(text)]
    if any(session.get("status") != "qualified" for session in sessions):
        measuring = ("measuring" in [session.get("status") for session in sessions] and
                     all(session.get("status") in ("measuring", None) for session in sessions))
        for row in ROW_NAMES:
            result[row]["status"] = "refused"
            result[row]["evidence"].append("a session is not status=qualified (measuring or unlabelled): no claims")
        if measuring and terminated_ok and BOOT_MARKER in text:
            for row, marker_ok, note in measuring_rows(text):
                if marker_ok:
                    result[row]["status"] = "measuring"
                    result[row]["evidence"].append(note)
        return result
    if not terminated_ok:
        for row in ROW_NAMES:
            result[row]["status"] = "refused"
            result[row]["evidence"].append("run did not terminate normally; no claims from this log")
        return result
    if BOOT_MARKER not in text:
        for row in ROW_NAMES:
            result[row]["status"] = "refused"
            result[row]["evidence"].append("no HALO_PS2_LOCAL boot line; the guest did not run")
        return result

    hashes = SESSION_HASH.findall(text)
    coop_starts = [(int(m.group(2)), int(m.group(4))) for m in SESSION_START.finditer(text)
                   if m.group(1) == "coop"]
    survival_starts = [m for m in SESSION_START.finditer(text) if m.group(1) == "survival"]
    kinds_with_bots = set()
    if any(bots >= 1 for _, bots in coop_starts):
        kinds_with_bots = set(m.group(1) for m in BOT_EVENT.finditer(text))
    waves = [int(m.group(1)) for m in SURVIVAL_WAVE.finditer(text)]

    def claim(row: str, ok: bool, note: str) -> None:
        if ok and hashes:
            result[row]["status"] = "claimed"
            result[row]["evidence"].append(note)
            result[row]["evidence"].append("session-hash " + hashes[-1])

    for kind, row in (("nav", "bots-navigate"), ("fight", "bots-fight"), ("death", "bots-die"),
                      ("respawn", "bots-respawn")):
        claim(row, kind in kinds_with_bots, "bot-event kind=" + kind + " in a coop session with bots")
    # score may come from a kill (credited by CE) or from an objective score event
    claim("bots-score", bool({"score", "kill"} & kinds_with_bots), "bot-event kind=score or kill")
    for name, number in COOP_MODES.items():
        claim("coop-" + name, any(c == number for c, _ in coop_starts), "session-start coop=%d" % number)
    claim("survival-waves", bool(survival_starts) and any(w >= 2 for w in waves) and
          bool(SURVIVAL_OVER.search(text)), "survival-wave wave>=2 and survival-over")
    for row in ROW_NAMES:
        if result[row]["status"] == "not-claimed":
            result[row]["evidence"].append("marker missing from this log")
    return result


def measuring_rows(text: str):
    """(row, markers present, note) for a measurement log: the same marker rules as evaluate_log, no claim."""
    hashes = SESSION_HASH.findall(text)
    coop_starts = [(int(m.group(2)), int(m.group(4))) for m in SESSION_START.finditer(text)
                   if m.group(1) == "coop"]
    survival_starts = [m for m in SESSION_START.finditer(text) if m.group(1) == "survival"]
    kinds = set(m.group(1) for m in BOT_EVENT.finditer(text)) if any(b >= 1 for _, b in coop_starts) else set()
    waves = [int(m.group(1)) for m in SURVIVAL_WAVE.finditer(text)]
    rows = []
    for kind, row in (("nav", "bots-navigate"), ("fight", "bots-fight"), ("death", "bots-die"),
                      ("respawn", "bots-respawn")):
        rows.append((row, kind in kinds and bool(hashes), "bot-event kind=" + kind + " (measuring)"))
    rows.append(("bots-score", bool({"score", "kill"} & kinds) and bool(hashes), "bot-event kind=score or kill (measuring)"))
    for name, number in COOP_MODES.items():
        rows.append(("coop-" + name, any(c == number for c, _ in coop_starts) and bool(hashes),
                     "session-start coop=%d (measuring)" % number))
    rows.append(("survival-waves", bool(survival_starts) and any(w >= 2 for w in waves) and
                 bool(SURVIVAL_OVER.search(text)) and bool(hashes), "survival-wave wave>=2 (measuring)"))
    return rows


def parse_session_line(fields: str) -> dict:
    """key=value fields of one session-start line (mode, coop, humans, bots, qualified, map, difficulty, status)."""
    parsed = {}
    for token in fields.split():
        key, sep, value = token.partition("=")
        if sep:
            parsed[key] = value
    for key in ("coop", "humans", "bots", "qualified"):
        if key in parsed:
            try:
                parsed[key] = int(parsed[key])
            except ValueError:
                parsed.pop(key)
    return parsed


def evidence_record(run_name: str, elf_sha256: str, log_sha256: str, text: str, exited: bool,
                    returncode, rows: dict, stopped_by_runner: bool = False, terminated_ok: bool = False) -> dict:
    """The record tools/c5_local_setup_rows.py reads. It states what the log showed; the generator decides."""
    sessions = [parse_session_line(m.group(1)) for m in SESSION_LINE.finditer(text)]
    last = sessions[-1] if sessions else {}
    hashes = SESSION_HASH.findall(text)
    session = None
    if last:
        session = {
            "mode": last.get("mode"),
            "coop": last.get("coop"),
            "humans": last.get("humans"),
            "bots": last.get("bots"),
            "map": last.get("map"),
            "difficulty": last.get("difficulty"),
            "status": last.get("status"),
        }
    return {
        "format": EVIDENCE_FORMAT,
        "run": run_name,
        "elf_sha256": elf_sha256,
        "log_sha256": log_sha256,
        "terminated_ok": bool(terminated_ok),
        "stopped_by_runner": bool(stopped_by_runner),
        "returncode": returncode,
        "boot_line": BOOT_MARKER in text,
        "terminal_marker": TERMINAL_MARKER in text,
        "session_hash": hashes[-1] if hashes else None,
        "session": session,
        "sessions_in_log": len(sessions),
        "rows": {name: {"status": rows[name]["status"]} for name in ROW_NAMES},
    }


def prepare_run(template: Path, run_dir: Path) -> Path:
    """Copy the emulator data directory for this run only. The template is never modified."""
    data = run_dir / "data"
    if data.exists():
        raise RuntimeError(f"run directory already has data: {data}")
    shutil.copytree(template, data, symlinks=False)
    return data


# The PCSX2 host: root is the ELF's directory (the probe and C2 lanes stage the same way). The UI map comes from the
# parent-link probe package; the level map package comes from the existing converter (tools/convert_map.py writes
# data/retail/convert/<level>/run-a/<level>.hp2) and the decompressed source maps from build/retail-maps.
UI_PACKAGE_DIR = ROOT / "build/hcu-parent-link-probe/maps"
RETAIL_MAPS = ROOT / "build/retail-maps"
LEVEL_PACKAGE_DIR = ROOT / "data/retail/convert"


def stage_host(elf: Path, run_dir: Path, level: str, package_tree: Path | None = None) -> Path:
    """Build the run's host: root: the ELF, maps/ui.{map,hp2}, maps/<level>.{hp2,map}, build/retail-maps.

    Every file is copied or linked from a pinned source; nothing is generated or edited here. A missing input is an
    error, so a run never starts with a partial host root.
    """
    host = run_dir / "host"
    if host.exists():
        raise RuntimeError(f"run directory already has a host root: {host}")
    (host / "maps").mkdir(parents=True)
    shutil.copy2(elf, host / elf.name)
    for name in ("ui.map", "ui.hp2"):
        source = UI_PACKAGE_DIR / name
        if not source.is_file():
            raise RuntimeError(f"missing UI map input: {source}")
        (host / "maps" / name).symlink_to(source.resolve())
    (host / "build").mkdir()
    (host / "build" / "retail-maps").symlink_to(RETAIL_MAPS.resolve())
    if package_tree is not None:
        # Runtime-row mode (the C2 headless guest): the selected package tree is mounted at the path the guest opens,
        # as tools/c2_guest_run.py mount_guest_package_tree does. The level converter output is not used here.
        if not (package_tree / "pkg").is_dir():
            raise RuntimeError(f"package tree has no pkg/: {package_tree}")
        (host / "build" / "m2-c2-r3-selected-packages").symlink_to(package_tree.resolve())
        return host / elf.name
    level_hp2 = LEVEL_PACKAGE_DIR / level / "run-a" / f"{level}.hp2"
    level_map = RETAIL_MAPS / "decompressed" / f"{level}.map"
    for source in (level_hp2, level_map):
        if not source.is_file():
            raise RuntimeError(f"missing level input: {source} (run tools/convert_map.py with MAP={level})")
        (host / "maps" / source.name).symlink_to(source.resolve())
    return host / elf.name


def launch(elf: Path, data: Path, log: Path, display: str) -> subprocess.Popen:
    env = {**os.environ, "DISPLAY": display}
    command = [str(PCSX2), "-batch", "-nogui", "-datapath", str(data),
               "-logfile", str(log), "-elf", str(elf)]
    process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    if process.pid in PROTECTED_PIDS:
        raise RuntimeError("refusing: pid collides with the user's PCSX2 window")
    return process


def marker_logged(log: Path) -> bool:
    try:
        return TERMINAL_MARKER in log.read_text(errors="replace")
    except OSError:
        return False


def stop_own_child(process: subprocess.Popen, grace: float) -> None:
    """SIGTERM, then SIGKILL after the grace period, to the process group of this run's own child only.

    launch() starts the child with start_new_session=True, so the child leads its own process group and the group
    holds nothing else. No other PID, name or group is ever signalled here.
    """
    group = process.pid
    try:
        os.killpg(group, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + grace
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.5)
    try:
        os.killpg(group, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=30)


def supervise(process: subprocess.Popen, log: Path, timeout: float, grace: float) -> dict:
    """Waits for the run. It ends when the process exits on its own, when the terminal marker is logged, or when the
    bounded timeout passes. In the last two cases the runner stops its own child (stop_own_child).

    terminated_ok: the process exited on its own with returncode 0, or the terminal marker was logged before the
    runner stopped it. A run stopped without the marker is never terminated_ok.
    """
    deadline = time.monotonic() + timeout
    while process.poll() is None:
        if marker_logged(log) or time.monotonic() >= deadline:
            break
        time.sleep(0.5)
    if process.poll() is not None:
        return {"exited": True, "stopped_by_runner": False, "terminal_marker_seen": marker_logged(log),
                "terminated_ok": process.returncode == 0}
    marker_before_stop = marker_logged(log)
    stop_own_child(process, grace)
    return {"exited": True, "stopped_by_runner": True, "terminal_marker_seen": marker_before_stop,
            "terminated_ok": marker_before_stop}


def run_once(args) -> dict:
    elf = args.elf.resolve()
    run_dir = OUT / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    record = {"run": args.run_name, "elf": str(elf), "elf_sha256": sha256(elf), "dry_run": args.dry_run,
              "package_tree": str(args.package_tree) if args.package_tree else None}
    if args.dry_run:
        record["rows"] = {row: {"status": "not-run", "evidence": ["dry run: PCSX2 not started"]}
                          for row in ROW_NAMES}
        record["note"] = "dry run: PCSX2 not started"
        return record
    log = run_dir / "pcsx2.log"
    data = prepare_run(args.data_template, run_dir)
    guest_elf = stage_host(elf, run_dir, args.level, args.package_tree)
    record["host_elf"] = str(guest_elf)
    process = launch(guest_elf, data, log, args.display)
    record["pid"] = process.pid
    state = supervise(process, log, args.timeout, STOP_GRACE_SECONDS)
    exited = state["exited"]
    record["exited"] = exited
    record["stopped_by_runner"] = state["stopped_by_runner"]
    record["terminal_marker_seen"] = state["terminal_marker_seen"]
    record["returncode"] = process.returncode if exited else None
    text = log.read_text(errors="replace") if log.exists() else ""
    record["log_bytes"] = len(text)
    record["rows"] = evaluate_log(text, terminated_ok=state["terminated_ok"])
    if log.exists():
        record["evidence"] = evidence_record(args.run_name, record["elf_sha256"], sha256(log), text, exited,
                                             record["returncode"], record["rows"],
                                             stopped_by_runner=state["stopped_by_runner"],
                                             terminated_ok=state["terminated_ok"])
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--elf", type=Path, help="HCU ELF built with the C5 modules")
    parser.add_argument("--data-template", type=Path, help="PCSX2 data directory copied for the run")
    parser.add_argument("--display", default=os.environ.get("C5_GUEST_DISPLAY", ":111"),
                        help="private Xvfb display (must be started by the operator; never the user's)")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--level", default="b30",
                        help="level whose package is staged at host:/maps (converted by tools/convert_map.py)")
    parser.add_argument("--package-tree", type=Path,
                        help="runtime-row mode: selected package tree (its pkg/) mounted at host:/build/"
                             "m2-c2-r3-selected-packages; replaces the level package staging")
    parser.add_argument("--run-name", default="c5-run")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--evaluate-log", type=Path, help="evaluate an existing PCSX2 log instead of running")
    parser.add_argument("--publish-evidence", action="store_true",
                        help="write the run's evidence record to docs/reports/c5-guest-<run-name>.json "
                             "(a real run only; a dry run or a log file publishes nothing)")
    args = parser.parse_args()

    if args.evaluate_log:
        text = args.evaluate_log.read_text(errors="replace")
        record = {"run": args.run_name, "log": str(args.evaluate_log), "rows": evaluate_log(text, True)}
    else:
        if not args.elf or not args.data_template:
            parser.error("--elf and --data-template are required unless --evaluate-log is given")
        if not args.elf.is_file():
            parser.error(f"no ELF at {args.elf}")
        if not args.dry_run and not shutil.which(str(PCSX2)) and not PCSX2.exists():
            parser.error(f"PCSX2 not found at {PCSX2}")
        record = run_once(args)

    if args.publish_evidence:
        if args.evaluate_log or args.dry_run or "evidence" not in record:
            parser.error("--publish-evidence needs a real run (not --evaluate-log or --dry-run)")
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        target = EVIDENCE_DIR / f"c5-guest-{args.run_name}.json"
        target.write_text(json.dumps(record["evidence"], indent=2, sort_keys=True) + "\n")
        print(f"evidence: {target}")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = OUT / "manifest.json"
    manifest.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    for row in ROW_NAMES:
        print(f"{row}: {record['rows'][row]['status']}")
    print(f"manifest: {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
