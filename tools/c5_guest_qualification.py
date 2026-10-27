#!/usr/bin/env python3
"""C5 guest qualification runner (skeleton): bots, coop modes and survival waves in PCSX2.

The runner launches one PCSX2 instance per run with its own copied data directory and its own Xvfb display, waits
for it with a bounded timeout, and then reads the log it wrote. It never kills a process: no kill, pkill, SIGTERM or
SIGKILL is sent to anything, including PCSX2 processes that were already running (the user's window is never
touched). A run that does not exit inside the timeout is recorded as unterminated, and its rows are refused.

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
    """Decide the rows one run's log supports. Only a normally terminated run with the boot line can claim."""
    result = {row: {"status": "not-claimed", "evidence": []} for row in ROW_NAMES}
    sessions = [parse_session_line(m.group(1)) for m in SESSION_LINE.finditer(text)]
    if any(session.get("status") != "qualified" for session in sessions):
        for row in ROW_NAMES:
            result[row]["status"] = "refused"
            result[row]["evidence"].append("a session is not status=qualified (measuring or unlabelled): no claims")
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
                    returncode, rows: dict) -> dict:
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
        "terminated_ok": bool(exited and returncode == 0),
        "returncode": returncode,
        "boot_line": BOOT_MARKER in text,
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


def launch(elf: Path, data: Path, log: Path, display: str) -> subprocess.Popen:
    env = {**os.environ, "DISPLAY": display}
    command = [str(PCSX2), "-batch", "-nogui", "-datapath", str(data),
               "-logfile", str(log), "-elf", str(elf)]
    process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    if process.pid in PROTECTED_PIDS:
        raise RuntimeError("refusing: pid collides with the user's PCSX2 window")
    return process


def wait_bounded(process: subprocess.Popen, timeout: float) -> bool:
    """Waits for the run to exit on its own. Returns True when it exited. Never signals the process."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return True
        time.sleep(0.5)
    return process.poll() is not None


def run_once(args) -> dict:
    elf = args.elf.resolve()
    run_dir = OUT / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    record = {"run": args.run_name, "elf": str(elf), "elf_sha256": sha256(elf), "dry_run": args.dry_run}
    if args.dry_run:
        record["rows"] = {row: {"status": "not-run", "evidence": ["dry run: PCSX2 not started"]}
                          for row in ROW_NAMES}
        record["note"] = "dry run: PCSX2 not started"
        return record
    log = run_dir / "pcsx2.log"
    data = prepare_run(args.data_template, run_dir)
    process = launch(elf, data, log, args.display)
    record["pid"] = process.pid
    exited = wait_bounded(process, args.timeout)
    record["exited"] = exited
    record["returncode"] = process.returncode if exited else None
    text = log.read_text(errors="replace") if log.exists() else ""
    record["log_bytes"] = len(text)
    record["rows"] = evaluate_log(text, terminated_ok=exited and process.returncode == 0)
    if log.exists():
        record["evidence"] = evidence_record(args.run_name, record["elf_sha256"], sha256(log), text, exited,
                                             record["returncode"], record["rows"])
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--elf", type=Path, help="HCU ELF built with the C5 modules")
    parser.add_argument("--data-template", type=Path, help="PCSX2 data directory copied for the run")
    parser.add_argument("--display", default=os.environ.get("C5_GUEST_DISPLAY", ":98"),
                        help="private Xvfb display (must be started by the operator; never the user's)")
    parser.add_argument("--timeout", type=float, default=600.0)
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
