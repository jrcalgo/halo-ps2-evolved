#!/usr/bin/env python3
"""Check whether historical Step 8 workload pins still have exact bytes locally.

This deliberately does not rebuild any fixture or promote a current source
file as a match for an older digest. It hashes current worktree files and all
Git blob objects in the parent and relevant submodule object stores.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/reports/m2-step8-historical-workload-pin-availability-2026-10-22.json"

PINS = {
    "d3f36c62a3915c4565b0ab8b21de05f540a650a6cb1d727636a4fc5ec12a21df": {
        "description": "Historical CE four-local-player diagnostic source",
        "expected_path": "submodules/halo-ce-universal/source/main/ps2_m2_ui_lifecycle_test.c",
        "report_paths": [
            "docs/reports/m2-step8-ce-four-local-player-workload-2026-10-22.md",
            "docs/reports/m2-step8-ce-actor-workload-boundary.md",
        ],
    },
    "4aaa2fb86459d77e4a5527b1109558cfcc17190517fa55e9006ba59b7ff59c9b": {
        "description": "Historical four-local-player closure-driver source pin",
        "expected_path": "tools/hcu_ps2_closure.py",
        "report_paths": ["docs/reports/m2-step8-ce-four-local-player-workload-2026-10-22.md"],
    },
    "21188c9068a30a0fb5b4bda3c1ce35902745de51aa48e757c80c9c7ea9f8d6be": {
        "description": "Historical four-local-player linker-driver source pin",
        "expected_path": "tools/hcu_ps2_link.py",
        "report_paths": ["docs/reports/m2-step8-ce-four-local-player-workload-2026-10-22.md"],
    },
    "987af62554e1cc95b299ce361d743300c617f96a7cac24028c1a338c4da97d88": {
        "description": "Historical CE actor ILP32 runner source pin",
        "expected_path": "tools/test_hcu_step8_ce_actor_ilp32.py",
        "report_paths": ["docs/reports/m2-step8-ce-actor-ilp32-attempt.md"],
    },
    "beee81293b9059ca2f51c04e6b49897e607e332750fe7f14fa201c2077258bf0": {
        "description": "Historical all-map candidate PCSX2 ELF",
        "expected_path": "build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-capacity-tagcache-4477120.elf",
        "report_paths": ["docs/reports/step8-mp-all-map-candidate-pcsx2-2026-10-22.md"],
    },
    "613b3e3bf0f1cf5a45679050df9cb37839973379a5b0b644937af43c809e4c7c": {
        "description": "Historical all-map candidate build report JSON",
        "expected_path": "build/hcu-parent-link-probe/result-step8-mp-capacity-tagcache-4477120.json",
        "report_paths": ["docs/reports/step8-mp-all-map-candidate-pcsx2-2026-10-22.md"],
    },
    "6544719db660b6be9b277f983a5a270ff9eb83ccf66c2e77d38a164ee6383a85": {
        "description": "Historical PCSX2 interpreter settings for the 13-map target probe",
        "expected_path": "build/hcu-ps2-closure/emulator-m1-interpreter-c98db8627d234473a8dc263c3288852d/data/PCSX2/inis/PCSX2.ini",
        "report_paths": ["docs/reports/m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.json"],
    },
    "29091d26012bf2b9470f2abcdd10b7cca2e8d7ae6e2c6fc2f4134348c52540a2": {
        "description": "Historical PCSX2 recompiler settings for the 13-map target probe",
        "expected_path": "build/hcu-ps2-closure/emulator-m1-recompiler-5b536c94e7b44a4ca19636cc2cfecacd/data/PCSX2/inis/PCSX2.ini",
        "report_paths": ["docs/reports/m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.json"],
    },
}

REPOSITORIES = [
    ".",
    "submodules/halo-ce-universal",
    "submodules/halo-ps2",
    "submodules/halo-64",
]

# These roots cover exact report-named artifacts, the complete retained PCSX2
# closure-run tree (for moved/copied settings and logs), and the local emulator
# config area searched by the target-identity binder. Unrelated build outputs
# outside these roots are not treated as candidates for these four artifact
# classes.
SEARCH_ROOTS = [
    # Exact all-map candidate artifacts and nearby retained outputs.
    "build/hcu-parent-link-probe",
    "build/hcu-step8-actor-ilp32",
    "build/step8-vehicle-seat-actors",
    "build/hcu-step8-mp-workload",
    "build/hcu-ps2-closure/emulator-m1-recompiler-3a78e285374b453f9cb18b6e2ae61fdf",
    "build/hcu-ps2-closure/emulator-m1-interpreter-15c010c1a47041618f6c159e1c41621e",
    # The paired current-target run dirs above are known from the report; scan
    # the full retained closure root for moved/copied matching INIs or logs.
    "build/hcu-ps2-closure",
    # The target identity binder also checked this retained local config root.
    ".local",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scan_worktree() -> dict:
    matches: dict[str, list[str]] = {pin: [] for pin in PINS}
    files_checked = 0
    bytes_checked = 0
    errors = []
    candidates = {ROOT / details["expected_path"] for details in PINS.values()}
    for rel in SEARCH_ROOTS:
        directory = ROOT / rel
        if directory.is_dir():
            candidates.update(path for path in directory.rglob("*") if path.is_file())
    for path in sorted(candidates):
        if not path.is_file() or ".git" in path.parts:
            continue
        try:
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                    size += len(block)
            files_checked += 1
            bytes_checked += size
            value = digest.hexdigest()
            if value in matches:
                matches[value].append(path.relative_to(ROOT).as_posix())
        except OSError as exc:
            errors.append({"path": path.relative_to(ROOT).as_posix(), "error": str(exc)})
    return {"files_checked": files_checked, "bytes_checked": bytes_checked,
            "matches": matches, "read_errors": errors}


def scan_git_blobs(repo_rel: str) -> dict:
    repo = ROOT / repo_rel
    listing = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch-all-objects",
         "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
        check=True, capture_output=True, text=True,
    ).stdout
    objects = [line.split() for line in listing.splitlines()]
    blobs = [row for row in objects if len(row) == 3 and row[1] == "blob"]
    matches: dict[str, list[dict[str, str]]] = {pin: [] for pin in PINS}
    # Batching keeps process overhead bounded while permitting exact content
    # hashes over every object, including unreachable local objects.
    for offset in range(0, len(blobs), 128):
        batch = blobs[offset:offset + 128]
        result = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "--batch"],
            input="".join(row[0] + "\n" for row in batch).encode("ascii"),
            check=True, capture_output=True,
        ).stdout
        cursor = 0
        for oid, _, expected_size in batch:
            header_end = result.find(b"\n", cursor)
            header = result[cursor:header_end].split()
            cursor = header_end + 1
            size = int(header[2])
            payload = result[cursor:cursor + size]
            cursor += size + 1
            if size != int(expected_size):
                raise RuntimeError(f"Git object size changed while reading {repo_rel}:{oid}")
            digest = sha256_bytes(payload)
            if digest in matches:
                matches[digest].append({"repository": repo_rel, "git_blob_oid": oid})
    return {"objects_checked": len(objects), "blob_objects_checked": len(blobs),
            "matches": matches}


def main() -> None:
    worktree = scan_worktree()
    git_scans = {repo: scan_git_blobs(repo) for repo in REPOSITORIES}
    pins = {}
    for digest, details in PINS.items():
        worktree_matches = worktree["matches"][digest]
        blob_matches = [match for scan in git_scans.values()
                        for match in scan["matches"][digest]]
        pins[digest] = {
            **details,
            "report_evidence": [
                {
                    "path": report_path,
                    "sha256": sha256_bytes((ROOT / report_path).read_bytes())
                    if (ROOT / report_path).is_file() else None,
                    "contains_pin": digest.encode("ascii") in (ROOT / report_path).read_bytes()
                    if (ROOT / report_path).is_file() else False,
                }
                for report_path in details["report_paths"]
            ],
            "current_expected_path_sha256": (
                sha256_bytes((ROOT / details["expected_path"]).read_bytes())
                if (ROOT / details["expected_path"]).is_file() else None
            ),
            "exact_worktree_matches": worktree_matches,
            "exact_git_blob_matches": blob_matches,
            "availability": "found" if worktree_matches or blob_matches else "not_found",
        }
    report = {
        "format": "hcu-step8-historical-workload-pin-availability-v1",
        "scope": "Exact-byte availability only. Current expected source paths and report-linked workload build roots are scanned; no rebuilt or current substitute is treated as historical evidence.",
        "worktree_search_roots": [*sorted({p.parent.relative_to(ROOT).as_posix() for p in (ROOT / d["expected_path"] for d in PINS.values())}), *SEARCH_ROOTS],
        "parent_head": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                       check=True, capture_output=True, text=True).stdout.strip(),
        "worktree_scan": {k: v for k, v in worktree.items() if k != "matches"},
        "git_object_scans": {
            repo: {k: v for k, v in scan.items() if k != "matches"}
            for repo, scan in git_scans.items()
        },
        "pins": pins,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": OUTPUT.relative_to(ROOT).as_posix(),
                      "worktree_files_checked": worktree["files_checked"],
                      "worktree_bytes_checked": worktree["bytes_checked"],
                      "pins_found": sum(p["availability"] == "found" for p in pins.values()),
                      "pins_not_found": sum(p["availability"] == "not_found" for p in pins.values()),
                      "git_blob_objects_checked": sum(s["blob_objects_checked"] for s in git_scans.values())},
                     sort_keys=True))


if __name__ == "__main__":
    main()
