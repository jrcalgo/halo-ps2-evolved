#!/usr/bin/env python3
"""Audit the C2 selected-session HCP2 packages against their partition rows.

For each retained session selection this compares two independently built
package trees (byte identity), runs the strict producer validator on each
package, and records the exact CE, BSP, media and claims byte counts beside
the matching row of the session map-capacity matrix.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from hcu_profile_validate import parse_package  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(lane: Path, matrix_path: Path) -> dict:
    matrix = json.loads(matrix_path.read_text())
    rows = {row["name"]: row for row in matrix["profiles"]}
    report = {
        "format": "hcu-c2-selected-package-audit-v1",
        "matrix": str(matrix_path.relative_to(ROOT)),
        "packages": [],
    }
    for selection in sorted((lane / "selections").glob("*.selection.json")):
        name = selection.name[: -len(".selection.json")]
        row = rows[name]
        first = lane / "pkg" / name / f"{name}.hcp"
        second = lane / "pkg2" / name / f"{name}.hcp"
        manifest_path = lane / "pkg" / name / f"{name}.json"
        manifest = json.loads(manifest_path.read_text())
        package_bytes = first.read_bytes()
        logical = parse_package(package_bytes,
                                expected_package_sha256=manifest["package_sha256"],
                                expected_profile_id=manifest["profile"]["id"])
        ce_image = int.from_bytes(logical["chunks"][(1, 0)][12:16], "little")
        bsp_payload = sum(int(root["payload_bytes"]) for root in manifest["profile"]["bsp_roots"])
        memory = manifest["memory"]
        report["packages"].append({
            "name": name,
            "package_path": str(first.relative_to(ROOT)),
            "package_bytes": len(package_bytes),
            "package_sha256": _sha(first),
            "second_build_sha256": _sha(second),
            "byte_identical_across_builds": _sha(first) == _sha(second),
            "producer_validation": "passed",
            "ce_image_bytes": ce_image,
            "ce_resident_bytes": memory["resident_ce_bytes"],
            "bsp_payload_bytes": bsp_payload,
            "media_bytes_independent": memory["independently_addressable_media_bytes"],
            "ctag_relocation_staging_bytes": memory["ctag_relocation_table_bytes"],
            "matrix_row": {
                "resident_ce_bytes": row["resident_ce_bytes"],
                "bsp_payload_bytes": row["bsp_payload_bytes"],
                "claims_bitmap_payload_capacity_floor_bytes": row["claims_bitmap_payload_capacity_floor_bytes"],
                "ctag_relocation_staging_bytes": row["ctag_relocation_staging_bytes"],
                "remaining_after_relocation_and_claim_floor_bytes": row["remaining_after_relocation_and_claim_floor_bytes"],
            },
            "ce_matches_row": ce_image == row["resident_ce_bytes"],
            "bsp_matches_row": bsp_payload == row["bsp_payload_bytes"],
            "selected_variants": manifest["selected_session_catalog"]["selected_variants"],
            "native_mount_preflight": "failed: fixture raw tag read (see report)",
        })
    return report


PARTITION_DEFAULT = ROOT / "build/m2-c2-r2-budget/partition-table-profile-v2.json"


def fit_rows(partition_path: Path, mount_dir: Path, names: list[str]) -> dict:
    """Per-package fit against the partition row and each mount result.json.

    The mount test writes one shared result.json, so per-case results are read
    from mount_dir/<name>/result.json. A missing result is reported as missing
    and never counted as a pass.
    """
    partition = json.loads(partition_path.read_text())
    rows = {row["name"]: row for row in partition["profiles"]}
    out = []
    for name in names:
        row = rows.get(name)
        result_path = mount_dir / name / "result.json"
        entry = {"name": name, "mount_result": None, "fits": False, "problems": []}
        if row is None:
            entry["problems"].append("no partition row")
            out.append(entry)
            continue
        if not result_path.is_file():
            entry["problems"].append("mount result.json missing for this case")
            entry["partition_row"] = {
                "map_render_backing_bytes": row["map_render_backing_bytes"],
                "resident_margin_bytes": row["resident_margin_bytes"],
                "render_residual_after_renderer_terms_bytes": row["render_residual_after_renderer_terms_bytes"],
                "claims_scratch_bytes": row["claims_scratch_bytes"],
            }
            out.append(entry)
            continue
        result = json.loads(result_path.read_text())
        tag_bytes = int(result["ce_ctag_image_bytes"])
        bsp_bytes = int(result["target_bsp_cache_capacity_bytes"])
        tag_cap = int(result["target_tag_cache_capacity_bytes"])
        entry["mount_result"] = {
            "path": result_path.relative_to(ROOT).as_posix() if result_path.is_relative_to(ROOT) else str(result_path),
            "status": result.get("status"),
            "run_returncode": result.get("run_returncode"),
            "mounted_tag_bytes": tag_bytes,
            "tag_cache_capacity_bytes": tag_cap,
            "bsp_bytes": bsp_bytes,
            "physical_segment_count": result.get("physical_segment_count"),
            "maximum_physical_segment_bytes": result.get("maximum_physical_segment_bytes"),
        }
        # Residency high-water is not in result.json: the fixture reports only capacities.
        entry["residency_high_water_bytes"] = None
        entry["residency_arena_bytes"] = row["render_texture_bytes"]
        entry["partition_row"] = {
            "tag_cache_bytes": row["tag_cache_bytes"],
            "structure_bsp_bytes": row["structure_bsp_bytes"],
            "claims_scratch_bytes": row["claims_scratch_bytes"],
            "resident_margin_bytes": row["resident_margin_bytes"],
            "render_residual_after_renderer_terms_bytes": row["render_residual_after_renderer_terms_bytes"],
            "map_render_backing_bytes": row["map_render_backing_bytes"],
        }
        if result.get("run_returncode") != 0 or result.get("status") != "host_profile_mounted_and_validated":
            entry["problems"].append("mount run did not pass")
        if tag_bytes > row["tag_cache_bytes"]:
            entry["problems"].append("mounted tag bytes exceed partition tag row")
        if bsp_bytes > row["structure_bsp_bytes"]:
            entry["problems"].append("BSP bytes exceed partition BSP row")
        if row["resident_margin_bytes"] < 0:
            entry["problems"].append("resident margin negative")
        if row["render_residual_after_renderer_terms_bytes"] < 0:
            entry["problems"].append("render residual negative")
        entry["fits"] = not entry["problems"]
        out.append(entry)
    return {"partition": str(partition_path.relative_to(ROOT)) if partition_path.is_relative_to(ROOT) else str(partition_path),
            "mount_dir": str(mount_dir), "packages": out,
            "all_fit": all(e["fits"] for e in out) and len(out) > 0}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lane", type=Path, default=ROOT / "build/m2-c2-r3-selected-packages")
    ap.add_argument("--matrix", type=Path,
                    default=ROOT / "build/m2-c2-session-map-capacity-2026-10-23/matrix.json")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--partition", type=Path, default=PARTITION_DEFAULT)
    ap.add_argument("--mount-dir", type=Path, default=None,
                    help="directory holding per-case mount results in <name>/result.json")
    ap.add_argument("--fit-output", type=Path, default=None)
    args = ap.parse_args(argv)
    report = audit(args.lane, args.matrix)
    if args.mount_dir is not None:
        names = sorted(p.name[: -len(".selection.json")]
                       for p in (args.lane / "selections").glob("*.selection.json"))
        fit = fit_rows(args.partition, args.mount_dir, names)
        target = args.fit_output or args.output.with_suffix(".fit.json")
        target.write_text(json.dumps(fit, indent=2, sort_keys=True) + "\n")
        print(f"fit: {sum(e['fits'] for e in fit['packages'])}/{len(names)} packages fit")
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    identical = sum(1 for p in report["packages"] if p["byte_identical_across_builds"])
    print(f"{len(report['packages'])} packages audited, {identical} byte-identical across builds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
