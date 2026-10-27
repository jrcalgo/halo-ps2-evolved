#!/usr/bin/env python3
"""Generate the C5 local-setup qualified rows from the measured evidence.

Inputs (read only):
  src/stream/hcu_memory_profile.c                           partition table hcu_partition_table_v2
  docs/reports/m2-c2-profile-guarded-fit-2026-10-24.json    per-profile guest fit
  docs/reports/m2-c2-profile-matrix-2026-10-24.json         per-row matrix pass
  docs/reports/c5-guest-*.json                              guest runs recorded by tools/c5_guest_qualification.py

Outputs:
  src/stream/hcu_local_setup_rows.inc                       generated row table
  docs/reports/m4-c5-local-setup-rows-2026-10-26.json       evidence and per-row reasons

A row is qualified only from recorded guest evidence. A guest record qualifies a map row when all of these hold:
  - format hcu-c5-guest-evidence-v1, the run exited with status 0, the HALO_PS2_LOCAL boot line was seen,
    and a session-hash line was seen;
  - the session is a stock coop session whose start line says status=qualified (a MEASURE run says
    status=measuring and never qualifies; neither does a session with no status);
  - the session's map is the row's map, its difficulty is one of the four names, and its coop mode's row is
    claimed (and, with bots, every bots-* row is claimed);
  - the map also has a measured C2 load fit (the checks above this module's inputs).
The record is self-reported by the runner. The generator checks its shape and its claims, not the emulator.

Per map, the qualified difficulty bits are the difficulties with a qualifying record. max_humans and max_bots are
the smallest of the per-difficulty maxima seen, so a row admits no more than every qualified difficulty did.
With no qualifying record a row stays qualified=0, with an empty difficulty mask and zero population.

Usage: python3 tools/c5_local_setup_rows.py [--check] [--root DIR]
  --check   compare the generated files with the committed ones and exit 1 when they differ (writes nothing)
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPS = ("beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout", "damnation", "hangemhigh",
        "longest", "prisoner", "putput", "ratrace", "sidewinder", "wizard")
GAMEPLAY_ROLES = ("marine_shotgun_4p4bot", "mounted_gunner_4p4bot")
EVIDENCE_FORMAT = "hcu-c5-guest-evidence-v1"
EVIDENCE_GLOB = "docs/reports/c5-guest-*.json"
DIFFICULTY_BITS = {"easy": 1, "normal": 2, "heroic": 3, "legendary": 4}   # CE difficulty -> enum value in hcu_local_setup.h
COOP_ROW_FOR_NUMBER = {1: "coop-team-slayer", 3: "coop-team-oddball", 5: "coop-team-king", 6: "coop-ctf",
                       8: "coop-team-race"}
BOT_ROWS = ("bots-navigate", "bots-fight", "bots-score", "bots-die", "bots-respawn")
PROFILE_RE = re.compile(r'\{\s*"([a-z0-9_]+)",\s*\{')
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX16 = re.compile(r"^[0-9a-f]{16}$")

POPULATION_GAPS = [
    "no qualifying guest evidence recorded for this map (docs/reports/c5-guest-*.json)",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def partition_names(source: str) -> list:
    start = source.index("hcu_partition_table_v2[] = {")
    end = source.index("};", start)
    return PROFILE_RE.findall(source[start:end])


def load_fit_by_map(root: Path) -> dict:
    """Load-fit verdict per map, as the C2 evidence gives it (unchanged from the first generator)."""
    names = partition_names((root / "src/stream/hcu_memory_profile.c").read_text())
    fit = json.loads((root / "docs/reports/m2-c2-profile-guarded-fit-2026-10-24.json").read_text())
    matrix = json.loads((root / "docs/reports/m2-c2-profile-matrix-2026-10-24.json").read_text())
    fit_by_name = {p["profile"]: p for p in fit["profiles"]}
    matrix_by_name = {r["row"]: r for r in matrix["rows"]}
    profiles = []
    for name in names:
        reasons = []
        fit_row = fit_by_name.get(name)
        mrow = matrix_by_name.get(name)
        if fit_row is None:
            reasons.append("no guarded fit record for this profile")
        else:
            if fit_row.get("profile_specific_guest_fit") != "measured_pass":
                reasons.append("guest fit not measured_pass")
            if not fit_row.get("hcp_package_sha256_matches_manifest"):
                reasons.append("package sha does not match manifest")
        if mrow is None:
            reasons.append("no profile matrix row")
        elif mrow.get("pass") is not True:
            reasons.append("profile matrix row did not pass")
        if name == "ui":
            reasons.append("menu package, not a gameplay setup target")
        if name == "bots_sidewinder":
            reasons.append("static package-derived candidate, no measured fit")
        profiles.append({
            "profile": name,
            "map": name.split("_")[0] if name not in ("ui", "bots_sidewinder") else name,
            "role": next((r for r in GAMEPLAY_ROLES if name.endswith(r)), None),
            "load_fit_measured": not reasons,
            "reasons": reasons,
        })
    verdict = {}
    for name in MAPS:
        roles = {p["role"]: p for p in profiles if p["map"] == name and p["role"]}
        verdict[name] = all(roles.get(r, {}).get("load_fit_measured") for r in GAMEPLAY_ROLES)
    return {"profiles": profiles, "by_map": verdict}


def is_qualifying(record: dict, load_ok: bool):
    """Returns (True, difficulty, humans, bots, map) for a record that qualifies a row, else (False, reason)."""
    if not isinstance(record, dict) or record.get("format") != EVIDENCE_FORMAT:
        return False, "not a hcu-c5-guest-evidence-v1 record"
    if record.get("terminated_ok") is not True or record.get("returncode") != 0:
        return False, "run did not exit with status 0"
    if record.get("boot_line") is not True:
        return False, "no HALO_PS2_LOCAL boot line"
    if not isinstance(record.get("session_hash"), str) or not HEX16.match(record["session_hash"]):
        return False, "no session-hash line"
    if not isinstance(record.get("elf_sha256"), str) or not HEX64.match(record["elf_sha256"]):
        return False, "no ELF sha256"
    session = record.get("session")
    if not isinstance(session, dict):
        return False, "no session record"
    if session.get("status") != "qualified":
        return False, "session status is %r: no qualification claim" % (session.get("status"),)
    if session.get("mode") != "coop":
        return False, "not a stock coop session (survival has no row)"
    map_name = session.get("map")
    if map_name not in MAPS:
        return False, "map %r has no row" % (map_name,)
    if not load_ok:
        return False, "map lacks a measured load fit"
    if session.get("difficulty") not in DIFFICULTY_BITS:
        return False, "difficulty %r is not one of the four" % (session.get("difficulty"),)
    humans, bots, coop = session.get("humans"), session.get("bots"), session.get("coop")
    if not (isinstance(humans, int) and 1 <= humans <= 4):
        return False, "humans outside 1..4"
    if not (isinstance(bots, int) and 0 <= bots <= 12):
        return False, "bots outside 0..12"
    if coop not in COOP_ROW_FOR_NUMBER:
        return False, "coop mode %r has no row" % (coop,)
    rows = record.get("rows") or {}
    if (rows.get(COOP_ROW_FOR_NUMBER[coop]) or {}).get("status") != "claimed":
        return False, "%s not claimed by this run" % COOP_ROW_FOR_NUMBER[coop]
    if bots > 0:
        missing = [r for r in BOT_ROWS if (rows.get(r) or {}).get("status") != "claimed"]
        if missing:
            return False, "bot rows not claimed: " + ", ".join(missing)
    return True, session["difficulty"], humans, bots, map_name


def load_evidence(root: Path) -> list:
    """Each evidence file, parsed. A file that does not parse is reported, never ignored silently."""
    items = []
    for path in sorted(root.glob(EVIDENCE_GLOB)):
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError) as error:
            items.append({"file": path.relative_to(root).as_posix(), "sha256": sha256(path),
                          "record": None, "error": "unreadable: %s" % error.__class__.__name__})
            continue
        items.append({"file": path.relative_to(root).as_posix(), "sha256": sha256(path),
                      "record": record, "error": None})
    return items


def build(root: Path) -> tuple:
    """Returns (inc_text, report) for the repository at root. Writes nothing."""
    fit = load_fit_by_map(root)
    evidence = load_evidence(root)

    per_map = {name: {"diffs": {}, "records": []} for name in MAPS}
    evidence_report = []
    for item in evidence:
        entry = {"file": item["file"], "sha256": item["sha256"]}
        if item["record"] is None:
            entry.update({"decision": "rejected", "reason": item["error"]})
        else:
            record = item["record"]
            entry["run"] = record.get("run") if isinstance(record, dict) else None
            entry["session_status"] = (record.get("session") or {}).get("status") \
                if isinstance(record, dict) and isinstance(record.get("session"), dict) else None
            map_name = (record.get("session") or {}).get("map") if isinstance(record, dict) else None
            ok = is_qualifying(record, fit["by_map"].get(map_name, False))
            if ok[0]:
                _, difficulty, humans, bots, _map = ok
                bucket = per_map[map_name]["diffs"].setdefault(difficulty, {"humans": 0, "bots": 0})
                bucket["humans"] = max(bucket["humans"], humans)
                bucket["bots"] = max(bucket["bots"], bots)
                entry.update({"decision": "qualifies", "map": map_name, "difficulty": difficulty,
                              "humans": humans, "bots": bots})
            else:
                entry.update({"decision": "no-claim", "reason": ok[1],
                              "map": map_name if map_name in MAPS else None})
        evidence_report.append(entry)

    maps = []
    for name in MAPS:
        diffs = per_map[name]["diffs"]
        if diffs:
            mask = 0
            for difficulty in diffs:
                mask |= 1 << DIFFICULTY_BITS[difficulty]
            max_humans = min(v["humans"] for v in diffs.values())
            max_bots = min(v["bots"] for v in diffs.values())
            qualified = True
            reasons = []
        else:
            mask, max_humans, max_bots, qualified = 0, 0, 0, False
            reasons = list(POPULATION_GAPS)
        if not fit["by_map"][name]:
            reasons.insert(0, "a gameplay role lacks a measured load fit")
        maps.append({"map": name, "mode": "HCU_LOCAL_MODE_STOCK_COOP", "load_fit_measured": fit["by_map"][name],
                     "qualified": qualified, "difficulty_mask": mask, "max_humans": max_humans,
                     "max_bots": max_bots, "difficulties": sorted(diffs), "reasons": reasons})

    rows_inc = [
        "/* Generated by tools/c5_local_setup_rows.py from the C2 and guest evidence.",
        " * Do not edit by hand. A row is qualified=1 only with recorded guest evidence (docs/reports/c5-guest-*.json):",
        " * see the report at docs/reports/m4-c5-local-setup-rows-2026-10-26.json. */",
        "#define HCU_LOCAL_GENERATED_ROW_COUNT %d" % len(maps),
        "static const hcu_local_qualified_row hcu_local_generated_rows[HCU_LOCAL_GENERATED_ROW_COUNT] = {",
    ]
    for m in maps:
        rows_inc.append('\t{ "%s", %s, 0x%xu, %du, %du }, /* qualified=%d load_fit=%d */' % (
            m["map"], m["mode"], m["difficulty_mask"], m["max_humans"], m["max_bots"],
            1 if m["qualified"] else 0, 1 if m["load_fit_measured"] else 0))
    rows_inc.append("};")
    inc_text = "\n".join(rows_inc) + "\n"

    qualified_count = sum(1 for m in maps if m["qualified"])
    inputs = {
        "src/stream/hcu_memory_profile.c": sha256(root / "src/stream/hcu_memory_profile.c"),
        "docs/reports/m2-c2-profile-guarded-fit-2026-10-24.json":
            sha256(root / "docs/reports/m2-c2-profile-guarded-fit-2026-10-24.json"),
        "docs/reports/m2-c2-profile-matrix-2026-10-24.json":
            sha256(root / "docs/reports/m2-c2-profile-matrix-2026-10-24.json"),
    }
    report = {
        "format": "hcu-c5-local-setup-rows-v2",
        "date": "2026-10-26",
        "generator": "tools/c5_local_setup_rows.py",
        "inputs": inputs,
        "evidence": evidence_report,
        "output": {"src/stream/hcu_local_setup_rows.inc": hashlib.sha256(inc_text.encode()).hexdigest()},
        "qualified_row_count": qualified_count,
        "summary": ("%d of %d rows are qualified from recorded guest evidence." % (qualified_count, len(maps))
                    if qualified_count else
                    "No row is qualified for a local setup: no qualifying guest evidence is recorded. "
                    "The C2 evidence is a load-and-release fit with no population or difficulty dimension."),
        "partition_profiles": fit["profiles"],
        "setup_rows": maps,
        "gaps": list(POPULATION_GAPS),
    }
    return inc_text, report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root (tests use a fixture root)")
    parser.add_argument("--check", action="store_true", help="fail when the committed files are stale")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    inc_path = root / "src/stream/hcu_local_setup_rows.inc"
    report_path = root / "docs/reports/m4-c5-local-setup-rows-2026-10-26.json"

    inc_text, report = build(root)
    report_text = json.dumps(report, indent=2) + "\n"
    if args.check:
        stale = [p.name for p, text in ((inc_path, inc_text), (report_path, report_text))
                 if not p.is_file() or p.read_text() != text]
        if stale:
            print("stale: " + ", ".join(stale))
            return 1
        print("rows up to date; qualified rows: %d of %d" % (report["qualified_row_count"], len(MAPS)))
        return 0
    inc_path.write_text(inc_text)
    report_path.write_text(report_text)
    print("wrote %s and %s; qualified rows: %d of %d" % (
        inc_path.name, report_path.name, report["qualified_row_count"], len(MAPS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
