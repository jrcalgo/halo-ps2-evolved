"""Explicit, pinned consumer exclusions for bitmap media in C1 profiles.

An exclusion row names a class of bitmap consumer references that has no live
PS2 consumer. A bitmap's media payload (BITM/TEXS image chunks) is dropped from a
profile only when every consumer reference to it in that profile matches some
row that applies to the profile's kind. CE tag metadata is never dropped.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

PROFILE_KINDS = ("ui", "bots", "survival")
MATCH_FIELDS = ("definition", "field", "owner_group", "role")
ROW_FIELDS = {"class", "reason", "profile_kinds", "match", "counts"}
DISPOSITION = "excluded_by_consumer_exclusion"
GUARD_REASON = "selected_or_model_covered_parent_material"
SELECTED_ROLES = frozenset({"ps2_model_otex_base_selected", "ps2_bsp_material_base_selected",
                            "ps2_bsp_lightmap_page_selected"})


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_row(row: object, index: int) -> dict:
    if not isinstance(row, dict) or set(row) != ROW_FIELDS:
        raise ValueError(f"consumer exclusion row {index} must have exactly {sorted(ROW_FIELDS)}")
    if not isinstance(row["class"], str) or not row["class"] or not isinstance(row["reason"], str):
        raise ValueError(f"consumer exclusion row {index} needs a class and reason")
    kinds = row["profile_kinds"]
    if not isinstance(kinds, list) or not kinds or any(k not in PROFILE_KINDS for k in kinds):
        raise ValueError(f"consumer exclusion row {index} has invalid profile_kinds")
    match = row["match"]
    if not isinstance(match, dict) or set(match) != set(MATCH_FIELDS):
        raise ValueError(f"consumer exclusion row {index} match must have exactly {list(MATCH_FIELDS)}")
    for key, value in match.items():
        if value is not None and not isinstance(value, str):
            raise ValueError(f"consumer exclusion row {index} match.{key} must be string or null")
    if not isinstance(row["counts"], dict):
        raise ValueError(f"consumer exclusion row {index} counts must be an object")
    return {"class": row["class"], "reason": row["reason"], "profile_kinds": sorted(set(kinds)),
            "match": {k: match[k] for k in MATCH_FIELDS}, "counts": row["counts"]}


def load_exclusions(path: Path) -> dict:
    """Return {'path','sha256','rows'} for a pinned exclusion file.

    The file is a JSON list of rows, or an object whose key
    `required_profile_exclusions` holds that list. Malformed rows fail closed.
    """
    path = Path(path)
    data = path.read_bytes()
    payload = json.loads(data)
    if isinstance(payload, dict):
        payload = payload.get("required_profile_exclusions")
    if not isinstance(payload, list):
        raise ValueError("consumer exclusions must be a list or contain required_profile_exclusions")
    rows = [_check_row(row, i) for i, row in enumerate(payload)]
    try:
        display = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        display = path.resolve().as_posix()
    return {"path": display, "sha256": _sha256_bytes(data), "rows": rows}


def applicable(rows: list[dict], profile_kind: str) -> list[dict]:
    return [row for row in rows if profile_kind in row["profile_kinds"]]


def reference_matches(row: dict, reference: dict, role: str) -> bool:
    """A null match field means any; otherwise the value must be equal."""
    values = {"definition": reference.get("definition"), "field": reference.get("field"),
              "owner_group": reference.get("owner_group"), "role": role}
    return all(row["match"][key] is None or row["match"][key] == values[key] for key in MATCH_FIELDS)


def reference_role(reference: dict) -> str:
    """Role of one consumer reference (the audit's classifier, applied to a single reference)."""
    return classify_role([reference])


def decide_references(references: list[dict], profile_kind: str, rows: list[dict]) -> dict:
    """Decide one bitmap from its references, matching each reference on its own role.

    keep=False (drop the MEDIA payload) only when every reference matches an applicable row.
    Any pixel-path reference, selected parent material, an undecided role, or zero references
    keeps the bitmap (fail closed). CE tag metadata is never affected by this decision.
    """
    if not references:
        return {"keep": True, "reason": "zero_references_fail_closed", "rows": [], "roles": []}
    applies = applicable(rows, profile_kind)
    roles, covering = [], []
    for reference in references:
        role = reference_role(reference)
        roles.append(role)
        if role in SELECTED_ROLES:
            return {"keep": True, "reason": "selected_parent_material", "rows": [], "roles": roles}
        if role.startswith("unknown") or role == "missing_owner_fail_closed":
            return {"keep": True, "reason": "undecided_role_fail_closed", "rows": [], "roles": roles}
        hits = [row for row in applies if reference_matches(row, reference, role)]
        if not hits:
            return {"keep": True, "reason": "pixel_path_reference_not_excluded", "rows": [], "roles": roles}
        covering.extend(hits)
    unique = {json.dumps(row, sort_keys=True): row for row in covering}
    return {"keep": False, "reason": "every_reference_excluded",
            "rows": [unique[key] for key in sorted(unique)], "roles": roles}


def decide(references: list[dict], role: str, profile_kind: str, rows: list[dict]) -> list[dict] | None:
    """Legacy whole-bitmap form: the applicable rows covering every reference, or None to keep."""
    if not references or role in SELECTED_ROLES or role.startswith("unknown") or role == "missing_owner_fail_closed":
        return None
    applies = applicable(rows, profile_kind)
    matched = []
    for reference in references:
        hits = [row for row in applies if reference_matches(row, reference, role)]
        if not hits:
            return None
        matched.extend(hits)
    unique = {json.dumps(row, sort_keys=True): row for row in matched}
    return [unique[key] for key in sorted(unique)]


def classify_role(owners: list[dict]) -> str:
    """Role classification shared with the consumer audit (imported, not copied)."""
    from audit_hcu_c1_bitmap_roles import classify_role as audit_classify_role
    return audit_classify_role([{"owner_group": o.get("owner_group"), "field": o.get("field"),
                                 "definition": o.get("definition"),
                                 "schema_kind": o.get("schema_kind")} for o in owners])


def typed_index_owners(image: bytes, schema: dict) -> dict[int, dict]:
    """Schema ownership of every typed tag_index byte offset in a CTAG image."""
    definitions = schema["definitions"]
    groups = {int.from_bytes(g["group"].encode("ascii"), "big"): g for g in schema["groups"]}
    table, _scenario, _checksum, count = struct.unpack_from("<4I", image)
    owners: dict[int, dict] = {}
    active = set()

    def walk(did, base, owner, path=()):
        identity = (str(did), base)
        if identity in active:
            raise ValueError("cycle while locating schema tag_index owner")
        active.add(identity)
        definition = definitions[str(did)]
        for field in definition["fields"]:
            name = field.get("name", "")
            fpath = path + ((name,) if name else ())
            at = base + field["offset"]
            if field["kind"] == "struct":
                for i in range(field["count"]):
                    walk(field["definition"], at + i * field["size"], owner, fpath)
            elif field["kind"] == "block":
                for i in range(field["count"]):
                    ptr = at + i * field["size"]
                    n, target = struct.unpack_from("<iI", image, ptr)
                    if n < 0 or n > 1_000_000:
                        raise ValueError("invalid count in schema block during owner join")
                    stride = definitions[str(field["definition"])]["size"]
                    if n and (target > len(image) or n * stride > len(image) - target):
                        raise ValueError("schema block outside imported tag image")
                    for j in range(n):
                        walk(field["definition"], target + j * stride, owner, fpath)
            elif field["kind"] == "tag_index":
                for i in range(field["count"]):
                    offset = at + i * field["size"]
                    target = int.from_bytes(image[offset:offset + field["size"]], "little")
                    if target not in (0xffff, (1 << (field["size"] * 8)) - 1):
                        owners[offset] = {"owner_output_datum": owner["datum"],
                            "owner_group": owner["group"], "owner_path": owner["path"],
                            "definition": definition["name"], "field": ".".join(fpath),
                            "field_offset": offset,
                            "typed_tag_index_target": target,
                            "schema_kind": "tag_index", "schema_field_size": field["size"]}
        active.remove(identity)

    for index in range(count):
        instance = table + index * 32
        group_value = struct.unpack_from("<I", image, instance)[0]
        group = "".join(chr(c) if 32 <= c < 127 else "?" for c in group_value.to_bytes(4, "big"))
        name_offset, root = struct.unpack_from("<II", image, instance + 16)
        end = image.find(b"\0", name_offset, min(len(image), name_offset + 256)) if name_offset else -1
        path = image[name_offset:end].decode("utf-8", "replace") if end >= 0 else ""
        declaration = groups.get(group_value)
        if root and declaration and declaration.get("definition") is not None:
            walk(declaration["definition"], root, {"datum": index, "group": group, "path": path})
    return owners


def typed_references(image: bytes, schema: dict, tag_index_remaps: list[dict]) -> dict[int, list[dict]]:
    """Typed tag_index bitmap references, joined to the manifest's own tag_index_remaps.

    A remap joins a schema owner when its field offset and width match and its target is a bitmap.
    Returns {bitmap output datum: [reference]}. Bitmap-owned tag_index fields are not references.
    """
    remaps = {int(r["field"]): r for r in tag_index_remaps if r.get("kind", "tag_index") == "tag_index"}
    joined: dict[int, list[dict]] = {}
    for field, owner in sorted(typed_index_owners(image, schema).items()):
        if owner["owner_group"] == "bitm":
            continue
        remap = remaps.get(field)
        if not remap or remap.get("width") != owner["schema_field_size"]:
            continue
        if not str(remap.get("target", "")).startswith("bitm:"):
            continue
        reference = dict(owner, bitmap_output_datum=int(remap["output_index"]),
                         bitmap_path=str(remap["target"]).removeprefix("bitm:"))
        joined.setdefault(int(remap["output_index"]), []).append(reference)
    return joined


_MODEL_READER = None
_MODEL_WRAPPER = r'''#include <stddef.h>
#include <stdint.h>
#include "world/model.h"
int hcu_model_pairs(const uint8_t *bytes,size_t size,uint32_t *out,size_t cap) {
 model_section s; uint32_t mi,perm,lod; size_t n=0;
 if(model_open(&s,bytes,size)!=MODEL_OK) return -1;
 for(mi=0;mi<s.model_count;mi++) {
  model_info m=model_get(&s,mi);
  for(perm=0;perm<m.permutation_count;perm++) for(lod=0;lod<MODEL_LODS;lod++) {
   model_part_range r=model_parts(&s,&m,perm,lod); uint32_t i;
   for(i=0;i<r.part_count;i++) {
    model_part p=model_get_part(&s,(uint32_t)r.first_part+i);
    size_t j; int found=0;
    for(j=0;j<n;j++) if(out[2*j]==m.tag_id && out[2*j+1]==p.shader_id) {found=1;break;}
    if(!found) { if(n>=cap) return -2; out[2*n]=m.tag_id; out[2*n+1]=p.shader_id; n++; }
   }
  }
 }
 return (int)n;
}
'''


def model_reader():
    """The production MODL reader (world/model.c) compiled once into the audit cache."""
    global _MODEL_READER
    if _MODEL_READER is not None:
        return _MODEL_READER
    import ctypes
    import subprocess
    engine = ROOT / "submodules/halo-ps2/engine"
    source = engine / "src/world/model.c"
    key = _sha256_bytes(_MODEL_WRAPPER.encode() + source.read_bytes())
    cache = ROOT / "build/hcu-c1-bitmap-role-audit"
    cache.mkdir(parents=True, exist_ok=True)
    wrapper = cache / f"model-{key}.c"
    library = cache / f"model-{key}.so"
    if not library.exists():
        wrapper.write_text(_MODEL_WRAPPER)
        subprocess.run(["cc", "-shared", "-fPIC", "-std=c11", "-I", str(engine / "src"),
                        str(wrapper), str(source), "-o", str(library)], check=True,
                       capture_output=True, text=True)
    lib = ctypes.CDLL(str(library))
    lib.hcu_model_pairs.argtypes = (ctypes.c_void_p, ctypes.c_size_t,
                                    ctypes.POINTER(ctypes.c_uint32), ctypes.c_size_t)
    lib.hcu_model_pairs.restype = ctypes.c_int
    _MODEL_READER = lib
    return lib


def selected_model_bitmaps(modl_chunks: list[tuple[str, bytes]], bindings: list[dict], map_for) -> set:
    """(source_key, datum) bitmaps that MODL shaders select through the production model reader.

    modl_chunks: [(chunk_key, MODL bytes)]; bindings: MODL bindings (owner, kind, chunk_key).
    Each MODL owner's parts resolve through objtex.resolve_object_shader to a base bitmap.
    """
    import ctypes
    from halo2ps2 import objtex
    reader = model_reader()
    selected: set = set()
    for chunk_key, blob in modl_chunks:
        owners = [b.get("owner", {}) for b in bindings if b.get("chunk_key") == chunk_key and b.get("kind") == "MODL"]
        if not owners:
            raise ValueError(f"MODL chunk lacks source owner: {chunk_key}")
        output = (ctypes.c_uint32 * (1 << 16))()
        count = reader.hcu_model_pairs(blob, len(blob), output, 1 << 15)
        if count < 0:
            raise ValueError(f"production MODL reader rejected {chunk_key}")
        for owner in owners:
            m = map_for(owner["source_key"])
            model_ids = {int(output[2 * i]) for i in range(count)}
            if int(owner["source_datum"]) not in model_ids:
                raise ValueError(f"MODL owner tag not in parsed section: {owner}")
            for i in range(count):
                model_id, shader_id = int(output[2 * i]), int(output[2 * i + 1])
                if model_id != int(owner["source_datum"]):
                    continue
                shader = objtex.resolve_object_shader(m, shader_id)
                if shader.bitmap_id is not None:
                    selected.add((owner["source_key"], int(shader.bitmap_id)))
    return selected


def selected_bsp_bitmaps(descriptors: list[tuple[str, int]], map_for) -> tuple[set, set, list[dict]]:
    """Bitmaps that the pinned source BSPs select through their shaders and lightmap pages.

    descriptors: [(source_key, source_file_offset)] for each selected SBSP. map_for(source_key)
    returns the source map. Returns (selected bitmap tags {(source_key, datum)},
    selected lightmap pages {(source_key, datum, page)}, per-BSP evidence). This is parent-reader
    evidence, so the builder and the audit both keep these bitmaps.
    """
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
    from halo2ps2 import bsp, texconv
    selected: set = set()
    lightmaps: set = set()
    evidence = []
    for source_key, source_file_offset in descriptors:
        m = map_for(source_key)
        locations = bsp.locate(m.index, m.region, m.header.decompressed_size)
        loc = next((loc for loc in locations if loc.file_offset == source_file_offset), None)
        if loc is None:
            raise ValueError(f"BSP file extent not found in pinned source: {source_key}")
        with Path(m.path).open("rb") as stream:
            stream.seek(loc.file_offset)
            block = stream.read(loc.size)
        if len(block) != loc.size:
            raise ValueError(f"short selected BSP source extent: {source_key}")
        info = texconv.scan_bsp(locations.index(loc), loc, block)
        if info.lightmap_tag is not None:
            lightmaps.update((source_key, int(info.lightmap_tag), int(page)) for page in info.pages)
        rows = []
        for shader_id in sorted(info.shaders):
            shader = texconv.resolve_shader(m, shader_id)
            if shader.bitmap_id is None:
                continue
            selected.add((source_key, int(shader.bitmap_id)))
            entry = m.by_id.get(int(shader.bitmap_id))
            rows.append({"shader_id": shader_id, "shader_group": shader.group, "shader_path": shader.path,
                         "bitmap_source_datum": int(shader.bitmap_id),
                         "bitmap_path": entry.path if entry else None,
                         "material_count": int(info.shaders[shader_id])})
        evidence.append({"bsp_source_key": source_key, "source_file_offset": loc.file_offset,
                         "selected_material_shader_count": len(info.shaders),
                         "selected_2d_bitmap_references": rows,
                         "selected_lightmap_bitmap_source_datum": info.lightmap_tag,
                         "selected_lightmap_page_indices": sorted(info.pages)})
    return selected, lightmaps, evidence


def decide_profile(manifest: dict, policy: dict | None, *, ctag_image: bytes | None = None,
                   schema: dict | None = None, guard_tags=frozenset()) -> dict:
    """The single drop decision for a profile's bitmaps, shared by the builder and the audit.

    manifest needs 'dependencies' (bitm rows: source_key, source_datum, output_datum, path),
    'bitmap_consumers', and 'tag_index_remaps'. With ctag_image and schema, typed tag_index
    references are joined in. guard_tags are (source_key, source_datum) bitmaps that are
    selected or model-covered parent material and always kept.
    Returns {(source_key, source_datum): {keep, reason, rows, classes, roles, reference_count,
    output_datum, path}} for every bitm dependency.
    """
    refs_by_output: dict[int, list[dict]] = {}
    for row in manifest.get("bitmap_consumers", []):
        refs_by_output.setdefault(int(row["bitmap_output_datum"]), []).append(row)
    if ctag_image is not None:
        for output, typed in typed_references(ctag_image, schema, manifest.get("tag_index_remaps", [])).items():
            refs_by_output.setdefault(output, []).extend(typed)
    kind = policy["kind"] if policy else None
    rows = policy["rows"] if policy else []
    decisions = {}
    deps = sorted((d for d in manifest.get("dependencies", []) if d.get("group") == "bitm"),
                  key=lambda d: (d["source_key"], d["path"], int(d["source_datum"])))
    for dep in deps:
        key = (dep["source_key"], int(dep["source_datum"]))
        output = int(dep["output_datum"])
        refs = refs_by_output.get(output, [])
        if not policy:
            decision = {"keep": True, "reason": "no_policy", "rows": [], "roles": []}
        elif key in guard_tags:
            decision = {"keep": True, "reason": GUARD_REASON,
                        "rows": [], "roles": [reference_role(r) for r in refs]}
        else:
            decision = decide_references(refs, kind, rows)
        decisions[key] = {**decision, "output_datum": output, "path": dep["path"],
                          "reference_count": len(refs),
                          "classes": sorted({row["class"] for row in decision["rows"]})}
    return decisions
