import hashlib
import json
from pathlib import Path

from tools.integrate_step7_step8_recovered_bindings import integrate


ROOT = Path(__file__).resolve().parents[1]


def test_recoverable_bindings_are_exact_and_do_not_upgrade_rows(tmp_path):
    manifest_path = ROOT / "docs/reports/m2-step7-step8-supplemental-bindings-2026-10-23.json"
    data = json.loads(manifest_path.read_text())
    assert data["format"] == "hcu-step7-step8-supplemental-recoverable-bindings-v1"
    ledger = json.loads((ROOT / "docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json").read_text())
    assert len(data["bindings"]) == len(ledger["evidence"]) == 75
    ledger_hash = hashlib.sha256((ROOT / "docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json").read_bytes()).hexdigest()
    assert data["ledger_sha256"] == ledger_hash
    by_name = {row["subcheck"]: row for row in ledger["evidence"]}
    assert {"local-players-4", "late-failure", "rendered-bsp"}.issubset(
        {row["subcheck"] for row in data["bindings"]})
    for row in data["bindings"]:
        assert row["recorded_result"] == by_name[row["subcheck"]]["result"]
        assert all(item["matches"] for item in row["fixture_bindings"])
        for report in row["source_reports"]:
            assert hashlib.sha256((ROOT / report["path"]).read_bytes()).hexdigest() == report["sha256"]
        for item in row["fixture_bindings"] + row["report_artifact_bindings"]:
            actual = hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
            assert actual == item["sha256"] == item["actual_sha256"]
        classifications = row["report_digest_classifications"]
        assert all(item["category"] in {
            "map fixture", "source", "package", "build artifact", "report pin", "unknown"
        } for item in classifications)
        assert all(item["status"] in {
            "path-bound", "reported-path-bytes-mismatch", "reported-path-missing", "digest-only-unresolved"
        } for item in classifications)
        for item in classifications:
            if item["status"] == "path-bound":
                assert item["resolved_paths"]
                for path in item["resolved_paths"]:
                    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == item["sha256"]
    render = next(row for row in data["bindings"] if row["subcheck"] == "rendered-bsp")
    assert len(render["fixture_bindings"]) == 13
    late = next(row for row in data["bindings"] if row["subcheck"] == "late-failure")
    assert late["recorded_result"] != "qualified"
    counts = data["digest_audit"]
    assert counts["references"] >= 1101
    assert counts["path_bound"] > 0
    assert counts["unresolved"] > 0

    # Recoveries are materialized on the canonical row, and they only resolve
    # a digest that was already pinned by that same row. The result/evidence
    # classification remains an independent acceptance gate.
    resolved = [(row, item) for row in ledger["evidence"]
                for values in row.get("fixture_input_hashes", {}).values()
                if isinstance(values, list) for item in values
                if isinstance(item, dict) and item.get("recovered_binding")]
    assert resolved
    for row, item in resolved:
        path = item["local_path"]
        actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        assert actual == item["sha256"] == item["local_sha256"]
        resolution = item["recovered_binding"]
        assert resolution["origin_path_asserted"] is False
        if resolution["source_reports"]:
            for report in resolution["source_reports"]:
                linked = {item["path"]: item["sha256"]
                          for item in row["evidence_files"]}
                assert linked.get(report["path"]) == report["sha256"]
                assert hashlib.sha256((ROOT / report["path"]).read_bytes()).hexdigest() == report["sha256"]


def test_integration_resolves_only_existing_row_pins_and_keeps_results(tmp_path):
    import copy

    report = tmp_path / "docs/report.json"
    artifact = tmp_path / "build/artifact.bin"
    map_file = tmp_path / "data/map.map"
    for path in (report, artifact, map_file):
        path.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"pinned artifact")
    map_file.write_bytes(b"stock map bytes")
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    map_sha = hashlib.sha256(map_file.read_bytes()).hexdigest()
    report.write_text(json.dumps({"artifact_sha256": artifact_sha,
                                  "map_sha256": map_sha}))
    report_sha = hashlib.sha256(report.read_bytes()).hexdigest()
    row_template = {
        "step": 7, "evidence_level": "host execution", "result": "partial",
        "evidence_files": [{"path": "docs/report.json", "sha256": report_sha}],
        "fixture_input_hashes": {"fixture_hashes": [], "reported_hash_pins": []},
    }
    pinned = copy.deepcopy(row_template)
    pinned["subcheck"] = "pinned-row"
    pinned["fixture_input_hashes"]["fixture_hashes"].append({
        "sha256": map_sha, "role": "fixture"})
    pinned["fixture_input_hashes"]["reported_hash_pins"].append({
        "sha256": artifact_sha, "role": "report pin"})
    unpinned = copy.deepcopy(row_template)
    unpinned["subcheck"] = "unpinned-row"
    ledger = {"source_maps": [{"path": "data/map.map", "sha256": map_sha}],
              "evidence": [pinned, unpinned]}
    bindings = []
    for row in ledger["evidence"]:
        bindings.append({
            "step": row["step"], "subcheck": row["subcheck"],
            "recorded_result": row["result"], "evidence_level": row["evidence_level"],
            "source_reports": [{"path": "docs/report.json", "sha256": report_sha}],
            "fixture_bindings": [{"path": "data/map.map", "sha256": map_sha,
                                  "matches": True}],
            "report_artifact_bindings": [{"path": "build/artifact.bin",
                                          "sha256": artifact_sha,
                                          "matches": True}],
        })
    manifest = {"format": "hcu-step7-step8-supplemental-recoverable-bindings-v1",
                "bindings": bindings}
    before = [(r["subcheck"], r["result"], r["evidence_level"])
              for r in ledger["evidence"]]
    counts = integrate(ledger, manifest, tmp_path)
    assert counts["map_identity_resolutions"] == 1
    assert counts["report_artifact_resolutions"] == 1
    assert [(r["subcheck"], r["result"], r["evidence_level"])
            for r in ledger["evidence"]] == before
    assert pinned["fixture_input_hashes"]["fixture_hashes"][0]["local_path"] == "data/map.map"
    assert pinned["fixture_input_hashes"]["reported_hash_pins"][0]["local_path"] == "build/artifact.bin"
    assert unpinned["fixture_input_hashes"]["fixture_hashes"] == []
    assert unpinned["fixture_input_hashes"]["reported_hash_pins"] == []
    integrated_once = json.dumps(ledger, sort_keys=True)
    again = integrate(ledger, manifest, tmp_path)
    assert again["rows_with_added_bindings"] == 0
    assert again["map_identity_resolutions"] == 0
    assert again["report_artifact_resolutions"] == 0
    assert json.dumps(ledger, sort_keys=True) == integrated_once
