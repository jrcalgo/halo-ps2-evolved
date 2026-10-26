#!/usr/bin/env python3
"""Generate and check the C4 BSP/scenario member ledger.

Every compiler-inventory member (top-level and typed nested record) gets one
row with a classification from the C4 vocabulary:

  consumed            named CE consumer AND member-exact parity fixture
  preserved-opaque    no CE consumer: grep of `.name` / `->name` in CE source
                      finds zero accesses (evidence recorded)
  runtime-normalized  C0 disposition is a pointer/count reset and the member lacks
                      member-exact consumer parity (the consumer gap stays in gap_type)
  synthetic-covered   empty in all audited retail maps, with a recorded synthetic
                      nonempty fixture and its test present
  blocked             anything else; gap_reason states exactly why

Gaps are never relabelled: a consumer that only has family-level reports is
`blocked` with gap_type `consumer-family-parity-only`, not `consumed`.

Usage:
  python3 tools/audit_c4_member_ledger.py          # check committed ledger
  python3 tools/audit_c4_member_ledger.py --write  # regenerate JSON and markdown
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
CROSSWALK = "docs/reports/m2-step7-bsp-consumer-crosswalk-2026-10-22.json"
C0_DISPOSITIONS = "docs/reports/m2-c0-byte-dispositions-2026-10-23.json"
EMPTY_FIELDS = "docs/reports/m2-step7-empty-bsp-fields-2026-10-22.json"
GAP_EVIDENCE = "docs/reports/m2-step7-gap-consumer-evidence-2026-10-22.json"
RELOCATION_JOURNAL = "docs/reports/m2-step7-multiplayer-relocation-runtime-atomicity-2026-10-21.md"
SYNTHETIC_TEST = "tests/test_step7_synthetic_empty_bsp_fields.py"
CE_SOURCE = "submodules/halo-ce-universal/source"
RANGE_LAYOUT = "docs/reports/m2-step7-bsp-range-member-layout-2026-10-22.json"
PARITY_DIR = "docs/reports"
PARITY_GLOB = "m4-c4-parity-*.json"
RANGE_GLOB = "m4-c4-range-dispositions-*.json"
PROMOTABLE_GAPS = {"consumer-family-parity-only", "consumed-pending-fixture", "validator-execution-unqualified"}
RANGE_DISPOSITIONS = {"runtime-normalized", "preserved-opaque", "consumed", "schema-gap", "blocked"}

# Deferral rows: a lane's blocked row that only hands the member to its owning lane. A member-exact pass
# from the owner lane supersedes that deferral. Any other blocked result still keeps the row blocked.
DEFERRALS = {
    "structure_fog_plane.runtime_material_type": {
        "deferring_lane": "fog",
        "owner_lane": "collision",
        "evidence": "fog parity row: 'Owned by the collision lane; left as is per coordinator instruction.'",
    },
}

# Recorded corrections to crosswalk-derived CE sites. The crosswalk itself is not edited.
CORRECTIONS = {
    "collision_leaf.<unclassified@0x0>": {
        "ce_access_sites": ["submodules/halo-ce-universal/source/physics/collision_bsp.c:2216"],
        "consumer": ("CE physics/collision_bsp.c:2216-2224 reads collision_leaf.flags through "
                     "TAG_BLOCK_GET_ELEMENT(...)->flags (two-sided bit selects contents)"),
        "note": ("collision_leaf.flags is consumed. An earlier name grep missed the ')->flags' accessor, so "
                 "the preserved-opaque reading was wrong. The DWARF range's other live member is "
                 "bsp2d_reference_count/first_bsp2d_reference_index (ranges-c lane)."),
    },
    "map_leaf.portal_designators": {
        "ce_access_sites": [
            "submodules/halo-ce-universal/source/structures/leaf_map.c:485",
            "submodules/halo-ce-universal/source/structures/leaf_map.c:514",
        ],
        "consumer": ("CE structures/leaf_map.c:472-525 (leaf_map_close_portal and leaf-map builder) reads "
                     "leaf->portal_designators; not debug-only"),
        "note": "Correction: portal_designators is read by the leaf-map builder, not only by debug drawing.",
    },
    "collision_surface.<unclassified@0x0>": {
        "ce_access_sites": [
            "submodules/halo-ce-universal/source/physics/collision_bsp.c:746",
            "submodules/halo-ce-universal/source/physics/collision_bsp.c:816",
        ],
        "consumer": ("CE physics/collision_bsp.c: plane_designator reaches the bsp3d plane at line 746 "
                     "(collision_surface_area) and is masked with LONG_MAX at line 816 "
                     "(collision_surface_project_point2d)"),
        "note": ("Sign-bit wording: collision_surface_area negates the designator's sign bit; "
                 "collision_surface_project_point2d masks the sign bit (LONG_MAX) instead. The 'sign bit = "
                 "negated' wording holds for area only."),
    },
    "structure_material.breakable_surface_index": {
        "ce_access_sites": ["submodules/halo-ce-universal/source/structures/structure_render.c:590"],
        "consumer": ("CE structures/structure_render.c:590 breakable_surface_extant(material->"
                     "breakable_surface_index) in the structure_material render path"),
        "note": ("Collision lane report: submodules/halo-ce-universal/source/ai/path.c:654 reads "
                 "struct collision_surface (surface->breakable_surface_index), a different member. "
                 "It is not a structure_material read and is removed from this row's sites."),
    },
}
OUT_JSON = "docs/reports/m4-c4-member-ledger-2026-10-26.json"
OUT_MD = "docs/reports/m4-c4-member-ledger-2026-10-26.md"

FORMAT = "m4-c4-member-ledger-v1"
CLASSES = ("consumed", "preserved-opaque", "runtime-normalized", "synthetic-covered",
           "covered-by-member-rows", "blocked")

# Families named in C4.1 plus the structural families the inventory needs.
C41_FAMILIES = (
    "collision-wrappers-materials-surfaces",
    "pvs-portals-pas",
    "fog-weather-wind",
    "sound-environments",
    "lightmaps",
    "breakables",
    "decals",
    "detail-objects",
    "lens-flares",
    "markers",
    "pathfinding",
    "runtime-normalized-values",
)
EXTRA_FAMILIES = ("bsp-root-and-checks", "predicted-resources", "typed-primitive-records")

RESET_DISPOSITIONS = {
    "preserve_count_and_elements_relocate_address_reset_definition",
    "preserve_size_and_content_relocate_address",
    "documented_runtime_reset",
}
# Artifact kinds that are source-inspection only and never count as parity.
NON_PARITY_KINDS = {
    "consumer disposition",
    "compiler source layout",
    "synthetic exact-range retention fixture",
    "compiler schema inventory plus focused extent test",
}
NO_CONSUMER_PREFIXES = ("No member-specific consumer", "Zero-byte schema check")

DEFINITION_FAMILY = {
    "collision_bsp": "collision-wrappers-materials-surfaces",
    "collision_edge": "collision-wrappers-materials-surfaces",
    "collision_leaf": "collision-wrappers-materials-surfaces",
    "collision_surface": "collision-wrappers-materials-surfaces",
    "collision_vertex": "collision-wrappers-materials-surfaces",
    "bsp2d_node": "collision-wrappers-materials-surfaces",
    "bsp2d_reference": "collision-wrappers-materials-surfaces",
    "bsp3d_node": "collision-wrappers-materials-surfaces",
    "structure_collision_material": "collision-wrappers-materials-surfaces",
    "structure_material": "collision-wrappers-materials-surfaces",
    "structure_surface": "collision-wrappers-materials-surfaces",
    "structure_surface_reference": "collision-wrappers-materials-surfaces",
    "structure_node": "collision-wrappers-materials-surfaces",
    "leaf_map": "pvs-portals-pas",
    "leaf_portal": "pvs-portals-pas",
    "map_leaf": "pvs-portals-pas",
    "map_leaf_face": "pvs-portals-pas",
    "structure_cluster": "pvs-portals-pas",
    "structure_cluster_portal": "pvs-portals-pas",
    "structure_portal_index": "pvs-portals-pas",
    "structure_subcluster": "pvs-portals-pas",
    "structure_leaf": "pvs-portals-pas",
    "structure_mirror": "pvs-portals-pas",
    "structure_fog_palette_entry": "fog-weather-wind",
    "structure_fog_plane": "fog-weather-wind",
    "structure_fog_region": "fog-weather-wind",
    "structure_weather_palette_entry": "fog-weather-wind",
    "structure_weather_polyhedron": "fog-weather-wind",
    "structure_sound_environment_palette_entry": "sound-environments",
    "structure_background_sound_palette_entry": "sound-environments",
    "structure_lightmap": "lightmaps",
    "render_lighting": "lightmaps",
    "structure_breakable_surface": "breakables",
    "structure_runtime_decal": "decals",
    "structure_detail_object_data": "detail-objects",
    "detail_object": "detail-objects",
    "detail_object_cell": "detail-objects",
    "detail_object_count": "detail-objects",
    "detail_object_z_reference_vector": "detail-objects",
    "structure_lens_flare": "lens-flares",
    "structure_lens_flare_marker": "markers",
    "predicted_resource": "predicted-resources",
    "real_plane3d": "typed-primitive-records",
    "real_point3d": "typed-primitive-records",
    "real_point2d": "typed-primitive-records",
    "byte": "typed-primitive-records",
    "long": "typed-primitive-records",
}
# structure_bsp top-level members, keyed by member name (path after the dot).
ROOT_MEMBER_FAMILY = {
    "lightmap_group": "lightmaps",
    "default_lighting": "lightmaps",
    "lightmaps": "lightmaps",
    "collision_materials": "collision-wrappers-materials-surfaces",
    "collision_bsp": "collision-wrappers-materials-surfaces",
    "nodes": "collision-wrappers-materials-surfaces",
    "surface_references": "collision-wrappers-materials-surfaces",
    "surfaces": "collision-wrappers-materials-surfaces",
    "leaves": "pvs-portals-pas",
    "clusters": "pvs-portals-pas",
    "cluster_data": "pvs-portals-pas",
    "cluster_portals": "pvs-portals-pas",
    "world_bounds": "pvs-portals-pas",
    "leaf_map": "pvs-portals-pas",
    "lens_flares": "lens-flares",
    "lens_flare_markers": "markers",
    "markers": "markers",
    "breakable_surfaces": "breakables",
    "fog_planes": "fog-weather-wind",
    "fog_regions": "fog-weather-wind",
    "fog_palette": "fog-weather-wind",
    "weather_palette": "fog-weather-wind",
    "weather_polyhedra": "fog-weather-wind",
    "pathfinding_surfaces": "pathfinding",
    "pathfinding_edges": "pathfinding",
    "background_sound_palette": "sound-environments",
    "sound_environment_palette": "sound-environments",
    "sound_cluster_data": "sound-environments",
    "detail_object_data": "detail-objects",
    "runtime_decals": "decals",
}

RE_PAD = re.compile(r"^pad", re.IGNORECASE)
RE_UNUSED = re.compile(r"unused|reserved", re.IGNORECASE)


def range_disposition(entry: dict | None) -> tuple[str, str | None, str]:
    """Disposition of one unclassified DWARF byte range from the compiler layout evidence.

    Only declared padding/unused fields in the CE struct layout (compiler-derived, overlapping the
    schema range) make a range preserved-opaque. Any overlapping live member makes it blocked.
    """
    if not entry or not entry.get("candidate_c_members"):
        return ("blocked", "unclassified-dwarf-range",
                "no compiler-selected C declaration covers this range; layout unknown, bytes retained only")
    off, size = entry["schema_range"]["offset"], entry["schema_range"]["size"]
    decl = entry.get("source_declaration") or {}
    where = f"{decl.get('path', '?')}:{decl.get('line', '?')}"
    live, pads, unused = [], [], []
    for c in entry["candidate_c_members"]:
        lo, hi = max(off, c["offset"]), min(off + size, c["offset"] + c["size"])
        if hi <= lo:
            continue
        if RE_PAD.match(c["name"]):
            pads.append(c["name"])
        elif RE_UNUSED.search(c["name"]):
            unused.append(c["name"])
        else:
            live.append(c["name"])
    if live:
        return ("blocked", "unclassified-dwarf-range",
                f"live CE member(s) {', '.join(live)} overlap this range ({where}) but are absent from the "
                "schema; a consumer and semantic reader are required")
    if pads and not unused:
        return ("preserved-opaque", None,
                f"alignment padding declared in CE layout ({', '.join(pads)} at {where}); retained byte-exact")
    if unused or pads:
        return ("preserved-opaque", None,
                f"declared unused/reserved span in CE layout ({', '.join(pads + unused)} at {where}); "
                "retained byte-exact")
    return ("blocked", "unclassified-dwarf-range",
            f"compiler declaration {where} overlaps the range but declares no unused or padding field")


RE_ACCESS = re.compile(r"(?:\.|->)\s*([A-Za-z_]\w*)")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(rel: str):
    return json.loads((ROOT / rel).read_text())


def member_name(path: str) -> str | None:
    """Field name used for CE access search, or None for byte-range rows."""
    leaf = path.split(".")[-1]
    if "<unclassified" in leaf:
        return None
    return re.sub(r"\[\d+\]$", "", leaf)


def structural_family(member: dict) -> str:
    definition = member["definition"]
    path = member["path"]
    if definition == "structure_bsp":
        name = path.split(".", 1)[1]
        name = re.sub(r"\[\d+\]$", "", name)
        if name in ROOT_MEMBER_FAMILY:
            return ROOT_MEMBER_FAMILY[name]
        return "bsp-root-and-checks"
    if member_name(path) and member_name(path).endswith("_check"):
        return "bsp-root-and-checks"
    if path.startswith("collision_bsp.bsp3d") or path.startswith("collision_bsp.bsp2d"):
        return "collision-wrappers-materials-surfaces"
    if definition in DEFINITION_FAMILY:
        return DEFINITION_FAMILY[definition]
    if path.startswith("structure_bsp."):
        return "bsp-root-and-checks"
    return "typed-primitive-records"


RE_DEF = re.compile(r"^[A-Za-z_][\w \*]*?\b([A-Za-z_]\w*)\s*\(")
RE_IDENT = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


def ce_index(names: set[str], idents: set[str]) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Field access sites (`.name`/`->name`) and column-0 function definitions in CE source."""
    index: dict[str, list[str]] = {n: [] for n in names}
    defs: dict[str, str] = {}
    base = ROOT / CE_SOURCE
    for src in sorted(base.rglob("*")):
        if src.suffix not in (".c", ".h", ".cpp", ".hpp", ".inl"):
            continue
        rel = src.relative_to(ROOT).as_posix()
        try:
            lines = src.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            for tok in RE_ACCESS.findall(line):
                if tok in index:
                    index[tok].append(f"{rel}:{lineno}")
            if line[:1].isalpha() and not line.rstrip().endswith(";"):
                m = RE_DEF.match(line)
                if m and m.group(1) in idents and m.group(1) not in defs:
                    defs[m.group(1)] = f"{rel}:{lineno}"
    return index, defs


def consumer_definition_sites(text: str, defs: dict[str, str]) -> list[str]:
    """CE definition sites of the function identifiers named in a crosswalk consumer string."""
    out = []
    for ident in RE_IDENT.findall(text):
        if ident in defs and defs[ident] not in out:
            out.append(defs[ident])
    return out[:3]


def parity_files(crosswalk_row: dict | None) -> list[str]:
    if not crosswalk_row:
        return []
    out = []
    for art in crosswalk_row.get("evidence_artifacts", []):
        if art["artifact_kind"] in NON_PARITY_KINDS:
            continue
        if (ROOT / art["path"]).exists() and art["path"] not in out:
            out.append(art["path"])
    return out


def build_rows() -> tuple[list[dict], dict[str, str]]:
    inventory = load(INVENTORY)
    crosswalk = load(CROSSWALK)
    c0 = load(C0_DISPOSITIONS)
    empty = load(EMPTY_FIELDS)
    gap = load(GAP_EVIDENCE)
    layout = {r["inventory_path"]: r for r in load(RANGE_LAYOUT)["ranges"]}

    # Key by inventory path: structure_bsp.lightmap_group and structure_bsp_check share offset 0.
    xw = {r["inventory_path"]: r for r in crosswalk["rows"]}
    disp = {r["path"]: r for r in c0["rows"]}
    fields = {f["path"]: f for f in empty["fields"]}
    empty_across = set(empty["empty_across_retail"])
    gaps = {
        g["inventory_path"]: g
        for g in gap["rows"]
    }

    members = inventory["members"]
    paths = [m["path"] for m in members]
    if len(set(paths)) != len(paths):
        raise SystemExit("inventory member paths are not unique")

    names = {member_name(m["path"]) for m in members} - {None}
    idents = set()
    for x in crosswalk["rows"]:
        idents.update(RE_IDENT.findall(x.get("source_consumer") or ""))
    access, defs = ce_index(names, idents)

    rows = []
    for m in members:
        x = xw.get(m["path"])
        d = disp.get(m["path"])
        if d is None or x is None:
            raise SystemExit(f"no crosswalk or C0 disposition row for {m['path']}")
        name = member_name(m["path"])
        field = fields.get(m["path"])
        if field is not None:
            retail_nonempty = field["retail_nonempty_bsp_count"] > 0
        else:
            retail_nonempty = None
        if m["path"] in empty_across:
            retail_nonempty = False
        synthetic = bool(field and field.get("synthetic_fixture")) and (ROOT / SYNTHETIC_TEST).exists()
        exact = bool(x and x["exact_member_behavior_fixture"])
        parity = parity_files(x)
        consumer_text = x["source_consumer"] if x else None
        consumer_named = bool(consumer_text) and not consumer_text.startswith(NO_CONSUMER_PREFIXES)
        hits = access.get(name, []) if name else []
        g = gaps.get(m["path"])
        gap_type = None
        needs_synthetic = False
        normalization = []
        consumer_sites: list[str] = []

        if m["classification"] == "unclassified":
            cls, gap_type, reason = range_disposition(layout.get(m["path"]))
            if g and g.get("candidate_ce_source_files"):
                for ov in g.get("compiled_member_overlaps", []):
                    for acc in ov.get("explicit_accesses_in_candidate_sources", []):
                        consumer_sites.append(f"{acc['path']}:{acc['line']}")
                consumer_sites = consumer_sites[:5]
            if cls == "preserved-opaque":
                consumer_sites = []
            parity = []
        elif m["path"] in empty_across:
            if synthetic:
                cls = "synthetic-covered"
                reason = ("empty in all audited retail maps; covered by recorded synthetic nonempty "
                          "fixture and its byte-walk test")
                if not exact:
                    needs_synthetic = True
                    gap_type = "consumer-behavior-on-synthetic-payload-unproven"
                    reason += "; no member-exact consumer behavior on the nonempty payload"
            else:
                cls = "blocked"
                needs_synthetic = True
                gap_type = "needs-synthetic-fixture"
                reason = "empty in all audited retail maps; no synthetic nonempty fixture recorded"
        elif consumer_named and exact and parity:
            cls = "consumed"
            reason = ""
        elif d["disposition"] in RESET_DISPOSITIONS:
            cls = "runtime-normalized"
            normalization = [C0_DISPOSITIONS, RELOCATION_JOURNAL]
            reason = "pointer/count reset normalized at runtime"
            if consumer_named and not exact:
                gap_type = "consumer-family-parity-only" if parity else "consumer-without-parity"
                reason += "; named consumer lacks member-exact parity"
        elif name and name.endswith("_check"):
            cls = "blocked"
            gap_type = "validator-execution-unqualified"
            reason = "zero-byte schema check descriptor; validator callback execution not qualified on target"
        elif consumer_named:
            cls = "blocked"
            if exact:
                gap_type = "consumer-without-parity"
                reason = "named consumer has member-exact fixture but parity files are missing"
            elif parity:
                gap_type = "consumer-family-parity-only"
                reason = ("named consumer has family-level parity reports only; no member-exact "
                          "behavior fixture")
            else:
                gap_type = "consumer-without-parity"
                reason = "named consumer has no parity evidence beyond source inspection"
            consumer_sites = hits[:5]
        elif name is None:
            cls = "blocked"
            gap_type = "unclassified-dwarf-range"
            reason = "byte range without member name"
        elif not hits:
            cls = "preserved-opaque"
            reason = ""
        else:
            cls = "blocked"
            gap_type = "candidate-accesses-without-consumer-assignment"
            reason = (f"CE accesses to .{name} exist ({len(hits)} sites) but no member-specific "
                      "consumer is assigned")
            consumer_sites = hits[:5]

        if cls == "preserved-opaque":
            consumer_sites = []
            reason = (f"no CE consumer: 0 `.{name}`/`->{name}` accesses in {CE_SOURCE}"
                      if name else reason)
        elif consumer_named:
            consumer_sites = consumer_definition_sites(consumer_text, defs) + hits[:5]
        elif not consumer_sites:
            consumer_sites = hits[:5]

        if cls == "blocked" and not gap_type:
            gap_type = "other"

        consumer = consumer_text if consumer_named else None

        family = "runtime-normalized-values" if cls == "runtime-normalized" else structural_family(m)
        rows.append({
            "family": family,
            "structural_family": structural_family(m),
            "member": m["path"],
            "definition": m["definition"],
            "offset": m["offset_within_definition"],
            "size": m["size"],
            "inventory_classification": m["classification"],
            "c0_disposition": d["disposition"],
            "classification": cls,
            "consumer": consumer,
            "ce_access_sites": consumer_sites,
            "ce_access_count": len(hits),
            "parity_evidence": parity if cls in ("consumed", "blocked", "synthetic-covered") else [],
            "parity_rows": [],
            "parity_scope": ("member-exact" if exact else ("family-level" if parity else "none")),
            "normalization_evidence": normalization,
            "retail_nonempty": retail_nonempty,
            "needs_synthetic_fixture": needs_synthetic,
            "gap_type": gap_type,
            "gap_reason": reason,
        })

    resolve_ranges(rows, layout)
    inputs = {p: sha256(ROOT / p) for p in (INVENTORY, CROSSWALK, C0_DISPOSITIONS, EMPTY_FIELDS, GAP_EVIDENCE, RANGE_LAYOUT)}
    return rows, inputs


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for lo, hi in sorted(spans):
        if out and lo <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def range_cover(entry: dict, rows: list[dict]) -> tuple[list[str], list[str]]:
    """Numeric coverage of one unclassified range by ledger member rows.

    Returns (covering_row_members, problems). Problems are empty only when every overlapping live
    member has its own ledger row (same definition, extent contained in that row) and every byte of the
    range is covered by live members or declared pad/unused spans.
    """
    off, size = entry["schema_range"]["offset"], entry["schema_range"]["size"]
    lo_r, hi_r = off, off + size
    spans, live = [], []
    for c in entry.get("candidate_c_members", []):
        lo, hi = max(lo_r, c["offset"]), min(hi_r, c["offset"] + c["size"])
        if hi <= lo:
            continue
        spans.append((lo, hi))
        if not (RE_PAD.match(c["name"]) or RE_UNUSED.search(c["name"])):
            live.append((c["name"], c["offset"], c["offset"] + c["size"]))
    problems, covering = [], []
    for name, m_lo, m_hi in live:
        owner = next((r for r in rows if r["definition"] == entry["definition"]
                      and "<unclassified" not in r["member"]
                      and r["offset"] <= m_lo and m_hi <= r["offset"] + r["size"]), None)
        if owner is None:
            problems.append(f"live member {name} [{m_lo},{m_hi}) has no own ledger row")
        else:
            covering.append(owner["member"])
    merged = _merge(spans)
    cursor, gaps = lo_r, []
    for lo, hi in merged:
        if lo > cursor:
            gaps.append((cursor, lo))
        cursor = max(cursor, hi)
    if cursor < hi_r:
        gaps.append((cursor, hi_r))
    for g_lo, g_hi in gaps:
        problems.append(f"bytes [{g_lo},{g_hi}) covered by no CE member or declared pad/unused span")
    return sorted(set(covering)), problems


def resolve_ranges(rows: list[dict], layout: dict[str, dict]) -> None:
    """Reclassify unclassified ranges to covered-by-member-rows only when coverage is numerically complete."""
    for r in rows:
        if r["inventory_classification"] != "unclassified" or r["classification"] != "blocked":
            continue
        entry = layout.get(r["member"])
        if not entry or not entry.get("candidate_c_members"):
            continue
        covering, problems = range_cover(entry, rows)
        if not covering and not problems:
            continue
        if problems:
            r["gap_reason"] = (f"{r['gap_reason'].split(';')[0]}; not covered by member rows: "
                               + "; ".join(problems))
            continue
        r["classification"] = "covered-by-member-rows"
        r["gap_type"] = None
        r["covering_member_rows"] = covering
        r["gap_reason"] = ("every overlapping live CE member has its own ledger row and the bytes are "
                           "covered by those rows plus declared pad/unused spans: " + ", ".join(covering))


def summarize(rows: list[dict]) -> dict:
    return {
        "row_count": len(rows),
        "classification_counts": {c: sum(r["classification"] == c for r in rows) for c in CLASSES},
        "family_counts": dict(sorted(Counter(r["family"] for r in rows).items())),
        "gap_type_counts": dict(sorted(Counter(r["gap_type"] for r in rows if r["gap_type"]).items())),
        "blocked_gap_rows": sum(r["classification"] == "blocked" for r in rows),
        "needs_synthetic_fixture_rows": sum(r["needs_synthetic_fixture"] for r in rows),
    }


def check_rows(rows: list[dict]) -> list[str]:
    errors = []
    for r in rows:
        if r["classification"] not in CLASSES:
            errors.append(f"unclassified or unknown class: {r['member']} -> {r['classification']}")
        if r["classification"] == "blocked" and not r["gap_reason"]:
            errors.append(f"blocked row without gap_reason: {r['member']}")
        if r["classification"] == "consumed" and not r["parity_evidence"]:
            errors.append(f"consumed row without parity evidence: {r['member']}")
        if r["needs_synthetic_fixture"] and r["retail_nonempty"] is not False:
            errors.append(f"synthetic flag on retail-nonempty member: {r['member']}")
    families = {r["family"] for r in rows}
    for fam in C41_FAMILIES:
        if fam not in families:
            errors.append(f"C4.1 family has zero rows: {fam}")
    return errors


def write_markdown(payload: dict) -> str:
    s = payload["summary"]
    lines = [
        "# M4 C4 member ledger (2026-10-26)",
        "",
        "Generated by `tools/audit_c4_member_ledger.py --write` from the Step 7 member inventory, "
        "consumer crosswalk, C0 byte dispositions, empty-field census and gap consumer evidence. "
        "Machine-readable rows: [`m4-c4-member-ledger-2026-10-26.json`](m4-c4-member-ledger-2026-10-26.json).",
        "",
        "A gap stays a gap until another lane supplies evidence. Nothing here is relabelled to close one.",
        "",
        f"## Counts ({s['row_count']} members, one row each)",
        "",
        "| classification | rows |",
        "| --- | ---: |",
    ]
    for c in CLASSES:
        lines.append(f"| {c} | {s['classification_counts'][c]} |")
    lines += ["", "| family | rows |", "| --- | ---: |"]
    for fam, n in s["family_counts"].items():
        lines.append(f"| {fam} | {n} |")
    lines += ["", "| gap type | rows |", "| --- | ---: |"]
    for g, n in s["gap_type_counts"].items():
        lines.append(f"| {g} | {n} |")
    rows = payload["rows"]
    findings = [r for r in rows if r["gap_type"] == "parity-failed"]
    lines += ["", "## Findings", ""]
    if findings:
        lines.append("Parity lanes reported a failing test for these rows. The rows stay blocked.")
        lines.append("")
        for r in findings:
            lines.append(f"- `{r['member']}` ({r['gap_reason']})")
    else:
        lines.append("No parity-failed rows.")
    lines += ["", "## Remaining blocked rows by gap type", ""]
    blocked = [r for r in rows if r["classification"] == "blocked"]
    gap_types = sorted({r["gap_type"] or "none" for r in blocked})
    lines += ["| gap type | rows |", "| --- | ---: |"]
    for g in gap_types:
        lines.append(f"| {g} | {sum((r['gap_type'] or 'none') == g for r in blocked)} |")
    for g in gap_types:
        selected = [r for r in blocked if (r["gap_type"] or "none") == g]
        lines += ["", f"### {g}: {len(selected)}", ""]
        for r in selected:
            lines.append(f"- `{r['member']}` ({r['family']})")
    covered = [r for r in rows if r["classification"] == "covered-by-member-rows"]
    lines += ["", f"### covered-by-member-rows (not blocked): {len(covered)}", ""]
    for r in covered:
        lines.append(f"- `{r['member']}` covered by {', '.join(r['covering_member_rows'])}")
    lines += [""]
    lines += [
        "## Method and limits",
        "",
        "- `consumed` needs a named consumer and a member-exact parity fixture; family-level reports "
        "are recorded in `parity_evidence` but keep the member `blocked`.",
        "- Lane parity rows (`docs/reports/m4-c4-parity-*.json`): a pass with member-exact scope and an "
        "existing test mentioning the field reclassifies a family-only row to `consumed`; a blocked result adds "
        "its notes to the gap reason; a fail sets gap_type `parity-failed` and is listed under Findings.",
        "- `covered-by-member-rows` is assigned only when every overlapping live CE member has its own ledger row "
        "and the range bytes are covered numerically by those members plus declared pad/unused spans.",
        "- `preserved-opaque` is assigned only when CE source contains zero `.name`/`->name` accesses. "
        "The search is textual, so macros and indirect access are not resolved.",
        "- `retail_nonempty` is null for members the empty-field census does not audit (scalars, references).",
        "- Host and synthetic evidence is not PCSX2 or retail-EE qualification.",
        "",
        "## Inputs",
        "",
    ]
    for p, h in payload["inputs"].items():
        lines.append(f"- `{p}` SHA-256 `{h}`")
    lines.append("")
    return "\n".join(lines)


def load_parity_docs(parity_dir: Path) -> tuple[list[tuple[str, dict]], dict[str, str], list[str]]:
    """Read per-lane parity files. Malformed files are reported, never ignored."""
    docs, hashes, errors = [], {}, []
    for path in sorted(parity_dir.glob(PARITY_GLOB)):
        rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()
        hashes[rel] = sha256(path)
        try:
            doc = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"parity-evidence-invalid: {rel}: unreadable JSON ({exc})")
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("lane"), str) or not isinstance(doc.get("rows"), list):
            errors.append(f"parity-evidence-invalid: {rel}: expected object with lane and rows")
            continue
        docs.append((rel, doc))
    return docs, hashes, errors


def apply_parity(rows: list[dict], docs: list[tuple[str, dict]]) -> list[str]:
    """Apply lane parity rows. Returns checker errors ('parity-evidence-invalid' only).

    pass + member-exact + existing test that mentions the field: blocked family-only rows become consumed.
    blocked: recorded, notes appended to gap_reason, row stays blocked.
    fail: row becomes blocked with gap_type 'parity-failed' (a finding, not a checker error).
    """
    by_member = {r["member"]: r for r in rows}
    errors: list[str] = []
    fails: list[tuple[str, dict]] = []
    blocked_notes: dict[str, list[str]] = {}
    blocked_lanes: dict[str, list[str]] = {}
    pass_lanes: dict[str, set[str]] = {}
    for rel, doc in docs:
        for prow in doc["rows"]:
            if not isinstance(prow, dict):
                errors.append(f"parity-evidence-invalid: {rel}: non-object row")
                continue
            member = prow.get("member")
            test = prow.get("test") or ""
            result = prow.get("result")
            scope = prow.get("scope")
            tag = f"parity-evidence-invalid: {rel} lane={doc['lane']} member={member}"
            row = by_member.get(member)
            if row is None:
                errors.append(f"{tag}: unknown ledger member")
                continue
            record = {"lane": doc["lane"], "source": rel, "test": test,
                      "command": prow.get("command", ""), "result": result, "scope": scope,
                      "notes": prow.get("notes", "")}
            if result == "pass":
                # A pytest node id ("file.py::Class::test") names the file that must exist.
                test_file_part = test.split("::", 1)[0] if test else ""
                test_path = ROOT / test_file_part if test_file_part else None
                field = member_name(member)
                if test_path is None or not test_path.is_file():
                    errors.append(f"{tag}: pass without an existing test file ({test!r})")
                    continue
                # Identifier match where '_' separates words (pytest node names use underscores too).
                if field and not re.search(r"(?<![A-Za-z0-9])" + re.escape(field) + r"(?![A-Za-z0-9])",
                                           test_path.read_text(errors="replace")):
                    errors.append(f"{tag}: test file does not mention field {field!r}")
                    continue
                if scope != "member-exact":
                    errors.append(f"{tag}: pass with scope {scope!r}; only member-exact passes count")
                    continue
                row["parity_rows"].append(record)
                pass_lanes.setdefault(member, set()).add(doc["lane"])
                if row["classification"] == "blocked" and row["gap_type"] in PROMOTABLE_GAPS:
                    row["classification"] = "consumed"
                    row["parity_scope"] = "member-exact"
                    row["parity_evidence"] = sorted(set(row["parity_evidence"]) | {test})
                    row["gap_type"] = None
                    row["gap_reason"] = ""
                elif row["classification"] == "runtime-normalized" and \
                        row["gap_type"] == "consumer-family-parity-only":
                    row["classification"] = "consumed"
                    row["parity_scope"] = "member-exact"
                    row["parity_evidence"] = sorted(set(row["parity_evidence"]) | {test})
                    row["gap_type"] = None
                    row["gap_reason"] = ""
                elif row["classification"] == "synthetic-covered":
                    row["parity_scope"] = "member-exact"
                    row["parity_evidence"] = sorted(set(row["parity_evidence"]) | {test})
                    row["needs_synthetic_fixture"] = False
                    row["gap_type"] = None
                    row["gap_reason"] = (f"empty in all audited retail maps; member-exact synthetic nonempty "
                                         f"parity passes ({test})")
            elif result == "blocked":
                row["parity_rows"].append(record)
                blocked_lanes.setdefault(member, []).append(doc["lane"])
                blocked_notes.setdefault(member, []).append(
                    f"parity lane {doc['lane']} blocked: " + str(prow.get("notes") or "no notes given"))
            elif result == "fail":
                row["parity_rows"].append(record)
                fails.append((member, record))
            else:
                errors.append(f"{tag}: unknown result {result!r}")
    # A lane-reported blocked result keeps the row blocked, with the lane's reason; it wins over passes.
    for member, notes in blocked_notes.items():
        row = by_member[member]
        deferral = DEFERRALS.get(member)
        superseded = (
            deferral is not None
            and set(blocked_lanes[member]) == {deferral["deferring_lane"]}
            and deferral["owner_lane"] in pass_lanes.get(member, set())
        )
        if superseded and not any(f[0] == member for f in fails):
            test_files = sorted({r["test"] for r in row["parity_rows"]
                                 if r["lane"] == deferral["owner_lane"] and r["result"] == "pass"})
            row["classification"] = "consumed"
            row["gap_type"] = None
            row["parity_scope"] = "member-exact"
            row["parity_evidence"] = sorted(set(row["parity_evidence"]) | set(test_files))
            row["gap_reason"] = (f"superseded deferral: owner lane {deferral['owner_lane']} member-exact pass "
                                 f"({', '.join(test_files)}) supersedes {deferral['deferring_lane']} "
                                 f"deferral ({deferral['evidence']})")
            continue
        row["classification"] = "blocked"
        row["gap_type"] = "parity-blocked"
        row["gap_reason"] = "; ".join(notes)
    for member, record in fails:
        row = by_member[member]
        row["classification"] = "blocked"
        row["gap_type"] = "parity-failed"
        row["parity_evidence"] = [t for t in row["parity_evidence"] if t != record["test"]]
        row["parity_scope"] = "failed"
        row["gap_reason"] = (f"parity lane {record['lane']} reports fail ({record['test']}): "
                             + str(record.get("notes", "")))
    return errors


def load_range_docs(parity_dir: Path) -> tuple[list[tuple[str, dict]], dict[str, str], list[str]]:
    """Read range-disposition files; absent files are fine, malformed ones are checker errors."""
    docs, hashes, errors = [], {}, []
    for path in sorted(parity_dir.glob(RANGE_GLOB)):
        rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()
        hashes[rel] = sha256(path)
        try:
            doc = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"range-disposition-invalid: {rel}: unreadable JSON ({exc})")
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("rows"), list):
            errors.append(f"range-disposition-invalid: {rel}: expected object with rows")
            continue
        docs.append((rel, doc))
    return docs, hashes, errors


def apply_range_dispositions(rows: list[dict], docs: list[tuple[str, dict]]) -> list[str]:
    """Apply lane range dispositions to unclassified DWARF range rows.

    runtime-normalized / preserved-opaque (with evidence) set that classification.
    consumed -> blocked with gap_type consumed-pending-fixture (a passing member-exact parity row promotes it).
    schema-gap / blocked -> blocked with the stated reason.
    """
    by_member = {r["member"]: r for r in rows}
    errors: list[str] = []
    for rel, doc in docs:
        for drow in doc["rows"]:
            if not isinstance(drow, dict):
                errors.append(f"range-disposition-invalid: {rel}: non-object row")
                continue
            member = drow.get("ledger_member")
            disp = drow.get("disposition")
            evidence = drow.get("evidence")
            tag = f"range-disposition-invalid: {rel} ledger_member={member}"
            row = by_member.get(member)
            if row is None:
                errors.append(f"{tag}: unknown ledger member")
                continue
            if row["inventory_classification"] != "unclassified":
                errors.append(f"{tag}: not an unclassified DWARF range row")
                continue
            if disp not in RANGE_DISPOSITIONS:
                errors.append(f"{tag}: unknown disposition {disp!r}")
                continue
            if disp in ("runtime-normalized", "preserved-opaque") and not evidence:
                errors.append(f"{tag}: {disp} without evidence")
                continue
            live = drow.get("live_members") or []
            note = drow.get("notes") or ""
            prefix = f"range disposition from {rel}"
            row["range_source"] = rel
            row["range_live_members"] = live
            row["range_needs_fixture"] = bool(drow.get("needs_fixture", False))
            if disp in ("runtime-normalized", "preserved-opaque"):
                row["classification"] = disp
                row["gap_type"] = None
                row["gap_reason"] = f"{prefix}: {evidence}" + (f"; {note}" if note else "")
                row["consumer"] = None
                row["ce_access_sites"] = []
                row["normalization_evidence"] = [rel] if disp == "runtime-normalized" else []
            elif disp == "consumed":
                row["classification"] = "blocked"
                row["gap_type"] = "consumed-pending-fixture"
                row["gap_reason"] = (f"{prefix}: consumed per evidence {evidence or ''}; stays blocked until "
                                     "a member-exact passing parity row exists" + (f"; {note}" if note else ""))
            else:
                row["classification"] = "blocked"
                row["gap_type"] = "schema-gap" if disp == "schema-gap" else "range-blocked"
                row["gap_reason"] = (f"{prefix}: {disp}: {evidence or ''}" + (f"; {note}" if note else ""))
    return errors


def apply_corrections(rows: list[dict]) -> None:
    by_member = {r["member"]: r for r in rows}
    for member, fix in CORRECTIONS.items():
        row = by_member.get(member)
        if row is None:
            continue
        row["ce_access_sites"] = list(fix["ce_access_sites"])
        row["consumer"] = fix["consumer"]
        row["ce_correction"] = fix["note"]


def build_payload(parity_dir: Path = ROOT / PARITY_DIR) -> tuple[dict, list[str]]:
    rows, inputs = build_rows()
    apply_corrections(rows)
    range_docs, range_hashes, errors = load_range_docs(parity_dir)
    errors += apply_range_dispositions(rows, range_docs)
    inputs.update(range_hashes)
    docs, parity_hashes, perr = load_parity_docs(parity_dir)
    errors += perr
    errors += apply_parity(rows, docs)
    inputs.update(parity_hashes)
    errors += check_rows(rows)
    payload = {
        "format": FORMAT,
        "generated_by": "tools/audit_c4_member_ledger.py",
        "families_required": list(C41_FAMILIES),
        "extra_families": list(EXTRA_FAMILIES),
        "inputs": inputs,
        "summary": summarize(rows),
        "rows": rows,
    }
    return payload, errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true", help="regenerate the JSON and markdown ledger")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any parity-failed rows exist (findings are otherwise reported only)")
    args = ap.parse_args(argv)

    payload, errors = build_payload()
    failed = [r["member"] for r in payload["rows"] if r["gap_type"] == "parity-failed"]
    if args.strict and failed:
        errors.append(f"--strict: {len(failed)} parity-failed row(s): {', '.join(failed)}")
    if args.write:
        if errors:
            for e in errors:
                print("ERROR:", e, file=sys.stderr)
            return 1
        (ROOT / OUT_JSON).write_text(json.dumps(payload, indent=1, sort_keys=False) + "\n")
        (ROOT / OUT_MD).write_text(write_markdown(payload))
        print(json.dumps(payload["summary"], indent=1))
        return 0

    committed_path = ROOT / OUT_JSON
    if not committed_path.exists():
        errors.append(f"missing committed ledger {OUT_JSON}; run with --write")
    else:
        committed = json.loads(committed_path.read_text())
        if committed["inputs"] != payload["inputs"]:
            errors.append("input hashes differ from committed ledger; regenerate with --write")
        old = {(r["member"]): r["classification"] for r in committed["rows"]}
        new = {(r["member"]): r["classification"] for r in payload["rows"]}
        if old.keys() != new.keys():
            errors.append("member set differs from committed ledger; regenerate with --write")
        for k in old.keys() & new.keys():
            if old[k] != new[k]:
                errors.append(f"classification drift for {k}: {old[k]} -> {new[k]}")
        if committed["summary"]["classification_counts"] != payload["summary"]["classification_counts"]:
            errors.append("classification counts differ from committed ledger")
    for e in errors:
        print("FAIL:", e, file=sys.stderr)
    if errors:
        return 1
    print(json.dumps(payload["summary"]["classification_counts"]))
    print(f"ok: {payload['summary']['row_count']} members, all classified, all C4.1 families present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
