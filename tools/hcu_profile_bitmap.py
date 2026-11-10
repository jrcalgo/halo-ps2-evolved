"""Deterministic per-image bitmap serialization for C1 profile inventory.

This produces validated TEXS chunks and provenance bindings. It does not claim
that HUD/effect/sprite consumers load these chunks at runtime.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HALO_TOOLS = ROOT / "submodules/halo-ps2/tools"
ENGINE = ROOT / "submodules/halo-ps2/engine"
import sys
if str(HALO_TOOLS) not in sys.path:
    sys.path.insert(0, str(HALO_TOOLS))
from halo2ps2 import bitmaps, texconv  # noqa: E402


class BitmapProfileError(ValueError):
    pass


OPTIONAL_FUELROD_REFLECTIONS = {
    r"vehicles\banshee\bitmaps\cubemap banshee",
    r"characters\grunt\bitmaps\reflection grunt diffuse",
}

# Retail flashlight gel: a 128x128 Y8 cube map whose face 0 (the first face, mip 0 at the start of the pixel
# data) is the bright ring pattern CE projects from the light (ligh.gel_map). The PS2 has no cube sampler, so face 0
# ships as an ordinary 2D texture for the parent's flashlight pool; the other five faces are unused by the spotlight.
FACE0_GEL_BITMAPS = {
    r"characters\cyborg\bitmaps\spotlight cyborg",
}


def _cube_face0(img):
    """A 2D view of cube face 0: same pixel offset, one face's mip chain, depth 1, type 2D."""
    import dataclasses
    face = bitmaps.level_size(img.format, img.width, img.height)
    return dataclasses.replace(img, type=bitmaps.TYPE_2D, depth=1, pixel_size=face, mip_count=0)


# These authored HUD strips are sampled at the weapon's native screen-space
# resolution. Preserve Xbox mip 0 for the two exact sniper angle-ticks assets;
# ordinary world/UI bitmap policy remains half-resolution and capped at 256.
SOURCE_RESOLUTION_HUD_BITMAPS = {
    r"weapons\sniper rifle\bitmaps\angle_ticks_mask",
    r"weapons\sniper rifle\bitmaps\angle_ticks",
    r"weapons\sniper rifle\bitmaps\angle_ticks2",
    # The zoom-selected full and split scope masks are authored at 512×256
    # and 256×256. Keep their mip 0 so the mask itself is not blurred by
    # package-time reduction (_convert_scope_mask packs them as PSMT4).
    r"ui\hud\bitmaps\sniper\sniper_scope_mask2",
    r"ui\hud\bitmaps\sniper\sniper_scope_mask_sm",
}

# The health/shield bar, ammo counters and motion sensor are drawn 1:1 on the
# 640-wide frame, so the half-resolution world policy shows them upscaled 2x.
# Keep Xbox mip 0 (all are power-of-two, 8..256) and drop the unused mip chain.
# The colour depth stays on the converter's automatic PSMT4/PSMT8 choice.
# The two HUD meter sheets (A8Y8: Y is the fill order, alpha the shape). Converted so the parent
# can build the meter's palette per draw; see texconv.convert_meter_rgba.
METER_HUD_BITMAPS = {
    r"ui\hud\bitmaps\combined\hud_unit_meters",
    r"ui\hud\bitmaps\combined\hud_ammo_meters",
}
NATIVE_RESOLUTION_HUD_BITMAPS = {
    r"ui\hud\bitmaps\combined\hud_unit_meters",
    r"ui\hud\bitmaps\combined\hud_unit_backgrounds",
    r"ui\hud\bitmaps\hud_health_base",
    r"ui\hud\bitmaps\combined\hud_ammo_meters",
    r"ui\hud\bitmaps\combined\hud_ammo_alphas",
    r"ui\hud\bitmaps\combined\hud_ammo_outlines",
    r"ui\hud\bitmaps\combined\hud_ammo_type_icons",
    r"ui\hud\bitmaps\combined\hud_counter_numbers",
    r"ui\hud\bitmaps\combined\hud_weapon_backgrounds",
    # Message icons: the weapon icon beside the pickup prompt and the other help-text glyphs.
    r"ui\hud\bitmaps\combined\hud_msg_icons",
    r"ui\hud\bitmaps\hud_msg_icons_sm",
    r"ui\hud\bitmaps\hud_sweeper",
    r"ui\hud\bitmaps\hud_sweeper_mask",
    r"ui\hud\bitmaps\hud_sensor_blip",
    r"ui\hud\bitmaps\hud_sensor_blip_custom",
    # Per-weapon reticles, their warning overlays and the sniper scope reticle. The
    # sniper crosshair strips stay on the default path: _sm has 4 px sides, below MIN_TEX.
    r"ui\hud\bitmaps\combined\hud_reticles",
    r"ui\hud\bitmaps\combined\hud_reticle_warnings",
    r"ui\hud\bitmaps\sniper\hud_reticles_scope",
}


def _source_sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''): digest.update(block)
    return digest.hexdigest()


# The zoom screen effect darkens the view by the mask's Y (retail: framebuffer * (1 - Y)), which is a black quad with alpha
# Y. Each mask is stored as that quad's texture: black texels whose GS alpha is Y, in 16 levels (PSMT4), so a 512x256 mask is
# a 64 KB chunk the HUD cache holds. The levels are the 16 most used Y values (the hole 0, the surround ~0.5, the ring 1.0
# are always among them); every other texel takes the nearest level, which only moves a few antialiased edge texels.
SCOPE_MASK_BITMAPS = {
    r"ui\hud\bitmaps\sniper\sniper_scope_mask2",
    r"ui\hud\bitmaps\sniper\sniper_scope_mask_sm",
    r"ui\hud\bitmaps\pistol\pistol_scope_mask",
    r"ui\hud\bitmaps\pistol\pistol_scope_mask split",
}


def scope_mask_levels(values, count=16):
    """The `count` Y values a mask keeps: the most used ones, always with the full-clear 0 and the full-dark 255."""
    freq = {}
    for v in values:
        freq[v] = freq.get(v, 0) + 1
    if len(freq) <= count:
        return sorted(freq)
    ranked = [v for v, _n in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))]
    keep = ranked[:count]
    for must in (0, 255):
        if must in freq and must not in keep:
            keep[-1 if keep[-1] not in (0, 255) else -2] = must
    return sorted(set(keep))


def _convert_scope_mask(m, img, source_id):
    """A8Y8 / AY8 scope mask -> PSMT4 texture of black texels with alpha Y (see SCOPE_MASK_BITMAPS)."""
    width, height, rgba = bitmaps.decode_level(img, m.pixels(img), 0)
    ys = [rgba[i] for i in range(0, len(rgba), 4)]
    levels = scope_mask_levels(ys)
    nearest = {y: min(range(len(levels)), key=lambda k: (abs(levels[k] - y), k)) for y in set(ys)}
    indices = bytes(nearest[y] for y in ys)
    clut = texconv.build_clut([(0, 0, 0, level) for level in levels], 16)
    black = bytearray(4 * len(ys))
    black[3::4] = bytes(levels[nearest[y]] for y in ys)
    return texconv.Ps2Texture(source_id, width, height, texconv.PSMT4, texconv.TF_BLEND, clut, 16,
        [texconv._pad16(texconv.pack_nibbles(indices))], texconv._average_rgba(bytes(black)), len(levels), 0.0)


def _engine_tex_reader():
    from hcu_profile_validate import _media_reader
    reader=_media_reader()
    return lambda data,size:reader(3,data,size)


def _schema_group(schema):
    if schema.get("format") != "hcu-schema-manifest-v1":
        raise BitmapProfileError("unsupported compiler schema manifest")
    groups = [g for g in schema.get("groups", []) if g.get("group") == "bitm"]
    if len(groups) != 1 or groups[0].get("definition") is None:
        raise BitmapProfileError("compiler schema has no bitmap_group definition")
    definitions = schema.get("definitions", {})
    return definitions[str(groups[0]["definition"])], definitions


def _field(definitions, definition_id, name, kind=None):
    definition = definitions[str(definition_id)]
    fields = [f for f in definition.get("fields", []) if f.get("name") == name]
    if len(fields) != 1 or (kind is not None and fields[0].get("kind") != kind):
        raise BitmapProfileError(f"compiler schema lacks unique {name} field")
    return fields[0]


def _block(image, base, field):
    off = base + int(field["offset"])
    if off < 0 or off > len(image) - 12:
        raise BitmapProfileError("bitmap tag block field outside source region")
    count, address = struct.unpack_from("<iI", image, off)
    if count < 0 or count > int(field.get("maximum", 0) or 65536):
        raise BitmapProfileError("bitmap tag block count outside compiler maximum")
    return count, address


def _sequence_metadata(mapdata, root_offset, schema, definitions):
    """Retain compiler-schema sequence and sprite metadata without dropping frames."""
    group = next(g for g in schema["groups"] if g.get("group") == "bitm")
    seq_field = _field(definitions, group["definition"], "sequences", "block")
    seq_id = seq_field["definition"]
    seq_def = definitions[str(seq_id)]
    sprite_field = _field(definitions, seq_id, "sprites", "block")
    count, addr = _block(mapdata.region, root_offset, seq_field)
    seq_at = addr - mapdata.base
    if count and (seq_at < 0 or count * int(seq_def["size"]) > len(mapdata.region) - seq_at):
        raise BitmapProfileError("sequence block outside source region")
    name_field = next((f for f in seq_def.get("fields", []) if f.get("name") == "name"), None)
    sprite_def = definitions[str(sprite_field["definition"])]
    bitmap_index_field = next((f for f in sprite_def.get("fields", [])
                               if f.get("kind") in ("tag_index", "block_index")), None)
    if name_field is None or bitmap_index_field is None:
        raise BitmapProfileError("compiler schema lacks sequence name or sprite bitmap index")
    sequences = []
    for i in range(count):
        at = seq_at + i * int(seq_def["size"])
        nstart = at + int(name_field["offset"])
        nsize = int(name_field["size"])
        raw_name = mapdata.region[nstart:nstart + nsize].split(b"\0", 1)[0]
        name = raw_name.decode("ascii", "strict")
        sprite_count, sprite_addr = _block(mapdata.region, at, sprite_field)
        sprites_at = sprite_addr - mapdata.base
        sprite_size = int(sprite_def["size"])
        if sprite_count and (sprites_at < 0 or sprite_count * sprite_size > len(mapdata.region) - sprites_at):
            raise BitmapProfileError("sprite frame block outside source region")
        frames = []
        for frame in range(sprite_count):
            so = sprites_at + frame * sprite_size
            bo = so + int(bitmap_index_field["offset"])
            width = int(bitmap_index_field["size"])
            if width not in (2, 4) or bo < 0 or bo + width > len(mapdata.region):
                raise BitmapProfileError("invalid compiler sprite bitmap index field")
            index = int.from_bytes(mapdata.region[bo:bo + width], "little", signed=(width == 2))
            frames.append({"frame_index": frame, "bitmap_index": index,
                           "compiler_record_hex": mapdata.region[so:so + sprite_size].hex()})
        sequences.append({"sequence_index": i, "name": name, "frames": frames,
                          "compiler_record_hex": mapdata.region[at:at + int(seq_def["size"])].hex()})
    return sequences


def serialize_bitmap(sources: dict, owner: dict, schema: dict, *,
                     allow_optional_fuelrod_reflection: bool = True,
                     source_sha256: str | None = None,
                     non2d_disposition: dict | None = None) -> dict:
    """Convert every 2D image of a bitmap tag into independent TEXS chunks.

    `owner` contains source_key/group/path/source_datum.  Unsupported 3D/cube
    records are returned as explicit dispositions; all are fatal except the
    exact documented optional fuel-rod reflection cube.
    """
    if owner.get("group") != "bitm":
        raise BitmapProfileError("owner is not a bitmap tag")
    source_key = str(owner["source_key"])
    if source_key not in sources:
        raise BitmapProfileError(f"missing bitmap source {source_key}")
    m = sources[source_key]
    datum = int(owner["source_datum"])
    entry = m.by_id.get(datum)
    if entry is None or entry.group != "bitm" or entry.path != owner["path"]:
        raise BitmapProfileError("bitmap source datum/path identity mismatch")
    schema_group, definitions = _schema_group(schema)
    root_offset = entry.data_address - m.base
    group_def_id = next(g["definition"] for g in schema["groups"] if g["group"] == "bitm")
    bitmap_field = _field(definitions, group_def_id, "bitmaps", "block")
    image_count, image_addr = _block(m.region, root_offset, bitmap_field)
    data_def = definitions[str(bitmap_field["definition"])]
    image_at = image_addr - m.base
    if image_count and (image_at < 0 or image_count * int(data_def["size"]) > len(m.region) - image_at):
        raise BitmapProfileError("bitmap_data array outside source region")
    images = bitmaps.parse_images(m.region, m.base, entry.data_address)
    if len(images) != image_count:
        raise BitmapProfileError("bitmap image inventory disagrees with compiler schema")
    sequences = _sequence_metadata(m, root_offset, schema, definitions)
    for sequence in sequences:
        for frame in sequence['frames']:
            if not 0<=frame['bitmap_index']<image_count:
                raise BitmapProfileError('sprite frame bitmap index leaves image array')
    source_sha = source_sha256 or _source_sha(m.path)
    reader = _engine_tex_reader()
    chunks, dispositions = [], []
    for img in images:
        identity = {"source_key": source_key, "source_sha256": source_sha,
                    "group": "bitm", "path": entry.path, "source_datum": datum,
                    "source_image_index": img.index}
        if (entry.path.casefold() in FACE0_GEL_BITMAPS and img.type == bitmaps.TYPE_CUBE and
                img.index == 0 and img.format_name == "y8"):
            img = _cube_face0(img)
        if not img.is_2d:
            exclusion=(non2d_disposition or {}).get(img.index)
            if exclusion is not None:
                if (exclusion.get('payload_disposition')!='exclude_from_current_ps2_visual_profile_under_explicit_feature_gate' or
                        not exclusion.get('feature_gate') or not exclusion.get('schema_consumers')):
                    raise BitmapProfileError('non-2D payload exclusion lacks a proven consumer disposition')
                raw=m.pixels(img)
                if len(raw)!=img.pixel_size: raise BitmapProfileError('non-2D raw pixel extent is truncated')
                dispositions.append({**identity,**exclusion,'type':img.type,'depth':img.depth,
                    'format':img.format_name,'width':img.width,'height':img.height,'mip_count':img.mip_count,
                    'source_pixel_offset':img.pixel_offset,'source_pixel_bytes':img.pixel_size,
                    'source_pixel_sha256':hashlib.sha256(raw).hexdigest(),
                    'disposition':'retained_ce_metadata_payload_has_no_enabled_consumer'})
                continue
            optional = (allow_optional_fuelrod_reflection and
                        entry.path.casefold() in OPTIONAL_FUELROD_REFLECTIONS and
                        img.type == bitmaps.TYPE_CUBE)
            cube_storage=None
            if optional:
                from hcu_profile_weapons import expected_cube_payload_bytes, validate_cube_record
                expected=expected_cube_payload_bytes(img)
                pixels=m.pixels(img)
                if img.pixel_size!=expected or len(pixels)!=expected:
                    raise BitmapProfileError('optional reflection cube has invalid payload extent')
                cube_storage=validate_cube_record(img)
                cube_storage['source_pixel_sha256']=hashlib.sha256(pixels).hexdigest()
            disposition = {**identity, 'cube_storage':cube_storage, "type": img.type, "depth": img.depth,
                           "format": img.format_name,
                           "disposition": "optional_reflection_omitted" if optional else "unsupported_required_image"}
            dispositions.append(disposition)
            if not optional:
                raise BitmapProfileError(f"unsupported required bitmap image {entry.path}[{img.index}] type={img.type}")
            continue
        try:
            path = entry.path.casefold()
            is_scope_mask = path in SCOPE_MASK_BITMAPS
            native_hud = path in NATIVE_RESOLUTION_HUD_BITMAPS
            preserve_source_resolution = path in SOURCE_RESOLUTION_HUD_BITMAPS or native_hud
            is_meter = path in METER_HUD_BITMAPS and img.format_name == "a8y8"
            texture = (_convert_scope_mask(m, img, datum) if is_scope_mask else
                       texconv.convert_meter_texture(m, img, datum) if is_meter else
                       texconv.convert_texture(m, img, datum, texconv.CLASS_BLEND,
                           preserve_source_resolution=preserve_source_resolution))
            if is_scope_mask:
                # The parent consumes mip 0 only. Omit converter-generated
                # lower levels so the native-resolution mask fits the measured
                # one-chunk staging and fixed C3 owner budgets.
                texture.mips = texture.mips[:1]
            elif native_hud:
                texture.mips = texture.mips[:1]
            payload = texconv.build_texs([texture], [])
        except (ValueError, IndexError, struct.error) as error:
            raise BitmapProfileError(f"bitmap image {entry.path}[{img.index}] decode failed: {error}") from error
        buffer = ctypes.create_string_buffer(payload)
        if not reader(buffer, len(payload)):
            raise BitmapProfileError("production engine tex_open rejected serialized bitmap")
        digest = hashlib.sha256(payload).hexdigest()
        chunks.append({"key": f"BITM:{digest}", "kind": "BITM", "bytes": len(payload),
                       "sha256": digest, "data": payload, "identity": identity,
                       "texture_source_id": datum, "width": texture.width,
                       "height": texture.height, "psm": texture.psm,
                       "image_format": img.format_name,
                       "source_pixel_offset":img.pixel_offset,"source_pixel_bytes":img.pixel_size,
                       "source_pixel_sha256":hashlib.sha256(m.pixels(img)).hexdigest()})
    if not chunks and not dispositions:
        raise BitmapProfileError("bitmap tag contains no images")
    return {"format": "hcu-bitmap-assets-v1", "source": source_key,
            "source_sha256": source_sha, "group": "bitm", "path": entry.path,
            "source_datum": datum, "sequences": sequences, "chunks": chunks,
            "dispositions": dispositions,
            "runtime_consumer": None,
            "decision": "serialized for independently addressable staging; not admitted to live UI/effect presentation"}


def serialize_bitmaps(sources: dict, owners: list[dict], schema: dict) -> list[dict]:
    """Serialize a deterministically ordered owner list, hashing each source once."""
    hashes = {}
    for owner in owners:
        source_key = str(owner["source_key"])
        if source_key not in hashes:
            if source_key not in sources:
                raise BitmapProfileError(f"missing bitmap source {source_key}")
            hashes[source_key] = _source_sha(sources[source_key].path)
    ordered = sorted(owners, key=lambda o: (str(o["source_key"]), str(o["group"]),
                                            str(o["path"]), int(o["source_datum"])))
    return [serialize_bitmap(sources, owner, schema, source_sha256=hashes[str(owner["source_key"])])
            for owner in ordered]

