#!/usr/bin/env python3
"""Generate the C3.objects table header from a profile package manifest.

The parent draws objects from MEDIA chunks (kind 2). This tool selects the MODL chunk of each object model
and its OTEX chunk from the package's chunk_bindings, and writes them with their expected logical SHA-256
into a header the EE build includes under HCU_C3_OBJECTS. The parent re-checks both hashes against the
mounted profile directory before it reads a byte.

Usage:
  python3 -I tools/hcu_c3_objects_table.py --package-json <row>.json --output build/c3/objects/gen/hcu_c3_objects_table.h
  python3 -I tools/hcu_c3_objects_table.py --package-json <row>.json --sky-from-scenario --output <dir>/hcu_c3_objects_table.h

--sky-from-scenario reads the sky reference of the package's own scenario map (manifest profile.map, verified against
its source_maps sha256). A map without a sky, or whose sky model is not a MODL, emits no HCU_C3_OBJECTS_SKY_INDEX, so
the sky pass stays disabled for that map.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))  # halo2ps2.skyconv (scenario sky reference)

# The synthetic publisher finds its entries by path; it is the only user of a path subset.
SYNTHETIC_PATHS = [
    "characters\\cyborg\\cyborg",
    "weapons\\assault rifle\\assault rifle",
    "weapons\\plasma grenade\\plasma grenade",
    "vehicles\\ghost\\ghost",
]


def select(manifest: dict, paths: list[str] | None = None) -> list[dict]:
    """Every MODL binding of the package (mode group), sorted by its output datum, or only `paths` when given.

    Resource ids are the low 16 bits of the output datum (the CE model index the snapshot publishes), so they
    must be unique; a collision is refused rather than resolved silently.
    """
    bindings = manifest["chunk_bindings"]
    models = [b for b in bindings if b["kind"] == "MODL" and b["owner"]["group"] == "mode"]
    if paths is not None:
        models = [b for b in models if b["owner"]["path"] in paths]
        missing = [p for p in paths if not any(b["owner"]["path"] == p for b in models)]
        if missing:
            raise SystemExit(f"no MODL binding for: {missing}")
    models.sort(key=lambda b: int(b["owner"]["output_datum"]))
    seen = {}
    rows = []
    for model in models:
        path = model["owner"]["path"]
        datum = int(model["owner"]["output_datum"])
        if (datum & 0xFFFF) in seen:
            raise SystemExit(f"{path}: resource id {datum & 0xFFFF} also used by {seen[datum & 0xFFFF]}")
        seen[datum & 0xFFFF] = path
        tex = [b for b in bindings if b["kind"] == "OTEX" and b["owner"]["path"] == path and b["owner"]["group"] == "mode"
               and int(b["owner"]["output_datum"]) == datum]
        if len(tex) > 1:
            raise SystemExit(f"{path}: expected at most one OTEX binding for datum {datum}, found {len(tex)}")
        rows.append({
            "path": path,
            "model_chunk": int(model["chunk_id"]),
            "model_sha256": model["sha256"],
            "texture_chunk": int(tex[0]["chunk_id"]) if tex else 0,
            "texture_sha256": tex[0]["sha256"] if tex else "00" * 32,
            "source_datum": datum,  # CE runtime tag datum (what the snapshot publishes)
            "tag_datum": int(model["owner"]["source_datum"]),  # CE tag id of the model (skyconv model_tag)
        })
    return rows


def c_bytes(hex_digest: str) -> str:
    raw = bytes.fromhex(hex_digest)
    if len(raw) != 32:
        raise SystemExit("sha256 must be 32 bytes")
    return "{" + ", ".join(f"0x{b:02x}" for b in raw) + "}"


def sky_index(rows: list[dict], sky_model_datum: int) -> int:
    """Table index of the scenario sky model (the MODL whose CE tag datum is the sky's model tag). The sky tag is
    read from the map with halo2ps2.skyconv.read_sky (model_tag); it is not in the package manifest. Refuses an
    absent or ambiguous sky so a wrong model is never drawn silently."""
    hits = [i for i, r in enumerate(rows) if r["tag_datum"] == sky_model_datum]
    if len(hits) != 1:
        raise SystemExit(f"sky model datum {sky_model_datum} matches {len(hits)} table entries, expected 1")
    return hits[0]


def scenario_sky_datum(manifest: dict, package_json: Path) -> int | None:
    """The CE model tag of the package's scenario sky, or None when the map has no sky.

    The map is the manifest's profile.map source; its file must match the manifest sha256 before it is read."""
    from halo2ps2 import skyconv  # noqa: E402  (imported here so tools without the submodule still run the rest)

    entry = manifest["source_maps"][manifest["profile"]["map"]]
    map_path = ROOT / entry["path"]
    if not map_path.is_file():
        raise SystemExit(f"scenario map missing: {entry['path']}")
    if hashlib.sha256(map_path.read_bytes()).hexdigest() != entry["sha256"]:
        raise SystemExit(f"scenario map sha256 mismatch: {entry['path']}")
    sky = skyconv.read_sky(map_path)
    if sky is None or not sky["model_tag"]:
        return None
    return int(sky["model_tag"])


def render(rows: list[dict], package_json: Path, sky: int | None = None) -> str:
    digest = hashlib.sha256(package_json.read_bytes()).hexdigest()
    lines = [
        "/* Generated by tools/hcu_c3_objects_table.py. Do not edit.",
        f" * source: {package_json.name} (sha256 {digest})",
        " */",
        "#ifndef HCU_C3_OBJECTS_TABLE_H",
        "#define HCU_C3_OBJECTS_TABLE_H",
        "",
        '#include "stream/hcu_render_objects.h"',
        "",
        f"#define HCU_C3_OBJECTS_TABLE_COUNT {len(rows)}u",
    ] + ([f"#define HCU_C3_OBJECTS_SKY_INDEX {sky}u"] if sky is not None else []) + [
        "static const hcu_render_objects_table_entry hcu_c3_objects_table[HCU_C3_OBJECTS_TABLE_COUNT] = {",
    ]
    for r in rows:
        path_c = r["path"].replace("\\", "\\\\")
        lines.append(
            f"\t{{ {r['model_chunk']}u, {r['texture_chunk']}u, {r['source_datum']}u,\n"
            f"\t  {c_bytes(r['model_sha256'])},\n"
            f"\t  {c_bytes(r['texture_sha256'])},\n"
            f"\t  \"{path_c}\" }},")
    lines += ["};", "", "#endif", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package-json", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--synthetic-paths", action="store_true", help="only the four synthetic publisher paths")
    ap.add_argument("--sky-model-datum", type=int, default=None,
                    help="CE tag datum of the scenario sky model (skyconv.read_sky model_tag); emits HCU_C3_OBJECTS_SKY_INDEX")
    ap.add_argument("--sky-from-scenario", action="store_true",
                    help="take the sky datum from the package's scenario map; a map without a sky emits no sky define")
    args = ap.parse_args(argv)
    if args.sky_model_datum is not None and args.sky_from_scenario:
        ap.error("--sky-model-datum and --sky-from-scenario are exclusive")
    manifest = json.loads(args.package_json.read_text())
    rows = select(manifest, SYNTHETIC_PATHS if args.synthetic_paths else None)
    datum = args.sky_model_datum
    if args.sky_from_scenario:
        datum = scenario_sky_datum(manifest, args.package_json)
    sky = sky_index(rows, datum) if datum is not None else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(rows, args.package_json, sky))
    print(f"entries {len(rows)} MODL {sum(1 for r in rows)} OTEX {sum(1 for r in rows if r['texture_chunk'])}")
    print(f"sky {'index ' + str(sky) if sky is not None else 'none (sky disabled)'}")
    print(f"wrote {args.output} ({len(rows)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
