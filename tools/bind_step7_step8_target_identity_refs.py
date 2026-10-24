#!/usr/bin/env python3
"""Verify row-specific file bindings for retained Step 7/8 target evidence.

This report supplements the core-ledger audit where a historical report names a
digest but not a repository-relative path. It only binds a reported identity
when the current bytes at the referenced path reproduce that digest. It never
edits the ledger or changes evidence levels/results.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json"
OUT = ROOT / "docs/reports/m2-step7-step8-target-identity-bindings-2026-10-22.json"
PACKAGE_INDEX = ROOT / "build/m2-mp-render-assets/tag-bsp-capacity-floor-v2.json"
EMU_CONFIG = ROOT / ".local/emulator.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def identity_hashes(row: dict, categories: tuple[str, ...]) -> set[str]:
    result: set[str] = set()
    all_ids = row.get("fixture_input_hashes", {})
    for category in categories:
        for item in all_ids.get(category, []):
            if item.get("sha256"):
                result.add(item["sha256"])
            if item.get("local_sha256"):
                result.add(item["local_sha256"])
    return result


def main() -> None:
    ledger = json.loads(LEDGER.read_text())
    rows = ledger["evidence"][:25]
    package_index = json.loads(PACKAGE_INDEX.read_text())
    emulator_config = json.loads(EMU_CONFIG.read_text()) if EMU_CONFIG.is_file() else None
    bindings: list[dict] = []
    unavailable: list[dict] = []
    checks = 0

    def bind(row_index: int, digest: str, path: Path, role: str, basis: str,
             source_report: str, categories: list[str] | None = None) -> None:
        nonlocal checks
        row = rows[row_index]
        cats = categories or ["reported_hash_pins"]
        declared = sorted(c for c in cats if digest in identity_hashes(row, (c,)))
        if not declared:
            raise RuntimeError(f"digest {digest} is not declared by core row {row_index}")
        path = path.resolve()
        checks += 1
        actual = sha(path) if path.is_file() else None
        if actual != digest:
            raise RuntimeError(f"identity mismatch for row {row_index} {path}: expected {digest}, got {actual}")
        try:
            report_path = path.relative_to(ROOT).as_posix()
            external = False
        except ValueError:
            report_path = str(path)
            external = True
        bindings.append({
            "core_row_index": row_index,
            "step": row["step"],
            "subcheck": row["subcheck"],
            "evidence_level": row["evidence_level"],
            "role": role,
            "sha256": digest,
            "path": report_path,
            "external_local_path": external,
            "bytes": path.stat().st_size,
            "categories_bound": declared,
            "source_report": source_report,
            "basis": basis,
            "bytes_match_reported_digest": True,
        })

    # The two PCSX2 collision/PVS rows share the all-map query report, but their
    # source identities are independently declared on each ledger row.
    row4 = rows[4]
    run4_dir = ROOT / "build/hcu-ps2-closure/emulator-m1-recompiler-86589bd6ec8442599f1f40698d50abd5"
    result4 = run4_dir / "result.json"
    log4 = run4_dir / "emulog.txt"
    r4 = json.loads(result4.read_text())
    bind(4, "dd67e9d3a5ff447aad881e1079bfbac1f20888969bb305244cc47668c1656853", log4,
         "PCSX2 guest log", "current emulog.txt bytes match report-pinned guest-log SHA-256",
         "docs/reports/m2-step8-mp-13-map-pcsx2-query-2026-10-22.md",
         ["log_hashes", "reported_hash_pins"])
    bind(4, "b72b3f69d8eeead6e87c227a1d0d98ab2351e3ed0560fad7cb8b72d0e308691f", result4,
         "PCSX2 run result manifest", "current result.json bytes match report-pinned runner JSON SHA-256",
         "docs/reports/m2-step8-mp-13-map-pcsx2-query-2026-10-22.md",
         ["reported_hash_pins"])
    target_bios = Path("/home/ai/Documents/Halo/SCPH-30001.rom0")
    if target_bios.is_file() and sha(target_bios) == "b0bf7184d50a209cf7ceb1ab0eb3a0c9b8c583f5f6b3c819e6536f282b93063b":
        bind(4, "b0bf7184d50a209cf7ceb1ab0eb3a0c9b8c583f5f6b3c819e6536f282b93063b", target_bios,
             "PS2 BIOS ROM", "same exact BIOS bytes are path-bound by the paired current-target probe report",
             "docs/reports/m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.json",
             ["executable_hashes", "reported_hash_pins"])
    # The retained result manifest independently identifies these external
    # files. Do not copy the BIOS or emulator image into the repository.
    if emulator_config:
        bios_path = Path(emulator_config["bios"]).resolve()
        emulator_path = Path(emulator_config["binary"]).resolve()
        for digest, path, role in (
            ("b0bf7184d50a209cf7ceb1ab0eb3a0c9b8c583f5f6b3c819e6536f282b93063b", bios_path, "PS2 BIOS ROM"),
            ("0c46bb6a88aa2782b10853a7b07cf3387ba99cbef2b966372cd2315b8571abea", emulator_path, "PCSX2 AppImage"),
        ):
            if r4.get("bios_sha256" if role == "PS2 BIOS ROM" else "emulator_sha256") != digest:
                raise RuntimeError(f"row 4 manifest does not corroborate {role} digest {digest}")
            bind(4, digest, path, role,
                 "path sourced from .local/emulator.json; bytes hash to the runner result.json pin and the report pin",
                 "docs/reports/m2-step8-mp-13-map-pcsx2-query-2026-10-22.md",
                 ["input_hashes", "source_hashes", "reported_hash_pins"])
    else:
        unavailable.append({"core_row_index": 4, "role": "BIOS and PCSX2 paths", "reason": ".local/emulator.json is unavailable"})

    # Row 5 and row 12 report the same 13 package digest set. The capacity
    # inventory supplies each exact output path; every package is rehashed.
    maps = {m["map"]: m for m in package_index["maps"]}
    all_map_report = "docs/reports/step8-mp-all-map-candidate-pcsx2-2026-10-22.md"
    for row_index in (5, 12):
        declared = identity_hashes(rows[row_index], ("reported_hash_pins",))
        for m in maps.values():
            digest = m["package_sha256"]
            if digest in declared:
                bind(row_index, digest, ROOT / m["package_path"], f"{m['map']} all-BSP HP2 package",
                     "tag-bsp-capacity-floor-v2 package_path; current package bytes reproduce report-pinned package_sha256",
                     all_map_report)
        # Preserve both PCSX2 modes and the failed/partial first recompiler
        # attempt as distinct run records.
        runs = [
            ("recompiler", "emulator-m1-recompiler-917db9651dd04ba7b358492437bec36b", "c92935e3a31c7ffb065717af7b44b77385c903d58466ba10140215313e25b921", "65024d7763daeb3f44d83b45cde12e27ccc0421bae9c5926e0ba4e97a0c11787", "failed first attempt; timed out after 11 maps"),
            ("recompiler", "emulator-m1-recompiler-067b2e2564d94f10b8bd3b956b7d2979", "a8cc5da2c8c3a04b3aa5277456da743b370fe5dba69937bb5618292bcbd5a9a1", "d871200f50b2259f819f024a8f238951c783042aebe55c6fb411a3335b458a25", "successful all-13 recompiler run"),
            ("interpreter", "emulator-m1-interpreter-4567e94c92d245ffb74c31fcd26bf208", "4d3c3b4c8cd1ff3e8bb53553c6aae526ba5bcd419ed6626f22c66dbaa66d4ade", "7dae6dc1f90a62f9d60d4ca256faaa2f27e2852dfae44ab86efd2598600f0178", "successful all-13 interpreter run"),
        ]
        for mode, run_dir, result_hash, log_hash, run_note in runs:
            run_path = ROOT / "build/hcu-ps2-closure" / run_dir
            result_path = run_path / "result.json"
            log_path = run_path / "emulog.txt"
            manifest = json.loads(result_path.read_text())
            if manifest.get("mode") != mode or manifest.get("status") not in ("passed", "failed"):
                raise RuntimeError(f"unexpected run metadata for {result_path}")
            # Retain the result status and claimed ELF digest beside each bound file.
            for digest, path, role in ((result_hash, result_path, f"{mode} {run_note} result manifest"),
                                       (log_hash, log_path, f"{mode} {run_note} guest log")):
                bind(row_index, digest, path, role,
                     f"current run artifact bytes reproduce report-pinned digest; result status={manifest.get('status')}; ELF pin={manifest.get('elf_sha256')}",
                     all_map_report)

    # Render-owner report names the runner and C fixture digests but omits local
    # paths for those two source identities. Bind only exact current file bytes.
    for digest, path, role in (
        ("14a1d05e95cc245fa2be901c2a29c25f232a67453c711316ebe0f640311b5cfe", ROOT / "tools/test_halo_ps2_mp_render_cache_stress.py", "render stress runner"),
        ("e2c48ceb50749b55b02f2935960fca8aef0ce09bbac536d8bca4a2d7d269a4d9", ROOT / "tests/mp_render_cache_stress_main.c", "render stress C fixture"),
    ):
        bind(13, digest, path, role, "current source bytes reproduce the report-pinned SHA-256",
             "docs/reports/mp-step8-live-render-cache-stress-2026-10-22.md",
             ["fixture_hashes", "reported_hash_pins"])

    # The new paired collision/PVS target probe also pins the local emulator and
    # BIOS as labels rather than path fields. Resolve those labels through the
    # same local emulator config, and verify them against the probe's run records.
    if emulator_config:
        target_report = "docs/reports/m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.json"
        target_data = json.loads((ROOT / target_report).read_text())
        for run in target_data["runs"]:
            run_root = ROOT / run["guest_log_path"]
            bind(24, run["guest_log_sha256"], run_root, f"{run['mode']} current-target guest log",
                 "current-target probe run record names exact output path and current bytes match its digest",
                 target_report, ["log_hashes"])
            bind(24, run["elf_sha256"], Path(run["elf_path"]), f"{run['mode']} current-target diagnostic ELF",
                 "current-target probe run record names exact output path and current bytes match its digest",
                 target_report, ["executable_hashes"])
            for digest, path, role, manifest_key in (
                ("b0bf7184d50a209cf7ceb1ab0eb3a0c9b8c583f5f6b3c819e6536f282b93063b", Path(emulator_config["bios"]).resolve(), "PS2 BIOS ROM", "bios_sha256"),
                ("0c46bb6a88aa2782b10853a7b07cf3387ba99cbef2b966372cd2315b8571abea", Path(emulator_config["binary"]).resolve(), "PCSX2 executable", "emulator_sha256"),
            ):
                if run.get(manifest_key) != digest:
                    raise RuntimeError(f"current-target {run['mode']} manifest does not corroborate {role} digest")
                bind(24, digest, path, f"{run['mode']} {role}",
                     "local emulator config path and current bytes match the paired target-run manifest pin",
                     target_report,
                     ["executable_hashes", "log_hashes"])

        # Search retained run INIs and candidate settings artifacts. The source
        # probe did not record a path, so only byte-identical artifacts qualify.
        settings_roots = [ROOT / "build", ROOT / ".local"]
        settings_candidates = []
        for base in settings_roots:
            if base.exists():
                settings_candidates.extend(p for p in base.rglob("*") if p.is_file() and
                                           (p.name.lower().endswith((".ini", ".conf", ".dat")) or p.name.lower().startswith("pcsx2")))
        settings_by_mode = {
            "interpreter": "6544719db660b6be9b277f983a5a270ff9eb83ccf66c2e77d38a164ee6383a85",
            "recompiler": "29091d26012bf2b9470f2abcdd10b7cca2e8d7ae6e2c6fc2f4134348c52540a2",
        }
        settings_investigation = []
        for run in target_data["runs"]:
            digest = run["settings_sha256"]
            matches = [p for p in settings_candidates if sha(p) == digest]
            if matches:
                for p in matches:
                    bind(24, digest, p, f"{run['mode']} PCSX2 settings", "retained settings bytes reproduce run-pinned settings digest",
                         target_report, ["log_hashes"])
            else:
                run_ini = ROOT / run["run_directory"] / "data/PCSX2/inis/PCSX2.ini"
                current_hash = sha(run_ini) if run_ini.is_file() else None
                unavailable.append({
                    "core_row_index": 24, "sha256": digest,
                    "role": f"{run['mode']} PCSX2 settings",
                    "reason": "no retained candidate settings file matches the report-pinned digest; run directory retains only a different current INI, so the historical settings bytes cannot be bound",
                    "current_run_ini_path": run_ini.relative_to(ROOT).as_posix(),
                    "current_run_ini_sha256": current_hash,
                    "candidate_files_searched": len(settings_candidates),
                    "matching_candidate_paths": [],
                })
            settings_investigation.append({
                "mode": run["mode"], "reported_sha256": digest,
                "current_run_ini_path": (run_ini.relative_to(ROOT).as_posix() if run_ini.is_relative_to(ROOT) else str(run_ini)),
                "current_run_ini_sha256": current_hash,
                "matching_retained_paths": [p.resolve().relative_to(ROOT).as_posix() for p in matches],
                "status": "bound" if matches else "unavailable",
            })
    else:
        settings_investigation = []
        unavailable.append({"core_row_index": 24, "role": "PCSX2 BIOS/emulator/settings paths", "reason": ".local/emulator.json is unavailable"})

    # Include a compact row-9 target anchor as a control: unlike the all-map
    # run, its report already carries explicit artifact paths.
    path_report = "docs/reports/m2-step7-mp-target-astar-2026-10-22.md"
    path_run = ROOT / "build/hcu-ps2-closure/emulator-m1-recompiler-80c299fa2b81415889d742d698a8c116"
    for digest, path, role in (
        ("aa1a711dfef03de8e09d7f6337d25050eb949d2355501eb56978b254bbdad3e2", path_run / "step7-path-validation.json", "path-validation output"),
        ("3e118a0f693b0737aa20f781ad300ca8f2ce211f7f77115425e223a986628e42", path_run / "result.json", "pathfinding guest result manifest"),
        ("5ddc2b0bb5b4be8795fa5eadcc92cf69db42e41f0837257f14bf085177158fd1", path_run / "emulog.txt", "pathfinding guest log"),
        ("3f8efe1407f44a1f74d3a5f0d8c7c8941173d19f54ef17ffef258ce320ff93e3", ROOT / "build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-capacity-tagcache-4477120.elf", "pathfinding guest ELF"),
    ):
        # These are explicit report anchors, even though the core audit already
        # finds the row-9 files through report-adjacent path scanning.
        if not path.is_file() or sha(path) != digest:
            raise RuntimeError(f"pathfinding anchor mismatch: {path}")
        bindings.append({"core_row_index": 9, "step": rows[9]["step"], "subcheck": rows[9]["subcheck"],
                         "evidence_level": rows[9]["evidence_level"], "role": role, "sha256": digest,
                         "path": path.resolve().relative_to(ROOT).as_posix(), "external_local_path": False,
                         "bytes": path.stat().st_size, "categories_bound": [], "source_report": path_report,
                         "basis": "explicit target-run path and digest in the report, rehashed from current bytes",
                         "bytes_match_reported_digest": True})

    # Preserve the two historic pins whose files are no longer present. A result
    # manifest states the old ELF SHA but cannot substitute for the ELF bytes.
    unavailable.extend([
        {"core_row_index": i, "sha256": "beee81293b9059ca2f51c04e6b49897e607e332750fe7f14fa201c2077258bf0",
         "role": "all-map diagnostic ELF", "reason": "result manifests retain this ELF digest, but current ELF path bytes differ; no matching ELF file was found in the current build outputs"}
        for i in (5, 12)
    ])
    unavailable.extend([
        {"core_row_index": i, "sha256": "613b3e3bf0f1cf5a45679050df9cb37839973379a5b0b644937af43c809e4c7c",
         "role": "all-map diagnostic build report", "reason": "hash is cited in prose but no file with matching bytes is present in current build outputs"}
        for i in (5, 12)
    ])

    target_rows = [4, 5, 9, 12, 13, 24]
    audit_path = ROOT / "docs/reports/m2-step7-step8-core-ledger-binding-audit-2026-10-22.json"
    audit = json.loads(audit_path.read_text()) if audit_path.is_file() else None
    before = {}
    if audit and audit.get("ledger_sha256") == sha(LEDGER):
        before = {i: len(next(x for x in audit["rows"] if x["core_row_index"] == i)["unresolved_identities"])
                  for i in target_rows}
    after_expected = {4: 0, 5: 2, 9: 0, 12: 2, 13: 0, 24: 2}
    out = {
        "format": "hcu-m2-step7-step8-target-identity-bindings-v1",
        "ledger_path": str(LEDGER.relative_to(ROOT)),
        "ledger_sha256": sha(LEDGER),
        "package_index_path": str(PACKAGE_INDEX.relative_to(ROOT)),
        "package_index_sha256": sha(PACKAGE_INDEX),
        "identity_policy": "A binding is recorded only when the current bytes at the named path reproduce the digest. External BIOS/AppImage paths are read and hashed in place; no proprietary bytes are copied into the repository. Historical ELF/build-report pins stay unbound unless their original bytes are found.",
        "target_rows": target_rows,
        "row_unresolved_count_before_from_current_audit": before,
        "row_unresolved_count_after_expected_when_bindings_are_consumed": after_expected,
        "verified_binding_count": len(bindings),
        "file_hash_checks": checks,
        "verified_bindings": bindings,
        "unavailable_or_unbound_historical_identities": unavailable,
        "current_target_settings_investigation": settings_investigation,
        "limitation": "This artifact adds identity references only. It does not upgrade result/evidence levels, the all-map guest qualification, renderer acceptance, or Step 7/8 closure.",
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"bindings": len(bindings), "file_hash_checks": checks,
                      "before": before, "after_expected": after_expected,
                      "unavailable": len(unavailable), "ledger_sha256": out["ledger_sha256"]}, sort_keys=True))
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
