#!/usr/bin/env python3
"""Per-class LOD and clustering search for the C3 object residency profile (host tool, read-only).

Each needed model of a profile package is converted from its retail source map under every candidate class plan
(a LOD plan = which stored geometry each engine LOD slot points at, plus a vertex clustering factor). The packet
bytes and texture bytes of the model are measured with the same accounting as NeededSetFitTest, and the detail of
a plan is the triangle count of the geometry the model shows at its nearest engine LOD (after clustering).

The search walks the object classes in priority order (first-person hands and weapons, bipeds, vehicles, world
weapons and equipment, sky, other). Each class takes the plan with the most detail that still lets every later class
fit at its cheapest plan under the budget. The budget is the C3 objects residency pool less 10 % headroom.

Usage:
  python3 -I tools/hcu_c3_object_classes.py --search            # print the candidate costs and the chosen table
  python3 -I tools/hcu_c3_object_classes.py --table             # print the table of modelconv.C3_OBJECT_PROFILE
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2 import modelconv as mc  # noqa: E402
from halo2ps2 import texconv  # noqa: E402

_spec = importlib.util.spec_from_file_location("hcu_c3_objects_measure", ROOT / "tools/hcu_c3_objects_measure.py")
measure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure)

MANIFEST = ROOT / "build/m2-c2-r3-selected-packages/pkg/bloodgulch_mounted_gunner_4p4bot/bloodgulch_mounted_gunner_4p4bot.json"
POOL_BYTES = 2071936  # C3 objects residency pool, budget v5 (was 1547648 under v4)
HEADROOM = 0.10


def budget_for(pool_bytes: int = POOL_BYTES, headroom: float = HEADROOM) -> int:
    """The largest total the needed set may take: the pool less the headroom."""
    return int(pool_bytes * (1 - headroom))


BUDGET = budget_for()
MAX_TEX = mc.C3_OBJECT_PROFILE.max_tex
MAX_LEVELS = mc.C3_OBJECT_PROFILE.max_levels
CLUSTERS = (0.0, 0.03, 0.08)
PRIORITY = mc.OBJECT_CLASSES  # fp, biped, vehicle, weapon, sky, other


def lod_plans() -> list[tuple[str, tuple[int, ...]]]:
    """Single stored LODs, and two-level plans (near LOD a, far LOD b) split after 1..4 engine slots."""
    plans = [(f"LOD{k}", (k,) * mc.MODEL_LODS) for k in range(mc.MODEL_LODS)]
    for a in range(mc.MODEL_LODS):
        for b in range(a + 1, mc.MODEL_LODS):
            for split in range(1, mc.MODEL_LODS):
                plans.append((f"LOD{a}x{split}/LOD{b}", (a,) * split + (b,) * (mc.MODEL_LODS - split)))
    return plans


def candidates() -> list[tuple[str, tuple[int, ...], float]]:
    return [(label, slots, c) for label, slots in lod_plans() for c in CLUSTERS]


def model_list(manifest: dict) -> list[dict]:
    """The Slayer needed models of the package: path, class, source key and source datum (manifest order)."""
    out = []
    for b in manifest["chunk_bindings"]:
        if b["kind"] == "MODL" and b["owner"]["group"] == "mode" and b["owner"]["path"] in measure.SLAYER_NEEDED:
            o = b["owner"]
            out.append({"path": o["path"], "class": mc.object_class(o["path"]), "key": o["source_key"],
                        "datum": int(o["source_datum"])})
    return out


def load_maps(manifest: dict) -> dict[str, texconv.MapData]:
    return {key: texconv.MapData.open(ROOT / row["path"]) for key, row in manifest["source_maps"].items()}


def model_cost(maps, model: dict, profile: mc.ObjectProfile) -> dict:
    """Packet bytes, texture bytes and near-LOD triangles of one model under `profile` (the convert_map accounting)."""
    r = mc.convert_map(maps[model["key"]], [model["datum"]], object_profile=profile)
    sec = mc.parse_section(r.modl)
    packets = sum(bt["vif_qwords"] * 16 + measure.BATCH_RECORD_BYTES for bt in sec.batches)
    textures = sum(measure.texs_sizes(r.otex)[1]) if r.otex else 0
    near = mc.bake_model(r.models[0]).triangles_lod0
    return {"packets": packets, "textures": textures, "bytes": packets + textures, "near": near}


def class_table(profile: mc.ObjectProfile, models: list[dict], maps) -> list[dict]:
    """One row per class present: the plan (LOD slots and cluster) of the class and the summed cost of its models."""
    rows: dict[str, dict] = {}
    for model in models:
        cls = model["class"]
        cost = model_cost(maps, model, profile)
        cl = profile.class_lod(model["path"])
        row = rows.setdefault(cls, {"class": cls, "slots": cl.slots, "cluster_fraction": cl.cluster_fraction,
                                    "models": 0, "packets": 0, "textures": 0, "bytes": 0, "near_triangles": 0})
        row["models"] += 1
        row["packets"] += cost["packets"]
        row["textures"] += cost["textures"]
        row["bytes"] += cost["bytes"]
        row["near_triangles"] += cost["near"]
    ordered = [rows[c] for c in PRIORITY if c in rows]
    return ordered


def choose(options: dict[str, list[tuple[int, int, int]]], budget: int = BUDGET) -> dict[str, tuple[int, int, int]]:
    """Priority greedy. `options[cls]` holds (bytes, detail, candidate index) for every candidate of the class.

    A class takes the candidate with the most detail (ties: fewer bytes) such that the bytes already chosen plus the
    cheapest candidate of every later class still fit the budget. Raises if even the cheapest plans do not fit."""
    order = [c for c in PRIORITY if c in options]
    cheapest = {c: min(o[0] for o in options[c]) for c in order}
    if sum(cheapest.values()) > budget:
        raise ValueError(f"cheapest plans need {sum(cheapest.values())} B, budget {budget} B")
    chosen: dict[str, tuple[int, int, int]] = {}
    spent = 0
    for i, c in enumerate(order):
        later = sum(cheapest[d] for d in order[i + 1:])
        feasible = [o for o in options[c] if spent + o[0] + later <= budget]
        best = max(feasible, key=lambda o: (o[1], -o[0]))
        chosen[c] = best
        spent += best[0]
    return chosen


def search(maps, models: list[dict]) -> tuple[dict, dict]:
    """Measure every candidate for every model and return (chosen per class, the measured table)."""
    cands = candidates()
    per_class: dict[str, dict[int, list[int]]] = {}
    for model in models:
        acc = per_class.setdefault(model["class"], {})
        for ci, (_label, slots, cluster) in enumerate(cands):
            prof = mc.ObjectProfile("c3-search", MAX_TEX, MAX_LEVELS, ((model["class"], mc.ClassLod(slots, cluster)),))
            cost = model_cost(maps, model, prof)
            tot = acc.setdefault(ci, [0, 0])
            tot[0] += cost["bytes"]
            tot[1] += cost["near"]
    options = {c: [(v[0], v[1], ci) for ci, v in acc.items()] for c, acc in per_class.items()}
    picked = choose(options)
    return {c: {"label": cands[ci][0], "slots": cands[ci][1], "cluster_fraction": cands[ci][2],
                "bytes": b, "near_triangles": d} for c, (b, d, ci) in picked.items()}, options


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--search", action="store_true", help="run the search over every candidate plan (slow)")
    ap.add_argument("--table", action="store_true", help="print the table of modelconv.C3_OBJECT_PROFILE")
    ap.add_argument("--json", type=Path, help="write the search result here")
    ap.add_argument("--v3", action="store_true", help="with --table: print modelconv.C3_OBJECT_PROFILE_V3 instead")
    args = ap.parse_args(argv)
    manifest = json.loads(MANIFEST.read_text())
    models = model_list(manifest)
    maps = load_maps(manifest)
    if args.table or not args.search:
        rows = class_table(mc.C3_OBJECT_PROFILE_V3 if args.v3 else mc.C3_OBJECT_PROFILE, models, maps)
        total = sum(r["bytes"] for r in rows)
        print(f"{'class':8} {'slots':>16} {'cluster':>8} {'models':>6} {'packets':>9} {'textures':>9} {'bytes':>9} {'near tris':>10}")
        for r in rows:
            print(f"{r['class']:8} {str(r['slots']):>16} {r['cluster_fraction']:8.3f} {r['models']:6d} {r['packets']:9d} "
                  f"{r['textures']:9d} {r['bytes']:9d} {r['near_triangles']:10d}")
        print(f"total {total} B, budget {BUDGET} B, headroom {100 * (1 - total / POOL_BYTES):.1f} % of the pool")
    if args.search:
        picked, options = search(maps, models)
        for c in PRIORITY:
            if c in picked:
                p = picked[c]
                print(f"{c:8} {p['label']:>18} cluster {p['cluster_fraction']:.3f} bytes {p['bytes']:9d} near tris {p['near_triangles']}")
        total = sum(p["bytes"] for p in picked.values())
        print(f"chosen total {total} B, budget {BUDGET} B")
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps({"budget": BUDGET, "chosen": picked,
                                             "options": {c: sorted(v) for c, v in options.items()}}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
