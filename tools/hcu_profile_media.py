#!/usr/bin/env python3
"""Profile only explicitly imported CE media tags and report independent chunk sizes."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2 import animconv, modelconv  # noqa: E402


CONSUMERS = {
    "mode": ("MODL", "submodules/halo-ps2/engine/src/world/model.c", "model_open"),
    "antr": ("ANIM", "submodules/halo-ps2/engine/src/world/anim.c", "anim_open"),
}
MEDIA_GROUPS = {"mode", "antr", "bitm", "snd!"}


def _source_hash(mapdata) -> str:
    h = hashlib.sha256()
    with mapdata.path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def media_json_summary(profile: dict) -> dict:
    """Return a JSON-safe inventory without embedding binary chunk payloads."""
    return {**profile, "chunks": [{k: v for k, v in chunk.items() if k != "data"}
                                   for chunk in profile["chunks"]]}


def _verify_consumer(kind: str) -> dict:
    _, relpath, function = CONSUMERS[kind]
    path = ROOT / relpath
    if not path.is_file() or function not in path.read_text(errors="replace"):
        raise ValueError(f"engine consumer {relpath}:{function} is absent")
    return {"path": relpath, "function": function, "source_sha256": _source_hash_file(path)}


def _source_hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_media(sources: dict, tags: list, *, conversion_cache=None, input_hashes=None,
                covered_out: dict | None = None, object_profile=None) -> dict:
    """Convert only `tags` entries shaped as source_key/group/path/source_datum.

    Unknown required groups fail closed: they need a real serialized format and
    engine consumer before they can enter an imported profile.
    """
    chunks_by_sha = {}
    bindings = []
    sound_metadata = {}
    covered_bitmaps = {}
    source_hashes = dict(input_hashes or {})
    conversions = conversion_cache if conversion_cache is not None else {}
    consumers = {}
    group_order = {"mode": 0, "antr": 1, "bitm": 2, "snd!": 3}
    for item in sorted(tags, key=lambda t: (t["source_key"], group_order.get(t["group"], 4),
                                           t["group"], int(t["source_datum"]))):
        group, source_key = item["group"], item["source_key"]
        if group not in MEDIA_GROUPS:
            continue
        if source_key not in sources:
            raise ValueError(f"missing media source {source_key!r}")
        datum = int(item["source_datum"])
        m = sources[source_key]
        entry = m.by_id.get(datum)
        if entry is None or entry.group != group:
            raise ValueError(f"missing {group} source datum {datum:#x} in {source_key}")
        if getattr(entry,'path',item['path']) != item['path']:
            raise ValueError('media datum/path identity mismatch')
        if group == "snd!":
            sound_metadata.setdefault(source_key, []).append({
                "datum": item["source_datum"], "path": item["path"],
                "playback": "identity/request metadata only; SPU2 raw sample playback is separate",
            })
            continue
        if group == "bitm":
            coverage = covered_bitmaps.get((source_key, datum))
            owner = {"source_key": source_key, "source_datum": datum,
                     "group": group, "path": item["path"]}
            if coverage is None:
                raise ValueError("bitmap has no model-generated OTEX binding/qualified consumer")
            chunk = chunks_by_sha[coverage]
            if owner not in chunk["owners"]:
                chunk["owners"].append(owner)
            bindings.append({"owner": owner, "kind": "OTEX", "chunk_key": coverage,
                             "covered_by_model": True})
            continue
        if group not in CONSUMERS:
            raise ValueError(f"no qualified media serializer/consumer for required group {group!r}")
        if source_key not in source_hashes: source_hashes[source_key] = _source_hash(m)
        source_sha = source_hashes[source_key]
        # object_profile None keeps the historical cache key and output; a profile is keyed by its name.
        cache_key=(source_sha,group,datum) if object_profile is None else (source_sha,group,datum,object_profile)
        if cache_key not in conversions:
            if group == "mode":
                result = modelconv.convert_map(m, [datum], object_profile=object_profile)
                data_by_kind = {"MODL": result.modl, "OTEX": result.otex}
                bitmap_ids=tuple(t.source_id for t in result.otex_result.textures)
            else:
                data_by_kind = {"ANIM": animconv.build_section(m.path, [datum])}
                bitmap_ids=()
            conversions[cache_key]=(data_by_kind,bitmap_ids)
        data_by_kind,bitmap_ids=conversions[cache_key]
        if group not in consumers: consumers[group] = _verify_consumer(group)
        consumer = consumers[group]
        for kind, data in data_by_kind.items():
            digest = hashlib.sha256(data).hexdigest()
            key = f"{kind}:{digest}"
            chunk = chunks_by_sha.setdefault(key, {
                "key": key, "bytes": len(data), "data": data, "kind": kind, "sha256": digest,
                "sources": [], "owners": [], "engine_consumer": consumer,
            })
            source = {"source_sha256": source_sha, "source_map": str(m.path)}
            if source not in chunk["sources"]:
                chunk["sources"].append(source)
            owner = {"source_key": source_key, "source_datum": datum,
                     "group": group, "path": item["path"]}
            if owner not in chunk["owners"]:
                chunk["owners"].append(owner)
            if kind == "OTEX" and group == "mode":
                for bitmap_id in bitmap_ids:
                    covered_bitmaps[(source_key, bitmap_id)] = key
            bindings.append({"owner": owner, "kind": kind, "chunk_key": key})
    chunks = sorted(chunks_by_sha.values(), key=lambda c: c["key"])
    if covered_out is not None:
        # Model-covered (source_key, bitmap datum) pairs; never part of the returned dict.
        covered_out.update({key: True for key in covered_bitmaps})
    return {
        "chunks": chunks,
        "bindings": sorted(bindings, key=lambda b: (b["owner"]["source_key"], b["owner"]["source_datum"], b["kind"])),
        "sound_metadata": {k: sorted(v, key=lambda r: (r["datum"], r["path"]))
                           for k, v in sorted(sound_metadata.items())},
        "memory": {
            "decoded_resident_ce_bytes": 0,
            "independently_addressable_converted_bytes": sum(c["bytes"] for c in chunks),
            "maximum_selected_transient_asset_requirement_bytes": max((c["bytes"] for c in chunks), default=0),
            "note": "Converted chunk sizes are independently addressable; they are not summed as concurrent runtime residency.",
        },
        "decisions": ["Only explicit mode/antr imports are converted.",
                      "Uncovered bitmap images are serialized as staged BITM/TEXS payloads; this does not qualify a live presentation consumer.",
                      "Sound records retain identities only; SPU2 raw sample playback is separate."],
    }
