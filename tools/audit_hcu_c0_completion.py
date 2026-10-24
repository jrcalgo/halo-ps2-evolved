#!/usr/bin/env python3
"""Verify the five C0 accounting/preservation requirements, without closing Steps 7/8."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from audit_hcu_c0_row_accounting import audit as row_audit, classify_identities
from audit_hcu_c0_byte_dispositions import build as byte_audit
from audit_step7_step8_identity_freshness import audit_freshness

ROOT = Path(__file__).resolve().parents[1]
LEDGER = "docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json"
OUTPUT = "docs/reports/m2-c0-closure-2026-10-23.json"
VALIDATION = "build/hcu-step7-step8-c0/c0-validation.xml"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    ledger = json.loads((ROOT / LEDGER).read_text())
    rows = ledger["evidence"]
    accounting = row_audit(ledger, ROOT)
    byte_report = byte_audit(ROOT)
    freshness = audit_freshness(ledger, ROOT)
    build_units = ledger["schema_build_units"]
    required_repos = {r["name"] for r in ledger["repository_identities"] + ledger["dependency_identities"]}
    compiled_sources_exact = all(
        sha(ROOT / "submodules/halo-ce-universal" / r["path"]) == r["built_source_sha256"]
        for r in build_units["source_identity"]["units"])
    package_ref = ledger["package_provenance"]
    package_report = json.loads((ROOT / package_ref["path"]).read_text())
    baseline = ({"parent", "halo-ce-universal", "halo-ps2", "halo-64"} <= required_repos
                and compiled_sources_exact and build_units["failed_count"] == 0
                and build_units["source_identity"]["status"] == "current"
                and package_ref["sha256"] == sha(ROOT / package_ref["path"])
                and package_report["reproduction_verification"]["counts"].get("byte_identical_reproduction") == package_report["package_count"])
    classification_current = all(r.get("identity_accounting") == classify_identities(r, ROOT) for r in rows)
    fields = not accounting["rows_missing_required_fields"]
    no_false_pass = not any(r["qualified_row_has_unbacked_identities"] for r in accounting["rows"])
    modes_separate = all(r.get("execution_results") for r in rows)
    imports = ([r for r in rows if r["subcheck"].startswith("swarm-")],
               [r for r in rows if r["subcheck"].startswith("report-")],
               [r for r in rows if r["subcheck"].startswith("mp-")])
    imported = (len(imports[0]) == 11 and len(imports[1]) == 28
                and sum(len(r.get("fixture_scope", {}).get("imported_reports", [])) for r in imports[2]) == 15
                and all(r["result"] != "qualified" for group in imports for r in group))
    byte_complete = (byte_report["inventory_rows"] == byte_report["disposition_rows"] == 164
                     and byte_report["unclassified_member_dispositions"] == 0
                     and byte_report["unexplained_removals"] == 0 and not byte_report["issues"])
    fresh = freshness["summary"]["stale_identity_count"] == 0
    suites = ET.parse(ROOT / VALIDATION).getroot()
    suites = [suites] if suites.tag == "testsuite" else list(suites.iter("testsuite"))
    test_counts = {k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "errors", "failures", "skipped")}
    tests_pass = test_counts["tests"] > 0 and not any(test_counts[k] for k in ("errors", "failures", "skipped"))
    checks = [
        {"item": 1, "passed": baseline, "evidence": "Repository/toolchain/schema/budget/map/package pins, dirty-source manifest, all compiled sources and reproducible current packages."},
        {"item": 2, "passed": fields and classification_current and no_false_pass and modes_separate,
         "evidence": "Every row records required fields and individual identity availability; incomplete identities cannot qualify a row; execution modes have separate records."},
        {"item": 3, "passed": imported,
         "evidence": "11 swarm reports, 28 Step 8 reports, and 15 MP reports in 11 scoped groups; imported diagnostic results are never promoted."},
        {"item": 4, "passed": byte_complete,
         "evidence": "164 member dispositions with complete definition byte coverage, linked compiler ownership, explicit normalization policies, retained-byte tests and synthetic nonempty coverage."},
        {"item": 5, "passed": fresh and tests_pass and no_false_pass,
         "evidence": "Current dependency freshness plus passing mutation/invalidation tests. Missing historical run settings keep exact-run acceptance partial."},
    ]
    return {"format": "hcu-c0-closure-v1", "status": "complete" if all(c["passed"] for c in checks) else "open",
            "scope": "C0 baseline, evidence accounting and byte dispositions only. Step 7/8 consumer, rendering, workload and exact-build acceptance remain open.",
            "checks": checks, "ledger_path": LEDGER, "ledger_sha256": sha(ROOT / LEDGER),
            "validation": {"path": VALIDATION, "sha256": sha(ROOT / VALIDATION), **test_counts},
            "byte_dispositions": {k: byte_report[k] for k in ("inventory_rows", "disposition_rows", "unclassified_member_dispositions", "unexplained_removals", "issues")},
            "identity_accounting": accounting["totals"], "freshness": freshness["summary"],
            "remaining_acceptance": ["All unresolved identities remain missing evidence on their original acceptance rows.",
                                     "Opaque member/runtime semantics, renderer integration, bots, survival, memory/timing and final exact-build qualification remain governed by C1-C7.",
                                     "24 historical package invocation paths remain unavailable; current 36-package reproduction is recorded separately."],
            "step_status": ledger["step_status"]}


if __name__ == "__main__":
    report = build()
    (ROOT / OUTPUT).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "checks": report["checks"]}, indent=2))
    raise SystemExit(0 if report["status"] == "complete" else 1)
