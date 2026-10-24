#!/usr/bin/env python3
"""Build compact HCM1 runtime tables from a finalized HCP and its manifest."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from hcu_bitmap_bindings import build as bitmap_bindings
from hcu_profile_validate import parse_package

HEADER = struct.Struct("<4sHHIIIIII")
BITMAP = struct.Struct("<IHHIII32sHH")
CBSP = struct.Struct("<III32s32s")
RANGE = struct.Struct("<III")

def _u(value, bits, what):
    value = int(value)
    if not 0 <= value < (1 << bits):
        raise ValueError(f"{what} outside u{bits}")
    return value

def build(manifest_path: Path, package_path: Path, *, cache_key_base: int = 0) -> bytes:
    manifest_path, package_path = Path(manifest_path), Path(package_path)
    m = json.loads(manifest_path.read_text())
    package = package_path.read_bytes()
    package_sha = hashlib.sha256(package).hexdigest()
    if m.get("format") != "hcu-built-profile-v1" or m.get("package_sha256") != package_sha:
        raise ValueError("manifest does not pin these final HCP bytes")
    pid = _u(m["profile"]["id"], 32, "profile id")
    parsed = parse_package(package, expected_package_sha256=package_sha, expected_profile_id=pid)
    bitmap = bitmap_bindings(manifest_path, package_path, cache_key_base=cache_key_base)["bindings"]
    b_rows = []
    for b in bitmap:
        b_rows.append(BITMAP.pack(_u(b["bitmap_output_datum"],32,"bitmap datum"),
            _u(b["bitmap_index"],16,"bitmap index"), _u(b["image_index"],16,"image index"),
            _u(b["chunk_id"],32,"bitmap chunk id"), _u(b["source_datum"],32,"source datum"), pid,
            bytes.fromhex(b["chunk_sha256"]), _u(b["cache_key"],16,"cache key"), 0))
    cb_rows=[]
    cb_bindings=[x for x in m.get("chunk_bindings",[]) if x.get("kind")=="CBSP"]
    roots=m.get("profile",{}).get("bsp_roots",[])
    if len(roots)!=len(cb_bindings): raise ValueError("CBSP root/chunk binding count is ambiguous")
    for root in roots:
        candidates=[b for b in cb_bindings if b.get("owner",{}).get("source_datum")==root.get("source_datum") and b.get("owner",{}).get("path")==root.get("path")]
        if len(candidates)!=1: raise ValueError("CBSP root has no unique final chunk binding")
        b=candidates[0]; chunk_id=_u(b["chunk_id"],32,"CBSP chunk id")
        payload=parsed["chunks"].get((2,chunk_id))
        if payload is None or hashlib.sha256(payload).hexdigest()!=b["sha256"]: raise ValueError("CBSP chunk is missing or not pinned")
        # `root.cbsp_sha256` pins the source-side normalized CBSP. The HCP
        # binding hash pins the rebased package payload, which has distinct
        # contents after tag-datum relocation. Validate each against its own
        # provenance instead of asserting those hashes are equal.
        if not root.get("cbsp_sha256") or len(root["cbsp_sha256"]) != 64:
            raise ValueError("CBSP root lacks its source payload hash")
        cb_rows.append(CBSP.pack(_u(root["source_file_offset"],32,"CBSP source offset"),
            _u(root["source_file_size"],32,"CBSP source size"),chunk_id,
            bytes.fromhex(root["source_map_sha256"]),bytes.fromhex(b["sha256"])))
    # Match sound extents to exactly one output tag datum, using the occurrence
    # remap's source identity and path. No row-order inference is permitted.
    occurrences=m.get("source_occurrence_remaps",[])
    ranges=[]
    profile_map = m.get("profile", {}).get("map")
    if not isinstance(profile_map, str) or profile_map not in m.get("source_maps", {}):
        raise ValueError("profile map has no exact source-map identity")
    profile_map_sha = m["source_maps"][profile_map]["sha256"]
    for r in m.get("resources",[]):
        if r.get("definition")!="sound_permutation" or r.get("field")!="samples": continue
        # The runtime mount can read raw source extents only from the map whose
        # identity is mounted. Other recipe/source sounds remain described by
        # sound_meta, with no raw sample playback gate in this table.
        if r.get("source") != profile_map:
            continue
        if r.get("source_sha256") != profile_map_sha:
            raise ValueError(f"sound resource {r.get('tag')} source identity differs from loaded map")
        # `sound_permutation` is the snd! leaf tag; lsnd with the same path is
        # a distinct parent and cannot own its sample extent.
        hits=[o for o in occurrences if o.get("source_key")==r.get("source") and
              o.get("path")==r.get("tag") and o.get("group")=="snd!"]
        if not hits:
            deps=[d for d in m.get("dependencies",[]) if d.get("source_key")==r.get("source") and d.get("path")==r.get("tag") and d.get("group")=="snd!"]
            hits=deps
        datums={_u(o["output_datum"],32,"resource output datum") for o in hits}
        if len(datums)!=1: raise ValueError(f"sound resource {r.get('tag')} has ambiguous output datum")
        ranges.append(RANGE.pack(datums.pop(),_u(r["source_offset"],32,"resource offset"),_u(r["bytes"],32,"resource size")))
    if pid==1 and len(ranges)!=75: raise ValueError(f"expected 75 UI sound ranges, found {len(ranges)}")
    # Bitmap rows must mirror the manifest's BITM chunk bindings and must never name a
    # consumer-excluded bitmap. The historical UI count (368) holds only when no pinned
    # consumer exclusions were applied to the profile.
    excluded_outputs={int(r["output_datum"]) for r in m.get("media",{}).get("consumer_exclusions",[])}
    if any(int(b["bitmap_output_datum"]) in excluded_outputs for b in bitmap):
        raise ValueError("HCM1 bitmap binding references a consumer-excluded bitmap")
    bitmap_chunk_bindings=[x for x in m.get("chunk_bindings",[]) if x.get("kind")=="BITM"]
    if len(bitmap)!=len(bitmap_chunk_bindings):
        raise ValueError(f"HCM1 bitmap rows {len(bitmap)} differ from manifest BITM bindings {len(bitmap_chunk_bindings)}")
    if pid==1 and "consumer_exclusions" not in m.get("media",{}) and len(bitmap)!=368:
        raise ValueError(f"expected 368 UI bitmap bindings, found {len(bitmap)}")
    if pid==1 and len(cb_rows)!=1: raise ValueError(f"expected one UI CBSP binding, found {len(cb_rows)}")
    total=HEADER.size+sum(map(len,b_rows+cb_rows+ranges))
    if total>0xffffffff: raise ValueError("metadata byte length exceeds wire field")
    out=bytearray(HEADER.pack(b"HCM1",1,HEADER.size,total,pid,len(b_rows),len(cb_rows),len(ranges),0))
    for row in b_rows+cb_rows+ranges: out.extend(row)
    return bytes(out)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",required=True,type=Path); p.add_argument("--package",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path); p.add_argument("--cache-key-base",type=int,default=0)
    a=p.parse_args(argv); data=build(a.manifest,a.package,cache_key_base=a.cache_key_base)
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_bytes(data)
    print(json.dumps({"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),"output":str(a.output)},sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
