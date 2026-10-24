#!/usr/bin/env python3
"""Build a conservative Step 7 BSP schema-to-consumer evidence crosswalk.

The crosswalk associates existing evidence by explicitly curated BSP families.
An association means related evidence only; it does not imply byte-level or
member-level semantic coverage unless the report invokes that consumer. All
compiler-inventory unclassified ranges remain unresolved.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
OUT = ROOT / "docs/reports/m2-step7-bsp-consumer-crosswalk-2026-10-22.json"
DISPOSITION = "docs/reports/m2-step7-bsp-consumer-disposition.md"
NESTED = "docs/reports/m2-step7-nested-bsp-field-consumers-2026-10-22.md"
MEMBER_LEDGER = "docs/reports/m2-step7-bsp-member-ledger-2026-10-21.md"
RANGE_LAYOUT = "docs/reports/m2-step7-bsp-range-member-layout-2026-10-22.json"
OPEN_ROOT = "docs/reports/m2-step7-open-root-bsp-dispositions-2026-10-22.json"
TARGET_PATH = "docs/reports/m2-step7-mp-target-astar-2026-10-22.md"
CURRENT_TARGET_PATH = "docs/reports/m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.md"
CURRENT_TARGET_JSON = "docs/reports/m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.json"
SENTINEL_TEST = "tools/test_step7_bsp_zero_size_sentinels.py"
UNMAPPED_RETENTION_REPORT = "docs/reports/m2-step7-unmapped-bsp-range-retention-2026-10-22.md"
UNMAPPED_RETENTION_TEST = "tests/test_step7_unmapped_bsp_range_retention.py"
GAP_CONSUMER_AUDIT = "docs/reports/m2-step7-gap-consumer-evidence-2026-10-22.json"
PREDICTED_RESOURCE_TEST = "tests/test_hcu_mp_predicted_resource_member.py"
FIXTURE_ROOT_PATH = "tests/test_hcu_step7_open_root_bsp_dispositions.py"

SWARM = {
    "decals": ("decal", "runtime decal PVS lifecycle; host ILP32; all 13 stock MP maps; request spy, no GS/draw"),
    "decals_all13": ("decal", "runtime decal ownership/lifecycle summary; host; all 13 stock MP maps"),
    "detail": ("detail", "CE detail-object presentation bound; host ILP32; all 13; all retail roots empty; no rasterizer calls"),
    "lensflare": ("lensflare", "CE lens-flare cluster selector; host; all 13; source oracle; no GS/VU/PCSX2"),
    "lightmap": ("geometry", "CE material-for-surface query; host ILP32; all 13; every surface; no PS2 rendering output"),
    "omissions": ("schema_disposition", "source/retail census; all 13; stored-field callsite and PS2-closure disposition, not behavior"),
    "pathsmooth": ("path", "CE path smoothing; host; Blood Gulch one route only; synthetic actor; not retail bot behavior"),
    "portals": ("visibility", "CE visibility/portal/surface-reference routines; host ILP32; all 13; broad walks, selected paths stubbed"),
    "soundreq": ("sound", "CE sound request seam characterization; host ILP32; all 13 raw map samples; no BSP publication or SPU2 backend"),
    "swept": ("collision", "CE pill/sphere BSP functions; host ILP32; synthetic + Blood Gulch only; not production publisher/query wrapper"),
    "weather": ("environment", "CE fog/weather selection routines; host ILP32; all 13 raw maps; no HP2 relocation or particle renderer"),
}

# Exact report-name filters keep this catalogue relevant and auditable. Generic
# source-disposition documents are attached separately to every applicable row.
REPORT_FILTERS = {
    "collision": ("collision", "swept", "breakable"),
    "visibility": ("portal", "pvs", "leaf", "visibility", "nested-bsp-extent", "nested-bsp-field"),
    "geometry": ("lightmap", "render-mapping", "presentation-omission", "omissions"),
    "environment": ("fog", "weather", "wind", "location"),
    "sound": ("sound",),
    "decal": ("decal",),
    "detail": ("detail",),
    "lensflare": ("lens-flare", "lensflare"),
    "path": ("path",),
    "schema_disposition": ("schema", "field-inventory", "bsp-alignment", "nested-bsp-field"),
}

TOPIC_DEFINITION_PATTERNS = {
    "collision": re.compile(r"collision|bsp3d|bsp2d|real_plane|real_point|surface_reference", re.I),
    "visibility": re.compile(r"portal|cluster|leaf|subcluster|surface_reference|leaf_map|map_leaf|node", re.I),
    "geometry": re.compile(r"surface|lightmap|material|mirror|render_lighting|vertex", re.I),
    "environment": re.compile(r"fog|weather|wind", re.I),
    "sound": re.compile(r"sound|predicted_resource", re.I),
    "decal": re.compile(r"decal", re.I),
    "detail": re.compile(r"detail_object", re.I),
    "lensflare": re.compile(r"lens_flare", re.I),
    "path": re.compile(r"pathfinding", re.I),
}

CONSUMER_BY_TOPIC = {
    "collision": "CE collision_test_vector / collision_bsp_test_pill / collision_bsp_test_sphere and collision material/surface/leaf lookup; source callsites identified in the BSP consumer disposition.",
    "visibility": "CE structure_bsp_get_cluster_pvs, structure_visibility surface/portal/leaf traversal, and leaf-to-cluster lookup; exact applicable call depends on member.",
    "geometry": "CE structure_bsp_find_material_for_surface, structures surface-reference preparation, and/or lens/detail presentation consumers; exact applicable call depends on member.",
    "environment": "CE scenario fog-region/location/weather selection and wind palette selection; exact applicable call depends on member.",
    "sound": "CE sound-cluster distance/obstruction and scenario sound-environment/background-sound selection; sound request/backend evidence is separate.",
    "decal": "CE structure_decals_update/disconnect/reconnect reads runtime decals and cluster ownership ranges.",
    "detail": "CE structure_render_detail_objects and detail-cell/count/z-reference consumers.",
    "lensflare": "CE lens-flare marker clustering and rasterizer_lens_flare_submit_for_cluster.",
    "path": "CE pathfinding surface/edge reads and path-smoothing collision/breakable inputs.",
    "vehicle": "CE vehicles.c reads BSP vehicle_floor / vehicle_ceiling for vehicle vertical constraints; source identified, no Step 7 behavior fixture mapped.",
}

GENERIC_TOPIC_TERMS = {
    "collision": ("collision", "collision_bsp", "material_type", "breakable"),
    "visibility": ("visibility", "pvs", "portal", "leaf", "surface_reference"),
    "geometry": ("surface", "lightmap", "material", "lighting"),
    "environment": ("fog", "weather", "wind"),
    "sound": ("sound", "occlusion", "obstruction"),
    "decal": ("decal",), "detail": ("detail object",),
    "lensflare": ("lens flare", "lens-flare"), "path": ("pathfinding", "path smoothing"),
    "vehicle": ("vehicle_floor", "vehicle_ceiling"),
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


MAP_NAMES = ["beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout", "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace", "sidewinder", "wizard"]


def evidence_level(text: str, kind: str) -> str:
    if kind == "consumer disposition":
        return "source inspection"
    if kind == "swarm consumer report":
        return "source inspection" if "omission" in text[:500].lower() else "host execution"
    low = text.lower()
    positive_target_lines = [line for line in text.splitlines() if re.search(r"\b(PCSX2|interpreter|recompiler)\b", line, re.I) and re.search(r"\b(pass(?:ed)?|complete[ds]?|qualified|ran)\b", line, re.I) and not re.search(r"\b(no|not|without|neither)\b", line, re.I)]
    if positive_target_lines:
        return "PCSX2 interpreter/recompiler (report states a positive run; scope still limited by report)"
    if "host ilp32" in low or "host" in low or "native ilp32" in low:
        return "host execution"
    return "source inspection"


def result_from(text: str) -> str:
    m = re.search(r"(?im)^\s*(?:status|result|disposition)\s*:\s*([^\n]+)", text)
    if m:
        return m.group(1).strip().strip("* ")
    for line in text.splitlines():
        if re.search(r"\b(pass|partial|issues|unresolved|not run|open)\b", line, re.I):
            return line.strip().lstrip("# ")[:240]
    return "Referenced; no machine-readable result label found."


def artifact(path: Path, topic: str, scope: str, kind: str) -> dict:
    rel = path.relative_to(ROOT).as_posix()
    text = path.read_text(errors="replace")
    lower = text.lower()
    maps = [name for name in MAP_NAMES if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", lower)]
    if len(maps) == len(MAP_NAMES):
        map_scope = {"kind": "all_stock_mp_maps", "maps": maps}
    elif maps:
        map_scope = {"kind": "named_map_subset", "maps": maps}
    else:
        map_scope = {"kind": "no_map_fixture_identified", "maps": []}
    fixture_clues = []
    for clue, pattern in (("host_ilp32", r"host ilp32|native ilp32|\b-m32\b"), ("synthetic_control", r"synthetic (?:control|fixture|square|input)"), ("retail_raw_source_oracle", r"raw (?:xbox )?(?:bsp|map)|raw oracle|retail (?:map|bsp)"), ("pcsx2", r"pcsx2"), ("source_callsite_inspection", r"source (?:inspection|callsite|consumer)|call.?site")):
        if re.search(pattern, lower): fixture_clues.append(clue)
    return {
        "path": rel,
        "sha256": sha(path),
        "topic": topic,
        "artifact_kind": kind,
        "evidence_level": evidence_level(text, kind),
        "result": result_from(text),
        "fixture_scope": scope,
        "map_scope": map_scope,
        "fixture_clues": fixture_clues,
        "limitations": "See report's Limits/Issues section; related evidence is not promoted to byte/member semantic qualification.",
    }


def row_topic(member: dict) -> list[str]:
    path = member["path"]
    name = member["definition"] + " " + path
    # Prefer narrow record families before broad names such as cluster/surface.
    ordered = ["decal", "detail", "lensflare", "path", "environment", "sound", "collision", "geometry", "visibility"]
    out = [topic for topic in ordered if TOPIC_DEFINITION_PATTERNS[topic].search(name)]
    # Root blocks map to their own semantic consumer family.
    if member["definition"] == "structure_bsp":
        field = path.split(".", 1)[1].split("[", 1)[0]
        root = {
            "collision_materials": "collision", "collision_bsp": "collision", "breakable_surfaces": "collision",
            "nodes": "visibility", "leaves": "visibility", "surface_references": "visibility",
            "surfaces": "geometry", "lightmaps": "geometry", "lens_flares": "lensflare",
            "lens_flare_markers": "lensflare", "clusters": "visibility", "cluster_data": "visibility",
            "cluster_portals": "visibility", "fog_planes": "environment", "fog_regions": "environment",
            "fog_palette": "environment", "weather_palette": "environment", "weather_polyhedra": "environment",
            "pathfinding_surfaces": "path", "pathfinding_edges": "path", "background_sound_palette": "sound",
            "sound_environment_palette": "sound", "sound_cluster_data": "sound", "detail_object_data": "detail",
            "runtime_decals": "decal", "leaf_map": "visibility", "markers": "visibility",
            "default_lighting": "geometry", "world_bounds": "visibility", "vehicle_floor": "vehicle",
            "vehicle_ceiling": "vehicle",
        }
        if field in root:
            out = [root[field]]
    # Exact declaration family is more useful than cross-category token noise.
    return list(dict.fromkeys(out))


def main() -> None:
    inv = json.loads(INVENTORY.read_text())
    range_layout_path = ROOT / RANGE_LAYOUT
    range_layout = json.loads(range_layout_path.read_text())
    range_by_key = {(x["definition_id"], x["schema_range"]["offset"], x["schema_range"]["size"]): x for x in range_layout["ranges"]}
    open_root_path = ROOT / OPEN_ROOT
    open_root = json.loads(open_root_path.read_text())
    open_by_path = {x["inventory_path"]: x for x in open_root["rows"]}
    sentinel_rows = [m for m in inv["members"] if m["kind"] == "check" and m["size"] == 0]
    sentinel_artifact = {
        "path": INVENTORY.relative_to(ROOT).as_posix(),
        "sha256": sha(INVENTORY),
        "schema_elf_path": inv["schema_elf"],
        "schema_elf_sha256": inv["schema_elf_sha256"],
        "test_path": SENTINEL_TEST,
        "test_sha256": sha(ROOT / SENTINEL_TEST),
        "members": [{"inventory_path": m["path"], "definition_id": m["definition_id"], "target_level": m["target_level"], "target_offset": m["target_offset"], "serialized_size": m["size"], "kind": m["kind"]} for m in sentinel_rows],
        "interpretation": "Compiler-inventory check descriptors at 0:0 have no serialized byte extent. They are nonserialized sentinel metadata and do not imply runtime validation/check callback execution.",
    }
    target_path = ROOT / TARGET_PATH
    target_artifact = artifact(target_path, "path", "PCSX2 recompiler; CE A* path_state route diagnostic on all 13 stock MP maps; does not exercise actors or steering", "PCSX2 recompiler consumer report")
    current_target_path = ROOT / CURRENT_TARGET_PATH
    current_target_json = ROOT / CURRENT_TARGET_JSON
    current_target_artifact = artifact(current_target_path, "collision", "Paired PCSX2 interpreter/recompiler current-target CE BSP query across all 13 stock MP maps", "PCSX2 interpreter/recompiler consumer report")
    current_target_members = set()
    if current_target_json.is_file():
        target_data = json.loads(current_target_json.read_text())
        current_target_members = {item["member"] for item in target_data.get("consumer_members_invoked", [])}
    # Each swarm report has a category and its own tightly stated fixture scope.
    evidence_by_topic: dict[str, list[dict]] = {}
    for directory, (topic, scope) in SWARM.items():
        p = ROOT / "build/step7-swarm" / directory / "report.md"
        evidence_by_topic.setdefault(topic, []).append(artifact(p, topic, scope, "swarm consumer report"))

    generic = []
    for rel in (DISPOSITION, NESTED, MEMBER_LEDGER):
        p = ROOT / rel
        generic.append(artifact(p, "source_disposition", "CE source consumer inventory; map-independent source inspection; not a behavior fixture", "consumer disposition"))
    generic.append(artifact(range_layout_path, "compiler source layout", "R5900 compiler-derived offsetof/sizeof mapping; source-layout association only, not semantic or target behavior", "compiler source layout"))
    generic.append(artifact(open_root_path, "root BSP disposition", "Per-member source pin and host fixture; target behavior remains unverified", "root disposition and host fixture"))
    gap_consumer_path = ROOT / GAP_CONSUMER_AUDIT
    gap_consumer_artifact = artifact(gap_consumer_path, "compiled member consumer audit", "46 schema-gap ranges with compiled C-member overlaps; textual source access discovery and curated related fixture mapping only", "machine-readable source/fixture crosswalk")
    gap_consumer_artifact["evidence_level"] = "source inspection"
    gap_consumer_artifact["fixture_clues"] = ["compiler_member_layout", "explicit_member_access_search", "fixture_association"]
    gap_consumer_artifact["limitations"] = "The report inventories source text accesses and fixture associations only; none is target execution or whole-range semantic closure."
    retention_test_path = ROOT / UNMAPPED_RETENTION_TEST
    retention_report_path = ROOT / UNMAPPED_RETENTION_REPORT
    synthetic_gap_retention_artifact = {
        "path": retention_report_path.relative_to(ROOT).as_posix(),
        "sha256": sha(retention_report_path),
        "test_path": retention_test_path.relative_to(ROOT).as_posix(),
        "test_sha256": sha(retention_test_path),
        "inventory_path": INVENTORY.relative_to(ROOT).as_posix(),
        "inventory_sha256": sha(INVENTORY),
        "covered_unclassified_ranges": sum(m["classification"] == "unclassified" for m in inv["members"]),
        "evidence_level": "host execution",
        "result": "All 54 unclassified inventory ranges passed exact-offset synthetic scalar-placeholder preservation; semantic disposition remains open.",
        "limitations": "Does not prove production traversal through nested records, retail pointer-domain validity, consumer semantics, safe normalization, or target behavior.",
    }
    generic_text = {e["path"]: (ROOT / e["path"]).read_text(errors="replace").lower() for e in generic}

    # Relevant Step 7 reports are discoverable by filename family. The names are
    # kept in the output so the curated association can be reviewed/revised.
    report_files = sorted((ROOT / "docs/reports").glob("*.md"))
    report_topic_files: dict[str, list[dict]] = {k: [] for k in REPORT_FILTERS}
    excluded_generic = {Path(DISPOSITION).name, Path(NESTED).name, Path(MEMBER_LEDGER).name}
    for p in report_files:
        stem = p.name.lower()
        if not (stem.startswith("m2-step7") or stem.startswith("step7")):
            continue
        if p.name in excluded_generic:
            continue
        body = p.read_text(errors="replace")
        # Require some BSP/consumer context; avoid indexing unrelated Step 7 docs.
        if not re.search(r"\b(bsp|cluster|collision|surface|fog|weather|portal|decal|sound|leaf|pathfinding|lens.flare)\b", body, re.I):
            continue
        for topic, tokens in REPORT_FILTERS.items():
            if any(token in stem for token in tokens):
                report_topic_files[topic].append(artifact(p, topic, "Scope is stated by the report; read its fixture/map table for exact tested members and maps.", "Step 7 report"))

    for topic, items in report_topic_files.items():
        evidence_by_topic.setdefault(topic, []).extend(items)

    # Per-member crosswalk. A family association remains `related`, unless the
    # report text names the member/path explicitly; even that does not imply full
    # byte-range semantic coverage for a host/selection fixture.
    rows = []
    for member in inv["members"]:
        topics = row_topic(member)
        path_lower = member["path"].lower()
        member_leaf = member["path"].split(".")[-1].split("[")[0].lower()
        cls = member["classification"]
        range_record = range_by_key.get((member["definition_id"], member.get("offset_within_definition"), member["size"])) if cls == "unclassified" else None
        root_record = open_by_path.get(member["path"])
        compiled_fields = range_record.get("candidate_c_members", []) if range_record else []
        is_sentinel = member in sentinel_rows
        evidence = []
        for e in generic:
            body = generic_text[e["path"]]
            exact_here = member_leaf and re.search(r"(?<![a-z0-9_])" + re.escape(member_leaf) + r"(?![a-z0-9_])", body)
            topic_here = any(term in body for t in topics for term in GENERIC_TOPIC_TERMS.get(t, ()))
            if path_lower in body or exact_here or topic_here:
                evidence.append(e)
        if range_record:
            evidence.append(generic[-2])
        if root_record:
            evidence.append(generic[-1])
            if root_record.get("fixture"):
                evidence.append({
                    "path": FIXTURE_ROOT_PATH,
                    "sha256": root_record.get("fixture_sha256") or sha(ROOT / FIXTURE_ROOT_PATH),
                    "topic": "opaque-byte-retention",
                    "artifact_kind": "exact-member host preservation fixture",
                    "evidence_level": "host execution",
                    "test_name": root_record["fixture"],
                    "result": "PASS: exact compiler-layout member bytes are unchanged; no relocation site or nested schema span intersects the omitted range",
                    "fixture_scope": root_record.get("fixture_scope", ""),
                    "map_scope": {"kind": "synthetic", "maps": []},
                    "fixture_clues": ["exact_member:" + member_leaf, "synthetic compiler-schema walk"],
                    "limitations": "Byte preservation and non-interpretation by this schema walk only. Field semantics, aliases/raw-offset readers, runtime consumer behavior, and target execution remain unresolved.",
                })
        if is_sentinel:
            evidence.append({"path": INVENTORY.relative_to(ROOT).as_posix(), "sha256": sha(INVENTORY), "topic": "schema sentinel", "artifact_kind": "compiler schema inventory plus focused extent test", "evidence_level": "source inspection and host assertion", "result": "zero serialized extent; runtime consumer semantics not tested", "fixture_scope": "three compiler-inventory check descriptors", "map_scope": {"kind": "not applicable", "maps": []}, "fixture_clues": ["compiler_schema_inventory"], "limitations": "Nonserialized descriptor classification only; no callback/runtime behavior claim."})
        if cls == "unclassified":
            report = ROOT / UNMAPPED_RETENTION_REPORT
            test = ROOT / UNMAPPED_RETENTION_TEST
            evidence.append({
                "path": UNMAPPED_RETENTION_REPORT,
                "sha256": sha(report),
                "topic": "opaque-byte-retention",
                "artifact_kind": "synthetic exact-range retention fixture",
                "evidence_level": "host execution",
                "test_path": test.relative_to(ROOT).as_posix(),
                "test_sha256": sha(test),
                "result": "synthetic scalar placeholder preserves this exact inventory offset/extent; semantic disposition remains unresolved",
                "fixture_scope": f"{member['path']} (offset {member['offset_within_definition']}, {member['size']} bytes); exact-offset schema-walker retention only",
                "map_scope": {"kind": "synthetic", "maps": []},
                "fixture_clues": [test.relative_to(ROOT).as_posix(), "54 inventory ranges exercised"],
                "limitations": "Does not recover a retail C member or validate its real nested pointer domain; does not establish consumer behavior, safe normalization, or target execution.",
            })
        if member["definition"] == "predicted_resource" and member.get("offset_within_definition") == 2 and member["size"] == 2:
            test = ROOT / PREDICTED_RESOURCE_TEST
            evidence.append({
                "path": test.relative_to(ROOT).as_posix(),
                "sha256": sha(test),
                "fixture_input_path": "tests/hcu_predicted_resource_member_main.c",
                "fixture_input_sha256": sha(ROOT / "tests/hcu_predicted_resource_member_main.c"),
                "topic": "predicted_resource",
                "artifact_kind": "exact-member behavior fixture",
                "evidence_level": "host execution",
                "result": "PASS: verbatim CE predicted_resource_valid accepts in-range bitmap resource_index values and rejects negative/end indices, wrong group, and missing tag",
                "fixture_scope": "predicted_resource.resource_index (offset 2, 2 bytes); synthetic bounded records; CE validator extracted verbatim",
                "map_scope": {"kind": "synthetic", "maps": []},
                "fixture_clues": ["exact_member:resource_index", "synthetic host fixture"],
                "limitations": "Host validator fixture only; does not exercise retail BSP publication, bitmap/sound cache side effects, PCSX2, or physical console behavior.",
            })
        for t in topics:
            evidence.extend(evidence_by_topic.get(t, []))
        target_rows = member["path"] in current_target_members or member["path"] in ("structure_bsp.pathfinding_surfaces", "structure_bsp.pathfinding_edges")
        if member["path"] in ("structure_bsp.pathfinding_surfaces", "structure_bsp.pathfinding_edges"):
            evidence.append(target_artifact)
        if member["path"] in current_target_members:
            evidence.append(current_target_artifact)
        # Deduplicate by path while preserving source-disposition artifacts.
        by_path = {e["path"]: e for e in evidence}
        evidence = list(by_path.values())
        exact = [e for e in evidence if member_leaf and re.search(r"(?<![a-z0-9_])" + re.escape(member_leaf) + r"(?![a-z0-9_])", (ROOT / e["path"]).read_text(errors="replace").lower())]
        behavior_evidence = [e for e in evidence if e["artifact_kind"] in ("swarm consumer report", "Step 7 report") and e["evidence_level"] in ("host execution", "PCSX2 interpreter/recompiler (report states a positive run; scope still limited by report)")]
        exact_behavior = [e for e in behavior_evidence if member_leaf and re.search(r"(?<![a-z0-9_])" + re.escape(member_leaf) + r"(?![a-z0-9_])", (ROOT / e["path"]).read_text(errors="replace").lower())]
        direct_member_behavior = [e for e in evidence if e["artifact_kind"] == "exact-member behavior fixture"]
        direct_member_retention = [e for e in evidence if e["artifact_kind"] == "exact-member host preservation fixture"]
        exact_artifact_kinds = []
        if exact: exact_artifact_kinds.append("artifact_text_names_member")
        if compiled_fields: exact_artifact_kinds.append("compiler_source_member_layout_only")
        if root_record: exact_artifact_kinds.append("root_source_disposition")
        if target_rows: exact_artifact_kinds.append("target_consumer_slice_member_mapping")
        if cls == "unclassified":
            exact_artifact_kinds.append("synthetic_exact_range_retention_only")
        if direct_member_behavior:
            exact_artifact_kinds.append("direct_exact_member_host_behavior_fixture")
        if direct_member_retention:
            exact_artifact_kinds.append("exact_member_host_retention_fixture")
        if cls == "unclassified":
            gap = "Serialized byte range has no schema field interpretation. Consumer references cannot classify it, and no safe-removal/normalization conclusion is permitted. Recover compiler/source record layout and audit exact readers, or preserve opaque bytes with a tested replacement."
            result = "unresolved range"
            relation = "related family reports only; range is not assigned a member consumer"
        elif cls == "consumer-disposition-open":
            gap = "Member is omitted/unrepresented by the validation schema. Exact C-layout extent does not establish a usable relocated pointer or safe behavior. Add a field schema or prove an explicit tested replacement; preserve bytes meanwhile."
            result = "open consumer disposition"
            relation = "source/layout evidence only; no semantic clearance"
        else:
            gap = "Family-level consumer evidence exists where listed, but exact field behavior, production-published BSP use, current PS2 target execution, and/or all-map scope remain unproven. Keep the member retained until its named consumer and bounds are qualified."
            result = "partial; no member-level closure"
            relation = "exact member named in artifact" if exact else ("related family evidence; not member-specific" if evidence else "no mapped consumer artifact")
        rows.append({
            "inventory_path": member["path"],
            "definition": member["definition"],
            "definition_id": member["definition_id"],
            "classification": cls,
            "kind": member["kind"],
            "offset_within_definition": member["offset_within_definition"],
            "size": member["size"],
            "count": member.get("count"),
            "schema_target": {k: member.get(k) for k in ("target_level", "target_offset", "groups") if k in member},
            "compiler_source_layout": ({"status": range_record["compiler_source_type_probe_status"], "source_declaration": range_record["source_declaration"], "source_declaration_sha256": range_record["source_declaration_sha256"], "candidate_c_members": compiled_fields, "schema_range": range_record["schema_range"], "interpretation": range_record["interpretation"]} if range_record else None),
            "open_root_disposition": ({"status": root_record["status"], "disposition": root_record["disposition"], "fixture": root_record.get("fixture"), "fixture_sha256": root_record.get("fixture_sha256"), "consumer": root_record.get("consumer")} if root_record else None),
            "consumer_topics": topics,
            "source_consumer": ("Zero-byte schema check descriptor; it carries no serialized payload member. The corresponding validator/callback execution remains a separate qualification question." if member["path"] == "structure_bsp.structure_bsp_check" else "CE objects/object_lights.c copies structure_bsp.default_lighting as fallback lighting (member ledger source: line 2411)." if member["path"] == "structure_bsp.default_lighting" else "CE structure_visibility.c reads structure_bsp.world_bounds for CPU visibility bounds (member ledger source: line 1588)." if member["path"] == "structure_bsp.world_bounds" else "; ".join(CONSUMER_BY_TOPIC[t] for t in topics) if topics else "No member-specific consumer assignment from the current source-disposition inventory; source search remains required."),
            "evidence_relation": ("compiler source member layout only; no semantic disposition" if compiled_fields and not exact else "exact root member source disposition; target behavior open" if root_record else relation),
            "no_serialized_range": member["size"] == 0,
            "exact_member_evidence": bool(exact) or bool(compiled_fields) or bool(root_record) or target_rows or is_sentinel or bool(direct_member_behavior),
            "exact_member_artifact_kinds": exact_artifact_kinds,
            "exact_member_source_layout_only": bool(compiled_fields) and not exact,
            "target_consumer_execution": target_rows,
            "nonserialized_schema_sentinel": is_sentinel,
            "exact_member_behavior_fixture": bool(exact_behavior or direct_member_behavior),
            "exact_member_retention_fixture": bool(direct_member_retention),
            "has_related_behavior_fixture": bool(behavior_evidence),
            "zero_consumer_evidence": member["size"] > 0 and not topics and not evidence,
            "result": result,
            "remaining_gap": gap,
            "evidence_artifacts": evidence,
        })

    # Definition summary marks true zero-consumer-evidence definitions, while
    # separately reporting definitions with source-only evidence and behavior.
    defs = []
    for d in inv["definitions"]:
        dr = [r for r in rows if r["definition"] == d["name"]]
        topics = list(dict.fromkeys(t for r in dr for t in r["consumer_topics"]))
        behavior = [r for r in dr if r["has_related_behavior_fixture"]]
        exact = [r for r in dr if r["exact_member_evidence"]]
        source = [e for r in dr for e in r["evidence_artifacts"] if e["artifact_kind"] == "consumer disposition"]
        defs.append({
            "definition": d["name"], "definition_id": d["definition_id"],
            "serialized_size": d["serialized_size"], "inventory_member_rows": len(dr),
            "schema_declared_rows": sum(r["classification"] == "schema-declared" for r in dr),
            "unclassified_rows": sum(r["classification"] == "unclassified" for r in dr),
            "consumer_disposition_open_rows": sum(r["classification"] == "consumer-disposition-open" for r in dr),
            "consumer_topics": topics,
            "has_source_disposition_reference": bool(source),
            "has_related_behavior_fixture": bool(behavior),
            "has_exact_member_evidence": bool(exact),
            "zero_behavior_fixture_coverage": not behavior,
            "zero_exact_member_evidence": not exact,
            "zero_consumer_evidence": not topics and not behavior,
            "remaining_gap": "At least one member has an unclassified byte range or open consumer disposition; family-level fixture association is not whole-definition coverage." if any(r["classification"] != "schema-declared" for r in dr) else "No whole-definition consumer closure: member-specific production consumer qualification and target evidence remain required.",
        })

    # All swarm rows are represented explicitly, including soundreq's negative
    # backend result and the omission survey's source-only disposition.
    swarm_artifacts = []
    for directory, (topic, scope) in SWARM.items():
        p = ROOT / "build/step7-swarm" / directory / "report.md"
        swarm_artifacts.append(artifact(p, topic, scope, "swarm consumer report"))

    payload = {
        "format": "hcu-m2-step7-bsp-consumer-crosswalk-v1",
        "generated_by": "tools/generate_step7_bsp_consumer_crosswalk.py",
        "inventory_path": INVENTORY.relative_to(ROOT).as_posix(),
        "inventory_sha256": sha(INVENTORY),
        "interpretation": "Conservative relation map from compiler-derived inventory rows to extant consumer evidence. Related family reports are not proof of each member's semantic use. No unclassified bytes are deemed safe, removable, or unused.",
        "mapping_policy": {
            "source_disposition": "Identifies CE consumer/source family only; not execution evidence.",
            "swarm_report": "Host fixture result with the exact scope/limitations summarized in the report. It remains host evidence, not PCSX2/retail-EE qualification.",
            "unclassified_range": "Always unresolved until exact byte layout and reader semantics are established.",
            "empty_retail_field": "An empty result for stock maps does not erase structural or future-consumer requirements.",
        },
        "source_disposition_artifacts": generic,
        "compiler_range_layout_artifact": artifact(range_layout_path, "compiler source layout", "R5900 compiler-derived offsetof/sizeof mapping; source-layout association only", "compiler source layout"),
        "gap_consumer_audit_artifact": gap_consumer_artifact,
        "synthetic_gap_retention_artifact": synthetic_gap_retention_artifact,
        "open_root_disposition_artifact": artifact(open_root_path, "root BSP disposition", "Per-member source pin and host fixture; target behavior remains unverified", "root disposition and host fixture"),
        "target_pathfinding_artifact": target_artifact,
        "swarm_reports": swarm_artifacts,
        "definition_count": len(defs),
        "inventory_row_count": len(rows),
        "definitions_with_zero_consumer_evidence": [d["definition"] for d in defs if d["zero_consumer_evidence"]],
        "definitions_with_zero_behavior_fixture_coverage": [d["definition"] for d in defs if d["zero_behavior_fixture_coverage"]],
        "definitions_with_zero_exact_member_evidence": [d["definition"] for d in defs if d["zero_exact_member_evidence"]],
        "definitions": defs,
        "rows": rows,
        "zero_size_sentinel_evidence": sentinel_artifact,
        "coverage_summary": {
            "inventory_rows": len(rows),
            "schema_declared_rows": sum(r["classification"] == "schema-declared" for r in rows),
            "unclassified_ranges": sum(r["classification"] == "unclassified" for r in rows),
            "target_semantic_qualification_open_rows": sum(r["classification"] == "consumer-disposition-open" for r in rows),
            "open_root_omitted_rows": len(open_root["rows"]),
            "open_root_semantics_open_rows": open_root["counts"]["preserve_only_semantics_open"],
            "open_root_source_disposition_resolved_rows": open_root["counts"]["source_backed_disposition_resolved"],
            "rows_without_mapped_topic": sum(not r["consumer_topics"] for r in rows),
            "rows_with_zero_consumer_evidence": sum(r["zero_consumer_evidence"] for r in rows),
            "rows_with_zero_exact_member_evidence": sum(not r["exact_member_evidence"] for r in rows),
            "rows_with_exact_member_behavior_fixture": sum(r["exact_member_behavior_fixture"] for r in rows),
            "rows_with_direct_exact_member_behavior_fixture": sum("direct_exact_member_host_behavior_fixture" in r["exact_member_artifact_kinds"] for r in rows),
            "rows_with_any_exact_member_artifact": sum(r["exact_member_evidence"] for r in rows),
            "rows_with_only_source_layout_exactness": sum(r["exact_member_source_layout_only"] for r in rows),
            "rows_without_any_exact_member_artifact": sum(not r["exact_member_evidence"] for r in rows),
            "rows_with_target_consumer_execution": sum(r["target_consumer_execution"] for r in rows),
            "unclassified_rows_with_compiled_source_member_overlap": sum(bool(r["compiler_source_layout"] and r["compiler_source_layout"]["candidate_c_members"]) for r in rows),
            "open_root_dispositions_source_backed": open_root["counts"]["source_backed_disposition_resolved"],
            "open_root_dispositions_semantics_open": open_root["counts"]["preserve_only_semantics_open"],
            "rows_with_only_family_related_evidence": sum(r["evidence_relation"] == "related family evidence; not member-specific" for r in rows),
            "definitions_with_zero_consumer_evidence": sum(d["zero_consumer_evidence"] for d in defs),
            "definitions_with_zero_behavior_fixture_coverage": sum(d["zero_behavior_fixture_coverage"] for d in defs),
            "definitions_with_zero_exact_member_evidence": sum(d["zero_exact_member_evidence"] for d in defs),
            "definitions_with_related_behavior_fixture": sum(d["has_related_behavior_fixture"] for d in defs),
            "current_target_execution_rows": sum(r["target_consumer_execution"] for r in rows),
        },
        "exact_member_count_definitions": {
            "rows_with_exact_member_behavior_fixture": "Rows with a host/PCSX2 execution artifact whose text names the exact schema member; family-only fixture association is excluded.",
            "rows_with_any_exact_member_artifact": "Rows with a member-naming artifact, compiler-derived C member layout association, or individually pinned root disposition. This is broader than behavioral coverage and does not imply semantic closure.",
            "rows_with_target_consumer_execution": "Inventory rows explicitly listed in the paired current-target report's consumer_members_invoked, plus pathfinding rows from the retained A* report. This is scoped diagnostic execution, not general whole-inventory qualification.",
        },
        "open_count_definitions": {
            "target_semantic_qualification_open_rows": "Compiler inventory rows classified consumer-disposition-open; all 12 are still pending target semantic qualification, whether or not a source-backed retention disposition exists.",
            "open_root_omitted_rows": "The separate source-pinned root omission ledger has 12 members total.",
            "open_root_semantics_open_rows": "Eight *_unused root omissions remain preserve-only with semantics unresolved; four others have source-backed dispositions, still without target behavior closure.",
        },
        "rows_without_any_exact_member_artifact": [r["inventory_path"] for r in rows if not r["exact_member_evidence"]],
        "remaining_consumer_gaps": [
            "No current PS2 guest row demonstrates any mapped BSP consumer; host ILP32/source evidence must not be promoted to guest qualification.",
            "All 54 compiler-inventory unclassified ranges now have exact-offset synthetic byte-retention checks. Their byte/member semantics, real nested pointer domains, and production traversal remain unresolved.",
            "The 12 schema-omitted C-layout members have extent assertions but no schema relocation/consumer replacement closure.",
            "The initial 57 rows without exact-member artifacts now link to range/layout or disposition evidence. The R5900 probe associates 46 ranges with compiled C members; a focused host fixture directly exercises predicted_resource.resource_index. Neither layout nor scalar retention classifies the other 53 opaque ranges; only this one member has direct exact-member host behavior evidence in this new crosswalk slice.",
            "Four of 12 open root omissions have source-backed retention dispositions with host fixtures; eight *_unused members remain preserve-only semantic open, and three source-backed members still lack target behavior verification. See the pinned open-root disposition artifact.",
            "Retail source-map behavior is uneven: several swarm fixtures cover all 13 maps, while swept collision and path smoothing are Blood Gulch-only and remain host fixtures.",
            "The BSP source disposition lists required collision, PVS, sound, fog/weather, surface/lightmap, predicted-resource, decal, detail, lens-flare, and path consumers; each still needs exact member bounds and current production/target behavior qualification.",
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} rows={len(rows)} definitions={len(defs)} zero_consumer_defs={len(payload['definitions_with_zero_consumer_evidence'])}")


if __name__ == "__main__":
    main()
