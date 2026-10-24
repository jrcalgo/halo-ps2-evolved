#!/usr/bin/env python3
"""Compile a quiescent, session-selected C1 survival CE residency image.

The full C1 profile remains an archive/catalog artifact. This compiler resolves
the exact selected actor recipes first, then imports their complete schema
reference/index closure together with the scenario, BSP dependencies, Spartan
assets, and all three required special-weapon roots. It emits a selected CTAG
image before any target CE arena allocation is made.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path[:0] = [str(TOOLS), str(ROOT / "submodules/halo-ps2/tools")]

import ctag  # noqa: E402
from hcu_multiplayer_profiles import BuildCache, MP_MAPS, _source_set, actor_bindings  # noqa: E402
from hcu_profile_import import import_profile  # noqa: E402
from hcu_schema_manifest import Elf32, SchemaManifest  # noqa: E402

DEFAULT_ROSTER = ROOT / "docs/reports/m2-c1-actor-roster-2026-10-23.json"
DEFAULT_SPECS = ROOT / "build/m2-c1-corpus-rebuild-v3/specs.json"
DEFAULT_CORPUS = ROOT / "build/m2-c1-corpus-rebuild-v3"
DEFAULT_SCHEMA_ELF = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"
DEFAULT_MAPS = ROOT / "build/retail-maps/decompressed"
LIMIT_BYTES = 10_485_760
OWNER_ALIGNMENT = 16
INNER_OWNER_GUARD_BYTES = 16
RECIPE_FIELDS = ("actor", "equipment", "major_upgrade", "ranged_weapon", "unit", "variant")


class ResidencyError(ValueError):
    pass


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def _variant_key(source: str, path: str) -> tuple[str, str]:
    return (source.casefold(), path.casefold())


def _recipe_signature(recipe: dict) -> tuple:
    return tuple(
        ((recipe.get(field) or {}).get("group"),
         (recipe.get(field) or {}).get("path", "").casefold())
        if recipe.get(field) else None
        for field in RECIPE_FIELDS
    )


def recipe_matrix(roster: dict) -> tuple[list[dict], list[dict]]:
    """Map all retained source occurrences to the 75 canonical C1 recipes."""
    logical = roster.get("unique_recipes", [])
    if len(logical) != 75:
        raise ResidencyError(f"retained C1 roster expected 75 unique recipes, found {len(logical)}")
    recipe_by_signature = {}
    recipe_ids = {}
    for recipe in logical:
        signature = _recipe_signature(recipe)
        recipe_id = "recipe-" + sha_bytes(json.dumps(signature, separators=(",", ":")).encode())[:16]
        if signature in recipe_by_signature:
            raise ResidencyError("retained C1 unique recipe table contains a duplicate recipe signature")
        recipe_by_signature[signature] = recipe
        recipe_ids[signature] = recipe_id

    source_by_hash = {row["sha256"]: row["map"] for row in roster.get("source_roots", [])}
    selections = []
    for signature, recipe in sorted(recipe_by_signature.items(), key=lambda item: recipe_ids[item[0]]):
        source_map = source_by_hash.get(recipe.get("source_map_sha256"))
        if source_map is None:
            raise ResidencyError("logical recipe source map hash is absent from retained C1 sources")
        variant = recipe.get("variant", {})
        occurrences = [row for row in roster.get("variants", [])
                       if row.get("map") == source_map and row.get("source_map_sha256") == recipe["source_map_sha256"]
                       and row.get("datum") == variant.get("datum")
                       and row.get("path", "").casefold() == variant.get("path", "").casefold()
                       and row.get("disposition") in ("combat", "mounted_occupant")]
        if len(occurrences) != 1:
            raise ResidencyError(f"recipe {recipe_ids[signature]} has {len(occurrences)} exact source occurrences")
        row = occurrences[0]
        selection = {
            "format": "hcu-session-roster-selection-v1",
            "name": recipe_ids[signature],
            "scenario_profile": "survival-bloodgulch",
            "local_players": 1,
            "spartan_bots": 0,
            "selected_variants": [{
                "source_map": row["map"], "source_map_sha256": row["source_map_sha256"],
                "source_datum": row["datum"], "path": row["path"]}],
            "logical_recipe": {
                "recipe_id": recipe_ids[signature],
                "source_map": source_map,
                "source_map_sha256": recipe["source_map_sha256"],
                "source_aliases": recipe.get("source_aliases", []),
                "catalog_disposition": row["disposition"],
            },
        }
        selections.append(selection)

    mapping = []
    for row in roster.get("variants", []):
        disposition = row.get("disposition")
        if disposition == "combat" and row.get("recipe"):
            signature = _recipe_signature(row["recipe"])
        elif disposition == "mounted_occupant" and row.get("mounted_recipes"):
            candidate = [signature for signature, recipe in recipe_by_signature.items()
                         if recipe.get("variant", {}).get("group") == "actv"
                         and recipe.get("variant", {}).get("path", "").casefold() == row["path"].casefold()
                         and row["map"] in recipe.get("source_aliases", [])]
            if len(candidate) != 1:
                raise ResidencyError(f"mounted occurrence {row['map']}:{row['path']} maps to {len(candidate)} recipes")
            signature = candidate[0]
        else:
            continue
        recipe = recipe_by_signature.get(signature)
        if recipe is None:
            raise ResidencyError(f"catalog occurrence has no unique C1 recipe: {row['map']}:{row['path']}")
        mapping.append({
            "source_map": row["map"],
            "source_map_sha256": row["source_map_sha256"],
            "source_datum": row["datum"],
            "tag_group": row["group"],
            "path": row["path"],
            "catalog_disposition": disposition,
            "recipe_id": recipe_ids[signature],
        })
    if len(mapping) != 255 or len({row["recipe_id"] for row in mapping}) != 75:
        raise ResidencyError(f"catalog mapping must cover 255 occurrences and 75 recipes, got {len(mapping)} / {len({row['recipe_id'] for row in mapping})}")
    return selections, mapping


def compile_selection(selection: dict, roster: dict, specs: dict, schema: dict,
                      maps_dir: Path, cache: BuildCache, roster_path: Path,
                      specs_path: Path, corpus: Path, base_manifest: dict) -> tuple[dict, bytes]:
    if selection.get("format") != "hcu-session-roster-selection-v1":
        raise ResidencyError("unsupported setup selection format")
    name = str(selection.get("name", ""))
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in name):
        raise ResidencyError("selection name must be a nonempty filename-safe identifier")
    local_players = selection.get("local_players")
    spartan_bots = selection.get("spartan_bots")
    if type(local_players) is not int or not 1 <= local_players <= 4:
        raise ResidencyError("local_players must be an integer from 1 through 4")
    if type(spartan_bots) is not int or not 0 <= spartan_bots <= 4:
        raise ResidencyError("spartan_bots must be an integer from 0 through 4")
    scenario_profile = selection.get("scenario_profile")
    all_profiles = {item["name"]: item for item in specs.get("profiles", [])}
    base = all_profiles.get(scenario_profile)
    if not base or base.get("kind") != "survival":
        raise ResidencyError("scenario_profile must name a retained C1 survival profile")
    selected_rows = selection.get("selected_variants")
    if not isinstance(selected_rows, list) or not selected_rows:
        raise ResidencyError("selected_variants must contain at least one resolved combat or mounted occurrence")

    source_hashes = {row["map"]: row["sha256"] for row in roster.get("source_roots", [])}
    available = {}
    for row in roster.get("variants", []):
        selectable_combat = row.get("disposition") == "combat" and row.get("recipe")
        selectable_mounted = row.get("disposition") == "mounted_occupant" and row.get("mounted_recipes")
        if not (selectable_combat or selectable_mounted):
            continue
        source = row["map"]
        key = (source.casefold(), str(row["datum"]), row["path"].casefold())
        if key in available:
            raise ResidencyError(f"ambiguous retained actor occurrence {key}")
        available[key] = row

    selected = []
    seen = set()
    for requested in selected_rows:
        if not isinstance(requested, dict):
            raise ResidencyError("each selected variant must be an identity object")
        source = requested.get("source_map")
        datum = requested.get("source_datum")
        path = requested.get("path")
        if not isinstance(source, str) or type(datum) is not int or not isinstance(path, str):
            raise ResidencyError("variant identity requires source_map, integer source_datum, and path")
        key = (source.casefold(), str(datum), path.casefold())
        row = available.get(key)
        if row is None:
            raise ResidencyError(f"selected variant is absent from the retained roster catalog: {source}:{path}#{datum}")
        if requested.get("source_map_sha256") != source_hashes.get(row["map"]):
            raise ResidencyError(f"source-map SHA-256 is missing or stale for {source}:{path}")
        if key in seen:
            raise ResidencyError(f"selected variant is duplicated: {source}:{path}#{datum}")
        seen.add(key)
        selected.append(row)

    selected_sources = {_variant_key(row["map"], row["path"]) for row in selected}
    actor_roots = [row for row in base.get("actor_roots", [])
                   if row.get("role") in ("combat_variant", "mounted_variant") and
                   _variant_key(row.get("source", ""), row.get("path", "")) in selected_sources]
    if not actor_roots:
        raise ResidencyError("selected catalog variants produced no profile actor roots")
    expected_roots = sum((1 if row.get("recipe") else 0) + len(row.get("mounted_recipes", []))
                         for row in selected)
    if len(actor_roots) != expected_roots:
        raise ResidencyError(f"selected actor roots are incomplete ({len(actor_roots)} != {expected_roots})")

    selected_parents = set()
    for actor in actor_roots:
        parent = actor.get("parent_vehicle")
        if parent:
            selected_parents.add((actor["source"].casefold(), parent["group"], parent["path"].casefold()))
    profile = copy.deepcopy(base)
    profile["name"] = f"{base['name']}-setup-{name}"
    profile["actor_roots"] = actor_roots
    roots = []
    for root in base["roots"]:
        role = root.get("role", "")
        if role in ("combat_variant", "mounted_variant"):
            if _variant_key(root.get("source", ""), root.get("path", "")) in selected_sources:
                roots.append(root)
        elif role == "mounted_parent_vehicle":
            identity = (root["source"].casefold(), root["group"], root["path"].casefold())
            if identity in selected_parents:
                roots.append(root)
        else:
            roots.append(root)
    profile["roots"] = roots
    if len([r for r in roots if r.get("role", "").startswith("special_weapon:")]) != 3:
        raise ResidencyError("setup profile did not retain sword, gravity rifle, and fuel rod roots")
    if len(profile.get("spartan_roots", [])) != 4:
        raise ResidencyError("setup profile did not retain the complete Spartan player/bot asset roots")

    sources = _source_set(profile, maps_dir, cache)
    c1_source_pins = {key: value["sha256"] for key, value in base_manifest.get("source_maps", {}).items()}
    for key, source in sources.items():
        if c1_source_pins.get(key) != source.sha256:
            raise ResidencyError(f"{key}: source map differs from the retained C1 profile pin")
    result = import_profile(sources, profile["roots"], schema,
                            source_priority=sorted(sources), scenario_root=profile["scenario"])
    bindings = actor_bindings(profile, result)
    if len(bindings) != len(actor_roots):
        raise ResidencyError("not every selected combat/mounted recipe resolved into the imported closure")
    decoded = ctag.decode(result["ctag"], max_image_size=len(result["image"]))
    if decoded.image != result["image"]:
        raise ResidencyError("selected CTAG image differs from the imported CE image")

    bsp_bytes = sum(int(item["payload_bytes"]) for item in profile.get("bsp_roots", []))
    ce_aligned = align_up(len(result["image"]), OWNER_ALIGNMENT)
    bsp_aligned = align_up(bsp_bytes, OWNER_ALIGNMENT)
    claims_capacity_floor = ((ce_aligned + bsp_aligned + 31) // 32) * 4
    relocation_staging = len(result["relocations"]) * 4
    map_render_tag_bsp_guard = ce_aligned + bsp_aligned + INNER_OWNER_GUARD_BYTES
    render_residual = LIMIT_BYTES - map_render_tag_bsp_guard
    cross_owner_known_sum = map_render_tag_bsp_guard + claims_capacity_floor + relocation_staging
    roles = {}
    for root in roots:
        role = root.get("role", "unclassified")
        roles[role] = roles.get(role, 0) + 1
    root_identity = [{"source": row["source"], "group": row["group"], "path": row["path"],
                      "role": row.get("role")} for row in roots]
    tag_rows = result["tags"]
    actor_groups = {"actv", "actr", "bipd"}
    imported_actor_tags = [
        {"source_key": row["source_key"], "group": row["group"], "path": row["path"],
         "source_datum": row["source_datum"], "output_datum": row["output_datum"],
         "source_aliases": row["source_aliases"]}
        for row in tag_rows if row["group"] in actor_groups
    ]
    hcp_ctag = result["ctag"]
    report = {
        "format": "hcu-session-roster-residency-v1",
        "selection": {
            "name": name,
            "scenario_profile": base["name"],
            "map": base["map"],
            "local_players": local_players,
            "spartan_bots": spartan_bots,
            "selected_variant_count": len(selected),
            **({"logical_recipe": selection["logical_recipe"]}
               if selection.get("logical_recipe") else {}),
            "selected_variants": [
                {"source_map": row["map"], "source_map_sha256": row["source_map_sha256"],
                 "source_datum": row["datum"], "group": row["group"], "path": row["path"],
                 "disposition": row["disposition"], "recipe": row["recipe"],
                 "mounted_recipes": row.get("mounted_recipes", [])}
                for row in selected
            ],
        },
        "archive_catalog": {
            "roster_format": roster["format"],
            "retained_roster_sha256": sha_file(roster_path),
            "c1_profile_spec_sha256": sha_file(specs_path),
            "selectable_catalog_occurrences": len(available),
            "c1_survival_actor_root_occurrences": len(base.get("actor_roots", [])),
            "full_union_profile_manifest_sha256": sha_file(corpus / f"{base['name']}.json"),
            "full_union_package_sha256": json.loads((corpus / f"{base['name']}.json").read_text())
                                          ["package_sha256"],
            "full_union_resident_ce_bytes": int(json.loads((corpus / f"{base['name']}.json").read_text())
                                                  ["memory"]["resident_ce_bytes"]),
            "full_union_loaded_for_this_selection": False,
        },
        "schema_elf_sha256": schema["elf_sha256"],
        "importer_closure": {
            "exact_import_profile_schema_walk": True,
            "tag_count": len(tag_rows),
            "resident_ce_bytes": len(result["image"]),
            "ctag_bytes": len(hcp_ctag),
            "ctag_sha256": sha_bytes(hcp_ctag),
            "pointer_relocations": len(result["relocations"]),
            "relocation_table_staging_bytes": relocation_staging,
            "relocation_staging_owner": "streaming/map-load staging; separate from candidate 10 MiB map/render owner",
            "bsp_payload_bytes": bsp_bytes,
            "claims_bitmap_bytes_if_aligned_payloads_are_capacities": claims_capacity_floor,
            "claims_bitmap_formula": "ceil((aligned_tag_capacity + aligned_bsp_capacity) / 32) * 4",
            "claims_bitmap_owner": "resident_gameplay under the current production binder; separate from candidate 10 MiB map/render owner",
            "ce_plus_bsp_payload_lower_bound_bytes": len(result["image"]) + bsp_bytes,
            "aligned_ce_bytes": ce_aligned,
            "aligned_bsp_bytes": bsp_aligned,
            "inner_guard_bytes": INNER_OWNER_GUARD_BYTES,
            "map_render_tag_bsp_guard_bytes": map_render_tag_bsp_guard,
            "nominal_10mib_backing_bytes": LIMIT_BYTES,
            "render_owner_residual_after_aligned_ce_bsp_and_inner_guard_bytes": render_residual,
            "cross_owner_known_sum_bytes_informational_only": cross_owner_known_sum,
            "ce_plus_bsp_over_10mib_bytes": max(0, len(result["image"]) + bsp_bytes - LIMIT_BYTES),
            "ce_plus_bsp_within_10mib_payload_floor": len(result["image"]) + bsp_bytes <= LIMIT_BYTES,
            "root_counts_by_role": dict(sorted(roles.items())),
            "root_identities": root_identity,
            "resolved_actor_recipe_bindings": bindings,
            "imported_actor_group_tags": imported_actor_tags,
            "typed_dependency_count": len(tag_rows),
            "source_map_sha256": {key: value.sha256 for key, value in sorted(sources.items())},
        },
        "setup_contract": [
            "Select the roster in this manifest before initializing or allocating any CE tag arena; load this emitted CTAG as one immutable image for the match.",
            "No live tag eviction, pointer rebinding, mid-match roster addition, or union-image predecode is permitted by this setup profile.",
            "All roots outside the selected actor rows are retained from the exact C1 profile, including the chosen scenario, its BSP dependency closure, four Spartan asset roots, and energy sword, gravity rifle, and fuel rod.",
            "Actor, mounted-occupant, vehicle-parent, and secondary tag dependencies are taken only from retained C1 recipes and the importer’s schema reference/tag-index closure.",
            "The C1 full-roster package and source catalog remain the selection archive; this setup CTAG contains only the selected roster closure plus the profile’s required non-roster roots.",
            "The map/render residual uses 16-byte alignment for the CE image and BSP payload plus a 16-byte inner owner guard. It excludes outer layout slop, canaries, render/texture/DMA owners, and other runtime storage.",
            "CTAG relocation staging belongs to streaming/map-load staging; the claims bitmap belongs to resident_gameplay under the current production binder. Their cross-owner sum is informational only and must not be subtracted from the 10 MiB map/render owner.",
            "The claims value is the exact binder formula evaluated with aligned payloads substituted for unknown capacities: ceil((tag_capacity + bsp_capacity) / 32) * 4. Actual binder capacities may increase it.",
        ],
    }
    return report, hcp_ctag


def _find_variant(roster: dict, source: str, path: str) -> dict:
    rows = [row for row in roster["variants"] if row.get("disposition") in ("combat", "mounted_occupant") and
            row["map"].casefold() == source.casefold() and row["path"].casefold() == path.casefold()]
    if len(rows) != 1:
        raise ResidencyError(f"sample source occurrence is not unique: {source}:{path}")
    row = rows[0]
    map_sha = next(item["sha256"] for item in roster["source_roots"]
                   if item["map"].casefold() == source.casefold())
    return {"source_map": row["map"], "source_map_sha256": map_sha,
            "source_datum": row["datum"], "path": row["path"]}


def sample_selections(roster: dict) -> list[dict]:
    single = [_find_variant(roster, "a30", "characters\\marine\\marine assault rifle")]
    mixed_keys = [
        ("a30", "characters\\marine\\marine assault rifle"),
        ("a10", "characters\\elite\\elite major\\elite major plasma rifle"),
        ("d40", "characters\\grunt\\grunt specops fuel rod"),
        ("a30", "characters\\jackal\\jackal major plasma pistol"),
        ("d40", "characters\\hunter\\hunter"),
        ("d40", "characters\\floodcombat elite\\floodcombat elite assault rifle"),
        ("d40", "characters\\sentinel\\sentinel major"),
    ]


def map_matrix_selections(roster: dict) -> list[dict]:
    """Exercise the largest single recipe and mounted recipe on every MP map."""
    cases = [
        ("marine_shotgun", _find_variant(
            roster, "c10", "characters\\marine\\marine shotgun")),
        ("mounted_gunner", _find_variant(
            roster, "a30", "vehicles\\c_dropship\\cd_gun\\cd gun turret gunner")),
    ]
    selections = []
    for map_name in MP_MAPS:
        for case_name, variant in cases:
            selections.append({
                "format": "hcu-session-roster-selection-v1",
                "name": f"{map_name}_{case_name}_4p4bot",
                "scenario_profile": f"survival-{map_name}",
                "local_players": 4,
                "spartan_bots": 4,
                "selected_variants": [variant],
                "map_matrix_case": case_name,
            })
    return selections


def reaccount_map_matrix(output_dir: Path) -> Path:
    """Recompute per-owner arithmetic from completed, hash-bound CE outputs.

    This deliberately does not rerun schema imports. It verifies every stored
    CTAG length/digest and CE/BSP measurement against the prior completed
    matrix, then emits corrected disjoint-owner floors in a new directory.
    """
    source_path = output_dir / "matrix.json"
    historical = json.loads(source_path.read_text())
    if historical.get("format") != "hcu-session-roster-residency-matrix-v1" or len(historical.get("profiles", [])) != 26:
        raise ResidencyError("existing map matrix is not a complete 26-profile result")
    reaccounted = []
    producer_hashes = set()
    for old in historical["profiles"]:
        profile_path = ROOT / old["report_path"]
        raw = profile_path.read_bytes()
        profile = json.loads(raw)
        inputs = profile.get("inputs", {})
        importer_hash = inputs.get("setup_compiler", {}).get("sha256")
        if not isinstance(importer_hash, str) or len(importer_hash) != 64:
            raise ResidencyError(f"{old['name']}: missing original setup compiler source hash")
        producer_hashes.add(importer_hash)
        image = profile.get("importer_closure", {})
        ce_bytes = int(image["resident_ce_bytes"])
        bsp_bytes = int(image["bsp_payload_bytes"])
        reloc_bytes = int(image["relocation_table_staging_bytes"])
        ctag_bytes = int(image["ctag_bytes"])
        ctag_hash = image["ctag_sha256"]
        if (old["name"] != profile["selection"]["name"] or
                old["map"] != profile["selection"]["map"] or
                ce_bytes != old["resident_ce_bytes"] or bsp_bytes != old["bsp_payload_bytes"] or
                ctag_hash != old["ctag_sha256"] or ctag_bytes != 52 + ce_bytes + reloc_bytes):
            raise ResidencyError(f"{old['name']}: stored profile no longer matches its original CTAG/image identity")
        if len(ctag_hash) != 64:
            raise ResidencyError(f"{old['name']}: CTAG digest is malformed")
        role_counts = image.get("root_counts_by_role", {})
        if (role_counts.get("spartan_asset") != 4 or
                sum(count for role, count in role_counts.items() if role.startswith("special_weapon:")) != 3):
            raise ResidencyError(f"{old['name']}: required Spartan/special weapon roots are missing")
        aligned_ce = align_up(ce_bytes, OWNER_ALIGNMENT)
        aligned_bsp = align_up(bsp_bytes, OWNER_ALIGNMENT)
        map_owner = aligned_ce + aligned_bsp + INNER_OWNER_GUARD_BYTES
        claims_floor = ((aligned_ce + aligned_bsp + 31) // 32) * 4
        render_residual = LIMIT_BYTES - map_owner
        reaccounted.append({
            "name": old["name"],
            "map": old["map"],
            "map_matrix_case": old.get("map_matrix_case"),
            "local_players": old["local_players"],
            "spartan_bots": old["spartan_bots"],
            "selected_variant_count": old["selected_variant_count"],
            "source_profile_manifest_path": old["report_path"],
            "source_profile_manifest_sha256": sha_bytes(raw),
            "source_profile_manifest_hash_matches_initial_complete_run": sha_bytes(raw) == old.get("report_sha256"),
            "original_setup_compiler_sha256": importer_hash,
            "source_ctag_sha256": ctag_hash,
            "ctag_bytes": ctag_bytes,
            "resident_ce_bytes": ce_bytes,
            "bsp_payload_bytes": bsp_bytes,
            "ce_plus_bsp_payload_bytes": ce_bytes + bsp_bytes,
            "raw_ce_bsp_payload_within_10mib": ce_bytes + bsp_bytes <= LIMIT_BYTES,
            "aligned_ce_owner_bytes": aligned_ce,
            "aligned_bsp_owner_bytes": aligned_bsp,
            "inner_guard_bytes": INNER_OWNER_GUARD_BYTES,
            "candidate_map_render_owner_ce_bsp_guard_bytes": map_owner,
            "render_owner_residual_after_ce_bsp_alignment_and_guard_bytes": render_residual,
            "ctag_relocation_staging_bytes": reloc_bytes,
            "ctag_relocation_owner": "streaming/map-load staging; separate from map/render",
            "claims_bitmap_formula": "ceil((aligned_tag_capacity + aligned_bsp_capacity) / 32) * 4",
            "claims_bitmap_bytes_if_aligned_payloads_are_capacities": claims_floor,
            "claims_bitmap_owner": "resident_gameplay; separate from map/render",
            "known_owner_sum_bytes_informational_only": map_owner + reloc_bytes + claims_floor,
            "full_union_resident_ce_bytes": profile["archive_catalog"]["full_union_resident_ce_bytes"],
            "root_counts_by_role": role_counts,
        })

    names = {row["name"] for row in reaccounted}
    maps = {row["map"] for row in reaccounted}
    if len(names) != 26 or len(maps) != 13:
        raise ResidencyError("map-matrix accounting lost a profile or map")
    max_render = min(reaccounted,
                     key=lambda row: row["render_owner_residual_after_ce_bsp_alignment_and_guard_bytes"])
    output_dir = output_dir / "reaccounted"
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "format": "hcu-session-map-capacity-disjoint-owner-audit-v1",
        "scope": "Post-process accounting of 26 already imported/map-selected CE images; no schema re-import or CTAG bytes were changed.",
        "input_matrix": {"path": str(source_path.resolve().relative_to(ROOT)), "sha256": sha_file(source_path)},
        "measurement_jobs": {
            "completed_profile_run_session_id": 49538,
            "corrective_repeat_session_id": 3266,
            "corrective_repeat_disposition": "intentionally interrupted after 9 profiles when owner separation was identified; completed first-run CTAG image lengths/digests remain the comparison oracle",
        },
        "measurement_script_sha256_by_completed_profile": sorted(producer_hashes),
        "accounting_script": {"path": "tools/hcu_setup_residency.py",
                              "sha256": sha_file(Path(__file__).resolve())},
        "source_pins": historical.get("source_pins", {}),
        "owner_rules": [
            "Map/render residual subtracts aligned CE and BSP payloads plus the 16-byte inner guard from the 10 MiB candidate map/render backing.",
            "Claims uses the exact binder word-rounding formula ceil((tag_capacity + bsp_capacity) / 32) * 4, with aligned payload extents used only as a lower-bound capacity estimate; its current owner is resident_gameplay.",
            "CTAG relocation bytes are a measured staging extent owned by streaming/map-load staging, not map/render.",
            "Claims and relocation staging are reported in a cross-owner informational sum only. They are not subtracted from the single 10 MiB map/render capacity.",
            "Renderer index/workspace, bounded conversion staging, outer alignment slop/canaries, texture residency, DMA lifetime, and actual EE high-water remain unmeasured.",
        ],
        "summary": {
            "map_count": len(maps),
            "profile_count": len(reaccounted),
            "raw_ce_plus_bsp_payload_within_10mib_count": sum(row["raw_ce_bsp_payload_within_10mib"] for row in reaccounted),
            "raw_ce_plus_bsp_payload_over_10mib_count": sum(not row["raw_ce_bsp_payload_within_10mib"] for row in reaccounted),
            "smallest_map_render_residual_profile": max_render["name"],
            "smallest_map_render_residual_map": max_render["map"],
            "smallest_map_render_residual_bytes": max_render["render_owner_residual_after_ce_bsp_alignment_and_guard_bytes"],
            "largest_resident_gameplay_claims_floor_bytes": max(row["claims_bitmap_bytes_if_aligned_payloads_are_capacities"] for row in reaccounted),
            "largest_streaming_relocation_staging_bytes": max(row["ctag_relocation_staging_bytes"] for row in reaccounted),
            "all_source_ctag_hashes_match_original_matrix": True,
        },
        "profiles": reaccounted,
    }
    report_path = output_dir / "matrix.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report_path
    mixed = [_find_variant(roster, source, path) for source, path in mixed_keys]
    return [
        {"format": "hcu-session-roster-selection-v1", "name": "single_marine",
         "scenario_profile": "survival-bloodgulch", "local_players": 1, "spartan_bots": 0,
         "selected_variants": single},
        {"format": "hcu-session-roster-selection-v1", "name": "single_marine_4p4bot",
         "scenario_profile": "survival-bloodgulch", "local_players": 4, "spartan_bots": 4,
         "selected_variants": single},
        {"format": "hcu-session-roster-selection-v1", "name": "mixed_three",
         "scenario_profile": "survival-bloodgulch", "local_players": 1, "spartan_bots": 0,
         "selected_variants": mixed[:3]},
        {"format": "hcu-session-roster-selection-v1", "name": "mixed_seven",
         "scenario_profile": "survival-bloodgulch", "local_players": 1, "spartan_bots": 0,
         "selected_variants": mixed},
        {"format": "hcu-session-roster-selection-v1", "name": "mixed_seven_4p4bot",
         "scenario_profile": "survival-bloodgulch", "local_players": 4, "spartan_bots": 4,
         "selected_variants": mixed},
        {"format": "hcu-session-roster-selection-v1", "name": "mounted_gunner",
         "scenario_profile": "survival-bloodgulch", "local_players": 1, "spartan_bots": 0,
         "selected_variants": [_find_variant(
             roster, "a30", "vehicles\\c_dropship\\cd_gun\\cd gun turret gunner")]},
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--selection", type=Path, help="session selection JSON to compile")
    choice.add_argument("--samples", action="store_true", help="compile the reproducible sample roster matrix")
    choice.add_argument("--all-recipes", action="store_true",
                        help="compile one closure for each of the 75 unique retained C1 recipes")
    choice.add_argument("--map-matrix", action="store_true",
                        help="compile the largest and mounted baseline recipes for all 13 stock MP maps")
    choice.add_argument("--reaccount-map-matrix", action="store_true",
                        help="recompute disjoint-owner floors from an existing completed 26-profile map matrix without reimporting CTAGs")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--specs", type=Path, default=DEFAULT_SPECS)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--schema-elf", type=Path, default=DEFAULT_SCHEMA_ELF)
    parser.add_argument("--maps", type=Path, default=DEFAULT_MAPS)
    args = parser.parse_args()

    if args.reaccount_map_matrix:
        report_path = reaccount_map_matrix(args.output_dir)
        report = json.loads(report_path.read_text())
        print(json.dumps({"report": str(report_path), "summary": report["summary"]}, indent=2))
        return 0

    roster = json.loads(args.roster.read_text())
    specs = json.loads(args.specs.read_text())
    schema = SchemaManifest(Elf32(args.schema_elf)).build()
    if schema["elf_sha256"] != roster.get("schema_elf_sha256"):
        raise ResidencyError("schema ELF does not match the retained actor catalog")
    layout_reference_path = args.corpus / "survival-bloodgulch.json"
    layout_reference = json.loads(layout_reference_path.read_text())
    layout = layout_reference.get("runtime_layout_probe", {}).get("layout")
    if layout_reference.get("schema_elf_sha256") != schema["elf_sha256"] or not layout:
        raise ResidencyError("retained Blood Gulch C1 profile does not provide the matching runtime layout probe")
    reference_pins = layout_reference.get("source_inputs", {})
    if reference_pins.get("roster", {}).get("sha256") != sha_file(args.roster):
        raise ResidencyError("actor roster differs from the roster bound into the retained C1 profile")
    if reference_pins.get("schema_elf", {}).get("sha256") != sha_file(args.schema_elf):
        raise ResidencyError("schema ELF differs from the schema bound into the retained C1 profile")
    schema["runtime_normalization_layout"] = {
        **layout, "schema_elf_sha256": schema["elf_sha256"]}

    catalog_mapping = None
    if args.samples:
        selections = sample_selections(roster)
    elif args.all_recipes:
        selections, catalog_mapping = recipe_matrix(roster)
    elif args.map_matrix:
        selections = map_matrix_selections(roster)
    else:
        selections = [json.loads(args.selection.read_text())]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cache = BuildCache()
    rows = []
    seen_names = set()
    cached_profile_name = None
    cached_profile_manifest = None
    for selection in selections:
        if selection.get("name") in seen_names:
            raise ResidencyError("selection names must be unique in one output batch")
        seen_names.add(selection.get("name"))
        profile_name = selection.get("scenario_profile")
        if profile_name != cached_profile_name:
            base_manifest_path = args.corpus / f"{profile_name}.json"
            cached_profile_manifest = json.loads(base_manifest_path.read_text())
            pinned_inputs = cached_profile_manifest.get("source_inputs", {})
            if pinned_inputs.get("roster", {}).get("sha256") != sha_file(args.roster):
                raise ResidencyError(f"{profile_name}: actor roster differs from retained C1 input")
            if pinned_inputs.get("schema_elf", {}).get("sha256") != sha_file(args.schema_elf):
                raise ResidencyError(f"{profile_name}: schema ELF differs from retained C1 input")
            profile_layout = cached_profile_manifest.get("runtime_layout_probe", {}).get("layout")
            if cached_profile_manifest.get("schema_elf_sha256") != schema["elf_sha256"] or profile_layout != layout:
                raise ResidencyError(f"{profile_name}: runtime layout/schema pin differs from retained C1 input")
            cached_profile_name = profile_name
        else:
            base_manifest_path = args.corpus / f"{profile_name}.json"
        base_manifest = cached_profile_manifest
        report, image = compile_selection(selection, roster, specs, schema, args.maps, cache,
                                          args.roster, args.specs, args.corpus, base_manifest)
        report["inputs"] = {
            "roster": {"path": args.roster.relative_to(ROOT).as_posix() if args.roster.is_relative_to(ROOT) else str(args.roster),
                       "sha256": sha_file(args.roster)},
            "profile_specs": {"path": args.specs.relative_to(ROOT).as_posix() if args.specs.is_relative_to(ROOT) else str(args.specs),
                              "sha256": sha_file(args.specs)},
            "schema_elf": {"path": args.schema_elf.relative_to(ROOT).as_posix() if args.schema_elf.is_relative_to(ROOT) else str(args.schema_elf),
                           "sha256": sha_file(args.schema_elf)},
            "base_c1_profile": {"path": base_manifest_path.relative_to(ROOT).as_posix() if base_manifest_path.is_relative_to(ROOT) else str(base_manifest_path),
                                "sha256": sha_file(base_manifest_path)},
            "setup_compiler": {"path": "tools/hcu_setup_residency.py",
                               "sha256": sha_file(Path(__file__).resolve())},
        }
        if args.all_recipes or args.map_matrix:
            details_dir = "recipes" if args.all_recipes else "profiles"
            report_path = args.output_dir / details_dir / f"{selection['name']}.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report["output"] = {"manifest_path": str(report_path.relative_to(ROOT))
                                if report_path.is_relative_to(ROOT) else str(report_path)}
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            ctag_path = None
        else:
            ctag_path = args.output_dir / f"{selection['name']}.ctag"
            report_path = args.output_dir / f"{selection['name']}.json"
            ctag_path.write_bytes(image)
            report["output"] = {"ctag_path": str(ctag_path.relative_to(ROOT)) if ctag_path.is_relative_to(ROOT) else str(ctag_path),
                                 "ctag_file_sha256": sha_file(ctag_path),
                                 "manifest_path": str(report_path.relative_to(ROOT)) if report_path.is_relative_to(ROOT) else str(report_path)}
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        rows.append({
            "name": selection["name"],
            "local_players": selection["local_players"],
            "spartan_bots": selection["spartan_bots"],
            "selected_variant_count": report["selection"]["selected_variant_count"],
            "resident_ce_bytes": report["importer_closure"]["resident_ce_bytes"],
            "bsp_payload_bytes": report["importer_closure"]["bsp_payload_bytes"],
            "ce_plus_bsp_payload_lower_bound_bytes": report["importer_closure"]["ce_plus_bsp_payload_lower_bound_bytes"],
            "render_owner_residual_after_aligned_ce_bsp_and_inner_guard_bytes":
                report["importer_closure"]["render_owner_residual_after_aligned_ce_bsp_and_inner_guard_bytes"],
            "aligned_ce_bytes": report["importer_closure"]["aligned_ce_bytes"],
            "aligned_bsp_bytes": report["importer_closure"]["aligned_bsp_bytes"],
            "inner_guard_bytes": report["importer_closure"]["inner_guard_bytes"],
            "map_render_tag_bsp_guard_bytes": report["importer_closure"]["map_render_tag_bsp_guard_bytes"],
            "ctag_relocation_staging_bytes": report["importer_closure"]["relocation_table_staging_bytes"],
            "relocation_staging_owner": report["importer_closure"]["relocation_staging_owner"],
            "claims_bitmap_bytes_if_aligned_payloads_are_capacities": report["importer_closure"]["claims_bitmap_bytes_if_aligned_payloads_are_capacities"],
            "claims_bitmap_owner": report["importer_closure"]["claims_bitmap_owner"],
            "cross_owner_known_sum_bytes_informational_only": report["importer_closure"]["cross_owner_known_sum_bytes_informational_only"],
            "full_union_resident_ce_bytes": report["archive_catalog"]["full_union_resident_ce_bytes"],
            "map": report["selection"]["map"],
            "map_matrix_case": selection.get("map_matrix_case"),
            "within_10mib_payload_floor": report["importer_closure"]["ce_plus_bsp_within_10mib_payload_floor"],
            "tag_count": report["importer_closure"]["tag_count"],
            "ctag_sha256": report["importer_closure"]["ctag_sha256"],
            "report_path": report["output"]["manifest_path"],
            "report_sha256": sha_file(report_path),
            "ctag_path": report["output"].get("ctag_path"),
        })
        if args.all_recipes or args.map_matrix:
            progress = {
                "format": "hcu-session-roster-residency-progress-v1",
                "completed_profile_count": len(rows),
                "expected_profile_count": len(selections),
                **({"recipe_to_catalog_occurrences": catalog_mapping}
                   if catalog_mapping is not None else {}),
                "completed_profiles": rows,
            }
            (args.output_dir / "progress.json").write_text(json.dumps(progress, indent=2, sort_keys=True) + "\n")
            print(f"compiled {len(rows)}/{len(selections)} {selection['name']}: "
                  f"CE {report['importer_closure']['resident_ce_bytes']} B + "
                  f"BSP {report['importer_closure']['bsp_payload_bytes']} B", flush=True)

    batch = {
        "format": "hcu-session-roster-residency-matrix-v1",
        "scope": "Selected setup-time CE closure measurements using the exact C1 importer; not runtime target fit or full C2 admission.",
        "archive_full_union_resident_ce_bytes_by_map": {
            row["map"]: row["full_union_resident_ce_bytes"] for row in rows
        },
        "nominal_10mib_backing_bytes": LIMIT_BYTES,
        "source_pins": {
            "roster_sha256": sha_file(args.roster),
            "profile_specs_sha256": sha_file(args.specs),
            "schema_elf_sha256": sha_file(args.schema_elf),
            "base_c1_profile_manifest_sha256": sha_file(base_manifest_path),
            "base_c1_profile_package_sha256": base_manifest["package_sha256"],
            "setup_compiler_sha256": sha_file(Path(__file__).resolve()),
            "actor_source_maps": {row["map"]: row["sha256"] for row in roster.get("source_roots", [])},
        },
        "setup_contract": "The setup integration must allocate only the emitted selected CTAG for a match. The complete C1 roster remains available as catalog input for subsequent independently selected setup profiles.",
        **({"recipe_to_catalog_occurrences": catalog_mapping} if catalog_mapping is not None else {}),
        "recipe_matrix_summary": ({
            "recipe_count": len(rows),
            "payload_floor_fit_count": sum(row["within_10mib_payload_floor"] for row in rows),
            "payload_floor_over_count": sum(not row["within_10mib_payload_floor"] for row in rows),
            "payload_floor_fit_recipe_ids": [row["name"] for row in rows if row["within_10mib_payload_floor"]],
            "payload_floor_over_recipe_ids": [row["name"] for row in rows if not row["within_10mib_payload_floor"]],
            "largest_single_recipe": max(rows, key=lambda row: row["ce_plus_bsp_payload_lower_bound_bytes"]),
            "smallest_single_recipe": min(rows, key=lambda row: row["ce_plus_bsp_payload_lower_bound_bytes"]),
        } if args.all_recipes else None),
        "map_matrix_summary": ({
            "map_count": len({row["map"] for row in rows}),
            "profile_count": len(rows),
            "payload_floor_fit_count": sum(row["within_10mib_payload_floor"] for row in rows),
            "payload_floor_over_count": sum(not row["within_10mib_payload_floor"] for row in rows),
            "largest_payload_profile": max(rows, key=lambda row: row["ce_plus_bsp_payload_lower_bound_bytes"]),
            "smallest_payload_profile": min(rows, key=lambda row: row["ce_plus_bsp_payload_lower_bound_bytes"]),
            "smallest_render_owner_residual_profile": min(rows, key=lambda row: row["render_owner_residual_after_aligned_ce_bsp_and_inner_guard_bytes"]),
            "smallest_render_owner_residual_bytes": min(row["render_owner_residual_after_aligned_ce_bsp_and_inner_guard_bytes"] for row in rows),
            "largest_render_owner_residual_profile": max(rows, key=lambda row: row["render_owner_residual_after_aligned_ce_bsp_and_inner_guard_bytes"]),
            "largest_claims_bitmap_payload_capacity_floor_bytes": max(row["claims_bitmap_bytes_if_aligned_payloads_are_capacities"] for row in rows),
            "largest_ctag_relocation_staging_bytes": max(row["ctag_relocation_staging_bytes"] for row in rows),
            "cross_owner_known_sum_usage": "informational only; claims and relocation staging are owned by resident_gameplay and streaming/map-load staging, respectively, and are not compared to the 10 MiB map/render capacity",
        } if args.map_matrix else None),
        "profiles": rows,
    }
    batch_path = args.output_dir / "matrix.json"
    batch_path.write_text(json.dumps(batch, indent=2, sort_keys=True) + "\n")
    print(f"compiled {len(rows)} selected roster(s); output {batch_path}")
    for row in rows:
        print(f"{row['name']}: CE {row['resident_ce_bytes']} B + BSP {row['bsp_payload_bytes']} B "
              f"= {row['ce_plus_bsp_payload_lower_bound_bytes']} B")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, IndexError) as error:
        raise SystemExit(f"setup residency compilation failed: {error}")
