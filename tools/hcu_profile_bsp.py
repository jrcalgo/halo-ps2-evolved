"""Rebind normalized CBSP tag identities to an imported profile CTAG image.

This module changes only schema-declared ``reference`` fields and ``tag_index``
slots. BSP-internal pointers and every other byte are preserved. It intentionally
fails when a referenced source occurrence was not retained by the profile.
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path
import sys

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
try:
    from . import cbsp
except ImportError:
    import cbsp


class ProfileBspError(ValueError):
    """The BSP cannot be safely rebound to the supplied profile."""


def _source_map_sha256(source_map) -> str:
    existing = getattr(source_map, "sha256", None) or getattr(source_map, "source_sha256", None)
    if existing is not None:
        if not isinstance(existing, str) or len(existing) != 64:
            raise ProfileBspError("source map has an invalid SHA-256 identity")
        return existing
    path = getattr(source_map, "path", None)
    if path is None:
        raise ProfileBspError("source map has no path for provenance hashing")
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    value = digest.hexdigest()
    try:
        source_map.sha256 = value
    except (AttributeError, TypeError):
        pass
    return value


def _bsp_dependencies(image: bytes, manifest: dict, source_map) -> list[dict]:
    """Enumerate only schema-typed tag references/indices in a normalized BSP."""
    group_decl = next((g for g in manifest.get("groups", ()) if g.get("group") == "sbsp"), None)
    if not group_decl or not group_decl.get("definition"):
        raise ProfileBspError("schema has no structure-BSP root definition")
    definitions = manifest.get("definitions", {})
    found: dict[tuple[str, str, int], dict] = {}
    visited = set()

    def target_for_datum(datum: int):
        entry = getattr(source_map, "by_id", {}).get(datum)
        if entry is None:
            entry = next((e for e in source_map.index.entries if e.tag_id == datum), None)
        if entry is None or not entry.group or not entry.path:
            raise ProfileBspError(f"BSP dependency datum {datum:#x} has no source tag tuple")
        return entry

    def add(entry, field_kind: str, source_value: int):
        key = (entry.group, entry.path, entry.tag_id)
        found[key] = {"group": entry.group, "path": entry.path,
                      "source_datum": entry.tag_id, "source_value": source_value,
                      "field_kind": field_kind}

    def walk(def_id, base, depth=0):
        if depth > 32:
            raise ProfileBspError("BSP schema nesting exceeds bound")
        definition = definitions.get(str(def_id))
        if not isinstance(definition, dict):
            raise ProfileBspError(f"missing BSP schema definition {def_id!r}")
        size = definition.get("size")
        if not isinstance(size, int) or size <= 0:
            raise ProfileBspError("invalid BSP schema structure size")
        _need(image, base, size, "BSP schema structure")
        key = (str(def_id), base)
        if key in visited:
            raise ProfileBspError("cyclic or aliased BSP schema structure")
        visited.add(key)
        for field in definition.get("fields", ()):
            kind, stride, count, offset = (field.get("kind"), field.get("size"),
                                           field.get("count"), field.get("offset"))
            if not all(isinstance(v, int) and v >= 0 for v in (stride, count, offset)):
                raise ProfileBspError("invalid schema field bounds")
            if offset > size or (count and stride > (size - offset) // count):
                raise ProfileBspError("schema field exceeds structure bounds")
            for i in range(count):
                pos = base + offset + i * stride
                if kind == "struct":
                    walk(field.get("definition"), pos, depth + 1)
                elif kind == "block":
                    if stride != 12:
                        raise ProfileBspError("invalid tag-block stride")
                    n, target = struct.unpack_from("<iI", image, pos)
                    if n < 0 or (field.get("maximum", 0) and n > field["maximum"]):
                        raise ProfileBspError("tag-block count exceeds schema bound")
                    nested = definitions.get(str(field.get("definition")), {})
                    nested_size = nested.get("size")
                    if not isinstance(nested_size, int) or nested_size <= 0:
                        raise ProfileBspError("invalid nested schema definition")
                    if n:
                        _need(image, target, n * nested_size, "tag-block data")
                        for j in range(n):
                            walk(field["definition"], target + j * nested_size, depth + 1)
                elif kind == "reference":
                    if stride != 16:
                        raise ProfileBspError("invalid tag-reference stride")
                    datum = struct.unpack_from("<I", image, pos + 12)[0]
                    if datum != 0xFFFFFFFF:
                        entry = target_for_datum(datum)
                        group = image[pos:pos + 4][::-1].decode("ascii", "strict")
                        if group != entry.group:
                            raise ProfileBspError("BSP reference group disagrees with source datum")
                        add(entry, "reference", datum)
                elif kind == "tag_index":
                    if stride not in (2, 4):
                        raise ProfileBspError("tag_index width must be 2 or 4")
                    value = int.from_bytes(image[pos:pos + stride], "little")
                    if value in (0xFFFF, 0xFFFFFFFF):
                        continue
                    index = value & 0xFFFF
                    choices = [entry for entry in source_map.index.entries
                               if entry.index == index and
                               (not field.get("groups") or entry.group in field["groups"])]
                    if len(choices) != 1:
                        raise ProfileBspError("BSP tag_index has no unique source tag tuple")
                    add(choices[0], "tag_index", value)
                elif kind in ("enum", "string", "reset", "check", "block_index"):
                    continue
                elif kind == "file_data":
                    if stride != 20:
                        raise ProfileBspError("invalid file_data descriptor stride")
                    byte_count = struct.unpack_from("<i", image, pos)[0]
                    if byte_count < 0:
                        raise ProfileBspError("negative BSP file_data length")
                    if byte_count:
                        raise ProfileBspError("file-backed BSP dependency needs a bound resource policy")
                elif kind == "data":
                    continue
                else:
                    raise ProfileBspError(f"unsupported BSP schema field kind {kind!r}")

    _need(image, 0, 24, "BSP header")
    if image[20:24] != b"psbs":
        raise ProfileBspError("bad structure-BSP signature")
    root = struct.unpack_from("<I", image, 0)[0]
    walk(group_decl["definition"], root)
    return [found[key] for key in sorted(found)]


def bsp_profile_inputs(source_map, schema_manifest: dict, *, source_key: str | None = None) -> list[dict]:
    """Compile every retail structure BSP in a map and enumerate its typed deps.

    Each returned descriptor owns one ``sbsp`` tag tuple and an encoded CBSP
    payload. ``tag_dependencies`` is the exact closure-root seed set for a
    profile importer; callers still run ``rebind_profile_bsp`` against the
    completed import result before packaging.
    """
    if schema_manifest.get("format") != "hcu-schema-manifest-v1":
        raise ProfileBspError("unsupported schema manifest")
    path = getattr(source_map, "path", None)
    header = getattr(source_map, "header", None)
    if path is None or header is None or not hasattr(source_map, "index"):
        raise ProfileBspError("source map must be an opened retail MapData")
    key = source_key or Path(path).stem
    try:
        ps2_tools = Path(__file__).resolve().parents[1] / "submodules/halo-ps2/tools"
        if str(ps2_tools) not in sys.path:
            sys.path.insert(0, str(ps2_tools))
        from halo2ps2 import bsp, mapinfo
        from .ctag_schema_walk import walk_structure_bsp
        from .convert_retail_bsp import make_tag_name_mapper
    except ImportError:
        from halo2ps2 import bsp, mapinfo
        from ctag_schema_walk import walk_structure_bsp
        from convert_retail_bsp import make_tag_name_mapper
    if mapinfo.read_header(Path(path)).engine != 5 or Path(path).stat().st_size != header.decompressed_size:
        raise ProfileBspError("source map must be a decompressed retail Xbox cache map")
    render_start = source_map.index.header.model_vertex_address - source_map.base
    render_end = (source_map.index.header.model_index_address - source_map.base +
                  source_map.index.index_region[1])
    if render_start < 0 or render_end < render_start or render_end > len(source_map.region):
        raise ProfileBspError("retail render-data interval leaves tag region")
    mapper = make_tag_name_mapper(source_map.region, source_map.base, ((render_start, render_end),))
    locations = bsp.locate(source_map.index, source_map.region, header.decompressed_size)
    source_hash = _source_map_sha256(source_map)
    descriptors = []
    with Path(path).open("rb") as stream:
        for loc in locations:
            entries = [e for e in source_map.index.entries
                       if e.group == "sbsp" and e.path == loc.path]
            if len(entries) != 1:
                raise ProfileBspError(f"BSP extent {loc.path!r} has no unique sbsp tag tuple")
            entry = entries[0]
            stream.seek(loc.file_offset)
            raw = stream.read(loc.size)
            if len(raw) != loc.size:
                raise ProfileBspError(f"truncated BSP extent for {loc.path}")
            try:
                walked = walk_structure_bsp(schema_manifest, raw, loc.address, mapper,
                                             file_data_policy="reject")
                payload = cbsp.encode(walked.image, walked.relocations, walked.tag_relocations,
                                      source_file_offset=loc.file_offset,
                                      source_file_size=loc.size)
            except (ValueError, struct.error) as error:
                raise ProfileBspError(f"cannot schema-normalize BSP {loc.path}: {error}") from error
            deps = _bsp_dependencies(walked.image, schema_manifest, source_map)
            descriptors.append({"source_key": key, "group": "sbsp", "path": loc.path,
                                "source_datum": entry.tag_id, "source_file_offset": loc.file_offset,
                                "source_file_size": loc.size, "source_xbox_base": loc.address,
                                "payload": payload, "cbsp_sha256": hashlib.sha256(payload).hexdigest(),
                                "source_map_sha256": source_hash,
                                "schema_elf_sha256": schema_manifest.get("elf_sha256"),
                                "tag_dependencies": [{**dep, "source_key": key} for dep in deps]})
    return descriptors


def _need(buf: bytes, off: int, size: int, what: str) -> None:
    if off < 0 or size < 0 or off > len(buf) or size > len(buf) - off:
        raise ProfileBspError(f"{what} leaves BSP image")


def _ctag_names(image: bytes) -> dict[int, tuple[str, str, int]]:
    if len(image) < 36 or struct.unpack_from("<I", image, 32)[0] != 0x74616773:
        raise ProfileBspError("import result has no valid CE tag image")
    table = struct.unpack_from("<I", image, 0)[0]
    count = struct.unpack_from("<I", image, 12)[0]
    if count == 0 or table > len(image) or count > (len(image) - table) // 32:
        raise ProfileBspError("imported CTAG tag table is out of bounds")
    result = {}
    for i in range(count):
        row = table + i * 32
        group = image[row:row + 4][::-1].decode("ascii", "strict")
        datum, name_at = struct.unpack_from("<II", image, row + 12)
        if name_at >= len(image):
            raise ProfileBspError("imported tag name pointer leaves CTAG image")
        end = image.find(b"\0", name_at, min(len(image), name_at + 256))
        if end < 0:
            raise ProfileBspError("imported tag name is not bounded")
        try:
            path = image[name_at:end].decode("ascii")
        except UnicodeDecodeError as error:
            raise ProfileBspError("imported tag path is not ASCII") from error
        if datum in result:
            raise ProfileBspError("duplicate output tag datum")
        result[datum] = (group, path, name_at)
    return result


def _source_entry(source_map, datum: int):
    entry = getattr(source_map, "by_id", {}).get(datum)
    if entry is None:
        entry = next((e for e in source_map.index.entries if e.tag_id == datum), None)
    if entry is None:
        raise ProfileBspError(f"BSP references missing source datum {datum:#x}")
    return entry


def _remap_for_source(import_result, source_key: str, entry):
    matches = [row for row in import_result.get("source_occurrence_remaps", ())
               if row.get("source_key") == source_key and row.get("group") == entry.group
               and row.get("path") == entry.path and row.get("source_datum") == entry.tag_id]
    if len(matches) != 1:
        raise ProfileBspError(
            f"profile does not retain BSP dependency {entry.group}:{entry.path} "
            f"(source key {source_key}, datum {entry.tag_id:#x})")
    return matches[0]


def _compact_name_offset(source_map, entry) -> int:
    """Match convert_retail_bsp's removal of the model vertex/index interval."""
    header = source_map.index.header
    base = source_map.base
    start = header.model_vertex_address - base
    end = header.model_index_address - base + source_map.index.index_region[1]
    raw = entry.path_address - base
    if raw < 0 or raw >= len(source_map.region) or not (0 <= start <= end <= len(source_map.region)):
        raise ProfileBspError("source tag-name address is outside bounded retail tag region")
    if start <= raw < end:
        raise ProfileBspError("source tag-name address lies in removed BSP render data")
    return raw - (end - start if raw >= end else 0)


def rebind_profile_bsp(payload: bytes, *, manifest: dict, import_result: dict,
                       source_map, source_key: str) -> dict:
    """Return deterministic CBSP bytes rebound to ``import_result``.

    ``manifest`` is the compiled CE schema manifest; ``source_map`` is the
    retail MapData used to normalize this BSP. The result contains output bytes,
    parsed tag tuple and SHA-256 bindings suitable for a profile manifest.
    """
    if manifest.get("format") != "hcu-schema-manifest-v1":
        raise ProfileBspError("unsupported schema manifest")
    if import_result.get("format") != "hcu-profile-image-v1":
        raise ProfileBspError("unsupported profile import result")
    imported_schema = import_result.get("manifest", {}).get("schema_elf_sha256")
    if imported_schema is not None and imported_schema != manifest.get("elf_sha256"):
        raise ProfileBspError("profile import and BSP schema ELF hashes disagree")
    try:
        decoded = cbsp.decode(payload, max_image_size=64 * 1024 * 1024)
    except (ValueError, struct.error) as error:
        raise ProfileBspError(f"invalid source CBSP: {error}") from error
    out_names = _ctag_names(import_result["image"])
    image = bytearray(decoded.image)
    group = next((g for g in manifest.get("groups", ()) if g.get("group") == "sbsp"), None)
    if not group or not group.get("definition"):
        raise ProfileBspError("schema has no structure-BSP root definition")
    _need(image, 0, 24, "structure-BSP header")
    if image[20:24] != b"psbs":
        raise ProfileBspError("bad structure-BSP signature")
    root = struct.unpack_from("<I", image, 0)[0]
    definitions = manifest.get("definitions", {})
    remapped = []
    visited = set()
    schema_tag_slots = set()

    def walk(def_id, base, depth=0):
        if depth > 32:
            raise ProfileBspError("BSP schema nesting exceeds bound")
        definition = definitions.get(str(def_id))
        if not isinstance(definition, dict):
            raise ProfileBspError(f"missing BSP schema definition {def_id!r}")
        size = definition.get("size")
        if not isinstance(size, int) or size <= 0:
            raise ProfileBspError("invalid BSP schema structure size")
        _need(image, base, size, "BSP schema structure")
        key = (str(def_id), base)
        if key in visited:
            raise ProfileBspError("cyclic or aliased BSP schema structure")
        visited.add(key)
        for f in definition.get("fields", ()):
            kind, stride, count, offset = f.get("kind"), f.get("size"), f.get("count"), f.get("offset")
            if not all(isinstance(v, int) and v >= 0 for v in (stride, count, offset)):
                raise ProfileBspError("invalid schema field bounds")
            if offset > size or (count and stride > (size - offset) // count):
                raise ProfileBspError("schema field exceeds structure bounds")
            for i in range(count):
                p = base + offset + i * stride
                if kind == "struct":
                    walk(f.get("definition"), p, depth + 1)
                elif kind == "block":
                    if stride != 12:
                        raise ProfileBspError("invalid tag-block stride")
                    n, target = struct.unpack_from("<iI", image, p)
                    if n < 0 or (f.get("maximum", 0) and n > f["maximum"]):
                        raise ProfileBspError("tag-block count exceeds schema bound")
                    nested = definitions.get(str(f.get("definition")), {})
                    nsize = nested.get("size")
                    if not isinstance(nsize, int) or nsize <= 0:
                        raise ProfileBspError("invalid nested schema definition")
                    if n:
                        _need(image, target, n * nsize, "tag-block data")
                        for j in range(n):
                            walk(f["definition"], target + j * nsize, depth + 1)
                elif kind == "reference":
                    if stride != 16:
                        raise ProfileBspError("invalid tag-reference stride")
                    group_code = image[p:p + 4][::-1].decode("ascii", "strict")
                    old_name = struct.unpack_from("<I", image, p + 4)[0]
                    datum = struct.unpack_from("<I", image, p + 12)[0]
                    if datum == 0xFFFFFFFF:
                        if old_name:
                            raise ProfileBspError("null tag datum has a nonnull name")
                        continue
                    schema_tag_slots.add(p + 4)
                    entry = _source_entry(source_map, datum)
                    if group_code != entry.group:
                        raise ProfileBspError(
                            f"typed reference group {group_code!r} disagrees with source tuple "
                            f"{entry.group!r}:{entry.path}")
                    expected_name = _compact_name_offset(source_map, entry)
                    if old_name != expected_name:
                        raise ProfileBspError("typed reference name offset disagrees with source tag tuple")
                    row = _remap_for_source(import_result, source_key, entry)
                    out_datum = row["output_datum"]
                    target = out_names.get(out_datum)
                    if target is None or target[:2] != (entry.group, entry.path):
                        raise ProfileBspError("imported output tag tuple disagrees with source alias")
                    struct.pack_into("<I", image, p + 4, target[2])
                    struct.pack_into("<I", image, p + 12, out_datum)
                    remapped.append({"field": p, "kind": "reference", "source_datum": datum,
                                     "output_datum": out_datum, "group": entry.group, "path": entry.path})
                elif kind == "tag_index":
                    if stride not in (2, 4):
                        raise ProfileBspError("tag_index width must be 2 or 4")
                    value = int.from_bytes(image[p:p + stride], "little")
                    if value in (0xFFFF, 0xFFFFFFFF):
                        continue
                    index = value & 0xFFFF
                    candidates = [e for e in source_map.index.entries if e.index == index and
                                  (not f.get("groups") or e.group in f["groups"])]
                    if len(candidates) != 1:
                        raise ProfileBspError("typed tag_index has no unique source tag tuple")
                    entry = candidates[0]
                    row = _remap_for_source(import_result, source_key, entry)
                    outdatum = row["output_datum"]
                    if stride == 2 and outdatum > 0xFFFF:
                        raise ProfileBspError("output datum does not fit typed 16-bit tag_index")
                    image[p:p + stride] = outdatum.to_bytes(stride, "little")
                    remapped.append({"field": p, "kind": "tag_index", "source_datum": entry.tag_id,
                                     "output_datum": outdatum, "group": entry.group, "path": entry.path})
                elif kind in ("enum", "string", "reset", "check", "block_index"):
                    pass
                elif kind in ("data", "file_data"):
                    if kind == "file_data":
                        raise ProfileBspError("file-backed BSP resources need a separate bound resource policy")
                else:
                    raise ProfileBspError(f"unsupported BSP schema field kind {kind!r}")

    _need(image, root, 1, "BSP root")
    walk(group["definition"], root)
    declared_tag_slots = {field for field, _target in decoded.tag_relocations}
    if declared_tag_slots != schema_tag_slots:
        raise ProfileBspError("CBSP tag-name relocation slots do not match schema references")
    new_payload = cbsp.encode(bytes(image), decoded.relocations,
                              tuple((field, struct.unpack_from("<I", image, field)[0])
                                    for field, _target in decoded.tag_relocations),
                              source_file_offset=decoded.source_file_offset,
                              source_file_size=decoded.source_file_size)
    return {"format": "hcu-profile-bsp-binding-v1", "payload": new_payload,
            "image": bytes(image), "tag_tuple": tuple(sorted((datum, *value) for datum, value in out_names.items())),
            "remaps": remapped, "source_cbsp_sha256": hashlib.sha256(payload).hexdigest(),
            "output_cbsp_sha256": hashlib.sha256(new_payload).hexdigest(),
            "ctag_image_sha256": hashlib.sha256(import_result["image"]).hexdigest(),
            "schema_elf_sha256": manifest.get("elf_sha256"),
            "source_map_sha256": getattr(source_map, "sha256", None)}
