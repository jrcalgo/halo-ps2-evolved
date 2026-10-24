"""Assemble complete C1 media candidates without claiming runtime admission."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
from hcu_profile_bitmap import serialize_bitmap  # noqa: E402
import hcu_profile_consumer_exclusions as exclusion_rules  # noqa: E402
from hcu_profile_media import build_media  # noqa: E402
from audit_hcu_profile_non2d import FIELD_RULES  # noqa: E402
from halo2ps2 import bitmaps  # noqa: E402

NON2D_REPORT = ROOT / "docs/reports/m2-c2-ui-non2d-consumers-2026-10-23.json"
SURVIVAL_NON2D_REPORT = ROOT / "docs/reports/m2-c2-survival-non2d-consumers-2026-10-23.json"
IMAGE_TYPE_NAMES = {bitmaps.TYPE_CUBE: "cube", bitmaps.TYPE_3D: "3d"}


def _pinned_non2d_evidence(profile: str, current_source_hashes: dict | None = None) -> dict:
    report_path = NON2D_REPORT if profile == "ui" else SURVIVAL_NON2D_REPORT
    report_bytes = report_path.read_bytes()
    report = json.loads(report_bytes)
    expected_schema = "m2-c1-ui-non2d-consumer-audit-v1" if profile == "ui" else "m2-c1-survival-non2d-consumer-audit-v1"
    if report.get("schema") != expected_schema or report.get("runtime_admitted") is not False:
        raise ValueError("unsupported or runtime-admitted non-2D audit evidence")
    pins = report.get("source_pins", {}) if profile == "ui" else report.get("pins", {})
    for relpath, expected in sorted(pins.items()):
        path = ROOT / relpath
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"non-2D audit evidence source pin changed: {relpath}")
    if profile == "ui":
        pinned_maps = {key: row.get("sha256") for key, row in report.get("catalog", {}).get("source_maps", {}).items()}
    else:
        pinned_maps = {Path(path).stem: digest for path, digest in pins.items()
                       if path.startswith("build/retail-maps/decompressed/") and path.endswith(".map")}
    for source_key, expected in pinned_maps.items():
        current = (current_source_hashes or {}).get(source_key)
        if current is not None and current != expected:
            raise ValueError(f"current profile map identity disagrees with non-2D policy evidence: {source_key}")
    if profile == "survival":
        if report.get("status") != "partial" or any(
                role.get("classification") == "unknown_fail_closed" for role in report.get("roles", [])):
            raise ValueError("survival non-2D audit is incomplete or contains unknown roles")
    audit_source = ROOT / "tools/audit_hcu_profile_non2d.py"
    return {"profile_policy": profile,
            "report_path": report_path.relative_to(ROOT).as_posix(),
            "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "source_pins": pins,
            "classifier_path": audit_source.relative_to(ROOT).as_posix(),
            "classifier_sha256": hashlib.sha256(audit_source.read_bytes()).hexdigest()}


def _normalize_consumer_fields(path: str, owners: list[dict]) -> list[dict]:
    normalized = []
    for owner in owners:
        group = str(owner.get("group", owner.get("owner_group", "")))
        field = str(owner.get("field", "")).casefold()
        candidates = [rule_field for rule_group, rule_field in FIELD_RULES
                      if rule_group.casefold() == group.casefold() and
                      (field == rule_field.casefold() or field.startswith(rule_field.casefold() + "."))]
        if len(candidates) != 1:
            return []
        normalized.append({"group": group, "field": candidates[0]})
    return normalized


def _all_feature_gates(exclusions: list[dict]) -> list[str]:
    return sorted({gate for row in exclusions
                   for gate in (row.get("feature_gate", []) if isinstance(row.get("feature_gate"), list)
                                else [row.get("feature_gate")]) if gate})


def classify_bitmap_role(path: str, image_type: str, owners: list[dict]) -> dict:
    """Pure classifier shared by candidate assembly and package validation.

    `owners` contains schema-derived group/field pairs. For path-specific
    Full nested fields are reduced only when they begin with one exact
    source-backed ``FIELD_RULES`` field for the same tag group.
    """
    normalized = _normalize_consumer_fields(path, owners)
    if not normalized or len(normalized) != len(owners):
        return {"classification": "unknown_fail_closed", "payload_disposition": "retain_or_block_profile",
                "reason": "no exact source-backed schema owner rule"}
    dispositions=[]
    for row in normalized:
        rule=FIELD_RULES.get((row["group"],row["field"]))
        if rule is None:
            return {"classification": "unknown_fail_closed", "payload_disposition": "retain_or_block_profile",
                    "reason": f"no source-backed rule for {row['group']}.{row['field']}"}
        classification,gate,evidence=rule
        dispositions.append({"classification":classification,"feature_gate":gate,
            "payload_disposition":"exclude_from_current_ps2_visual_profile_under_explicit_feature_gate",
            "consumer_evidence":evidence,
            "replacement_if_enabled":"Implement the referenced CE shader/effect consumer with native volume or cube sampling and actual PS2 presentation."})
    return {"classification":"role_gated_no_current_ps2_payload_consumer",
            "payload_disposition":"exclude_from_current_ps2_visual_profile_under_explicit_feature_gate",
            "owner_dispositions":dispositions,
            "feature_gate":sorted({row["feature_gate"] for row in dispositions})}


def classify_profile_non2d(sources: dict, tags: list, bitmap_consumers: list,
                           skip_outputs: set | None = None) -> dict:
    """Map selected non-2D source images to exact owner-field feature gates."""
    consumers = defaultdict(list)
    source_hashes = {}
    for row in bitmap_consumers:
        consumers[int(row["bitmap_output_datum"])].append(row)
    decisions = {}
    for tag in (row for row in tags if row.get("group") == "bitm"
                and int(row["output_datum"]) not in (skip_outputs or ())):
        output_datum = int(tag["output_datum"])
        source = tag["source_key"]
        m = sources[source]
        entry = m.by_id.get(int(tag["source_datum"]))
        if entry is None or entry.group != "bitm" or entry.path != tag["path"]:
            raise ValueError("bitmap non-2D classification source identity mismatch")
        images = bitmaps.parse_images(m.region, m.base, entry.data_address)
        for image in images:
            if image.is_2d:
                continue
            owners = consumers.get(output_datum, [])
            owner_rows = [{"group": row["owner_group"], "field": row["field"]} for row in owners]
            disposition = classify_bitmap_role(tag["path"], IMAGE_TYPE_NAMES.get(image.type, "unknown"), owner_rows)
            if disposition.get("payload_disposition") != "exclude_from_current_ps2_visual_profile_under_explicit_feature_gate":
                raise ValueError(f"unclassified required non-2D bitmap {tag['path']}[{image.index}]")
            pixels = m.pixels(image)
            if source not in source_hashes:
                claimed = tag.get("source_sha256")
                if claimed:
                    source_hashes[source] = claimed
                else:
                    digest = hashlib.sha256()
                    with m.path.open("rb") as stream:
                        for block in iter(lambda: stream.read(1 << 20), b""):
                            digest.update(block)
                    source_hashes[source] = digest.hexdigest()
            schema_consumers = [{k: row[k] for k in (
                "owner_output_datum", "owner_group", "owner_path", "source_key",
                "definition", "field", "bitmap_output_datum", "bitmap_path")}
                for row in owners]
            decisions.setdefault(output_datum, {})[image.index] = {
                **disposition, "source_key": source,
                "source_sha256": source_hashes[source],
                "source_datum": int(tag["source_datum"]),
                "bitmap_output_datum": output_datum, "bitmap_path": tag["path"],
                "image_index": image.index,
                "source_pixel_bytes": len(pixels),
                "source_pixel_sha256": hashlib.sha256(pixels).hexdigest(),
                "schema_consumers": schema_consumers,
                "runtime_admitted": False,
            }
    return decisions


def consumer_drops(sources: dict, tags: list, bitmap_consumers: list, covered: dict,
                   bsp_selected: set, policy: dict | None, *, ctag_image: bytes | None = None,
                   schema: dict | None = None, tag_index_remaps: list | None = None) -> dict:
    """Return {output_datum: decision} for bitmaps whose MEDIA payload is excluded.

    The decision is hcu_profile_consumer_exclusions.decide_profile, shared with the audit.
    Guards keep model-covered (OTEX) and BSP-selected bitmaps. Zero references keep. Typed
    tag_index references join through the CTAG when ctag_image and schema are given. CE tag
    metadata is never affected: only the bitmap's image payload is left out.
    """
    if not policy:
        return {}
    view = {"dependencies": [row for row in tags if row["group"] == "bitm"],
            "bitmap_consumers": bitmap_consumers,
            "tag_index_remaps": tag_index_remaps or []}
    guard = {(k[0], int(k[1])) for k in covered} | {(k[0], int(k[1])) for k in (bsp_selected or set())}
    decisions = exclusion_rules.decide_profile(view, policy, ctag_image=ctag_image, schema=schema,
                                               guard_tags=guard)
    tags_by_key = {(row["source_key"], int(row["source_datum"])): row for row in tags if row["group"] == "bitm"}
    drops = {}
    for key, decision in decisions.items():
        if decision["keep"]:
            continue
        tag = tags_by_key[key]
        drops[decision["output_datum"]] = {"tag": tag, "role": "+".join(sorted(set(decision["roles"]))),
                                           "rows": decision["rows"],
                                           "reference_count": decision["reference_count"]}
    return drops


def _dropped_bitmap(sources: dict, decision: dict, policy: dict) -> tuple[dict, list[dict]]:
    """Catalog entry plus per-image dispositions for one consumer-excluded bitmap."""
    tag = decision["tag"]
    source = sources[tag["source_key"]]
    entry = source.by_id[int(tag["source_datum"])]
    source_sha = tag.get("source_sha256") or sha_bytes(source.path.read_bytes())
    classes = sorted({row["class"] for row in decision["rows"]})
    reasons = sorted({row["reason"] for row in decision["rows"]})
    dispositions = []
    for img in bitmaps.parse_images(source.region, source.base, entry.data_address):
        pixels = source.pixels(img)
        dispositions.append({
            "source_key": tag["source_key"], "source_sha256": source_sha, "group": "bitm",
            "path": tag["path"], "source_datum": int(tag["source_datum"]),
            "source_image_index": img.index, "type": img.type, "depth": img.depth,
            "format": img.format_name, "width": img.width, "height": img.height,
            "mip_count": img.mip_count, "source_pixel_offset": img.pixel_offset,
            "source_pixel_bytes": len(pixels), "source_pixel_sha256": sha_bytes(pixels),
            "is_2d": bool(img.is_2d),
            "disposition": exclusion_rules.DISPOSITION, "exclusion_classes": classes,
            "exclusion_reasons": reasons, "exclusion_sha256": policy["sha256"],
            "role": decision["role"], "runtime_admitted": False})
    owner = {"source_key": tag["source_key"], "source_datum": int(tag["source_datum"]),
             "group": "bitm", "path": tag["path"]}
    catalog = {**owner, "source_sha256": source_sha, "sequences": [], "dispositions": dispositions,
               "decision": "consumer-excluded by pinned exclusions; no image payload staged"}
    return catalog, dispositions


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_complete_media(sources: dict, tags: list, bitmap_schema: dict,
                         bitmap_consumers: list | None = None, *,
                         conversion_cache=None, bitmap_cache=None, input_hashes=None,
                         consumer_exclusions: dict | None = None,
                         bsp_selected: set | None = None, ctag_image: bytes | None = None,
                         schema: dict | None = None, tag_index_remaps: list | None = None) -> dict:
    """Build MODL/OTEX/ANIM plus every selected bitmap image as staged BITM.

    BITM uses the existing TEXS serializer, structural reader, and host-qualified
    packet emitter. The manifest leaves live CE presentation admission false
    because the runtime UI/effect/sprite path is not registered.

    `consumer_exclusions` is {'path','sha256','kind','rows'} for a pinned exclusion
    file; None keeps the historical output exactly.
    """
    ordinary = [row for row in tags if row["group"] != "bitm"]
    covered = {}
    media = build_media(sources, ordinary, conversion_cache=conversion_cache,
                        input_hashes=input_hashes, covered_out=covered)
    chunks = {row["key"]: row for row in media["chunks"]}
    bindings = list(media["bindings"])
    bitmap_catalog = []
    if consumer_exclusions:
        # MODL shader bitmaps selected by the production model reader are parent-reader live.
        modl = [(c["key"], c["data"]) for c in media["chunks"] if c.get("kind") == "MODL"]
        for key in exclusion_rules.selected_model_bitmaps(modl, media["bindings"],
                                                          lambda k: sources[k]):
            covered.setdefault(key, True)
    drops = consumer_drops(sources, tags, bitmap_consumers or [], covered,
                           bsp_selected or set(), consumer_exclusions, ctag_image=ctag_image,
                           schema=schema, tag_index_remaps=tag_index_remaps)
    consumer_records = []
    non2d = classify_profile_non2d(sources, tags, bitmap_consumers or [], set(drops))
    policy_profile="ui" if set(sources)=={"ui"} else "survival"
    non2d_evidence = _pinned_non2d_evidence(policy_profile,input_hashes) if non2d else None
    source_hashes: dict[str, str] = dict(input_hashes or {})
    tex_source = ROOT / "submodules/halo-ps2/engine/src/world/tex.c"
    quad_source = ROOT / "src/stream/hcu_bitmap_quad.c"
    fixture_source = ROOT / "tests/test_hcu_bitmap_quad.py"
    consumer = {"path": "src/stream/hcu_bitmap_quad.c", "function": "hcu_bitmap_quad_emit",
                "source_sha256": hashlib.sha256(quad_source.read_bytes()).hexdigest(),
                "parser": {"path": "submodules/halo-ps2/engine/src/world/tex.c",
                           "function": "tex_open",
                           "source_sha256": hashlib.sha256(tex_source.read_bytes()).hexdigest()},
                "capture_fixture": {"path": "tests/test_hcu_bitmap_quad.py",
                                    "source_sha256": hashlib.sha256(fixture_source.read_bytes()).hexdigest()}}
    for tag in sorted((row for row in tags if row["group"] == "bitm"),
                      key=lambda row: (row["source_key"], row["path"], int(row["source_datum"]))):
        owner = {"source_key": tag["source_key"], "source_datum": int(tag["source_datum"]),
                 "group": "bitm", "path": tag["path"]}
        if int(tag["output_datum"]) in drops:
            decision = drops[int(tag["output_datum"])]
            catalog, dispositions = _dropped_bitmap(sources, decision, consumer_exclusions)
            bitmap_catalog.append(catalog)
            consumer_records.append({**owner, "output_datum": int(tag["output_datum"]),
                "role": decision["role"], "reference_count": decision["reference_count"],
                "exclusion_classes": sorted({row["class"] for row in decision["rows"]}),
                "exclusion_reasons": sorted({row["reason"] for row in decision["rows"]}),
                "exclusion_sha256": consumer_exclusions["sha256"],
                "image_count": len(dispositions),
                "dropped_source_images": [d["source_image_index"] for d in dispositions]})
            continue
        source_sha = tag.get("source_sha256", source_hashes.get(tag["source_key"]))
        if source_hashes.get(tag["source_key"]) not in (None, source_sha):
            raise ValueError(f"bitmap source hash disagrees with pinned input map {tag['source_key']}")
        if source_sha is None:
            digest = hashlib.sha256()
            with sources[tag["source_key"]].path.open("rb") as stream:
                for block in iter(lambda: stream.read(1 << 20), b""):
                    digest.update(block)
            source_sha = digest.hexdigest()
        source_hashes[tag["source_key"]] = source_sha
        non2d_rows=non2d.get(int(tag["output_datum"]), {})
        cache_policy={index:{k:row[k] for k in ("classification","payload_disposition","feature_gate","owner_dispositions")}
                      | {"schema_consumers":sorted({(consumer["owner_group"],consumer["field"])
                         for consumer in row["schema_consumers"]})}
                      for index,row in non2d_rows.items()}
        decision_sha=hashlib.sha256(json.dumps(cache_policy,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        bitmap_key=(source_sha,int(tag["source_datum"]),decision_sha)
        asset=(bitmap_cache or {}).get(bitmap_key) if bitmap_cache is not None else None
        if asset is None:
            asset = serialize_bitmap(sources, owner, bitmap_schema, source_sha256=source_sha,
                                     non2d_disposition=non2d_rows)
            if bitmap_cache is not None:
                bitmap_cache[bitmap_key]=asset
        else:
            # Conversion bytes are reusable across profiles; rebuild profile-specific
            # owner provenance on each caller without mutating the shared cache entry.
            asset={**asset,"dispositions":[dict(row) for row in asset["dispositions"]]}
            for row in asset["dispositions"]:
                row.update(source_key=owner["source_key"],source_sha256=source_sha,
                           group="bitm",path=owner["path"],source_datum=owner["source_datum"])
                current=non2d_rows.get(int(row.get("source_image_index",-1)))
                if current is not None:
                    pixel_hash=row.get("source_pixel_sha256")
                    pixel_bytes=row.get("source_pixel_bytes")
                    disposition=row.get("disposition")
                    row.update(current)
                    row.update(source_pixel_sha256=pixel_hash,source_pixel_bytes=pixel_bytes,
                               disposition=disposition)
        bitmap_catalog.append({**owner, "source_sha256": asset["source_sha256"],
                               "sequences": asset["sequences"],
                               "dispositions": asset["dispositions"],
                               "decision": asset["decision"]})
        for record in asset["chunks"]:
            key = record["key"]
            chunk = chunks.setdefault(key, {"key": key, "kind": "BITM", "bytes": record["bytes"],
                "data": record["data"], "sha256": record["sha256"], "sources": [], "owners": [],
                "engine_consumer": consumer, "runtime_consumer": None, "runtime_admitted": False})
            source = {"source_sha256": asset["source_sha256"],
                      "source_map": str(sources[tag["source_key"]].path)}
            if source not in chunk["sources"]:
                chunk["sources"].append(source)
            image_owner = {**owner, "source_image_index": int(record["identity"]["source_image_index"])}
            if image_owner not in chunk["owners"]:
                chunk["owners"].append(image_owner)
            bindings.append({"owner": image_owner, "kind": "BITM", "chunk_key": key,
                             "source_image_index": image_owner["source_image_index"],
                             "runtime_admitted": False})
    media["chunks"] = sorted(chunks.values(), key=lambda row: row["key"])
    media["bindings"] = sorted(bindings, key=lambda row: (
        row["owner"]["source_key"], row["owner"]["source_datum"], row["kind"],
        row.get("source_image_index", -1), row["chunk_key"]))
    media["bitmap_catalog"] = sorted(bitmap_catalog,
        key=lambda row: (row["source_key"], row["path"], row["source_datum"]))
    if consumer_exclusions:
        media["consumer_exclusions"] = sorted(consumer_records, key=lambda row: (
            row["source_key"], row["path"], row["source_datum"]))
        media["consumer_exclusion_policy"] = {"path": consumer_exclusions["path"],
            "sha256": consumer_exclusions["sha256"], "profile_kind": consumer_exclusions["kind"],
            "rows": consumer_exclusions["rows"]}
        media["decisions"].append(
            f"{len(consumer_records)} bitmap(s) consumer-excluded under the pinned exclusion file; "
            "their image payloads are omitted and every image is accounted as excluded.")
    media["non2d_exclusions"] = sorted(
        (decision for by_image in non2d.values() for decision in by_image.values()),
        key=lambda row: (row["image_index"], row["source_pixel_sha256"]))
    media["non2d_policy_evidence"] = non2d_evidence
    media["disabled_features"] = _all_feature_gates(media["non2d_exclusions"])
    media["memory"]["independently_addressable_converted_bytes"] = sum(row["bytes"] for row in media["chunks"])
    media["memory"]["maximum_selected_transient_asset_requirement_bytes"] = max(
        (row["bytes"] for row in media["chunks"]), default=0)
    media["decisions"].append("BITM assets are structurally validated staging candidates; live UI/effect/sprite admission is false.")
    return media


def append_cbsp_chunks(media: dict, bsp_assets: list[dict]) -> None:
    """Attach schema-normalized, CTAG-rebound BSPs as staged CBSP chunks.

    CBSP payloads are independently addressable package data. This records
    their SBSP owner and typed tag remaps without claiming runtime admission.
    """
    chunks = {row["key"]: row for row in media.get("chunks", [])}
    bindings = list(media.get("bindings", []))
    catalog = list(media.get("bsp_catalog", []))
    for asset in sorted(bsp_assets, key=lambda row: (row["source_key"], row["path"],
                                                     int(row["source_datum"]))):
        data = bytes(asset["payload"])
        digest = hashlib.sha256(data).hexdigest()
        if digest != asset.get("output_cbsp_sha256"):
            raise ValueError("CBSP payload hash disagrees with rebound identity")
        key = f"CBSP:{digest}"
        owner = {k: asset[k] for k in
                 ("source_key", "group", "path", "source_datum", "output_datum")}
        chunk = chunks.setdefault(key, {"key": key, "kind": "CBSP", "bytes": len(data),
            "data": data, "sha256": digest, "sources": [], "owners": [],
            "engine_consumer": None, "runtime_consumer": None, "runtime_admitted": False})
        if chunk["data"] != data:
            raise ValueError("CBSP SHA-256 collision in candidate media")
        source = {"source_sha256": asset["source_map_sha256"],
                  "source_map": asset["source_key"]}
        if source not in chunk["sources"]:
            chunk["sources"].append(source)
        if owner not in chunk["owners"]:
            chunk["owners"].append(owner)
        bindings.append({"owner": owner, "kind": "CBSP", "chunk_key": key,
                         "runtime_admitted": False})
        catalog.append({"owner": owner, "source_file_offset": asset["source_file_offset"],
            "source_file_size": asset["source_file_size"],
            "source_xbox_base": asset["source_xbox_base"],
            "source_map_sha256": asset["source_map_sha256"],
            "schema_elf_sha256": asset["schema_elf_sha256"],
            "source_cbsp_sha256": asset["source_cbsp_sha256"],
            "output_cbsp_sha256": digest, "chunk_key": key,
            "tag_dependencies": asset["tag_dependencies"],
            "tag_remaps": asset["tag_remaps"], "runtime_admitted": False})
    media["chunks"] = sorted(chunks.values(), key=lambda row: row["key"])
    media["bindings"] = sorted(bindings, key=lambda row: (
        row["owner"]["source_key"], row["owner"]["source_datum"], row["kind"],
        row.get("source_image_index", -1), row["chunk_key"]))
    media["bsp_catalog"] = sorted(catalog, key=lambda row: (
        row["owner"]["source_key"], row["owner"]["path"], row["owner"]["source_datum"]))
    memory = media.setdefault("memory", {})
    memory["independently_addressable_converted_bytes"] = sum(
        row["bytes"] for row in media["chunks"])
    memory["maximum_selected_transient_asset_requirement_bytes"] = max(
        (row["bytes"] for row in media["chunks"]), default=0)
    memory["note"] = ("Converted chunk sizes are independently addressable and are not summed as "
                       "concurrent runtime residency; CBSP runtime admission is false.")
    if bsp_assets:
        media.setdefault("decisions", []).append(
            "CBSP payloads are schema-normalized and CTAG-rebound package candidates; runtime admission is false.")


def append_presentation_chunks(media: dict, presentation: dict, spec: dict,
                              source_occurrence_remaps: list[dict]) -> dict:
    """Attach separately sourced sword/gravity HPOS payloads to their CE roots."""
    raw_provenance = presentation.get("presentation_provenance", {})
    pose_provenance = presentation.get("provenance", {})
    root_provenance = {
        "format": presentation.get("format"),
        "adapter_files": raw_provenance.get("adapter_files", {}),
        "source_animation_map": dict(raw_provenance.get("source_animation_map", {})),
    }
    for asset_id, public_id in (("sword", "energy_sword"), ("gravity_rifle", "gravity_rifle")):
        source = pose_provenance.get(asset_id, {})
        root_provenance[public_id] = {
            "pose_header": source.get("source_header"),
            "pose_header_sha256": source.get("source_header_sha256"),
        }
    roots = {row.get("role"): row for row in spec.get("roots", [])
             if row.get("role") in ("special_weapon:energy_sword", "special_weapon:gravity_rifle")}
    if not roots:
        return {**root_provenance, "assets": {}}
    bindings_by_asset = {row["asset_id"]: row for row in presentation.get("bindings", [])}
    assets, media_bindings = {}, list(media.get("bindings", []))
    chunks = {row["key"]: row for row in media.get("chunks", [])}
    role_by_asset = {"sword": "special_weapon:energy_sword",
                     "gravity_rifle": "special_weapon:gravity_rifle"}
    for asset_id, role in role_by_asset.items():
        root = roots.get(role)
        if root is None:
            continue
        binding = bindings_by_asset.get(asset_id)
        if binding is None:
            raise ValueError(f"presentation source lacks {asset_id} payload binding")
        if binding.get("tag_group") != root["group"] or binding.get("tag_path", "").casefold() != root["path"].casefold():
            raise ValueError(f"presentation tag identity does not match selected {role} root")
        owners = [row for row in source_occurrence_remaps if
                  (row["source_key"], row["group"], row["path"]) ==
                  (root["source"], root["group"], root["path"])]
        if len(owners) != 1:
            raise ValueError(f"presentation {asset_id} root has {len(owners)} exact imported source occurrences")
        owner_row = owners[0]
        owner = {k: owner_row[k] for k in
                 ("source_key", "group", "path", "source_datum", "output_datum")}
        payload = bytes(presentation["chunks"][int(binding["chunk_id"])])
        digest = hashlib.sha256(payload).hexdigest()
        if digest != binding.get("chunk_sha256"):
            raise ValueError(f"presentation {asset_id} payload SHA-256 mismatch")
        key = f"POSE:{digest}"
        provenance = presentation.get("provenance", {}).get(asset_id)
        if not isinstance(provenance, dict):
            raise ValueError(f"presentation {asset_id} lacks source provenance")
        source = {"source_sha256": provenance["source_map_sha256"],
                  "source_map": provenance["source_map"]}
        pose_consumer_path = "src/stream/hcu_pose_asset.c"
        pose_consumer_source = ROOT / pose_consumer_path
        pose_consumer = {"path": pose_consumer_path, "function": "hcu_pose_asset_sample",
                         "source_sha256": hashlib.sha256(pose_consumer_source.read_bytes()).hexdigest()}
        chunk = chunks.setdefault(key, {"key": key, "kind": "POSE", "bytes": len(payload),
            "data": payload, "sha256": digest, "sources": [], "owners": [],
            "engine_consumer": pose_consumer, "runtime_consumer": None, "runtime_admitted": False})
        if chunk.get("engine_consumer") != pose_consumer:
            raise ValueError("POSE chunk consumer provenance changed")
        if chunk["data"] != payload:
            raise ValueError("POSE SHA-256 collision in candidate media")
        if source not in chunk["sources"]:
            chunk["sources"].append(source)
        if owner not in chunk["owners"]:
            chunk["owners"].append(owner)
        media_bindings.append({"owner": owner, "kind": "POSE", "chunk_key": key,
                               "asset_id": asset_id, "presentation_chunk_id": int(binding["chunk_id"]),
                               "jmad": binding["jmad"], "runtime_admitted": False})
        assets[asset_id] = {"key": key, "kind": "POSE", "asset_id": asset_id,
            "sha256": digest, "bytes": len(payload), "source_map": provenance["source_map"],
            "source_map_sha256": provenance["source_map_sha256"],
            "source_map_build": provenance.get("source_map_build"),
            "source_map_path": provenance.get("source_map_path"),
            "source_map_retained": provenance.get("source_map_retained"),
            "source_pose": provenance["source_header"],
            "source_pose_sha256": provenance["source_header_sha256"],
            "owner": owner, "presentation_chunk_id": int(binding["chunk_id"]),
            "jmad": binding["jmad"], "engine_consumer": pose_consumer,
            "runtime_admitted": False}
    media["chunks"] = sorted(chunks.values(), key=lambda row: row["key"])
    media["bindings"] = sorted(media_bindings, key=lambda row: (
        row["owner"]["source_key"], row["owner"]["source_datum"], row["kind"],
        row.get("source_image_index", -1), row["chunk_key"]))
    media["pose_catalog"] = []
    chunk_ids = {row["key"]: index + 1 for index, row in enumerate(media["chunks"])}
    for asset_id in sorted(assets):
        row = assets[asset_id]
        row["chunk_id"] = chunk_ids[row["key"]]
        row["owners"] = [row["owner"]]
        media["pose_catalog"].append(row)
    media["memory"]["independently_addressable_converted_bytes"] = sum(
        row["bytes"] for row in media["chunks"])
    media["memory"]["maximum_selected_transient_asset_requirement_bytes"] = max(
        (row["bytes"] for row in media["chunks"]), default=0)
    media.setdefault("decisions", []).append(
        "POSE payloads preserve separate source provenance; runtime admission is false.")
    return {**root_provenance, "assets": assets}
