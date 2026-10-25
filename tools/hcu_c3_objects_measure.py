#!/usr/bin/env python3
"""Measure the C3 object residency footprint of a profile package (read-only).

For every MODL entry of the package's mode group this prints the loaded bytes (the MODL section and the OTEX
section that the parent's residency pool copies, 64-byte aligned), the LOD count and the bytes of each LOD's
VU1 packets, the vertex format, and the texture bytes. It then totals a named needed set (the Slayer workload:
bipeds, weapons with first-person models, vehicles, sky) under the loader's current policy (every LOD, every
texture) and under the cheaper policies a loader could apply, and compares each total with the residency pool.

Usage:
  python3 -I tools/hcu_c3_objects_measure.py --package-dir build/m2-c2-r3-selected-packages/pkg/bloodgulch_mounted_gunner_4p4bot
  python3 -I tools/hcu_c3_objects_measure.py --package-dir <dir> --json build/c3/c3-6c/bloodgulch_entries.json

<dir> holds <row>.hcp and <row>.json. The HCP2 segments are reassembled and each chunk is read as written; this
tool does not verify hashes (the parent does, before it reads a byte).

Vertex format (MODL version 1, docs/11-model-section.md): one VU1 batch packet per <= 24 triangles, expanded
triangle lists, 3 vertices per triangle, 20 bytes per vertex (s16 x3 + palette slot, s16 s/t + slot + weight,
s8 normal), plus a 40-byte batch record and 16-byte aligned packet headers. There is no index buffer.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))  # halo2ps2.modelconv (MODL reader, the engine's twin)

HCP_HEADER = struct.Struct("<4s7I")
HCP_RECORD = struct.Struct("<8I32s32s")
OBJ_ALIGN = 64
BATCH_RECORD_BYTES = 40
POOL_BYTES_DEFAULT = 2071936  # the C3 objects residency pool (budget v5, user-approved 2026-10-25)
LOD_NAMES = ("lod0_super_high", "lod1", "lod2", "lod3", "lod4_super_low")

# The Slayer workload of the 4-player Blood Gulch row (bipeds, every weapon with its first-person model, the
# vehicles the scenario places, the sky). Tag paths as the package manifest spells them.
SLAYER_NEEDED = [
    "characters\\cyborg\\cyborg", "characters\\cyborg\\fp\\fp",
    "vehicles\\warthog\\warthog", "vehicles\\ghost\\ghost", "vehicles\\scorpion\\scorpion_mp\\scorpion_mp",
    "sky\\mp clear afternoon\\mp clear afternoon",
]
SLAYER_WEAPONS = ["assault rifle", "pistol", "shotgun", "sniper rifle", "needler", "plasma rifle", "plasma pistol",
                  "rocket launcher", "flamethrower", "frag grenade", "plasma grenade", "energy sword", "fuel rod gun"]
for _w in SLAYER_WEAPONS:
    SLAYER_NEEDED += [f"weapons\\{_w}\\{_w}", f"weapons\\{_w}\\fp\\fp"]


def read_chunks(hcp: bytes) -> dict[tuple[int, int], bytes]:
    """Media chunks (kind 2) of an HCP2 pack, keyed by chunk id, reassembled from their segments."""
    magic, version, _hs, _pid, count, dir_off, _rows, _total = HCP_HEADER.unpack_from(hcp, 0)
    if magic != b"HCP2" or version != 2:
        raise SystemExit("not an HCP2 pack")
    segs: dict[int, dict[int, bytes]] = defaultdict(dict)
    for i in range(count):
        kind, cid, off, size, _lo, _ls, index, _n, _sha, _whole = HCP_RECORD.unpack_from(hcp, dir_off + i * HCP_RECORD.size)
        if kind == 2:
            segs[cid][index] = hcp[off:off + size]
    return {cid: b"".join(parts[k] for k in sorted(parts)) for cid, parts in segs.items()}


def texs_sizes(blob: bytes) -> tuple[dict[int, int], list[int]]:
    """shader id -> texture index (binding table), and the bytes of each texture (CLUT + mip pixels)."""
    count = struct.unpack_from("<I", blob, 0x08)[0]
    nbind = struct.unpack_from("<I", blob, 0x0C)[0]
    toff, boff = struct.unpack_from("<II", blob, 0x10)
    binds = {}
    for i in range(nbind):
        sid, tix = struct.unpack_from("<IH", blob, boff + 32 * i)
        binds[sid] = tix
    sizes = []
    for i in range(count):
        base = toff + 32 * i
        pix = struct.unpack_from("<I", blob, base + 0x14)[0]
        entries = struct.unpack_from("<H", blob, base + 0x18)[0]
        sizes.append(pix + 4 * entries)
    return binds, sizes


def align(n: int) -> int:
    return (n + OBJ_ALIGN - 1) & ~(OBJ_ALIGN - 1)


def measure_entry(sec, binds: dict[int, int], tex_sizes: list[int]) -> dict:
    lod_parts = [set() for _ in range(5)]
    for pm in sec.perms:
        for lod, (first, count) in enumerate(pm["ranges"]):   # MODL order: index 0 = super high
            lod_parts[lod].update(range(first, first + count))

    def packets(lods) -> tuple[int, int, set[int]]:
        # Batch bytes (packet + batch record), part count and texture indices of the parts of these LODs.
        parts, batch_bytes, tex = set(), 0, set()
        for lod in lods:
            parts |= lod_parts[lod]
        for pt in parts:
            part = sec.parts[pt]
            for bi in range(part["first_batch"], part["first_batch"] + part["batch_count"]):
                batch_bytes += sec.batches[bi]["vif_qwords"] * 16 + BATCH_RECORD_BYTES
            tix = binds.get(part["shader_id"])
            if tix is not None and tix != 0xFFFF:
                tex.add(tix)
        return batch_bytes, len(parts), tex

    per_lod = []
    for lod in range(5):
        pk, nparts, _tex = packets([lod])
        per_lod.append({"name": LOD_NAMES[lod], "parts": nparts, "packet_bytes": pk})
    return {"per_lod": per_lod, "packets": packets, "tex_sizes": tex_sizes}


def scenario_bytes(info: dict, lods: list[int]) -> dict:
    pk, nparts, tex = info["packets"](lods)
    tex_bytes = sum(info["tex_sizes"][t] for t in tex if t < len(info["tex_sizes"]))
    return {"packet_bytes": pk, "texture_bytes": tex_bytes, "parts": nparts, "textures": len(tex)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package-dir", type=Path, required=True)
    ap.add_argument("--row", help="package row name (default: the directory name)")
    ap.add_argument("--pool-bytes", type=int, default=POOL_BYTES_DEFAULT)
    ap.add_argument("--json", type=Path, help="write per-entry and totals JSON here")
    args = ap.parse_args(argv)
    from halo2ps2 import modelconv as mc  # the MODL reader the engine's model_open is checked against

    row = args.row or args.package_dir.name
    manifest = json.loads((args.package_dir / f"{row}.json").read_text())
    chunks = read_chunks((args.package_dir / f"{row}.hcp").read_bytes())
    bindings = manifest["chunk_bindings"]
    models = sorted((b for b in bindings if b["kind"] == "MODL" and b["owner"]["group"] == "mode"),
                    key=lambda b: int(b["owner"]["output_datum"]))
    entries = []
    for b in models:
        path = b["owner"]["path"]
        datum = int(b["owner"]["output_datum"])
        modl = chunks[b["chunk_id"]]
        sec = mc.parse_section(modl)
        tex = [t for t in bindings if t["kind"] == "OTEX" and t["owner"]["path"] == path
               and t["owner"]["group"] == "mode" and int(t["owner"]["output_datum"]) == datum]
        otex = chunks[tex[0]["chunk_id"]] if tex else b""
        binds, tex_sizes = texs_sizes(otex) if otex else ({}, [])
        info = measure_entry(sec, binds, tex_sizes)
        all_lods = scenario_bytes(info, [0, 1, 2, 3, 4])
        packet_union = all_lods["packet_bytes"]
        entries.append({
            "path": path, "model_bytes": len(modl), "texture_bytes": len(otex),
            "loaded_bytes": align(len(modl)) + (align(len(otex)) if otex else 0),
            "lods": sum(1 for p in info["per_lod"] if p["parts"]),
            "per_lod": info["per_lod"], "packets_all_lods": packet_union,
            "table_bytes": len(modl) - len(sec.vif),
            "vertex_format": "expanded triangles, 20 B/vertex (V4-16 pos+slot, V4-16 uv+slot+weight, V4-8 normal), 60 B/triangle, no index buffer",
            "textures": len(tex_sizes), "parts": len(sec.parts), "batches": len(sec.batches), "perms": len(sec.perms),
            "nodes": len(sec.nodes),
            "scen_all": all_lods,
            "scen_no_lod0": scenario_bytes(info, [1, 2, 3, 4]),
            "scen_lod2_only": scenario_bytes(info, [2]),
            "_info": info,
        })

    needed = [e for e in entries if e["path"] in SLAYER_NEEDED]
    missing = [p for p in SLAYER_NEEDED if p not in {e["path"] for e in entries}]
    totals = {}
    for key in ("loaded_bytes", "model_bytes", "texture_bytes"):
        totals[f"all_{key}"] = sum(e[key] for e in entries)
    for scen in ("scen_all", "scen_no_lod0", "scen_lod2_only"):
        floor_tex = sum(e[scen]["texture_bytes"] for e in needed)
        floor_pk = sum(e[scen]["packet_bytes"] for e in needed)
        totals[f"needed_{scen}_packets"] = floor_pk
        totals[f"needed_{scen}_textures"] = floor_tex
        totals[f"needed_{scen}_total"] = floor_pk + floor_tex
    totals["needed_entries"] = len(needed)
    totals["needed_missing"] = missing
    totals["pool_bytes"] = args.pool_bytes
    totals["needed_loaded_bytes_all"] = sum(e["loaded_bytes"] for e in needed)
    totals["needed_fits_pool_all"] = totals["needed_loaded_bytes_all"] <= args.pool_bytes

    for e in entries:
        del e["_info"]
    print(f"{row}: {len(entries)} MODL entries, model {totals['all_model_bytes']} B, textures {totals['all_texture_bytes']} B,"
          f" loaded {totals['all_loaded_bytes']} B")
    print(f"{'bytes':>9} {'tex':>8} {'lod0':>7} {'lod1':>7} {'lod2':>7} {'lod3':>7} {'lod4':>7} {'tris':>5}  path")
    for e in sorted(entries, key=lambda e: -e["loaded_bytes"]):
        lod = [p["packet_bytes"] // 1024 for p in e["per_lod"]]
        print(f"{e['model_bytes']:>9} {e['texture_bytes']:>8} " + " ".join(f"{v:>6}K" for v in lod) + f"  {e['path']}")
    print(f"needed set ({len(needed)} of {len(SLAYER_NEEDED)} Slayer entries present; missing {missing})")
    for scen in ("scen_all", "scen_no_lod0", "scen_lod2_only"):
        print(f"  {scen:15s} packets {totals[f'needed_{scen}_packets']:>9} textures {totals[f'needed_{scen}_textures']:>9}"
              f" total {totals[f'needed_{scen}_total']:>9}  pool {args.pool_bytes}  fits={totals[f'needed_{scen}_total'] <= args.pool_bytes}")
    print(f"  loaded as today (all LODs, all textures, 64 B aligned): {totals['needed_loaded_bytes_all']} B"
          f" fits={totals['needed_fits_pool_all']}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"row": row, "entries": entries, "totals": totals}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
