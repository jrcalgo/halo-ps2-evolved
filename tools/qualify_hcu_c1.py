#!/usr/bin/env python3
"""Fail-closed, requirement-scoped qualification gate for C1 HCP profiles.

This checks evidence completeness and integrity. A pass is limited to the C1
asset-profile contract; it does not imply C2 EE fit, C3 rendering, or console
qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import ctag
from hcu_profile_consumer_exclusions import DISPOSITION as CONSUMER_EXCLUDED_IMAGE
from hcu_profile_chunks import encode as encode_hcp
from hcu_profile_validate import parse_package, validate, ProfileValidationError
from hcu_schema_manifest import Elf32, SchemaManifest

MP_MAPS = ("beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
           "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
           "sidewinder", "wizard")
EXPECTED = (("ui", "ui", "ui"), *[(f"bots-{name}", "bots", name) for name in MP_MAPS],
            *[(f"survival-{name}", "survival", name) for name in MP_MAPS])
DEFAULT_ROSTER = ROOT / "docs/reports/m2-c1-actor-roster-2026-10-23.json"
DEFAULT_WEAPONS = ROOT / "docs/reports/m2-c1-special-weapons-2026-10-23.json"
DEFAULT_SCHEMA_ELF = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"
DEFAULT_CE_REPORT = ROOT / "build/m2-c1-ce-validation/result.json"
DEFAULT_BITMAP_DIR = ROOT / "build/m2-c1-bitmap-pipeline-v3b"
DEFAULT_PREFLIGHT_REPORT = ROOT / "build/m2-c1-real-preflight/result.json"
DEFAULT_BITMAP_DISPATCH = ROOT / "build/m2-c1-bitmap-live-dispatch/result.json"
DEFAULT_NATIVE_CORPUS = ROOT / "build/m2-c1-native-corpus-v3b/native-corpus.json"
DEFAULT_PROFILES = Path(os.environ.get("HCU_C1_PROFILES", ROOT / "build/m2-c1-corpus-primary-v3"))
DEFAULT_REBUILD = Path(os.environ.get("HCU_C1_REBUILD", ROOT / "build/m2-c1-corpus-rebuild-v3"))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha(value) -> str:
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _read_json(path: Path):
    return json.loads(Path(path).read_text())


def _file(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _evidence(path: Path, *, role: str, details=None) -> dict:
    result = {"role": role, "path": str(path)}
    if path.is_file():
        result["sha256"] = sha_file(path)
        result["bytes"] = path.stat().st_size
    if details is not None:
        result["details"] = details
    return result


def _audit_delta_spans(delta: dict) -> tuple[int, list[str]]:
    """Recompute the exact changed-byte count and reject invalid/overlapping spans."""
    errors = []
    spans = delta.get("spans", [])
    changed = 0
    ranges = []
    try:
        if not isinstance(spans, list):
            raise ValueError
        for span in spans:
            offset = span["offset"]
            before = bytes.fromhex(span["before_hex"])
            after = bytes.fromhex(span["after_hex"])
            if (not isinstance(offset, int) or offset < 0 or not before or len(before) != len(after) or
                    before == after or offset + len(after) > delta.get("image_size", -1)):
                raise ValueError
            changed += sum(a != b for a, b in zip(before, after))
            ranges.append((offset, offset + len(after)))
        ranges.sort()
        if any(a[1] > b[0] for a, b in zip(ranges, ranges[1:])):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        errors.append("correction spans are malformed, out of image bounds, or overlapping")
    if (delta.get("format") != "hcu-validator-byte-deltas-v1" or changed <= 0 or
            changed != delta.get("changed_bytes") or len(spans) != delta.get("span_count")):
        errors.append("correction span bytes do not equal the declared changed-byte total")
    return changed, errors


def _requirement(number: int, title: str, limitations=()) -> dict:
    return {"id": f"C1.{number}", "title": title, "status": "open",
            "evidence_grade": "not_run_or_missing",
            "findings": [], "evidence": [], "measurements": {}, "checks": [],
            "limitations": list(limitations), "deferred_to": []}


def _finding(row: dict, message: str, *, status="fail") -> None:
    row["findings"].append({"status": status, "message": str(message)})
    if status == "fail":
        row["status"] = "fail"


def _finish(row: dict) -> None:
    if row["status"] != "fail" and not row["findings"]:
        row["status"] = "pass"
    elif row["status"] != "fail":
        row["status"] = "open"
    row["evidence_grade"] = {"pass": "verified", "fail": "contradicted_or_stale",
                             "open": "not_run_or_missing"}[row["status"]]


def _expected_actor_occurrences(roster: dict) -> set[tuple[str, str, int, str]]:
    rows = set()
    for variant in roster.get("variants", []):
        if variant.get("disposition") == "combat" and variant.get("recipe"):
            rows.add((variant["map"], variant["path"], variant["datum"], "combat_variant"))
        for recipe in variant.get("mounted_recipes", []):
            rows.add((variant["map"], variant["path"], variant["datum"], "mounted_variant"))
    return rows


def _producer_and_source_pins(manifest: dict, *, root=ROOT) -> list[str]:
    errors = []
    producers = manifest.get("producers")
    if not isinstance(producers, dict) or not producers:
        errors.append("manifest has no producer source pins")
    else:
        for name, expected in producers.items():
            path = _file(root, name)
            if not path.is_file():
                errors.append(f"producer source is missing: {name}")
            elif not isinstance(expected, str) or sha_file(path) != expected:
                errors.append(f"producer source hash is stale: {name}")
    sources = manifest.get("source_maps")
    if not isinstance(sources, dict) or not sources:
        errors.append("manifest has no source-map pins")
    else:
        for source, pin in sources.items():
            if not isinstance(pin, dict) or not pin.get("path") or not pin.get("sha256"):
                errors.append(f"source-map pin is incomplete: {source}")
                continue
            path = _file(root, pin["path"])
            if not path.is_file():
                errors.append(f"source map is missing: {pin['path']}")
            elif sha_file(path) != pin["sha256"]:
                errors.append(f"source map hash is stale: {pin['path']}")
    return errors


def _profile_files(directory: Path, name: str):
    return directory / f"{name}.hcp", directory / f"{name}.json"


def _check_specs(directory: Path, row: dict, roster: dict | None, weapons: dict | None) -> dict | None:
    specs_path = directory / "specs.json"
    if not specs_path.is_file():
        _finding(row, f"missing profile specs: {specs_path}", status="open")
        return None
    try:
        specs = _read_json(specs_path)
    except (OSError, json.JSONDecodeError) as error:
        _finding(row, f"invalid specs file: {error}")
        return None
    if not isinstance(specs, dict):
        _finding(row, "profile specs root must be a JSON object")
        return None
    profile_rows = specs.get("profiles", [])
    if not isinstance(profile_rows, list) or any(not isinstance(p, dict) for p in profile_rows):
        profile_rows = []
    actual = [(p.get("name"), p.get("kind"), p.get("map")) for p in profile_rows]
    if actual != list(EXPECTED):
        _finding(row, "specs do not contain the exact ordered UI + 13 bots + 13 survival profiles")
    if roster is not None and specs.get("roster_sha256") != canonical_sha(roster):
        _finding(row, "specs actor-roster input hash does not match the supplied roster")
    if weapons is not None and specs.get("weapon_report_sha256") != canonical_sha(weapons):
        _finding(row, "specs special-weapon input hash does not match the supplied report")
    row["evidence"].append(_evidence(specs_path, role="profile-specs", details={
        "profile_count": len(actual), "roster_sha256": specs.get("roster_sha256"),
        "weapon_report_sha256": specs.get("weapon_report_sha256")}))
    row["measurements"]["profile_count"] = len(actual)
    return specs


def _load_manifests(directory: Path, row: dict) -> dict[str, dict]:
    manifests = {}
    for name, _kind, _map in EXPECTED:
        package_path, manifest_path = _profile_files(directory, name)
        if not package_path.is_file() or not manifest_path.is_file():
            _finding(row, f"missing package/manifest pair for {name}", status="open")
            continue
        try:
            manifest = _read_json(manifest_path)
        except (OSError, json.JSONDecodeError) as error:
            _finding(row, f"invalid profile manifest for {name}: {error}")
            continue
        if not isinstance(manifest, dict):
            _finding(row, f"profile manifest root is not an object: {name}")
            continue
        manifests[name] = manifest
    return manifests


def _validate_pair(directory: Path, name: str, schema: dict) -> tuple[dict | None, list[str]]:
    package_path, manifest_path = _profile_files(directory, name)
    errors = []
    if not package_path.is_file() or not manifest_path.is_file():
        return None, [f"missing package/manifest pair for {name}"]
    try:
        manifest = _read_json(manifest_path)
        profile = manifest.get("profile", {})
        expected_index = next((i for i, row in enumerate(EXPECTED, 1) if row[0] == name), None)
        expected_row = next((row for row in EXPECTED if row[0] == name), None)
        if expected_row is not None and (profile.get("id"), profile.get("kind"), profile.get("map")) != (
                expected_index, expected_row[1], expected_row[2]):
            errors.append("manifest profile id/kind/map does not match the canonical 27-profile matrix")
        package_bytes = package_path.read_bytes()
        actual_sha = _sha(package_bytes)
        if manifest.get("package_sha256") != actual_sha:
            errors.append("manifest package_sha256 does not match package bytes")
        if profile.get("name") != name:
            errors.append("manifest profile name does not match file identity")
        validation = validate(package_bytes, manifest, schema,
                              expected_package_sha256=actual_sha,
                              expected_profile_id=profile.get("id"),
                              expected_scenario=profile.get("scenario", {}).get("path", ""))
        if manifest.get("validation") != validation:
            errors.append("recorded validation summary differs from fresh validation")
        return {"manifest": manifest, "validation": validation,
                "package_sha256": actual_sha,
                "package_path": str(package_path), "manifest_path": str(manifest_path)}, errors
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return None, [f"{name}: {error}"]


def _audit_import_identities(name: str, manifest: dict) -> list[str]:
    """Check that dependency and source-occurrence ledgers form unique output identities."""
    errors = []
    dependencies = manifest.get("dependencies")
    remaps = manifest.get("source_occurrence_remaps")
    if not isinstance(dependencies, list) or not isinstance(remaps, list):
        return [f"{name}: dependency/source-occurrence identity ledgers are missing"]
    by_output = {}
    by_tag_identity = {}
    for dep in dependencies:
        datum = dep.get("output_datum")
        identity = (dep.get("group"), dep.get("path"))
        stable_key = dep.get("stable_key")
        if datum is None or not all(identity) or not isinstance(stable_key, str) or not stable_key:
            errors.append(f"{name}: imported dependency has no stable output datum/group/path identity")
            continue
        if datum in by_output:
            errors.append(f"{name}: duplicate imported dependency output datum {datum}")
        stable_identity = (*identity, stable_key)
        if stable_identity in by_tag_identity:
            errors.append(f"{name}: duplicate stable dependency identity {stable_identity}")
        by_output[datum] = identity
        by_tag_identity[stable_identity] = dep.get("source_key")
    seen_occurrences = set()
    for remap in remaps:
        source_identity = tuple(remap.get(field) for field in
                                ("source_key", "group", "path", "source_datum"))
        datum = remap.get("output_datum")
        if any(value is None for value in source_identity) or datum is None:
            errors.append(f"{name}: source occurrence remap lacks a complete source/output identity")
            continue
        if source_identity in seen_occurrences:
            errors.append(f"{name}: duplicate source occurrence remap {source_identity}")
        seen_occurrences.add(source_identity)
        if by_output.get(datum) != (remap.get("group"), remap.get("path")):
            errors.append(f"{name}: source occurrence remap does not resolve to a matching stable output identity")
    # Distinct source occurrences may legitimately alias a single output after
    # content deduplication; every dependency still needs at least one retained origin.
    remapped_output = {row.get("output_datum") for row in remaps}
    for datum in by_output:
        if datum not in remapped_output:
            errors.append(f"{name}: imported dependency output datum {datum} has no retained source occurrence")
    decisions = manifest.get("decisions")
    if not isinstance(decisions, list) or len(decisions) != len(dependencies):
        errors.append(f"{name}: import decisions do not cover every retained dependency")
    else:
        deps_by_datum = {dep.get("output_datum"): dep for dep in dependencies}
        decision_datums = set()
        for decision in decisions:
            datum = decision.get("output_datum")
            dep = deps_by_datum.get(datum)
            if datum in decision_datums or dep is None:
                errors.append(f"{name}: import decision has a duplicate or unknown output datum")
                continue
            decision_datums.add(datum)
            if (decision.get("stable_key") != dep.get("stable_key") or
                    decision.get("canonical_source") != dep.get("source_key") or
                    decision.get("source_aliases") != dep.get("source_aliases") or
                    decision.get("conflicts") != dep.get("conflicts")):
                errors.append(f"{name}: import decision does not match retained dependency identity/source choice")
            if (decision.get("decision") not in ("retained", "content_deduplicated", "conflict_variant_preserved") or
                    (decision.get("decision") == "conflict_variant_preserved" and not dep.get("conflicts"))):
                errors.append(f"{name}: dependency import decision is not an accepted deterministic disposition")
    return errors


def _audit_stock_mp_actor_origins(name: str, manifest: dict, roster: dict) -> list[str]:
    """Reject stock bot-profile ACTV dependencies without retained retail identities."""
    profile = manifest.get("profile", {})
    if profile.get("kind") != "bots":
        return []
    known = {(row.get("map"), row.get("path"), row.get("datum"))
             for row in roster.get("variants", []) if row.get("group") == "actv"}
    errors = []
    for dep in manifest.get("dependencies", []):
        if dep.get("group") != "actv":
            continue
        identity = (dep.get("source_key"), dep.get("path"), dep.get("source_datum"))
        if identity not in known:
            errors.append(f"{name}: stock multiplayer ACTV dependency is not a retained retail actor occurrence: {identity}")
    return errors


def _audit_actor_source_closures(name: str, manifest: dict, roster: dict) -> list[str]:
    """Require each resolved actor's retained source dependency closure in the profile."""
    retained = {(row.get("source_key"), row.get("group"), row.get("path"), row.get("source_datum"))
                for row in manifest.get("source_occurrence_remaps", [])}
    errors = []
    checked = 0
    for variant in roster.get("variants", []):
        if not ((variant.get("disposition") == "combat" and variant.get("recipe")) or
                variant.get("mounted_recipes")):
            continue
        source_key = variant.get("map")
        for dependency in variant.get("dependencies", []):
            checked += 1
            identity = (source_key, dependency.get("group"), dependency.get("path"),
                        dependency.get("datum"))
            if identity not in retained:
                errors.append(f"{name}: actor source closure dependency is absent: {identity}")
                if len(errors) >= 8:
                    errors.append(f"{name}: additional actor source closure dependencies are absent")
                    break
        if len(errors) >= 8:
            break
    if not checked:
        errors.append(f"{name}: retained roster has no actor closure dependencies")
    return errors


def compare_profile_builds(primary: Path, rebuild: Path, name: str) -> list[str]:
    """Compare exact package and manifest bytes for one independent build."""
    package_a, manifest_a = _profile_files(Path(primary), name)
    package_b, manifest_b = _profile_files(Path(rebuild), name)
    errors = []
    if not all(path.is_file() for path in (package_a, manifest_a, package_b, manifest_b)):
        return [f"missing package/manifest pair for {name}"]
    if package_a.read_bytes() != package_b.read_bytes():
        errors.append(f"independent package bytes differ for {name}")
    if manifest_a.read_bytes() != manifest_b.read_bytes():
        errors.append(f"independent manifest bytes differ for {name}")
    return errors


def _check_root_and_special_identity(name: str, manifest: dict, weapon_report: dict, *, root=ROOT) -> list[str]:
    errors = []
    profile = manifest.get("profile", {})
    map_name = profile.get("map")
    scenario = profile.get("scenario", {})
    if (scenario.get("source"), scenario.get("group")) != (map_name, "scnr"):
        errors.append("profile scenario identity is not sourced from its selected multiplayer map")
    scenarios = [r for r in manifest.get("roots", []) if r.get("group") == "scnr"]
    if len(scenarios) != 1 or scenarios[0].get("source") != map_name or \
            scenarios[0].get("path", "").casefold() != profile.get("scenario", {}).get("path", "").casefold():
        errors.append("scenario root is missing, duplicated, campaign-sourced, or mismatched")
    special_roles = {f"special_weapon:{key}" for key in weapon_report.get("weapon_roots", {})}
    if name != "ui":
        roots = {r.get("role"): r for r in manifest.get("roots", [])}
        if len(special_roles) != 3 or not special_roles.issubset(roots):
            errors.append("non-UI profile does not include all three special weapon roots")
        else:
            for key, source in weapon_report.get("weapon_roots", {}).items():
                root_record = roots[f"special_weapon:{key}"]
                expected = (Path(source.get("source_map", "")).stem,
                            source.get("root_tag", {}).get("group"),
                            source.get("root_tag", {}).get("path"))
                if (root_record.get("source"), root_record.get("group"), root_record.get("path")) != expected:
                    errors.append(f"special weapon root {key} does not match its pinned source tuple")
                source_key = expected[0]
                # A retained source occurrence may canonicalize to an identical
                # stable-key dependency from an alias map. Use occurrence records
                # for source closure coverage, while dependency rows retain the
                # deterministic selected source bytes.
                imported = {(occurrence.get("group"), occurrence.get("path"))
                            for occurrence in manifest.get("source_occurrence_remaps", [])
                            if occurrence.get("source_key") == source_key}
                closure = {(group, tag_path) for group, paths in source.get("dependencies_by_group", {}).items()
                           for tag_path in paths}
                if not closure or not closure.issubset(imported):
                    missing = sorted(closure - imported)
                    errors.append(f"special weapon {key} separately sourced presentation closure is incomplete: {missing[:4]}")
                source_pin = manifest.get("source_maps", {}).get(source_key, {})
                if (source_pin.get("sha256") != source.get("source_map_sha256") or
                        not source_pin.get("path")):
                    errors.append(f"special weapon {key} dependency map is not pinned as a separate profile input")
        presentation = weapon_report.get("presentation_provenance", {})
        adapter_pins = presentation.get("adapter_files", {})
        if not isinstance(adapter_pins, dict) or len(adapter_pins) < 4:
            errors.append("special-weapon presentation adapter source pins are incomplete")
        else:
            for adapter_path, expected_sha in adapter_pins.items():
                local = _file(root, adapter_path)
                if not local.is_file() or sha_file(local) != expected_sha:
                    errors.append(f"special-weapon presentation adapter input is missing or stale: {adapter_path}")
            for key in ("energy_sword", "gravity_rifle", "fuel_rod"):
                row = presentation.get(key, {})
                pose_path = row.get("pose_header")
                if not pose_path or pose_path not in adapter_pins:
                    errors.append(f"special-weapon {key} presentation pose is not separately source-pinned")
    return errors


def _audit_special_weapon_metadata(report: dict) -> list[str]:
    """Require explicit, extent-checked dispositions for undecodable reached bitmap records."""
    errors = []
    records = report.get("undecodable_reached_records")
    if not isinstance(records, list) or not records:
        errors.append("special-weapon report has no undecodable bitmap records to disposition")
        return errors
    if len(records) != 2:
        errors.append(f"special-weapon report has {len(records)} undecodable reached bitmap records; expected both records")
    for record in records:
        storage = record.get("cube_storage", {})
        disposition = record.get("presentation_policy", "")
        if (record.get("decodable") is not False or not record.get("path") or
                storage.get("extent_valid") is not True or
                not isinstance(storage.get("actual_extent_bytes"), int) or
                storage.get("actual_extent_bytes", 0) <= 0 or
                storage.get("actual_extent_bytes") != storage.get("expected_extent_bytes") or
                storage.get("faces") != 6 or storage.get("mip_levels_per_face") != 7 or
                "omit optional environment reflection" not in disposition or
                "preserve base/diffuse" not in disposition):
            errors.append(f"undecodable reached bitmap lacks an explicit extent-checked disposition: {record.get('path')}")
    if report.get("visual_admitted") is not True:
        errors.append("special-weapon report has not admitted the qualified base-material visual profile")
    if "No full visual parity claim" not in report.get("presentation_policy", ""):
        errors.append("special-weapon presentation policy omits its visual-parity limitation")
    fuel_rod = report.get("presentation_provenance", {}).get("fuel_rod", {})
    if ("arms only" not in fuel_rod.get("pose", "") or
            "CE FP model/animation refs null" not in fuel_rod.get("policy", "")):
        errors.append("fuel-rod presentation does not preserve the documented arms-only CE policy")
    return errors


def _source_bsp_inventory(path: Path, source_key: str) -> dict[tuple, dict]:
    """Read the selected retail scenario's BSP list and exact source extents."""
    ps2_tools = ROOT / "submodules/halo-ps2/tools"
    if str(ps2_tools) not in sys.path:
        sys.path.insert(0, str(ps2_tools))
    from halo2ps2 import bsp, texconv

    source = texconv.MapData.open(path)
    locations = bsp.locate(source.index, source.region, source.header.decompressed_size)
    inventory = {}
    for location in locations:
        entries = [entry for entry in source.index.entries
                   if entry.group == "sbsp" and entry.path == location.path]
        if len(entries) != 1:
            raise ValueError(f"retail BSP location has no unique SBSP tag identity: {location.path}")
        entry = entries[0]
        identity = (source_key, "sbsp", location.path, entry.tag_id)
        inventory[identity] = {"source_file_offset": location.file_offset,
                               "source_file_size": location.size,
                               "source_xbox_base": location.address}
    return inventory


def _audit_profile_presentation(name: str, result: dict, weapon_report: dict, *, root=ROOT) -> list[str]:
    """Require separately sourced sword/carbine pose assets in each non-UI HCP."""
    if name == "ui":
        return []
    errors = []
    manifest = result["manifest"]
    package = parse_package(Path(result["package_path"]).read_bytes(),
        expected_package_sha256=result["package_sha256"],
        expected_profile_id=manifest.get("profile", {}).get("id"))
    media = manifest.get("media", {})
    catalog = media.get("pose_catalog", [])
    bindings = media.get("bindings", [])
    roots = weapon_report.get("weapon_roots", {})
    adapter_files = weapon_report.get("presentation_provenance", {}).get("adapter_files", {})
    expected = (("sword", "energy_sword", 1), ("gravity_rifle", "gravity_rifle", 2))
    for asset_id, weapon_key, chunk_id in expected:
        root_row = roots.get(weapon_key, {})
        source_key = Path(root_row.get("source_map", "")).stem
        root_tag = root_row.get("root_tag", {})
        occurrence_rows = [remap for remap in manifest.get("source_occurrence_remaps", [])
            if remap.get("source_key") == source_key and remap.get("group") == root_tag.get("group") and
            remap.get("path") == root_tag.get("path") and remap.get("source_datum") == root_tag.get("tag_id")]
        if len(occurrence_rows) != 1:
            errors.append(f"{name}: {weapon_key} presentation root has no unique source-occurrence remap")
            continue
        remap = occurrence_rows[0]
        owner_candidates = [dep for dep in manifest.get("dependencies", [])
            if dep.get("output_datum") == remap.get("output_datum") and
            dep.get("group") == root_tag.get("group") and dep.get("path") == root_tag.get("path")]
        if len(owner_candidates) != 1:
            errors.append(f"{name}: {weapon_key} root output datum does not resolve to a unique imported dependency")
            continue
        dep = owner_candidates[0]
        asset_rows = [item for item in catalog if item.get("asset_id", item.get("pose_id")) == asset_id]
        if len(asset_rows) != 1:
            errors.append(f"{name}: separately sourced {asset_id} POSE catalog entry is missing or duplicated")
            continue
        asset = asset_rows[0]
        owner = asset.get("owner", {})
        if (owner.get("source_key"), owner.get("group"), owner.get("path"),
                owner.get("source_datum"), owner.get("output_datum")) != (
                source_key, dep.get("group"), dep.get("path"), root_tag.get("tag_id"), dep.get("output_datum")):
            errors.append(f"{name}: {asset_id} POSE is not bound to its separately sourced selected weapon tag")
        animation_source = weapon_report.get("presentation_provenance", {}).get("source_animation_map", {})
        animation_path = str(animation_source.get("path", "")).removesuffix(" (not retained)")
        animation_name = Path(animation_path).name.casefold()
        if (not animation_name or animation_name not in asset.get("source_map", "").casefold() or
                asset.get("source_map_path") != animation_path or
                asset.get("source_map_retained") is not False or
                asset.get("source_map_sha256") != animation_source.get("sha256")):
            errors.append(f"{name}: {asset_id} POSE lacks the separate H2 animation-map provenance pin")
        presentation = weapon_report.get("presentation_provenance", {}).get(weapon_key, {})
        expected_pose_file = presentation.get("pose_header")
        expected_pose_sha = adapter_files.get(expected_pose_file) if expected_pose_file else None
        source_file = asset.get("source_pose_path", asset.get("source_pose", asset.get("source_header")))
        source_sha = asset.get("source_pose_sha256", asset.get("source_header_sha256"))
        if source_file != expected_pose_file or source_sha != expected_pose_sha:
            errors.append(f"{name}: {asset_id} POSE source bytes do not match the independently pinned adapter")
        elif not expected_pose_file or not _file(root, expected_pose_file).is_file() or \
                sha_file(_file(root, expected_pose_file)) != expected_pose_sha:
            errors.append(f"{name}: {asset_id} adapter source file is missing or stale")
        key = asset.get("key", f"POSE:{asset.get('sha256', '')}")
        chunk_sha = asset.get("sha256")
        package_chunk_id = asset.get("chunk_id", asset.get("presentation_chunk_id", chunk_id))
        data = package.get("chunks", {}).get((2, package_chunk_id))
        if (not isinstance(data, bytes) or _sha(data) != chunk_sha or asset.get("bytes") != len(data) or
                asset.get("kind") != "POSE" or
                asset.get("runtime_admitted") is not False):
            errors.append(f"{name}: {asset_id} POSE bytes/hash/kind do not match the final package")
        if not any(binding.get("kind") == "POSE" and binding.get("chunk_key") == key and
                   binding.get("owner") == owner and binding.get("runtime_admitted") is False
                   for binding in bindings):
            errors.append(f"{name}: {asset_id} POSE package binding is absent or has another owner")
    return errors


def _native_package_identity_errors(pins: dict, profiles: dict[str, dict],
                                    rebuild_profiles: dict[str, dict] | None) -> list[str]:
    """Compare native CE input package, manifest, and CTAG identities to both builds."""
    errors = []
    for name, package_pin, manifest_pin, ctag_pin in (
            ("ui", "ui_package_sha256", "ui_manifest_sha256", "ui_ctag_sha256"),
            ("survival-beavercreek", "survival_package_sha256", "survival_manifest_sha256",
             "survival_ctag_sha256")):
        for label, mapping in (("primary", profiles), ("independent rebuild", rebuild_profiles)):
            if mapping is None:
                continue
            current = mapping.get(name)
            if current is None:
                errors.append(f"{label} lacks native CE profile input: {name}")
                continue
            if pins.get(package_pin) != current.get("package_sha256"):
                errors.append(f"native CE {label} package differs from final input: {name}")
            manifest_path = Path(current["manifest_path"])
            if not manifest_path.is_file() or pins.get(manifest_pin) != sha_file(manifest_path):
                errors.append(f"native CE {label} manifest differs from final input: {name}")
            package = parse_package(Path(current["package_path"]).read_bytes(),
                expected_package_sha256=current["package_sha256"],
                expected_profile_id=current["manifest"].get("profile", {}).get("id"))
            if _sha(package["chunks"][(1, 0)]) != pins.get(ctag_pin):
                errors.append(f"native CE {label} CTAG differs from final input: {name}")
    return errors


def _verify_bitmap_profile_binding(meta: dict, profile: dict, *, root=ROOT) -> str | None:
    """Bind a native sample to its exact final UI source image and package TEXS."""
    manifest = profile["manifest"]
    source_key = Path(meta.get("source_map", "")).stem
    source_pin = manifest.get("source_maps", {}).get(source_key, {})
    pinned_map_path = _file(root, source_pin.get("path", ""))
    if (source_pin.get("sha256") != meta.get("source_map_sha256") or
            not source_pin.get("path") or
            _file(root, meta.get("source_map", "")).resolve() != pinned_map_path.resolve() or
            sha_file(pinned_map_path) != source_pin.get("sha256")):
        return "bitmap native sample source map is not pinned by the final UI profile"
    source_datum, image_index = meta.get("source_datum"), meta.get("source_image_index")
    source_path = meta.get("source_path")
    tags = [d for d in manifest.get("dependencies", []) if
            d.get("source_key") == source_key and d.get("group") == "bitm" and
            d.get("source_datum") == source_datum and d.get("path") == source_path]
    if len(tags) != 1:
        return "bitmap native sample source identity is not a unique final UI dependency"
    catalog = [entry for entry in manifest.get("media", {}).get("bitmap_catalog", [])
               if entry.get("source_key") == source_key and entry.get("source_datum") == source_datum and
               entry.get("path") == source_path]
    if len(catalog) != 1:
        return "bitmap native sample has no unique final UI bitmap catalog entry"
    dispositions = [item for item in catalog[0].get("dispositions", [])
                    if item.get("source_image_index") == image_index or item.get("image_index") == image_index]
    tex_sha = meta.get("serialized_texs_sha256")
    chunks = [item for item in manifest.get("media", {}).get("chunks", [])
              if item.get("kind") == "BITM" and item.get("sha256") == tex_sha]
    if len(chunks) != 1:
        return "native serialized TEXS bytes are not a unique final UI BITM chunk"
    owner = {"source_key": source_key, "group": "bitm", "path": source_path,
             "source_datum": source_datum, "source_image_index": image_index}
    if owner not in chunks[0].get("owners", []):
        return "final UI BITM chunk is not bound to the sampled source image"
    # Current HCP catalogs retain the source tag and package owners, while the
    # standalone native case report carries the decoded source-pixel digest.
    # Older catalog forms may also carry per-image digests; compare them when
    # present, but use the exact package owner for the current compact catalog.
    if dispositions and (len(dispositions) != 1 or
            dispositions[0].get("source_pixel_sha256") != meta.get("source_pixel_sha256")):
        return "bitmap source image index/pixel hash differs from final UI catalog"
    pixel_sha = meta.get("source_pixel_sha256")
    if not isinstance(pixel_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", pixel_sha):
        return "native bitmap source pixel digest is missing or malformed"
    consumer = chunks[0].get("engine_consumer", {})
    for source in (consumer, consumer.get("parser", {}), consumer.get("capture_fixture", {})):
        source_path = _file(root, source.get("path", ""))
        if (not source.get("path") or not source_path.is_file() or
                sha_file(source_path) != source.get("source_sha256")):
            return "final UI BITM engine/parser/capture consumer source pin is missing or stale"
    if chunks[0].get("runtime_admitted") is not False:
        return "final UI BITM package overstates runtime admission"
    binding = [item for item in manifest.get("media", {}).get("bindings", [])
               if item.get("kind") == "BITM" and item.get("chunk_key") == chunks[0].get("key") and
               item.get("owner") == owner]
    if len(binding) != 1:
        return "final UI BITM package binding does not uniquely identify the sampled image"
    return None


def _bitmap_evidence(bitmap_dir: Path, row: dict, *, root=ROOT,
                     schema_elf=DEFAULT_SCHEMA_ELF, ui_profile=None) -> dict:
    expected_cases = ("test_actual_retail_ui_bitmap_c0", "test_actual_retail_ui_bitmap_c1")
    observed = []
    for case in expected_cases:
        folder = bitmap_dir / case
        metadata_path = folder / "case-metadata.json"
        if not metadata_path.is_file():
            raise FileNotFoundError(f"missing bitmap pipeline case metadata: {metadata_path}")
        meta = _read_json(metadata_path)
        if not isinstance(meta, dict):
            raise ValueError(f"bitmap case metadata root is not an object: {case}")
        if ui_profile is None:
            raise ValueError("bitmap proof cannot bind to a validated final UI package")
        binding_error = _verify_bitmap_profile_binding(meta, ui_profile, root=root)
        if binding_error:
            raise ValueError(f"{case}: {binding_error}")
        if meta.get("execution_returncode") != 0 or "pipeline-ok" not in meta.get("execution_stdout", ""):
            raise ValueError(f"native UI bitmap case did not pass: {case}")
        commands = meta.get("compiler_commands", [])
        if (not commands or any(item.get("returncode") != 0 for item in commands) or
                not any("-m32" in item.get("command", []) for item in commands)):
            raise ValueError(f"bitmap fixture lacks a passing native ILP32 compile record: {case}")
        native = meta.get("native_fixture", {})
        executable = native.get("executable", {}) if isinstance(native, dict) else {}
        compile_record = native.get("compile_record", {}) if isinstance(native, dict) else {}
        native_log = native.get("log", {}) if isinstance(native, dict) else {}
        executable_path = _file(root, executable.get("path", "")) if isinstance(executable, dict) else Path()
        compile_record_path = _file(root, compile_record.get("path", "")) if isinstance(compile_record, dict) else Path()
        native_log_path = _file(root, native_log.get("path", "")) if isinstance(native_log, dict) else Path()
        native_command = native.get("command", []) if isinstance(native, dict) else []
        if (not isinstance(native, dict) or native.get("returncode") != 0 or
                not executable_path.is_file() or sha_file(executable_path) != executable.get("sha256") or
                not compile_record_path.is_file() or sha_file(compile_record_path) != compile_record.get("sha256") or
                not native_log_path.is_file() or sha_file(native_log_path) != native_log.get("sha256") or
                "pipeline-ok" not in native_log_path.read_text(errors="replace") or
                not isinstance(native_command, list) or not native_command or
                Path(native_command[0]).name != executable_path.name):
            raise ValueError(f"bitmap native fixture executable/compile/log identity is not pinned: {case}")
        source_pins = native.get("source_pins", {})
        if not isinstance(source_pins, dict) or not source_pins:
            raise ValueError(f"bitmap native fixture has no producer source pins: {case}")
        for source_path, source_sha in source_pins.items():
            pinned_source = _file(root, source_path)
            if not pinned_source.is_file() or sha_file(pinned_source) != source_sha:
                raise ValueError(f"bitmap native fixture source is stale: {source_path}")
        source = _file(root, meta["source_map"])
        if not source.is_file() or sha_file(source) != meta.get("source_map_sha256"):
            raise ValueError(f"bitmap source map pin is stale: {meta.get('source_map')}")
        ps2_tools = ROOT / "submodules/halo-ps2/tools"
        if str(ps2_tools) not in sys.path:
            sys.path.insert(0, str(ps2_tools))
        from halo2ps2 import bitmaps, texconv
        source_data = texconv.MapData.open(source)
        source_entry = source_data.by_id.get(meta.get("source_datum"))
        if (source_entry is None or source_entry.group != "bitm" or
                source_entry.path != meta.get("source_path")):
            raise ValueError("bitmap source image owner differs from selected retail map tag")
        source_images = bitmaps.parse_images(source_data.region, source_data.base,
                                             source_entry.data_address)
        image_index = meta.get("source_image_index")
        if not isinstance(image_index, int) or image_index < 0 or image_index >= len(source_images):
            raise ValueError("bitmap source image index is outside the real retail tag image table")
        source_image = source_images[image_index]
        pixel_bytes = source_data.pixels(source_image)
        if (meta.get("source_pixel_offset") != source_image.pixel_offset or
                meta.get("source_pixel_bytes") != source_image.pixel_size or
                _sha(pixel_bytes) != meta.get("source_pixel_sha256")):
            raise ValueError("bitmap source pixel index/extent/hash differs from real retail image bytes")
        case_schema_elf = _file(root, meta.get("schema_elf", ""))
        expected_schema_elf = _file(root, schema_elf)
        if (not case_schema_elf.is_file() or sha_file(case_schema_elf) != meta.get("schema_elf_sha256") or
                not expected_schema_elf.is_file() or meta.get("schema_elf_sha256") != sha_file(expected_schema_elf)):
            raise ValueError("bitmap compiler-schema ELF pin is stale or mismatched")
        stage = _file(root, meta.get("stage_catalog", ""))
        if not stage.is_file() or sha_file(stage) != meta.get("stage_catalog_sha256"):
            raise ValueError("bitmap source-stage catalog pin is stale")
        source_code = _file(root, meta.get("interface_source", ""))
        if not source_code.is_file():
            raise ValueError("bitmap interface source is missing")
        interface_text = source_code.read_text(errors="replace")
        try:
            start = interface_text.index("void interface_draw_bitmap(")
            end = interface_text.index("\nstatic long interface_get_weapon_hud_index", start)
        except ValueError as error:
            raise ValueError("bitmap interface draw function is missing from pinned CE source") from error
        exact_draw = interface_text[start:end].rstrip() + "\n"
        if _sha(exact_draw.encode()) != meta.get("interface_source_sha256"):
            raise ValueError("bitmap exact interface draw source pin is stale")
        texs_path = folder / "actual-ui-bitmap.texs"
        if not texs_path.is_file() or sha_file(texs_path) != meta.get("serialized_texs_sha256"):
            raise ValueError(f"serialized TEXS image does not match metadata: {case}")
        log_value = Path(meta.get("execution_log", ""))
        log = log_value if log_value.is_absolute() else folder / log_value
        if not log.is_file() or "pipeline-ok" not in log.read_text(errors="replace"):
            raise ValueError(f"bitmap native success log is missing: {case}")
        observed.append({"case": case, "source_datum": meta.get("source_datum"),
                         "source_image_index": meta.get("source_image_index"),
                         "source_pixel_sha256": meta.get("source_pixel_sha256"),
                         "serialized_texs_sha256": meta.get("serialized_texs_sha256"),
                         "bound_ui_package_sha256": ui_profile["package_sha256"],
                         "native_fixture_executable": _evidence(executable_path, role="native-bitmap-executable"),
                         "native_fixture_compile_record": _evidence(compile_record_path, role="native-bitmap-compile"),
                         "native_fixture_log": _evidence(native_log_path, role="native-bitmap-execution"),
                         "metadata": _evidence(metadata_path, role="retail-bitmap-case"),
                         "native_log": _evidence(log, role="native-CE-to-GS-log"),
                         "serialized_image": _evidence(texs_path, role="serialized-bitmap")})
    native_dir = bitmap_dir / "test_exact_ce_bitmap_draw_capt0"
    fixture = native_dir / "bitmap-pipeline-fixture"
    if not fixture.is_file():
        raise FileNotFoundError("missing exact CE bitmap draw fixture executable")
    compile_path = native_dir / "compile.json"
    compile_data = _read_json(compile_path)
    if (not isinstance(compile_data, list) or not compile_data or
            any(item.get("returncode") != 0 for item in compile_data) or
            not any("-m32" in item.get("command", []) for item in compile_data)):
        raise ValueError("exact CE draw fixture lacks a passing ILP32 compile record")
    for filename, marker in (("run-success.log", "pipeline-ok"),
                             ("run-full.log", "pipeline-full"),
                             ("run-bad_asset.log", "rejected=1")):
        path = native_dir / filename
        if not path.is_file() or marker not in path.read_text(errors="replace"):
            raise ValueError(f"native GS fixture evidence missing marker {marker}: {path}")
    return {"cases": observed, "exact_fixture": [
        _evidence(fixture, role="native-CE-GS-fixture"),
        _evidence(compile_path, role="native-CE-GS-compile"),
        *[_evidence(native_dir / filename, role="native-GS-case-log")
          for filename in ("run-success.log", "run-full.log", "run-bad_asset.log")]]}


def _check_ce_report(path: Path, profiles: dict[str, dict], rebuild_profiles=None, *, root=ROOT) -> dict:
    report = _read_json(path)
    if not isinstance(report, dict):
        raise ValueError("CE report root is not a JSON object")
    errors = []
    evidence = []
    artifact_dir = _file(root, report.get("artifact_directory", str(path.parent)))
    def artifact(relative: str) -> Path:
        return artifact_dir / relative
    if report.get("format") != "hcu-c1-ce-native-validation-v1":
        errors.append("CE validation report format is unsupported")
    if report.get("runtime_admitted") is not False:
        errors.append("CE report makes an unsupported runtime admission claim")
    if report.get("host_62mb_storage_is_ee_capacity_evidence") is not False:
        errors.append("host oversized CE result is incorrectly represented as EE capacity")
    if report.get("target_tag_cache_capacity_bytes") != 2 * 1024 * 1024:
        errors.append("target capacity correction is not recorded as 2 MiB")
    results = report.get("results", {})
    ui = results.get("ui", "")
    target = results.get("survival", "")
    host = results.get("survival_host_oversized_diagnostic", "")
    if not all(token in ui for token in ("validator=accepted", "mount=1", "corrupt_schema_rejected=1")):
        errors.append("native UI CE validation acceptance evidence is incomplete")
    if not all(token in target for token in ("validator=rejected", "capacity=2097152")):
        errors.append("survival target-capacity rejection evidence is missing")
    if not all(token in host for token in ("validator=accepted", "capacity=67108864")):
        errors.append("host 64 MiB semantic diagnostic is missing or failed")
    if "survival_host_oversized_diagnostic" in results and report.get("host_62mb_storage_is_ee_capacity_evidence") is not False:
        errors.append("host-only semantic diagnostic is not clearly excluded from EE admission")
    callbacks = results.get("survival_host_oversized_correction_callbacks", {})
    if not all(isinstance(callbacks.get(name), int) and callbacks[name] > 0
               for name in ("model_geometry_part_check", "sound_check")):
        errors.append("named CE runtime correction callbacks are missing")
    deltas = artifact("survival-beavercreek-validation-deltas.json")
    sound_fixups = artifact("survival-beavercreek-sound-owner-fixups.tsv")
    callback_audit_path = artifact("survival-beavercreek-callback-delta-audit.json")
    if not deltas.is_file() or not sound_fixups.is_file() or not callback_audit_path.is_file():
        errors.append("CE runtime correction evidence files are missing")
    else:
        delta = _read_json(deltas)
        callback_audit = _read_json(callback_audit_path)
        changed_bytes, delta_errors = _audit_delta_spans(delta)
        if delta_errors:
            errors.append("CE byte-correction report does not record actual bounded fixups")
        survival_profile = profiles.get("survival-beavercreek")
        if survival_profile:
            survival_package = parse_package(Path(survival_profile["package_path"]).read_bytes(),
                expected_package_sha256=survival_profile["package_sha256"],
                expected_profile_id=survival_profile["manifest"].get("profile", {}).get("id"))
            survival_ctag = ctag.decode(survival_package["chunks"][(1, 0)],
                                         max_image_size=len(survival_package["chunks"][(1, 0)]))
            if (delta.get("image_size") != len(survival_ctag.image) or
                    report.get("survival_host_image_bytes") != len(survival_ctag.image)):
                errors.append("CE correction and host-run image sizes differ from final survival CTAG")
        if (callback_audit.get("all_byte_deltas_attributed_to_validator_mutation_sites") is not True or
                callback_audit.get("whole_image_delta_bytes") != delta.get("changed_bytes") or
                callback_audit.get("whole_image_delta_bytes_verified") != delta.get("changed_bytes") or
                not isinstance(callback_audit.get("model_geometry_hardware_format_changed_bytes"), int) or
                callback_audit.get("model_geometry_hardware_format_changed_bytes", 0) <= 0 or
                callback_audit.get("model_geometry_changed_bytes_within_compiled_hardware_format_fields") is not True or
                callback_audit.get("null_reference_name_repairs_match_compiled_empty_name_pointer") is not True):
            errors.append("CE correction attribution audit is incomplete")
        rows = sound_fixups.read_text(errors="replace").splitlines()
        try:
            parsed = [line.split("\t") for line in rows]
            if (not parsed or any(len(fields) != 3 or
                    not re.fullmatch(r"0x[0-9a-fA-F]+", fields[0]) or
                    not re.fullmatch(r"[0-9a-fA-F]{8}", fields[1]) or
                    not re.fullmatch(r"[0-9a-fA-F]{8}", fields[2]) for fields in parsed)):
                raise ValueError
            if len(rows) != 2 * callbacks.get("sound_check", 0):
                raise ValueError
            if callback_audit.get("sound_owner_index_field_writes") != len(rows):
                raise ValueError
        except ValueError:
            errors.append("sound correction rows do not match the two named sound permutation owner fields")
        test_pin = report.get("implementation_source_pins", {}).get(
            "tests/test_hcu_profile_ce_validation.py")
        test_source = _file(root, "tests/test_hcu_profile_ce_validation.py")
        source_text = test_source.read_text(errors="replace") if test_source.is_file() else ""
        if (not test_pin or not test_source.is_file() or sha_file(test_source) != test_pin or
                "hcu_test_log_sound_owner" not in source_text or
                'for member in ("unknown2", "unknown3")' not in source_text):
            errors.append("sound correction owner-field instrumentation is not pinned/explained")
    current_pins = report.get("implementation_source_pins", {})
    for name, expected in current_pins.items():
        source = _file(root, name)
        if not source.is_file() or sha_file(source) != expected:
            errors.append(f"CE implementation pin is missing or stale: {name}")
    # Compare the retained report against available current profile identities.
    pins = report.get("pins", {})
    errors.extend(_native_package_identity_errors(pins, profiles, rebuild_profiles))
    ui_manifest = profiles.get("ui", {}).get("manifest", {})
    if pins.get("ui_source_map_sha256") != ui_manifest.get("source_maps", {}).get("ui", {}).get("sha256"):
        errors.append("native UI CE run source map differs from final UI profile input")
    survival_manifest = profiles.get("survival-beavercreek", {}).get("manifest", {})
    if pins.get("survival_schema_elf_sha256") != survival_manifest.get("schema_elf_sha256"):
        errors.append("native survival CE schema differs from final survival profile input")
    for profile_name, tag_key, artifact_name in (
            ("ui", "ui_ctag_sha256", "ui.ctag"),
            ("survival-beavercreek", "survival_ctag_sha256", "survival-beavercreek.ctag")):
        artifact_path = artifact(artifact_name)
        if not artifact_path.is_file() or sha_file(artifact_path) != pins.get(tag_key):
            errors.append(f"CE report CTAG artifact is missing or stale: {artifact_name}")
    # Runs and compiled artifacts must carry explicit content identity pins.
    runs = report.get("runs", {})
    executable_records = report.get("executables", {})
    for run_name, profile_name in (("ui", "ui"), ("survival", "survival-beavercreek"),
                                   ("survival_host_oversized_diagnostic", "survival-beavercreek")):
        run = runs.get(run_name, {})
        current = profiles.get(profile_name)
        expected_ctag = pins.get("ui_ctag_sha256" if profile_name == "ui" else "survival_ctag_sha256")
        if (not current or not isinstance(run, dict) or run.get("returncode") != 0 or
                run.get("package_sha256") != current.get("package_sha256") or
                run.get("ctag_sha256") != expected_ctag):
            errors.append(f"native CE run lacks current package/CTAG identity: {run_name}")
        run_log = run.get("log", {}) if isinstance(run, dict) else {}
        run_log_path = _file(root, run_log.get("path", "")) if isinstance(run_log, dict) else Path()
        if (not isinstance(run_log, dict) or not run_log_path.is_file() or
                sha_file(run_log_path) != run_log.get("sha256")):
            errors.append(f"native CE run log is not content-pinned: {run_name}")
        else:
            log_text = run_log_path.read_text(errors="replace")
            required_log_tokens = {
                "ui": ("validator=accepted", "mount=1"),
                "survival": ("validator=rejected", f"capacity={report.get('target_tag_cache_capacity_bytes')}"),
                "survival_host_oversized_diagnostic": ("validator=accepted",
                    f"capacity={report.get('host_oversized_capacity_bytes')}"),
            }[run_name]
            if not all(token in log_text for token in required_log_tokens):
                errors.append(f"native CE run log has incorrect validator result: {run_name}")
        command = run.get("command", []) if isinstance(run, dict) else []
        expected_executable = executable_records.get("host" if run_name == "survival_host_oversized_diagnostic"
                                                      else "target", {})
        if (not isinstance(command, list) or not command or not isinstance(expected_executable, dict) or
                not expected_executable.get("path") or
                Path(command[0]).name != Path(expected_executable["path"]).name):
            errors.append(f"native CE run command does not identify its pinned executable: {run_name}")
    for exe_name in ("target", "host"):
        exe = executable_records.get(exe_name, {})
        exe_path = _file(root, exe.get("path", "")) if isinstance(exe, dict) else Path()
        if not isinstance(exe, dict) or not exe_path.is_file() or sha_file(exe_path) != exe.get("sha256"):
            errors.append(f"native CE {exe_name} executable is not content-pinned")
    generated_sources = report.get("generated_sources", {})
    if not isinstance(generated_sources, dict) or not generated_sources:
        errors.append("generated CE instrumentation sources have no content pins")
    else:
        for role, item in generated_sources.items():
            source = _file(root, item.get("path", "")) if isinstance(item, dict) else Path()
            if not isinstance(item, dict) or not source.is_file() or sha_file(source) != item.get("sha256"):
                errors.append(f"generated CE source pin is missing or stale: {role}")
    for name, pin in report.get("pins", {}).get("survival_source_maps", {}).items():
        source = _file(root, pin.get("path", ""))
        if not source.is_file() or sha_file(source) != pin.get("sha256"):
            errors.append(f"CE survival source-map pin is stale: {name}")
    if "beavercreek" not in report.get("pins", {}).get("survival_source_maps", {}):
        errors.append("native survival CE evidence does not pin the selected final source map")
    else:
        final_survival_source = survival_manifest.get("source_maps", {}).get("beavercreek", {})
        ce_survival_source = report["pins"]["survival_source_maps"]["beavercreek"]
        if (ce_survival_source.get("sha256") != final_survival_source.get("sha256") or
                ce_survival_source.get("path") != final_survival_source.get("path")):
            errors.append("native survival CE source map differs from final profile input")
    diag = _file(root, report.get("diagnostic_path", "build/m2-c1-survival-dedup/survival-beavercreek.failure.json"))
    if not diag.is_file() or sha_file(diag) != pins.get("survival_diagnostic_sha256"):
        errors.append("CE validator survival diagnostic input is stale")
    for log_key in ("ui", "survival", "survival_host_oversized_diagnostic"):
        log_name = report.get("logs", {}).get(log_key)
        log_path = _file(root, log_name or "")
        if not log_name or not log_path.is_file():
            errors.append(f"native CE validation log is missing: {log_key}")
        else:
            evidence.append(_evidence(log_path, role=f"native-CE-log:{log_key}"))
    for artifact_name, role in (
            ("hcu-profile-ce-validation", "native-CE-validator-fixture"),
            ("hcu-profile-ce-validation-host64m", "host-oversized-semantic-fixture"),
            ("compile.log", "native-CE-compile-log"),
            ("compile-host64m.log", "host-semantic-compile-log"),
            ("survival-beavercreek-validation-deltas.json", "CE-byte-delta-audit"),
            ("survival-beavercreek-callback-delta-audit.json", "CE-callback-attribution-audit"),
            ("survival-beavercreek-sound-owner-fixups.tsv", "CE-sound-owner-fixups")):
        artifact_path = artifact(artifact_name)
        if not artifact_path.is_file():
            errors.append(f"native CE evidence artifact is missing: {artifact_name}")
        else:
            evidence.append(_evidence(artifact_path, role=role))
    return {"errors": errors, "metrics": {
        "target_capacity_bytes": report.get("target_tag_cache_capacity_bytes"),
        "survival_image_bytes": report.get("survival_host_image_bytes"),
        "host_semantic_capacity_bytes": report.get("host_oversized_capacity_bytes"),
        "host_ee_capacity_claim": report.get("host_62mb_storage_is_ee_capacity_evidence"),
        "correction_callbacks": callbacks,
        "changed_bytes": locals().get("delta", {}).get("changed_bytes"),
        "correction_explanations": [
            {"callback": "model_geometry_part_check", "invocations": callbacks.get("model_geometry_part_check"),
             "changed_bytes": locals().get("callback_audit", {}).get("model_geometry_hardware_format_changed_bytes"),
             "interpretation": "Host CE validator corrected model vertex/triangle hardware-format fields; audited writes stayed within compiled fields."},
            {"callback": "sound_check", "invocations": callbacks.get("sound_check"),
             "owner_index_writes": locals().get("callback_audit", {}).get("sound_owner_index_field_writes"),
             "interpretation": "Host CE validator remapped two sound-permutation owner indices per sound check; this is metadata fixup evidence, not SPU2 playback."}]},
        "path": path, "sha256": sha_file(path), "evidence": evidence}


def _check_preflight_report(path: Path, profiles: dict[str, dict], rebuild_profiles: dict[str, dict],
                           schema_elf: Path, *, root=ROOT) -> dict:
    """Bind real CE pre-teardown validation to current UI packages and code pins."""
    report = _read_json(path)
    errors = []
    current_ui = profiles.get("ui")
    if current_ui is None:
        errors.append("native preflight has no freshly validated UI package")
    else:
        manifest_path = Path(current_ui["manifest_path"])
        checks = {
            "profile_package_sha256": current_ui["package_sha256"],
            "profile_manifest_sha256": sha_file(manifest_path),
            "schema_elf_sha256": sha_file(Path(schema_elf)),
        }
        for field, expected in checks.items():
            if report.get(field) != expected:
                errors.append(f"native preflight {field} differs from current C1 input")
        host = report.get("host_validation", {})
        validation = current_ui.get("validation", {})
        for field in ("package_sha256", "profile_id", "scenario", "tag_count", "media_chunk_count", "bsp_count", "bitmap_coverage"):
            if host.get(field) != validation.get(field):
                errors.append(f"native preflight host validation {field} differs from fresh UI HCP validation")
        if rebuild_profiles is not None:
            rebuilt = rebuild_profiles.get("ui")
            if rebuilt is None or rebuilt.get("package_sha256") != report.get("profile_package_sha256") or \
                    sha_file(Path(rebuilt["manifest_path"])) != report.get("profile_manifest_sha256"):
                errors.append("native preflight UI package/manifest identity differs from independent rebuild")
    if (report.get("result") != "passed" or report.get("native_exit_code") != 0 or
            report.get("accepted_actual_package_before_teardown") is not True or
            report.get("incompatible_actual_profile_rejected_before_teardown") is not True or
            report.get("corrupt_actual_package_rejected_before_teardown") is not True or
            report.get("active_ce_and_service_snapshot_preserved") is not True):
        errors.append("native preflight did not prove accepted package, incompatible/corrupt rejection, and preserved active CE snapshot")
    if "pre-unload map service" not in report.get("scope", ""):
        errors.append("native preflight scope does not identify the real CE pre-unload map service")
    fixture = root / "tests/hcu_ce_map_lifecycle_main.c"
    test_source = root / "tests/test_hcu_ce_map_lifecycle.py"
    for label, source_path, key in (("fixture", fixture, "lifecycle_fixture_source_sha256"),
                                    ("test", test_source, "lifecycle_test_source_sha256")):
        if not source_path.is_file() or sha_file(source_path) != report.get(key):
            errors.append(f"native preflight {label} source pin is missing or stale")
    command = report.get("command", [])
    if not command:
        errors.append("native preflight executable command is missing")
    else:
        executable = _file(root, command[0])
        if not executable.is_file() or sha_file(executable) != report.get("elf_sha256"):
            errors.append("native preflight executable pin is missing or stale")
        if current_ui is not None:
            package_path = Path(current_ui["package_path"]).resolve()
            if Path(command[-1]).resolve() != package_path:
                errors.append("native preflight command does not target the current UI HCP package")
        map_path = executable.with_suffix(".map")
        log_path = Path(path).parent / "runtime.log"
        if not map_path.is_file() or sha_file(map_path) != report.get("link_map_sha256"):
            errors.append("native preflight link map is missing or stale")
        if not log_path.is_file() or sha_file(log_path) != report.get("runtime_log_sha256"):
            errors.append("native preflight runtime log is missing or stale")
        elif not all(marker in log_path.read_text(errors="replace") for marker in (
                "actual UI HCP rejected for incompatible map before teardown",
                "actual validated UI HCP identity and complete chunk inventory accepted before same-map unload",
                "corrupt actual UI HCP rejected before teardown; active CE snapshot retained")):
            errors.append("native preflight runtime log lacks real accepted/rejected package lifecycle markers")
    return {"errors": errors, "metrics": {"preflight_ui_package_sha256": report.get("profile_package_sha256"),
            "preflight_ui_chunk_count": report.get("host_validation", {}).get("media_chunk_count"),
            "preflight_native_exit_code": report.get("native_exit_code")}}


def _check_bitmap_live_dispatch(path: Path, profiles: dict[str, dict], rebuild_profiles: dict[str, dict], *, root=ROOT) -> dict:
    """Verify real CE bitmap requests dispatch through the final UI profile into GS chains."""
    report = _read_json(path)
    errors, open_findings, deferred = [], [], []
    ui = profiles.get("ui")
    if ui is None:
        errors.append("native bitmap dispatch has no freshly validated UI profile")
        return {"errors": errors, "open_findings": [], "deferred": [], "metrics": {},
                "evidence": _evidence(Path(path), role="native-live-bitmap-dispatch")}
    manifest = ui["manifest"]
    package_path = Path(ui["package_path"])
    manifest_path = Path(ui["manifest_path"])
    package = parse_package(package_path.read_bytes(), expected_package_sha256=ui["package_sha256"],
                            expected_profile_id=manifest.get("profile", {}).get("id"))
    if report.get("schema") != "hcu-c1-bitmap-live-dispatch-v1":
        errors.append("native bitmap dispatch report format is unsupported")
    if (report.get("status") != "host_qualified" or report.get("returncode") != 0 or report.get("stderr") or
            report.get("runtime_admitted") is not False or report.get("pre_fence_evidence") is not True):
        errors.append("native bitmap dispatch did not pass without overclaiming runtime admission")
    frame_bound = report.get("actual_ce_frame_bound", None)
    live_scope = report.get("live_consumer_evidence")
    uncovered = live_scope.get("not_covered") if isinstance(live_scope, dict) else None
    frame_item_uncovered = isinstance(uncovered, list) and any(
        isinstance(item, str) and "production ps2_render.render_frame binding" in item for item in uncovered)
    if frame_bound is True:
        pass
    elif frame_bound is False and frame_item_uncovered:
        # User decision (2026-10-23): frame binding needs the parent render loop, which is C3 work.
        # C1.4 carries it as a structured deferral rather than an open finding. Only an explicit
        # False that also lists the production frame binding as not covered qualifies; anything
        # else (missing, None, other values, or False without the item) is an error below.
        deferred.append({
            "gate": "C3", "item": "C3.4/C3.6/C3.7",
            "reason": ("native fixture proves the CE interface request to renderer chain path; registration and "
                       "queue-end are not bound to the running CE frame because the HCU image has no parent render "
                       "loop (CE render_frame only publishes a pointer-free snapshot), and renderer chain binding, HUD, "
                       "and GS-fenced cache reuse are C3 work"),
            "decided_by": "user 2026-10-23"})
    else:
        errors.append("native bitmap dispatch report does not state its frame-binding scope")
    live = report.get("live_consumer_evidence")
    if (not isinstance(live, dict) or not live.get("registration") or
            not live.get("dispatch_hook") or not live.get("actual_ce_calls") or
            not live.get("ce_blend_table_source") or not live.get("asserted_modes") or
            not live.get("host_packets")):
        open_findings.append("native bitmap dispatch report lacks complete registration, CE-call, blend-mode, and packet evidence")
    elif report.get("actual_ce_frame_bound") is True and any(
            "production ps2_render.render_frame binding" in item
            for item in live.get("not_covered", [])):
        errors.append("native bitmap report claims a frame binding while listing the production frame as untested")
    stdout = report.get("stdout", "")
    if not all(marker in stdout for marker in ("bitmap-dispatch-ok", "ctag_reader=end-hook",
            "upload_qw=", "geometry_qw=")) or not ("lease=held" in stdout or "leases=held" in stdout):
        errors.append("native bitmap dispatch lacks queue-end, upload/geometry chain, or held-lease evidence")
    if "real GPU fence" not in report.get("completion", "") or \
            "no EE, GS execution, framebuffer" not in report.get("limitation", ""):
        errors.append("native bitmap dispatch omits its host-only/fence limitation")
    for field, expected in (("package", ui["package_sha256"]),
                            ("manifest", sha_file(manifest_path)),
                            ("ui_ctag_sha256", _sha(package["chunks"][(1, 0)]))):
        if field == "package":
            actual = report.get(field, {}).get("sha256")
        elif field == "manifest":
            actual = report.get(field, {}).get("sha256")
        else:
            actual = report.get(field)
        if actual != expected:
            errors.append(f"native bitmap dispatch {field} does not match the current UI profile")
    if rebuild_profiles is not None:
        rebuilt = rebuild_profiles.get("ui")
        if rebuilt is None or rebuilt.get("package_sha256") != ui["package_sha256"] or \
                sha_file(Path(rebuilt["manifest_path"])) != sha_file(manifest_path):
            errors.append("native bitmap dispatch UI profile differs from independent rebuild")
    source_map = manifest.get("source_maps", {}).get("ui", {})
    source_map_path = _file(root, source_map.get("path", ""))
    if (not source_map_path.is_file() or sha_file(source_map_path) != source_map.get("sha256") or
            report.get("source_map_sha256") != source_map.get("sha256")):
        errors.append("native bitmap dispatch UI retail map pin is stale")
    if report.get("source_pins", {}).get("ui_ctag_chunk_sha256") != report.get("ui_ctag_sha256"):
        errors.append("native bitmap dispatch CTAG source pin differs")
    for source_name, expected_sha in report.get("source_pins", {}).items():
        if source_name == "ui_ctag_chunk_sha256":
            continue
        source_path = _file(root, source_name)
        if not source_path.is_file() or sha_file(source_path) != expected_sha:
            errors.append(f"native bitmap dispatch source pin is missing or stale: {source_name}")
    artifact_names = report.get("artifacts", {})
    for label in ("bindings", "compile_record", "executable", "interface_body", "log"):
        source_name = artifact_names.get(label)
        if not source_name:
            errors.append(f"native bitmap dispatch artifact path is missing: {label}")
            continue
        source_path = _file(root, source_name)
        pin = report.get("source_pins", {}).get(source_name)
        if not source_path.is_file() or not pin or sha_file(source_path) != pin:
            errors.append(f"native bitmap dispatch artifact is missing or stale: {label}")
    table_path = _file(root, artifact_names.get("bindings", ""))
    try:
        table = _read_json(table_path)
    except (OSError, json.JSONDecodeError) as error:
        table = {}
        errors.append(f"native bitmap binding table is missing or invalid: {error}")
    compile_path = _file(root, artifact_names.get("compile_record", ""))
    try:
        compile_rows = _read_json(compile_path)
    except (OSError, json.JSONDecodeError) as error:
        compile_rows = []
        errors.append(f"native bitmap compile record is missing or invalid: {error}")
    if (not isinstance(compile_rows, list) or not compile_rows or
            any(not isinstance(row, dict) or row.get("returncode") != 0 or "-m32" not in row.get("command", [])
                for row in compile_rows) or
            sha_file(compile_path) != report.get("compile_record_sha256")):
        errors.append("native bitmap dispatch compile record is incomplete, unsuccessful, or stale")
    bindings = table.get("bindings", [])
    if table.get("schema_elf_sha256") != manifest.get("schema_elf_sha256"):
        errors.append("native bitmap binding table schema ELF identity differs from the current UI profile")
    coverage = ui.get("validation", {}).get("bitmap_coverage", {})
    if (table.get("format") != "hcu-c1-bitmap-bindings-v1" or
            table.get("package", {}).get("sha256") != ui["package_sha256"] or
            table.get("manifest", {}).get("sha256") != sha_file(manifest_path) or
            table.get("binding_count") != len(bindings) or
            len(bindings) != coverage.get("serialized_images")):
        errors.append("native bitmap binding table does not cover the serialized images of the final UI profile")
    seen_samples = set()
    media_chunks = manifest.get("media", {}).get("chunks", [])
    dependencies = manifest.get("dependencies", [])
    for binding in bindings:
        identity = (binding.get("source_datum"), binding.get("source_image_index"))
        if identity in seen_samples:
            errors.append(f"native bitmap binding table duplicates a source image: {identity}")
        seen_samples.add(identity)
        owner = {"source_key": "ui", "group": "bitm", "path": binding.get("path"),
                 "source_datum": binding.get("source_datum"),
                 "source_image_index": binding.get("source_image_index")}
        tags = [dep for dep in dependencies if dep.get("output_datum") == binding.get("bitmap_output_datum")]
        chunks = [chunk for chunk in media_chunks if chunk.get("kind") == "BITM" and
                  chunk.get("sha256") == binding.get("chunk_sha256")]
        package_chunk = package.get("chunks", {}).get((2, binding.get("chunk_id")))
        if (len(tags) != 1 or (tags[0].get("source_key"), tags[0].get("group"), tags[0].get("path"),
                tags[0].get("source_datum")) != ("ui", "bitm", binding.get("path"), binding.get("source_datum")) or
                len(chunks) != 1 or owner not in chunks[0].get("owners", []) or
                chunks[0].get("runtime_admitted") is not False or
                not isinstance(package_chunk, bytes) or _sha(package_chunk) != binding.get("chunk_sha256") or
                binding.get("runtime_admitted") is not False):
            errors.append(f"native bitmap binding does not match the final UI source image/package chunk: {identity}")
        catalog = [item for item in manifest.get("media", {}).get("bitmap_catalog", [])
                   if item.get("source_key") == "ui" and item.get("source_datum") == binding.get("source_datum")
                   and item.get("path") == binding.get("path")]
        if len(catalog) != 1:
            errors.append(f"native bitmap source image lacks one final UI catalog owner: {identity}")
    selected = report.get("binding", {})
    selected_owner = {"source_key": "ui", "group": "bitm", "path": report.get("source_path"),
        "source_datum": report.get("source_datum"), "source_image_index": selected.get("source_image_index")}
    selected_tags = [dep for dep in dependencies if dep.get("output_datum") == selected.get("bitmap_output_datum")]
    selected_chunks = [chunk for chunk in media_chunks if chunk.get("kind") == "BITM" and
                       chunk.get("sha256") == selected.get("chunk_sha256")]
    if (selected not in bindings or len(selected_tags) != 1 or len(selected_chunks) != 1 or
            selected_owner not in selected_chunks[0].get("owners", []) or
            report.get("media_chunk_sha256") != selected.get("chunk_sha256")):
        errors.append("dispatched sample is not bound to its final UI dependency and content-addressed BITM chunk")
    run_command = report.get("run_command", [])
    executable_path = _file(root, artifact_names.get("executable", ""))
    log_path = _file(root, artifact_names.get("log", ""))
    if not run_command or Path(run_command[0]).resolve() != executable_path.resolve() or \
            len(run_command) < 4 or Path(run_command[1]).resolve() != package_path.resolve():
        errors.append("native bitmap dispatch command does not name the pinned executable and final UI HCP")
    log_text = log_path.read_text(errors="replace") if log_path.is_file() else ""
    if stdout.strip() not in log_text:
        errors.append("native bitmap dispatch log does not contain the recorded chain/lease result")
    return {"errors": errors, "open_findings": open_findings, "deferred": deferred,
        "evidence": _evidence(Path(path), role="native-live-bitmap-dispatch",
        details={"binding_count": len(bindings), "selected_chunk_sha256": report.get("media_chunk_sha256"),
                 "runtime_admitted": report.get("runtime_admitted"), "limitation": report.get("limitation")}),
        "metrics": {"native_live_bitmap_dispatches": 1, "native_bitmap_image_bindings": len(bindings),
                    "native_bitmap_pre_fence": report.get("pre_fence_evidence")}}


def _check_native_corpus(path: Path, profiles: dict[str, dict], rebuild_profiles: dict[str, dict], *, root=ROOT) -> dict:
    """Verify the all-profile native CE corpus against both fresh package builds."""
    errors, evidence = [], []
    report = _read_json(path)
    if (report.get("format") != "hcu-c1-native-ce-corpus-v1" or
            report.get("status") != "complete" or
            report.get("complete_27_profile_corpus") is not True or
            report.get("run_count") != 27 or len(report.get("profiles", [])) != 27):
        errors.append("native CE corpus report is not a complete successful 27-profile run")
    if report.get("runtime_admitted") is not False:
        errors.append("native CE corpus overstates C1 host evidence as runtime admission")
    if report.get("target_capacity_bytes") != 2 * 1024 * 1024:
        errors.append("native CE corpus does not preserve the default 2 MiB target-capacity limitation")
    for label, exe in report.get("executables", {}).items():
        executable = _file(root, exe.get("path", ""))
        if label not in ("target", "host") or not executable.is_file() or sha_file(executable) != exe.get("sha256"):
            errors.append(f"native CE corpus {label} executable pin is missing or stale")
        command = report.get("compile_commands", {}).get(label)
        required_generated = ("halo_ps2_msvc_semantics.h",) if label == "target" else tuple(
            report.get("generated_sources", {}))
        generated_present = all(
            str(_file(root, report["generated_sources"][name].get("path", "")).resolve()) in command
            for name in required_generated) if isinstance(command, list) else False
        if (not isinstance(command, list) or not command or "-m32" not in command or
                str(executable.resolve()) not in command or not generated_present):
            errors.append(f"native CE corpus {label} compile command is incomplete or does not bind generated sources")
    for label, source in report.get("generated_sources", {}).items():
        generated = _file(root, source.get("path", ""))
        if not generated.is_file() or sha_file(generated) != source.get("sha256"):
            errors.append(f"native CE corpus generated source pin is missing or stale: {label}")
    schema = report.get("schema_elf", {})
    schema_path = _file(root, schema.get("path", ""))
    if not schema_path.is_file() or sha_file(schema_path) != schema.get("sha256"):
        errors.append("native CE corpus schema ELF pin is missing or stale")
    for source_name, expected_sha in report.get("implementation_source_pins", {}).items():
        source_path = _file(root, source_name)
        if not source_path.is_file() or sha_file(source_path) != expected_sha:
            errors.append(f"native CE corpus implementation source pin is missing or stale: {source_name}")
    seen = set()
    for case in report.get("profiles", []):
        name = case.get("profile")
        if name not in {row[0] for row in EXPECTED} or name in seen:
            errors.append(f"native CE corpus has an unknown or duplicate profile: {name}")
            continue
        seen.add(name)
        for label, built in (("primary", profiles), ("independent rebuild", rebuild_profiles)):
            current = built.get(name)
            if current is None:
                errors.append(f"native CE {label} profile is unavailable: {name}")
                continue
            manifest = current["manifest"]
            package = parse_package(Path(current["package_path"]).read_bytes(),
                expected_package_sha256=current["package_sha256"],
                expected_profile_id=manifest.get("profile", {}).get("id"))
            pins = {"package_sha256": current["package_sha256"],
                    "manifest_sha256": sha_file(Path(current["manifest_path"])),
                    "ctag_sha256": _sha(package["chunks"][(1, 0)])}
            for field, expected_value in pins.items():
                if case.get(field) != expected_value:
                    errors.append(f"native CE {label} {field} differs from current profile {name}")
            source_pins = case.get("source_map_pins", {})
            expected_sources = manifest.get("source_maps", {})
            for key, source in expected_sources.items():
                pin = source_pins.get(key, {})
                if pin.get("sha256") != source.get("sha256") or pin.get("path") != source.get("path"):
                    errors.append(f"native CE {label} source-map identity differs from profile {name}:{key}")
        for run_name in ("target", "host_semantic"):
            run = case.get(run_name, {})
            result = run.get("result", "")
            command = run.get("command", [])
            executable_label = "target" if run_name == "target" else "host"
            expected_executable = report.get("executables", {}).get(executable_label, {}).get("path")
            expected_capacity = ("capacity=2097152" if run_name == "target" else
                                 f"capacity={report.get('host_semantic_capacity_bytes')}")
            accepted = ("validator=accepted" in result and "mount=1" in result and
                        "released_after_unmount=1" in result)
            expected_target_rejection = (name != "ui" and "validator=rejected" in result and
                        "mount=0" in result and "capacity=2097152" in result and
                        "released_after_unmount=not_applicable" in result)
            validation_expected = (expected_target_rejection if run_name == "target" and name != "ui"
                                   else accepted)
            if (run.get("returncode") != 0 or not run.get("log", {}).get("path") or
                    not run.get("log", {}).get("sha256") or
                    not command or str(command[0]) != str(expected_executable) or
                    not validation_expected or
                    "corrupt_schema_rejected=1" not in result or
                    "pointers_stable=1" not in result or
                    "owner_unpublished=1" not in result or
                    expected_capacity not in result):
                errors.append(f"native CE {run_name} validation/ownership evidence is incomplete: {name}")
            if run_name == "target" and name != "ui" and case.get("image_size", 0) <= 2 * 1024 * 1024:
                errors.append(f"native CE target capacity refusal is not explained by an oversized profile: {name}")
            log = run.get("log", {})
            log_path = _file(root, log.get("path", ""))
            if not log_path.is_file() or sha_file(log_path) != log.get("sha256"):
                errors.append(f"native CE {run_name} log is missing or stale: {name}")
            for artifact_name, artifact in run.get("artifacts", {}).items():
                artifact_path = _file(root, artifact.get("path", ""))
                if not artifact_path.is_file() or sha_file(artifact_path) != artifact.get("sha256"):
                    errors.append(f"native CE {run_name} audit artifact is missing or stale: {name}:{artifact_name}")
        evidence.append({"profile": name, "package_sha256": case.get("package_sha256"),
                         "target_result": case.get("target", {}).get("result"),
                         "host_result": case.get("host_semantic", {}).get("result")})
    if seen != {row[0] for row in EXPECTED}:
        errors.append("native CE corpus profile set is not the canonical 27-profile matrix")
    return {"errors": errors, "evidence": evidence,
            "metrics": {"native_profile_runs": len(seen), "native_target_capacity_bytes": report.get("target_capacity_bytes"),
                        "native_runtime_admitted": report.get("runtime_admitted")}}


DEFAULT_CONSUMER_ROLES = ROOT / "docs/reports/m2-c1-bitmap-consumer-roles-2026-10-23.json"
CONSUMER_LIVE = "live-consumer"
CONSUMER_EXCLUDED = "excluded-by-proven-profile-policy"
CONSUMER_DROPPED = "drop-no-ps2-reader"
CONSUMER_ALLOWED = (CONSUMER_LIVE, CONSUMER_EXCLUDED, CONSUMER_DROPPED)
CONSUMER_REMOVED = (CONSUMER_EXCLUDED, CONSUMER_DROPPED)


def _pick(mapping, *names):
    """First present key among names; tolerates small key-name variations from the audit and builder agents."""
    if not isinstance(mapping, dict):
        return None
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _disposition_of(row):
    value = _pick(row, "disposition", "decision", "status")
    return value if isinstance(value, str) else None


def _consumer_elf_pairs(report: dict) -> list[tuple[str, object]]:
    """(path, sha256) pairs from elf_inputs: {path: sha256} or [{"path", "sha256"}] (also "file"/"sha")."""
    raw = report.get("elf_inputs")
    pairs = []
    if isinstance(raw, dict):
        for path, value in raw.items():
            if isinstance(value, dict) and isinstance(value.get("path"), str):
                path = value["path"]  # v4: {name: {"path", "sha256"}}
            pairs.append((path, _pick(value, "sha256", "sha") if isinstance(value, dict) else value))
    elif isinstance(raw, list):
        for item in raw:
            pairs.append((_pick(item, "path", "file"), _pick(item, "sha256", "sha")))
    return pairs


def _consumer_pin(manifest: dict):
    """(path, sha256) of the consumer-exclusion input a built manifest records, or None.

    The builder (tools/hcu_multiplayer_profiles.py) writes source_inputs.consumer_exclusions = {"path", "sha256"}
    only for profiles built with --consumer-exclusions.
    """
    value = manifest.get("source_inputs")
    entry = value.get("consumer_exclusions") if isinstance(value, dict) else None
    if isinstance(entry, dict) and isinstance(entry.get("path"), str) and isinstance(entry.get("sha256"), str):
        return entry["path"], entry["sha256"]
    return None


def _dropped_images(manifest: dict, pin_sha: str | None) -> tuple[set, list[str]]:
    """Distinct images a built manifest drops under consumer exclusions, plus integrity errors.

    An image is identified by (source_key, source_datum, source_image_index). The authoritative per-image
    record is media.bitmap_catalog[].dispositions[] with disposition "excluded_by_consumer_exclusion"
    (tools/hcu_profile_consumer_exclusions.DISPOSITION). media.consumer_exclusions is the per-bitmap index
    and must name exactly the same images; media.consumer_exclusion_policy must pin the same file sha256.
    """
    errors: list[str] = []
    media = manifest.get("media") if isinstance(manifest.get("media"), dict) else {}
    catalog = media.get("bitmap_catalog")
    if not isinstance(catalog, list):
        return set(), ["media.bitmap_catalog is missing; dropped images cannot be reconciled"]
    dropped: list[tuple] = []
    for entry in catalog:
        dispositions = entry.get("dispositions") if isinstance(entry, dict) else None
        for disposition in dispositions if isinstance(dispositions, list) else []:
            if not isinstance(disposition, dict) or disposition.get("disposition") != CONSUMER_EXCLUDED_IMAGE:
                continue
            if pin_sha is not None and disposition.get("exclusion_sha256") != pin_sha:
                errors.append("dropped image does not cite the pinned consumer exclusion sha256")
            dropped.append((disposition.get("source_key"), disposition.get("source_datum"),
                            disposition.get("source_image_index")))
    if len(dropped) != len(set(dropped)):
        errors.append("a bitmap image is dropped more than once in the bitmap catalog")
    images = set(dropped)

    records = media.get("consumer_exclusions")
    if not isinstance(records, list):
        errors.append("media.consumer_exclusions is missing; dropped bitmaps cannot be reconciled")
    else:
        indexed = [(record.get("source_key"), record.get("source_datum"), index)
                   for record in records if isinstance(record, dict)
                   for index in (record.get("dropped_source_images") or [])]
        if len(indexed) != len(set(indexed)) or set(indexed) != images:
            errors.append("media.consumer_exclusions records disagree with the bitmap catalog dispositions")

    policy = media.get("consumer_exclusion_policy")
    if pin_sha is not None and (not isinstance(policy, dict) or policy.get("sha256") != pin_sha):
        errors.append("media.consumer_exclusion_policy does not match the pinned consumer exclusion input")
    return images, errors


def _check_consumer_roles(path: Path, profiles: dict[str, dict], *, root=ROOT) -> dict:
    """C1.4 consumer-role gate (user decision 2026-10-23). Fails closed.

    Expected keys in the consumer-roles report (default docs/reports/m2-c1-bitmap-consumer-roles-2026-10-23.json):
      rule                         non-empty string
      elf_inputs                   {path: sha256} or [{"path", "sha256"}]; relative paths resolve against ROOT
      occurrences                  [{"disposition": live-consumer | excluded-by-proven-profile-policy |
                                     drop-no-ps2-reader, ...}]; any other or missing disposition is blocking/undecided
      blocking                     optional; must be 0/absent
      required_profile_exclusions  [{"class", "reason", "profile_kinds": [kind], "match": {...},
                                     "counts": {profile_name: int}}]
                                   counts[profile_name] is the number of DISTINCT dropped images in that
                                   profile; every row naming a profile must state the same count for it.
      deferred_to                  recorded only

    Expected keys in each built profile manifest (tools/hcu_profile_package.py, hcu_multiplayer_profiles.py):
      source_inputs.consumer_exclusions = {"path", "sha256"}
          sha256 of the exclusion file; that file is a JSON list of rows (or an object with
          "required_profile_exclusions") and its rows must equal the report's required_profile_exclusions
      media.consumer_exclusion_policy   = {"path", "sha256", "profile_kind", "rows"}; sha256 must match the pin
      media.consumer_exclusions         [per-bitmap {source_key, source_datum, dropped_source_images, ...}]
      media.bitmap_catalog[].dispositions[] with disposition "excluded_by_consumer_exclusion"
          the per-image records; their distinct (source_key, source_datum, source_image_index) is the profile's
          dropped-image count
    Reconciliation: distinct dropped images in each manifest == report counts for that profile.
    Metrics are per profile kind (ui, bots, survival): profiles, live, excluded; "live" is the report-wide
    live-consumer occurrence count, since reader liveness is not per profile.
    """
    errors, open_findings, metrics = [], [], {}
    evidence = _evidence(Path(path), role="consumer-roles-audit")
    try:
        report = _read_json(path)
    except (OSError, ValueError) as error:
        open_findings.append(f"consumer roles report is missing or unreadable: {error}")
        return {"errors": errors, "open_findings": open_findings, "metrics": metrics, "evidence": evidence}
    if not isinstance(report, dict):
        errors.append("consumer roles report is not a JSON object")
        return {"errors": errors, "open_findings": open_findings, "metrics": metrics, "evidence": evidence}
    rule = report.get("rule")
    if isinstance(rule, dict):  # v4: the quoted user decision plus its media/admission clarifications
        rule = rule.get("user_decision")
    if not isinstance(rule, str) or not rule.strip():
        errors.append("consumer roles report lacks its consumer rule")
    pairs = _consumer_elf_pairs(report)
    if not pairs:
        errors.append("stale consumer audit: report pins no elf_inputs")
    for name, expected in pairs:
        elf = _file(root, str(name or ""))
        if not elf.is_file() or not isinstance(expected, str) or sha_file(elf) != expected:
            errors.append(f"stale consumer audit: elf input is missing or its sha256 differs from disk: {name}")

    occurrences = report.get("occurrences")
    live_counts = {disposition: 0 for disposition in CONSUMER_ALLOWED}
    blocking = 0
    if isinstance(occurrences, list) and occurrences:
        for row in occurrences:
            disposition = _disposition_of(row)
            if disposition in live_counts:
                live_counts[disposition] += 1
            else:
                blocking += 1
    else:
        # v4 aggregates dispositions; every counted key must be allowed and "undecided" must be zero.
        totals = (report.get("totals") or {}).get("disposition_occurrence_counts")
        if not isinstance(totals, dict) or not totals:
            errors.append("consumer roles report has no occurrence dispositions")
            totals = {}
        for disposition, count in totals.items():
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                errors.append(f"consumer roles disposition count is invalid: {disposition}")
            elif disposition in live_counts:
                live_counts[disposition] += count
            else:
                blocking += count
        if totals and report.get("result") != "all_occurrences_decided":
            errors.append("consumer roles report does not state that all occurrences are decided")
    if blocking or report.get("blocking") not in (None, 0):
        errors.append(f"consumer roles report has blocking or undecided dispositions: {blocking}")

    exclusions = report.get("required_profile_exclusions")
    expected_removed: dict[str, int] = {}
    per_profile = None
    dropped_images = report.get("dropped_images")
    if isinstance(dropped_images, dict) and "per_profile" in dropped_images:
        if dropped_images.get("unit") != "distinct 2D source images":
            errors.append("consumer roles dropped_images does not state the distinct 2D source image unit")
        per_profile = dropped_images.get("per_profile")
        if not isinstance(per_profile, dict):
            errors.append("consumer roles dropped_images.per_profile is not an object")
            per_profile = {}
    if not isinstance(exclusions, list):
        errors.append("consumer roles report lacks required_profile_exclusions")
        exclusions = []
    for item in exclusions:
        counts = item.get("counts") if isinstance(item, dict) else None
        if not isinstance(counts, dict):
            errors.append("consumer roles required_profile_exclusions entry lacks a counts object")
            continue
        kinds = item.get("profile_kinds") or []
        for profile_name, count in counts.items():
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                errors.append(f"consumer roles count for {profile_name} is not a non-negative integer")
                continue
            if count and str(profile_name).split("-")[0] not in kinds:
                errors.append(f"consumer exclusion counts {profile_name} outside its profile_kinds")
            if per_profile is None:
                if profile_name in expected_removed and expected_removed[profile_name] != count:
                    errors.append(f"consumer roles counts for {profile_name} disagree across rows; "
                                  "counts are distinct dropped images per profile")
                expected_removed[profile_name] = count
    if per_profile is not None:
        # v4: rows count per exclusion class; the per-profile totals come from the shared decision function.
        for profile_name, count in per_profile.items():
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                errors.append(f"consumer roles dropped_images for {profile_name} is not a non-negative integer")
            else:
                expected_removed[profile_name] = count

    pins, manifests = {}, {}
    for name, result in profiles.items():
        manifest = result.get("manifest") if isinstance(result, dict) else None
        if not isinstance(manifest, dict):
            errors.append(f"{name}: manifest is missing for consumer reconciliation")
            continue
        manifests[name] = manifest
        pins[name] = _consumer_pin(manifest)
    shared_pin = None
    if any(pin is None for pin in pins.values()):
        open_findings.append("profiles were built without the consumer exclusions")
    elif pins and len(set(pins.values())) > 1:
        errors.append("profiles record different consumer exclusion inputs")
    elif pins:
        pin_path, pin_sha = next(iter(set(pins.values())))
        shared_pin = pin_sha
        exclusion_file = _file(root, pin_path)
        if not exclusion_file.is_file() or sha_file(exclusion_file) != pin_sha:
            errors.append(f"consumer exclusion input is missing or its sha256 differs from the profile pin: {pin_path}")
        else:
            try:
                exclusion_doc = _read_json(exclusion_file)
            except (OSError, ValueError):
                exclusion_doc = None
            rows = exclusion_doc.get("required_profile_exclusions") if isinstance(exclusion_doc, dict) else exclusion_doc
            if canonical_sha(rows) != canonical_sha(exclusions):
                errors.append("consumer exclusion input does not carry the report's required_profile_exclusions")
        evidence["details_exclusion_input"] = {"path": pin_path, "sha256": pin_sha}
        report_pin = report.get("consumer_exclusions")
        if isinstance(report_pin, dict) and report_pin.get("sha256") != pin_sha:
            errors.append("consumer roles report pins a different exclusion input than the built profiles")

    for name, manifest in manifests.items():
        _all_dropped, dropped_errors = _dropped_images(manifest, shared_pin)
        errors.extend(f"{name}: {message}" for message in dropped_errors)
        # Unit (user decision 2026-10-23): distinct 2D source images. Non-2D images are reported separately.
        dropped = set()
        for entry in (manifest.get("media") or {}).get("bitmap_catalog") or []:
            for disposition in entry.get("dispositions") or [] if isinstance(entry, dict) else []:
                if (isinstance(disposition, dict) and disposition.get("disposition") == CONSUMER_EXCLUDED_IMAGE
                        and disposition.get("is_2d") is not False):  # v3 rows state is_2d; older rows are 2D
                    dropped.add((disposition.get("source_key"), disposition.get("source_datum"),
                                 disposition.get("source_image_index")))
        expected = expected_removed.get(name, 0)
        if len(dropped) != expected:
            errors.append(f"{name}: manifest removed {len(dropped)} distinct dropped images but report counts {expected}")
        kind = str(name).split("-")[0]
        bucket = metrics.setdefault(kind, {"profiles": 0, "live": live_counts[CONSUMER_LIVE], "excluded": 0})
        bucket["profiles"] += 1
        bucket["excluded"] += len(dropped)
    metrics = {"per_profile_kind": metrics,
               "report_occurrences": {"live": live_counts[CONSUMER_LIVE],
                                      "excluded": live_counts[CONSUMER_EXCLUDED],
                                      "dropped": live_counts[CONSUMER_DROPPED], "blocking": blocking}}
    return {"errors": errors, "open_findings": open_findings, "metrics": metrics, "evidence": evidence}


def qualify(profiles_dir: Path, rebuild_dir: Path, *, roster_path=DEFAULT_ROSTER,
            weapon_report_path=DEFAULT_WEAPONS, schema_elf=DEFAULT_SCHEMA_ELF,
            ce_report_path=DEFAULT_CE_REPORT, bitmap_dir=DEFAULT_BITMAP_DIR,
            bitmap_dispatch_path=DEFAULT_BITMAP_DISPATCH,
            preflight_report_path=DEFAULT_PREFLIGHT_REPORT,
            native_corpus_path=None, consumer_roles_path=DEFAULT_CONSUMER_ROLES,
            root=ROOT) -> dict:
    profiles_dir, rebuild_dir = Path(profiles_dir), Path(rebuild_dir)
    rows = [
        _requirement(1, "Deterministic manifests for UI, stock multiplayer, and survival; source roots, dependencies, hashes, import decisions, package hashes, memory needs, and no campaign scenario roots"),
        _requirement(2, "Every resolved retail combat actor variant is imported from retained sources with complete dependencies and valid placement recipes; noncombat/script-only dispositions are explicit and hollow recipes are rejected",
                     limitations=("Placement recipes do not prove bot runtime behavior",)),
        _requirement(3, "Schema-driven import, reference remapping, stable output identities, dependency deduplication, and deterministic source choice for conflicts; no synthesized stock-MP actor references",
                     limitations=("Host package validation does not prove target loading",)),
        _requirement(4, "CE data is resident for pointer lifetime; render/media payloads use independently addressable integrity-checked chunks, and only proven live-consumer data is included",
                     limitations=("Host CE-to-GS packets do not prove framebuffer parity",)),
        _requirement(5, "Sword, gravity-rifle, and fuel-rod closures and separately sourced presentation assets are provenance-bound, including resolved fuel-rod bitmap metadata",
                     limitations=("CBSP and POSE package integrity does not prove C2 placement or rendered frames",)),
        _requirement(6, "Missing, corrupt, or incompatible dependencies fail closed; sound identities and request metadata remain available while SPU2 playback stays unqualified",
                     limitations=("No SPU2 playback qualification", "No C2 EE memory-fit claim")),
    ]
    rows[0]["checks"] = ["exact 27-profile matrix and deterministic independent manifests/packages",
        "pinned producer/source-map/source-root provenance", "selected scenario and custom roots resolve without campaign scenario roots"]
    rows[1]["checks"] = ["retained 336-variant/75-recipe roster and complete 255 combat/mounted occurrence set",
        "exact source-roster recipe comparison including required fields", "output-datum-bound actor occurrence references"]
    rows[2]["checks"] = ["fresh schema-derived CE walk and package validation", "typed reference and tag-index remaps match schema slots",
        "unique source-occurrence remaps bind every dependency to output identities", "duplicate output identities are rejected; dependency source choices remain deterministic through exact rebuild equality"]
    rows[3]["checks"] = ["per-profile bitmap image accounting", "native UI bitmap fixture binds final package/source image and reaches native GS packet output",
        "media chunks are integrity checked and resource admission is explicit",
        "live media lifecycle: payload to registered CE request to profile binding to cache lease/upload to actual chain emission"]
    rows[4]["checks"] = ["all selected BSP owners match retail source extents", "separate sword/gravity POSE payload provenance and bindings",
        "three custom weapon closures and fuel-rod metadata dispositions are validated"]
    rows[5]["checks"] = ["missing/incompatible package dependencies fail fresh validation", "sound metadata-only policy and request identities are explicit",
        "CE corrections, memory needs, and native admission limits are evidence-bound",
        "real current UI HCP accepted before same-map teardown; incompatible/corrupt packages rejected while active CE snapshot is preserved"]
    r1, r2, r3, r4, r5, r6 = rows
    errors = []
    try:
        roster = _read_json(Path(roster_path))
        weapon_report = _read_json(Path(weapon_report_path))
        if not isinstance(roster, dict) or not isinstance(weapon_report, dict):
            raise ValueError("roster and special-weapon files must be JSON objects")
    except (OSError, json.JSONDecodeError) as error:
        roster = weapon_report = None
        _finding(r1, f"roster or special-weapon report is missing/invalid: {error}", status="open")
    if roster is not None:
        expected_actor = _expected_actor_occurrences(roster)
        r3["measurements"].update({"roster_variant_occurrences": len(roster.get("variants", [])),
                                   "unique_recipes": len(roster.get("unique_recipes", [])),
                                   "expected_combat_mounted_occurrences": len(expected_actor)})
        variants = roster.get("variants", [])
        if len(variants) != 336:
            _finding(r3, f"actor roster has {len(variants)} source variants; expected all 336 retained occurrences")
        allowed_dispositions = {"combat", "mounted_occupant", "noncombat", "hollow_or_unplaceable"}
        for variant in variants:
            disposition = variant.get("disposition")
            if disposition not in allowed_dispositions:
                _finding(r3, f"actor roster has a missing or unsupported disposition: {variant.get('path')}")
            if disposition == "combat" and not variant.get("recipe"):
                _finding(r3, f"combat actor lacks a non-hollow placement recipe: {variant.get('path')}")
            elif disposition == "mounted_occupant" and not variant.get("mounted_recipes"):
                _finding(r3, f"mounted actor lacks an occupant placement recipe: {variant.get('path')}")
            elif disposition in ("noncombat", "hollow_or_unplaceable") and (
                    variant.get("recipe") or variant.get("mounted_recipes")):
                _finding(r3, f"noncombat/hollow actor is incorrectly accepted as a spawn recipe: {variant.get('path')}")
        if len(expected_actor) != 255:
            _finding(r3, f"actor roster has {len(expected_actor)} complete combat/mounted occurrences; expected 255")
        if len(roster.get("unique_recipes", [])) != 75:
            _finding(r3, "actor roster does not pin the expected 75 logical recipes")
        for source in roster.get("source_roots", []):
            source_path = _file(root, source.get("path", ""))
            if not source_path.is_file() or sha_file(source_path) != source.get("sha256"):
                _finding(r1, f"actor source-root file/hash is missing or stale: {source.get('path')}")
    if weapon_report is not None:
        for error in _audit_special_weapon_metadata(weapon_report):
            _finding(r5, error)
        if set(weapon_report.get("weapon_roots", {})) != {"energy_sword", "gravity_rifle", "fuel_rod"}:
            _finding(r1, "special-weapon input does not contain the three required custom roots")
        if len(weapon_report.get("weapon_roots", {})) != 3:
            _finding(r1, "special-weapon input is incomplete")
        source_name = Path(weapon_report.get("source_map", "")).name
        source_map = _file(root, weapon_report.get("source_map", ""))
        if not source_map.is_file():
            source_map = root / "build/retail-maps/decompressed" / source_name
        if not source_map.is_file() or sha_file(source_map) != weapon_report.get("source_map_sha256"):
            _finding(r1, "special-weapon source map pin is missing or stale")
        r1["evidence"].append(_evidence(Path(weapon_report_path), role="special-weapon-input"))
    if roster is not None:
        r1["evidence"].append(_evidence(Path(roster_path), role="actor-roster-input"))

    schemas = None
    try:
        schemas = SchemaManifest(Elf32(Path(schema_elf))).build()
    except (OSError, ValueError, KeyError) as error:
        _finding(r2, f"compiler-derived schema ELF is unavailable: {error}", status="open")

    specs_a = _check_specs(profiles_dir, r1, roster, weapon_report)
    specs_b = _check_specs(rebuild_dir, r1, roster, weapon_report)
    if specs_a is not None and specs_b is not None and specs_a != specs_b:
        _finding(r2, "primary and independent rebuild profile specs differ")
        _finding(r1, "primary and independent profile manifests/specifications are not deterministic")
    if not Path(schema_elf).is_file():
        _finding(r1, f"schema ELF is missing: {schema_elf}", status="open")
    elif schemas:
        r1["evidence"].append(_evidence(Path(schema_elf), role="compiler-derived-schema-ELF",
                                         details={"elf_sha256": schemas.get("elf_sha256")}))

    manifests_a = _load_manifests(profiles_dir, r2)
    manifests_b = _load_manifests(rebuild_dir, r2)
    manifest_evidence_names = set()
    for name, _kind, _map in EXPECTED:
        for manifest in (manifests_a.get(name), manifests_b.get(name)):
            if manifest is None:
                continue
            for error in _audit_import_identities(name, manifest):
                _finding(r2, error)
            if roster is not None:
                for error in _audit_stock_mp_actor_origins(name, manifest, roster):
                    _finding(r3, error)
            for error in _producer_and_source_pins(manifest, root=root):
                _finding(r1, f"{name}: {error}")
            if roster is not None and weapon_report is not None:
                for error in _check_root_and_special_identity(name, manifest, weapon_report, root=root):
                    _finding(r1, f"{name}: {error}")
            if manifest.get("schema_elf_sha256") != (schemas or {}).get("elf_sha256"):
                _finding(r1, f"{name}: schema ELF identity is stale or mismatched")
            if name not in manifest_evidence_names:
                rowpath = _profile_files(profiles_dir, name)[1]
                if rowpath.is_file():
                    r1["evidence"].append(_evidence(rowpath, role="profile-manifest-provenance",
                        details={"source_map_count": len(manifest.get("source_maps", {})),
                                 "source_map_pins": manifest.get("source_maps", {}),
                                 "producer_pins": manifest.get("producers", {})}))
                    manifest_evidence_names.add(name)
            if manifest.get("profile", {}).get("kind") == "survival" and roster is not None:
                _audit_actor_bindings(name, manifest, expected_actor, r3, roster=roster)
                for error in _audit_actor_source_closures(name, manifest, roster):
                    _finding(r3, error)

    # Per-profile actual HCP parsing/schema validation and independent equality.
    validations = {}
    rebuild_validations = {}
    if schemas is not None:
        for name, _kind, _map in EXPECTED:
            a, ea = _validate_pair(profiles_dir, name, schemas)
            b, eb = _validate_pair(rebuild_dir, name, schemas)
            for error in ea + eb:
                _finding(r2, error, status="open" if "missing" in error else "fail")
            if a is None or b is None:
                continue
            if not ea and not eb:
                rebuild_validations[name] = b
            for error in compare_profile_builds(profiles_dir, rebuild_dir, name):
                _finding(r2, error)
                _finding(r1, f"{name}: {error}")
            validations[name] = a
            if not ea and not eb:
                r2["evidence"].append({"profile": name, "package_sha256": a["package_sha256"],
                                       "package_path": a["package_path"],
                                       "manifest_path": a["manifest_path"],
                                       "tag_count": a["validation"]["tag_count"],
                                       "media_chunk_count": a["validation"]["media_chunk_count"],
                                       "bsp_count": a["validation"]["bsp_count"]})
                coverage = a["validation"].get("bitmap_coverage", {})
                images = coverage.get("images", 0)
                serialized = coverage.get("serialized_images", 0)
                excluded = coverage.get("excluded_nonconsumer_images", 0)
                if images != serialized + excluded:
                    _finding(r4, f"{name}: per-image bitmap inventory is not completely accounted for")
                if name == "ui" and images <= 0:
                    _finding(r4, "UI bitmap profile has no schema-derived images")
                r4["evidence"].append({"profile": name, "package_path": a["package_path"],
                    "package_sha256": a["package_sha256"], "bitmap_coverage": coverage})
                r4["measurements"].setdefault("bitmap_images_by_profile", {})[name] = coverage

    # Actor rows are based on the fully validated CTAG source-occurrence map.
    survival_names = [name for name, kind, _ in EXPECTED if kind == "survival"]
    if len(survival_names) != 13 or sum(manifests_a.get(n, {}).get("profile", {}).get("kind") == "survival"
                                        for n in survival_names) != 13:
        _finding(r3, "all thirteen survival profile manifests are required", status="open")
    for name in survival_names:
        manifest_path = _profile_files(profiles_dir, name)[1]
        if name in manifests_a and manifest_path.is_file():
            r3["evidence"].append(_evidence(manifest_path, role="survival-actor-bindings",
                details={"binding_count": len(manifests_a[name].get("actor_bindings", []))}))
    if len(validations) != len(EXPECTED):
        for row in (r3, r4, r5, r6):
            _finding(row, "full 27-profile package set has not validated", status="open")

    # Bitmap proof is a separate named CE-to-GS native fixture; each profile's
    # inventory and coverage are also supplied by the fresh HCP validation.
    try:
        bitmap_evidence = _bitmap_evidence(Path(bitmap_dir), r4, root=root, schema_elf=schema_elf,
                                           ui_profile=validations.get("ui"))
        r4["evidence"].extend(bitmap_evidence["cases"])
        r4["evidence"].extend(bitmap_evidence["exact_fixture"])
        r4["measurements"]["native_retail_bitmap_cases"] = len(bitmap_evidence["cases"])
        r4["measurements"]["qualified_ui_image_coverage_profiles"] = sum(
            name in validations and validations[name]["validation"].get("bitmap_coverage", {}).get("images", 0) >=
            validations[name]["validation"].get("bitmap_coverage", {}).get("serialized_images", 0)
            for name, kind, _ in EXPECTED if kind == "ui")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        _finding(r4, f"bitmap native pipeline evidence is missing or invalid: {error}", status="open")
    try:
        dispatch = _check_bitmap_live_dispatch(Path(bitmap_dispatch_path), validations,
                                               rebuild_validations, root=root)
        for error in dispatch["errors"]:
            _finding(r4, error, status="open" if "missing" in error else "fail")
        for message in dispatch["open_findings"]:
            _finding(r4, message, status="open")
        r4["deferred_to"].extend(dispatch["deferred"])
        if dispatch["deferred"]:
            r4["limitations"].append("Native bitmap dispatch is host-only and pre-fence; running-frame binding is deferred to C3")
        r4["evidence"].append(dispatch["evidence"])
        r4["measurements"].update(dispatch["metrics"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError) as error:
        _finding(r4, f"native live bitmap dispatch evidence is missing or invalid: {error}", status="open")
    try:
        consumer = _check_consumer_roles(Path(consumer_roles_path), validations, root=root)
        for message in consumer["errors"]:
            _finding(r4, message)
        for message in consumer["open_findings"]:
            _finding(r4, message, status="open")
        r4["measurements"]["consumer_roles"] = consumer["metrics"]
        # User decision 2 (2026-10-23): live readers' hookup into the HCU frame is carried by the audit as a
        # C3 deferral. Kept HUD media is live only under it, so the row states it explicitly.
        roles_report = _read_json(Path(consumer_roles_path))
        for item in roles_report.get("deferred_to") or [] if isinstance(roles_report, dict) else []:
            if isinstance(item, dict) and item not in r4["deferred_to"]:
                r4["deferred_to"].append({**item, "decided_by": item.get("decided_by", "user 2026-10-23"),
                                          "source": "consumer-roles audit"})
                r4["limitations"].append("Kept HUD and parent-reader media are live-consumer data under the consumer "
                                         "rule; their hookup into the running HCU frame is deferred to C3.6")
        r4["evidence"].append(consumer["evidence"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        _finding(r4, f"consumer roles evidence is missing or invalid: {error}", status="open")

    for name, result in validations.items():
        manifest = result["manifest"]
        media = manifest.get("media") if isinstance(manifest.get("media"), dict) else {}
        catalog = media.get("bsp_catalog", [])
        if not isinstance(catalog, list):
            catalog = []
        expected = sum(t.get("group") == "sbsp" for t in manifest.get("dependencies", []))
        if len(catalog) != expected or result["validation"].get("bsp_count") != expected:
            _finding(r5, f"{name}: BSP catalog does not cover every selected SBSP tag")
        if any(item.get("runtime_admitted") is not False for item in catalog):
            _finding(r5, f"{name}: CBSP catalog incorrectly claims runtime admission")
        profile = manifest.get("profile", {})
        source_key = profile.get("map")
        source_pin = manifest.get("source_maps", {}).get(source_key, {})
        source_path = _file(root, source_pin.get("path", ""))
        if not source_path.is_file():
            _finding(r5, f"{name}: selected retail source map is unavailable for BSP inventory", status="open")
            source_inventory = {}
        else:
            try:
                source_inventory = _source_bsp_inventory(source_path, source_key)
            except (OSError, ValueError, KeyError) as error:
                _finding(r5, f"{name}: cannot enumerate retail scenario BSPs: {error}")
                source_inventory = {}
        descriptor_owners = [tuple(row.get("owner", {}).get(field) for field in
                                   ("source_key", "group", "path", "source_datum"))
                             for row in catalog]
        if (set(descriptor_owners) != set(source_inventory) or
                len(descriptor_owners) != len(source_inventory)):
            _finding(r5, f"{name}: CBSP owner set does not match every retail scenario BSP")
        for descriptor in catalog:
            owner = descriptor.get("owner", {})
            identity = tuple(owner.get(field) for field in
                             ("source_key", "group", "path", "source_datum"))
            extent = source_inventory.get(identity)
            if extent is None:
                continue
            for field, expected_value in extent.items():
                if descriptor.get(field) != expected_value:
                    _finding(r5, f"{name}: CBSP {field} differs from retail source extent")
            if (descriptor.get("source_map_sha256") != source_pin.get("sha256") or
                    descriptor.get("schema_elf_sha256") != manifest.get("schema_elf_sha256")):
                _finding(r5, f"{name}: CBSP source map or schema ELF pin is stale")
        if catalog:
            r5["evidence"].append({"profile": name, "package_path": result["package_path"],
                                   "package_sha256": result["package_sha256"],
                                   "bsp_count": len(catalog),
                                   "retail_source_bsp_count": len(source_inventory),
                                   "catalog_sha256": canonical_sha(catalog)})

    # Metadata-only sound and host CE validation. No playback or EE fit claims.
    for name, result in validations.items():
        manifest = result["manifest"]
        resource_policy = manifest.get("resource_policy")
        if not isinstance(resource_policy, dict) or resource_policy.get("sound_samples") != "metadata_only_spu2_unqualified":
            _finding(r6, f"{name}: sound policy does not state metadata-only/SPU2 unqualified")
        memory = manifest.get("memory", {})
        if not isinstance(memory, dict):
            memory = {}
            _finding(r6, f"{name}: profile memory needs are not an object")
            _finding(r1, f"{name}: profile memory needs are not an object")
        if not isinstance(memory.get("resident_recipe_bytes"), int) or memory.get("resident_recipe_bytes", 0) <= 0:
            _finding(r6, f"{name}: profile memory needs are absent")
            _finding(r1, f"{name}: profile memory needs are absent")
        package = parse_package(Path(result["package_path"]).read_bytes(),
            expected_package_sha256=result["package_sha256"],
            expected_profile_id=manifest.get("profile", {}).get("id"))
        ce_blob = package["chunks"][(1, 0)]
        decoded = ctag.decode(ce_blob, max_image_size=len(ce_blob))
        expected_memory = {"image_bytes": len(decoded.image), "resident_ce_bytes": len(decoded.image),
                           "resident_recipe_bytes": len(decoded.image),
                           "normalized_ctag_bytes": len(ce_blob),
                           "ctag_relocation_entries": len(decoded.relocations),
                           "pointer_relocations": len(decoded.relocations)}
        for field, value in expected_memory.items():
            if memory.get(field) != value:
                _finding(r6, f"{name}: per-profile memory field {field} differs from package bytes")
                _finding(r1, f"{name}: per-profile memory field {field} differs from package bytes")
        if memory.get("tag_relocations") != len(manifest.get("tag_relocations") or []):
            _finding(r6, f"{name}: per-profile tag relocation need differs from schema ledger")
            _finding(r1, f"{name}: per-profile tag relocation need differs from schema ledger")
        r6["evidence"].append({"profile": name, "package_path": result["package_path"],
            "package_sha256": result["package_sha256"], "memory_needs": memory,
            "validated_ctag_image_bytes": len(decoded.image),
            "validated_ctag_relocation_entries": len(decoded.relocations)})
        if name == "ui" or name == "survival-beavercreek":
            if result["validation"].get("package_sha256") != result["package_sha256"]:
                _finding(r6, f"{name}: validated package hash mismatch")
        sound_blob = package["chunks"][(3, 0)]
        r6["evidence"].append({"profile": name, "package_path": result["package_path"],
            "package_sha256": result["package_sha256"], "sound_metadata_sha256": _sha(sound_blob),
            "resource_policy": manifest.get("resource_policy")})
    try:
        if native_corpus_path is not None:
            ce = _check_native_corpus(Path(native_corpus_path), validations, rebuild_validations, root=root)
            ce_report_role = "native-CE-all-profile-corpus"
        else:
            ce = _check_ce_report(Path(ce_report_path), validations, rebuild_validations, root=root)
            ce_report_role = "native-CE-validation-report"
        for error in ce["errors"]:
            _finding(r6, error, status="open" if "missing" in error else "fail")
        evidence_path = Path(native_corpus_path) if native_corpus_path is not None else Path(ce_report_path)
        r6["evidence"].append(_evidence(evidence_path, role=ce_report_role,
                                        details=ce["metrics"]))
        r6["evidence"].extend(ce["evidence"])
        r6["measurements"].update(ce["metrics"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError) as error:
        _finding(r6, f"native CE validation evidence is missing or invalid: {error}", status="open")
    try:
        preflight = _check_preflight_report(Path(preflight_report_path), validations,
            rebuild_validations, Path(schema_elf), root=root)
        for error in preflight["errors"]:
            _finding(r6, error, status="open" if "missing" in error else "fail")
        r6["evidence"].append(_evidence(Path(preflight_report_path), role="native-CE-real-preflight",
                                        details=preflight["metrics"]))
        r6["measurements"].update(preflight["metrics"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError) as error:
        _finding(r6, f"real CE preflight evidence is missing or invalid: {error}", status="open")

    # Every required root must be backed by a source occurrence and CTAG output
    # datum; no imported resource may silently be lost between builder ledgers.
    for name, result in validations.items():
        manifest = result["manifest"]
        if weapon_report is not None:
            for error in _audit_profile_presentation(name, result, weapon_report, root=root):
                _finding(r5, error)
        remaps = manifest.get("source_occurrence_remaps", [])
        dependencies = manifest.get("dependencies", [])
        source_occurrences = {(r.get("source_key"), r.get("group"), r.get("path"), r.get("source_datum"))
                              for r in remaps}
        for dep in dependencies:
            identity = (dep.get("source_key"), dep.get("group"), dep.get("path"), dep.get("source_datum"))
            if identity not in source_occurrences:
                _finding(r1, f"{name}: dependency lacks source occurrence provenance: {identity}")
        for binding in manifest.get("media", {}).get("bindings", []):
            if binding.get("kind") == "CBSP" and not binding.get("chunk_key", "").startswith("CBSP:"):
                _finding(r5, f"{name}: CBSP media binding lacks content-addressed identity")

    for row in rows:
        _finish(row)
    complete = all(row["status"] == "pass" for row in rows)
    overall_status = "pass" if complete else ("fail" if any(r["status"] == "fail" for r in rows) else "open")
    verification_paths = [Path(roster_path), Path(weapon_report_path), Path(schema_elf),
                          Path(bitmap_dispatch_path), Path(preflight_report_path),
                          Path(bitmap_dir) / "test_actual_retail_ui_bitmap_c0" / "case-metadata.json",
                          Path(bitmap_dir) / "test_actual_retail_ui_bitmap_c1" / "case-metadata.json"]
    if native_corpus_path is not None:
        verification_paths.append(Path(native_corpus_path))
    # The CE report is read in both configurations, so it is always pinned.
    verification_paths.append(Path(ce_report_path))
    for directory in (profiles_dir, rebuild_dir):
        for profile_name, _, _ in EXPECTED:
            verification_paths.extend(_profile_files(directory, profile_name))
    verification_inputs = [_evidence(path, role="qualification-input") for path in verification_paths]
    report = {"format": "hcu-c1-qualification-v1", "status": overall_status,
              "qualified": complete,
              "acceptance_contract": {"plan": "plans/7.hcu-remake-m2-m4.md",
                  "section": "C1 — Produce complete multiplayer asset profiles",
                  "requirements": [row["id"] for row in rows],
                  "interpretation": "Each C1.N row corresponds to plan clause N; checks name the evidence subchecks supporting that clause. Shared corpus and provenance checks may be cited by more than one clause."},
              "producer": {"path": "tools/qualify_hcu_c1.py",
                           "sha256": sha_file(Path(__file__).resolve())},
              "verification_inputs": verification_inputs,
              "scope": "C1 profile assets and evidence only; no C2 EE fit, C3 rendered frame, SPU2 playback, or console admission claim.",
              "inputs": {"profiles": str(profiles_dir), "independent_rebuild": str(rebuild_dir),
                         "roster": str(roster_path), "special_weapons": str(weapon_report_path),
                         "schema_elf": str(schema_elf), "native_ce_report": str(ce_report_path),
                         "native_bitmap_dispatch": str(bitmap_dispatch_path),
                         "real_ce_preflight_report": str(preflight_report_path),
                         "bitmap_native_evidence": str(bitmap_dir),
                         "consumer_roles": str(consumer_roles_path),
                         "native_ce_corpus": str(native_corpus_path) if native_corpus_path else None},
              "requirements": rows,
              "summary": {"passed": sum(r["status"] == "pass" for r in rows),
                          "failed": sum(r["status"] == "fail" for r in rows),
                          "open": sum(r["status"] == "open" for r in rows)}}
    return report


def _source_recipe(value):
    if isinstance(value, list):
        return [_source_recipe(item) for item in value]
    if isinstance(value, dict):
        return {key: _source_recipe(item) for key, item in value.items()
                if key not in ('output_datum', 'stable_key')}
    return value


def _audit_actor_bindings(name: str, manifest: dict, expected: set, row: dict, *, roster=None) -> None:
    bindings = manifest.get("actor_bindings", [])
    if len(bindings) != 255:
        _finding(row, f"{name}: has {len(bindings)} actor bindings; expected all 255 combat/mounted occurrences")
        return
    remaps = manifest.get("source_occurrence_remaps", [])
    by_output = {}
    for remap in remaps:
        by_output.setdefault((remap.get("source_key"), remap.get("output_datum")), []).append(remap)
    actual = set()
    recipes = {}
    for variant in (roster or {}).get('variants', []):
        identity = (variant['map'], variant['path'], variant['datum'])
        if variant.get('disposition') == 'combat' and variant.get('recipe'):
            recipes.setdefault((*identity, 'combat_variant'), []).append(variant['recipe'])
        for recipe in variant.get('mounted_recipes', []):
            recipes.setdefault((*identity, 'mounted_variant'), []).append(recipe)
    tags = {d.get("output_datum"): (d.get("group"), d.get("path"))
            for d in manifest.get("dependencies", [])}
    def inspect(value):
        if isinstance(value, dict):
            if value.get("group") and value.get("path"):
                datum = value.get("output_datum")
                if datum is None or tags.get(datum) != (value["group"], value["path"]):
                    raise ValueError("actor recipe reference has no matching CTAG output datum")
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    try:
        for binding in bindings:
            if binding.get("role") not in ("combat_variant", "mounted_variant"):
                raise ValueError("actor binding has an unsupported placement role")
            source = binding.get("source_key")
            path = binding.get("path")
            outputs = by_output.get((source, binding.get("output_datum")), [])
            matches = [r for r in outputs if r.get("group") == "actv" and r.get("path") == path]
            if len(matches) != 1:
                raise ValueError("actor source occurrence does not resolve to exactly one output datum")
            source_datum = matches[0].get("source_datum")
            identity = (source, path, source_datum, binding['role'])
            actual.add(identity)
            recipe = binding.get('recipe')
            required = ('variant', 'unit', 'actor') if binding['role'] == 'combat_variant' else ('variant', 'parent_vehicle', 'seat_index')
            if not isinstance(recipe, dict) or any(recipe.get(field) is None for field in required):
                raise ValueError('actor placement recipe is empty or lacks required fields')
            if roster is not None and _source_recipe(recipe) not in recipes.get(identity, []):
                raise ValueError('actor placement recipe differs from the retained source roster')
            inspect(recipe)
        if len(actual) != len(bindings) or actual != expected:
            raise ValueError("actor binding source occurrences differ from the complete roster")
    except (TypeError, ValueError) as error:
        _finding(row, f"{name}: {error}")
    else:
        row["measurements"].setdefault("actor_occurrence_bindings", {})[name] = len(actual)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES,
                        help="primary clean HCP output directory (env HCU_C1_PROFILES)")
    parser.add_argument("--rebuild", type=Path, default=DEFAULT_REBUILD,
                        help="independent clean HCP rebuild directory (env HCU_C1_REBUILD)")
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--weapons", type=Path, default=DEFAULT_WEAPONS)
    parser.add_argument("--schema-elf", type=Path, default=DEFAULT_SCHEMA_ELF)
    parser.add_argument("--ce-report", type=Path, default=DEFAULT_CE_REPORT)
    parser.add_argument("--bitmap-dir", type=Path, default=DEFAULT_BITMAP_DIR)
    parser.add_argument("--bitmap-dispatch", type=Path, default=DEFAULT_BITMAP_DISPATCH)
    parser.add_argument("--preflight-report", type=Path, default=DEFAULT_PREFLIGHT_REPORT)
    parser.add_argument("--native-corpus", type=Path, default=DEFAULT_NATIVE_CORPUS,
                        help="all-27-profile native CE report; replaces the historical UI/survival pair report")
    parser.add_argument("--consumer-roles", type=Path, default=DEFAULT_CONSUMER_ROLES,
                        help="C1.4 consumer-role audit; its exclusions must be pinned by every profile manifest")
    parser.add_argument("--output", type=Path,
                        help="optional explicit report path; no report file is written without this option")
    args = parser.parse_args(argv)
    report = qualify(args.profiles, args.rebuild, roster_path=args.roster,
                     weapon_report_path=args.weapons, schema_elf=args.schema_elf,
                     ce_report_path=args.ce_report, bitmap_dir=args.bitmap_dir,
                     bitmap_dispatch_path=args.bitmap_dispatch,
                     preflight_report_path=args.preflight_report,
                     native_corpus_path=args.native_corpus,
                     consumer_roles_path=args.consumer_roles)
    payload = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
    print(payload, end="")
    return 0 if report["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
