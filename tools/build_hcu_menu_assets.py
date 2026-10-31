#!/usr/bin/env python3
"""Build the PS2 menu atlases from a user-owned Halo CE Xbox disc image."""

from __future__ import annotations

import argparse
import ctypes
import math
import struct
import sys
import tempfile
from ctypes import Structure, byref, c_bool, c_char_p, c_double, c_int, c_void_p
from pathlib import Path

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFilter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules" / "halo-ps2" / "tools"))
sys.path.insert(0, str(ROOT / "submodules" / "halo-64"))

from halo2ps2 import bitmaps, mapinfo, modelconv, texconv  # noqa: E402
from halo2ps2.tagindex import TagIndex  # noqa: E402
from tools.n64.xiso import XboxDisc  # noqa: E402


MAP_BITMAP = r"ui\shell\bitmaps\mp_map_grafix"
GAME_TYPE_BITMAP = r"ui\shell\bitmaps\game_type_grafix"
RING_INNER_BITMAP = r"scenery\halo\bitmaps\halo inner ring"
RING_OUTER_BITMAP = r"scenery\halo\bitmaps\halo outer ring"
LOGO_BITMAP = r"ui\shell\main_menu\halo_logo"
MULTIPLAYER_BITMAP = r"ui\shell\main_menu\menu_multiplayer"
SETTINGS_BITMAP = r"ui\shell\main_menu\menu_settings"
PLANET_BITMAP = r"sky\planets\threshold space"
SPACE_BITMAP = r"sky\sky_x10\bitmaps\space"
STARS_BITMAP = r"sky\space\bitmaps\stars"
# Keep this order in sync with MENU_GLYPH_* in src/stream/hcu_main_menu.c.
BUTTON_ICON_DIR = Path("/home/ai/Documents/Halo/ps2buttons")
GLYPH_CELL = 16
GLYPH_ATLAS = (256, 16)
GLYPH_SOURCES = (
    "Playstation-Button-X.svg",
    "Playstation-Button-C.svg",
    "Playstation-Button-S.svg",
    "Playstation-Button-T.svg",
    "Playstation-Button-Start.svg",
    "Playstation-Button-Select.svg",
    "Playstation-Button-L1.svg",
    "Playstation-Button-L2.svg",
    "Playstation-Button-R1.svg",
    "Playstation-Button-R2.svg",
    "Playstation-Button-L3.svg",
    "Playstation-Button-R3.svg",
    "Playstation-Dpad-Neutral.svg",
)
# Start and Select draw a tiny word under the button. At footer size that
# wordmark collapses into a black smear, so the caption band is left transparent.
GLYPH_CAPTION_KEEP = {
    "Playstation-Button-Start.svg": 17.5 / 24.0,
    "Playstation-Button-Select.svg": 17.5 / 24.0,
}


def rgb5a1(image: Image.Image) -> bytes:
    result = bytearray()
    for red, green, blue, alpha in image.convert("RGBA").getdata():
        word = (red >> 3) | ((green >> 3) << 5) | ((blue >> 3) << 10)
        word |= (1 if alpha >= 24 else 0) << 15
        result += struct.pack("<H", word)
    return bytes(result)


def decode_group(ui_map: Path, tag_path: str) -> list[Image.Image]:
    header = mapinfo.read_header(ui_map)
    index = TagIndex.read(ui_map)
    with ui_map.open("rb") as source:
        source.seek(header.tag_data_offset)
        region = source.read(header.tag_data_size)
    tag = next(entry for entry in index.entries if entry.group == "bitm" and entry.path == tag_path)
    reader = bitmaps.file_reader(ui_map)
    images = []
    for metadata in bitmaps.parse_images(region, index.base, tag.data_address):
        width, height, rgba = bitmaps.decode_level(metadata, bitmaps.read_pixels(metadata, reader))
        images.append(Image.frombytes("RGBA", (width, height), rgba))
    return images


def write_atlas(images: list[Image.Image], count: int, columns: int, rows: int,
                destination: Path, name: str) -> None:
    atlas = Image.new("RGBA", (columns * 128, rows * 64), (0, 0, 0, 0))
    for index, image in enumerate(images[:count]):
        tile = image.resize((128, 64), Image.Resampling.LANCZOS)
        atlas.alpha_composite(tile, ((index % columns) * 128, (index // columns) * 64))
    atlas.save(destination / f"{name}.png")
    (destination / f"{name}.rgb5a1").write_bytes(rgb5a1(atlas))


def write_ring_texture(image: Image.Image, destination: Path, name: str,
                       size: tuple[int, int]) -> None:
    """Preserve the retail material's aspect ratio in its GS texture."""
    texture = image.convert("RGBA").resize(size, Image.Resampling.LANCZOS)
    texture.save(destination / f"{name}.png")
    (destination / f"{name}.rgb5a1").write_bytes(rgb5a1(texture))


def write_space_texture(image: Image.Image, destination: Path, name: str,
                        stars: bool = False) -> None:
    """Convert CE's tiling space/star bitmap to a compact menu texture."""
    source = image.convert("RGBA").resize((128, 128), Image.Resampling.LANCZOS)
    if stars:
        # The retail star bitmap is stored over opaque black. Make its dark
        # field transparent so the CE nebula bitmap remains visible beneath it.
        gray = source.convert("L")
        source.putalpha(gray.point(lambda value: 255 if value >= 28 else 0))
    source.save(destination / f"{name}.png")
    (destination / f"{name}.rgb5a1").write_bytes(rgb5a1(source))


def write_loading_backplate(destination: Path) -> None:
    """Reconstruct CE's tinted-glass Halo loading image for the PS2 renderer.

    The supplied Xbox XISO has no loose loading.tga. The moving blue progress
    flash is rendered at runtime; this static art is deliberately separate
    from the menu planet, star field, and material textures.
    """
    scale = 2
    width, height = 512 * scale, 448 * scale
    canvas = Image.new("RGBA", (width, height), (1, 3, 9, 255))
    pixels = canvas.load()
    for y in range(height):
        for x in range(width):
            dx = (x - width * 0.5) / width
            dy = (y - height * 0.48) / height
            lift = max(0.0, 1.0 - (dx * dx * 5.5 + dy * dy * 8.0))
            value = int(3 + lift * 8)
            pixels[x, y] = (value, value + 2, value + 7, 255)

    box = (24 * scale, 126 * scale, 488 * scale, 350 * scale)
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(box, outline=(115, 157, 194, 92), width=20 * scale)
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(15 * scale)))

    far = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    fd = ImageDraw.Draw(far)
    fd.arc(box, 180, 360, fill=(75, 104, 132, 145), width=9 * scale)
    fd.arc((38 * scale, 137 * scale, 474 * scale, 339 * scale), 180, 360,
           fill=(35, 54, 76, 185), width=4 * scale)
    canvas.alpha_composite(far)

    near = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    nd = ImageDraw.Draw(near)
    nd.arc(box, 0, 180, fill=(128, 160, 186, 205), width=10 * scale)
    nd.arc((38 * scale, 137 * scale, 474 * scale, 339 * scale), 0, 180,
           fill=(61, 83, 105, 225), width=4 * scale)
    nd.arc((49 * scale, 143 * scale, 463 * scale, 333 * scale), 0, 180,
           fill=(24, 38, 55, 235), width=3 * scale)
    for i in range(17):
        x = (66 + i * 23) * scale
        y = (263 + int(23 * (1.0 - abs(x / scale - 256) / 210))) * scale
        nd.line((x, y, x, y + 8 * scale), fill=(89, 112, 132, 165), width=scale)
    canvas.alpha_composite(near)

    label = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ld = ImageDraw.Draw(label)
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11 * scale)
    except OSError:
        from PIL import ImageFont
        font = ImageFont.load_default()
    text = "LOADING"
    bounds = ld.textbbox((0, 0), text, font=font)
    ld.text(((width - (bounds[2] - bounds[0])) // 2, 390 * scale), text,
            font=font, fill=(122, 153, 177, 165))
    canvas.alpha_composite(label)
    canvas = canvas.convert("RGB").resize((512, 448), Image.Resampling.LANCZOS)
    canvas.save(destination / "halo_ce_loading_backplate.png")
    (destination / "loading.rgb5a1").write_bytes(rgb5a1(canvas.convert("RGBA")))


def write_title_art(ui_map: Path, destination: Path) -> None:
    logo_source = decode_group(ui_map, LOGO_BITMAP)[0]
    content = logo_source.getbbox()
    if not content:
        raise ValueError("retail logo bitmap is empty")
    logo = logo_source.crop((0, 0, content[2], logo_source.height)).resize(
        (512, 128), Image.Resampling.LANCZOS)
    logo.save(destination / "halo_ce_logo.png")
    (destination / "halo_ce_logo.rgb5a1").write_bytes(rgb5a1(logo))

    buttons = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    # Even rows are the bright highlight. The following row is the dim idle plate.
    slots = (
        (0, MULTIPLAYER_BITMAP, 1),
        (1, MULTIPLAYER_BITMAP, 0),
        (2, SETTINGS_BITMAP, 1),
        (3, SETTINGS_BITMAP, 0),
    )
    decoded = {}
    for row, path, index in slots:
        if path not in decoded:
            decoded[path] = decode_group(ui_map, path)
        buttons.alpha_composite(decoded[path][index], (0, row * 64))
    buttons.save(destination / "halo_ce_buttons.png")
    (destination / "halo_ce_buttons.rgb5a1").write_bytes(rgb5a1(buttons))

    source = decode_group(ui_map, PLANET_BITMAP)[0].convert("RGBA")
    planet = source.resize((256, 256), Image.Resampling.LANCZOS)
    pixels = planet.load()
    for y in range(256):
        for x in range(256):
            dx, dy = x - 128, y - 128
            radius = (dx * dx + dy * dy) ** 0.5
            red, green, blue, alpha = pixels[x, y]
            pixels[x, y] = red, green, blue, alpha if radius < 124 else 0
    planet.save(destination / "halo_ce_planet.png")
    (destination / "halo_ce_planet.rgb5a1").write_bytes(rgb5a1(planet))


def write_menu_camera_path(ui_map: Path, destination: Path) -> bytes:
    """Extract the title camera's named path from the retail UI scenario.

    ScenarioCutsceneCameraPoint records are 0x68 bytes in the Xbox cache.
    The `ring_loop` script visits uicam, then point_2 through point_11.
    Store the placed Halo position and those points as camera position,
    forward/up, and horizontal FOV.
    """
    header = mapinfo.read_header(ui_map)
    index = TagIndex.read(ui_map)
    scenario = next(e for e in index.entries
                    if e.group == "scnr" and e.path == r"levels\ui\ui")
    with ui_map.open("rb") as source:
        source.seek(header.tag_data_offset)
        tag_data = source.read(header.tag_data_size)

    def at(address: int, size: int) -> bytes:
        offset = address - index.base
        if offset < 0 or offset + size > len(tag_data):
            raise ValueError("UI scenario pointer falls outside the tag data")
        return tag_data[offset:offset + size]

    scenario_data = at(scenario.data_address, 0x4FC)
    scenery_count, scenery_address = struct.unpack_from("<iI", scenario_data, 0x210)
    if scenery_count < 1:
        raise ValueError("UI scenario has no placed Halo scenery")
    scenery = at(scenery_address, 32)
    ring_position = struct.unpack_from("<3f", scenery, 8)
    yaw, pitch, roll = struct.unpack_from("<3f", scenery, 20)
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    ring_basis = (cy * cp, sy * cr - cy * sp * sr, cy * sp * cr + sy * sr,
                  -(sy * cp), sy * sp * sr + cy * cr, cy * sr - sy * sp * cr,
                  -sp, -(cp * sr), cp * cr)
    count, address = struct.unpack_from("<iI", scenario_data, 0x4F0)
    records = {}
    for i in range(max(0, count)):
        raw = at(address + i * 0x68, 0x68)
        name = raw[4:36].split(b"\0", 1)[0].decode("ascii", "replace")
        if name not in {"uicam", *(f"point_{n}" for n in range(2, 12))}:
            continue
        position = struct.unpack_from("<3f", raw, 0x28)
        yaw, pitch, roll = struct.unpack_from("<3f", raw, 0x34)
        fov = struct.unpack_from("<f", raw, 0x40)[0]
        cr, sr = math.cos(roll), math.sin(roll)
        cp, sp = math.cos(pitch), math.sin(pitch)
        cy, sy = math.cos(yaw), math.sin(yaw)
        forward = (cy * cp, sy * cr - cy * sp * sr, cy * sp * cr + sy * sr)
        up = (-sp, -cp * sr, cp * cr)
        records[name] = (*position, *forward, *up, fov)

    names = ("uicam", *(f"point_{n}" for n in range(2, 12)))
    missing = [name for name in names if name not in records]
    if missing:
        raise ValueError(f"UI scenario camera path is missing {', '.join(missing)}")
    payload = b"HCM3" + struct.pack("<I3f9f", len(names), *ring_position, *ring_basis)
    payload += b"".join(struct.pack("<10f", *records[name]) for name in names)
    (destination / "halo_ce_camera.bin").write_bytes(payload)
    return payload


def write_menu_ring_mesh(ui_map: Path, destination: Path) -> bytes:
    """Export the retail scenery\halo\halo triangles and their two ring UV sets."""
    data = texconv.MapData.open(ui_map)
    model = next(e for e in data.index.entries
                 if e.group == "mode" and e.path == r"scenery\halo\halo")
    source = modelconv.read_model(data, model)
    parts = source.geometries[0]
    shadow_part = next((p for p in parts
                        if "shadow" in data.by_id[p.shader_id].path), None)
    if shadow_part is None:
        raise ValueError("retail Halo model has no inner ring shadow material")
    shadow_shader = texconv.resolve_shader(data, shadow_part.shader_id)
    shadow_bitmap = data.by_id[shadow_shader.bitmap_id]
    images = bitmaps.parse_images(data.region, data.base, shadow_bitmap.data_address)
    width, height, rgba = bitmaps.decode_level(images[0],
        bitmaps.read_pixels(images[0], bitmaps.file_reader(ui_map)))
    shadow = Image.frombytes("RGBA", (width, height), rgba).resize(
        (128, 8), Image.Resampling.LANCZOS)
    shadow.save(destination / "halo_ce_ring_shadow.png")
    shadow_encoded = rgb5a1(shadow)
    (destination / "halo_ce_ring_shadow.rgb5a1").write_bytes(shadow_encoded)
    payload = bytearray(b"HMR1" + struct.pack("<I", len(parts)))
    tag_paths = {e.tag_id: e.path for e in data.index.entries}
    for part in parts:
        path = tag_paths.get(part.shader_id, "")
        kind = 2 if "shadow" in path else 0 if "inner ring" in path else 1
        payload += struct.pack("<II", kind, len(part.tris))
        for tri in part.tris:
            for vertex in tri:
                payload += struct.pack("<5f", *part.pos[vertex], *part.uv[vertex])
    (destination / "halo_ce_ring_mesh.bin").write_bytes(payload)
    return bytes(payload)


class _RsvgRectangle(Structure):
    _fields_ = (
        ("x", c_double), ("y", c_double), ("width", c_double), ("height", c_double))


def _svg_image(path: Path, size: int) -> Image.Image:
    """Rasterize one SVG through the system librsvg. Cairo pixels are premultiplied."""
    try:
        librsvg = ctypes.CDLL("librsvg-2.so.2")
        libcairo = ctypes.CDLL("libcairo.so.2")
        libgobject = ctypes.CDLL("libgobject-2.0.so.0")
    except OSError as error:
        raise RuntimeError("controller glyphs need librsvg, cairo, and gobject") from error
    librsvg.rsvg_handle_new_from_file.argtypes = [c_char_p, c_void_p]
    librsvg.rsvg_handle_new_from_file.restype = c_void_p
    librsvg.rsvg_handle_render_document.argtypes = [c_void_p, c_void_p,
                                                    ctypes.POINTER(_RsvgRectangle), c_void_p]
    librsvg.rsvg_handle_render_document.restype = c_bool
    libgobject.g_object_unref.argtypes = [c_void_p]
    libcairo.cairo_image_surface_create.argtypes = [c_int, c_int, c_int]
    libcairo.cairo_image_surface_create.restype = c_void_p
    libcairo.cairo_create.argtypes = [c_void_p]
    libcairo.cairo_create.restype = c_void_p
    libcairo.cairo_destroy.argtypes = [c_void_p]
    libcairo.cairo_surface_destroy.argtypes = [c_void_p]
    libcairo.cairo_surface_flush.argtypes = [c_void_p]
    libcairo.cairo_image_surface_get_data.argtypes = [c_void_p]
    libcairo.cairo_image_surface_get_data.restype = c_void_p
    libcairo.cairo_image_surface_get_stride.argtypes = [c_void_p]
    libcairo.cairo_image_surface_get_stride.restype = c_int
    handle = librsvg.rsvg_handle_new_from_file(str(path).encode(), None)
    if not handle:
        raise RuntimeError(f"could not read controller icon {path}")
    surface = libcairo.cairo_image_surface_create(0, size, size)
    context = libcairo.cairo_create(surface)
    viewport = _RsvgRectangle(0, 0, float(size), float(size))
    rendered = librsvg.rsvg_handle_render_document(handle, context, byref(viewport), None)
    libcairo.cairo_surface_flush(surface)
    stride = libcairo.cairo_image_surface_get_stride(surface)
    raw = ctypes.string_at(libcairo.cairo_image_surface_get_data(surface), stride * size)
    libcairo.cairo_destroy(context)
    libcairo.cairo_surface_destroy(surface)
    libgobject.g_object_unref(handle)
    if not rendered:
        raise RuntimeError(f"could not render controller icon {path}")
    pixels = bytearray(size * size * 4)
    for y in range(size):
        row = raw[y * stride:y * stride + size * 4]
        for x in range(size):
            blue, green, red, alpha = row[x * 4:x * 4 + 4]
            if alpha and alpha < 255:
                red = min(255, (red * 255 + alpha // 2) // alpha)
                green = min(255, (green * 255 + alpha // 2) // alpha)
                blue = min(255, (blue * 255 + alpha // 2) // alpha)
            elif not alpha:
                red = green = blue = 0
            offset = (y * size + x) * 4
            pixels[offset:offset + 4] = bytes((red, green, blue, alpha))
    return Image.frombytes("RGBA", (size, size), bytes(pixels))


def write_button_glyphs(destination: Path, svg_dir: Path) -> None:
    """Pack the controller SVGs into the 256x16 RGB5A1 atlas the menu uploads."""
    if len(GLYPH_SOURCES) * GLYPH_CELL > GLYPH_ATLAS[0] or GLYPH_CELL > GLYPH_ATLAS[1]:
        raise ValueError("controller glyph atlas is too small for its cells")
    if not svg_dir.is_dir():
        raise FileNotFoundError(f"missing controller icon directory {svg_dir}")
    atlas = Image.new("RGBA", GLYPH_ATLAS, (0, 0, 0, 0))
    inner = GLYPH_CELL - 2
    for index, name in enumerate(GLYPH_SOURCES):
        source = svg_dir / name
        if not source.is_file():
            raise FileNotFoundError(f"missing controller icon {source}")
        icon = _svg_image(source, 128)
        keep = GLYPH_CAPTION_KEEP.get(name)
        if keep is not None:
            cut = int(icon.height * keep)
            blank = Image.new("RGBA", (icon.width, icon.height - cut), (0, 0, 0, 0))
            icon.paste(blank, (0, cut))
        fitted = icon.resize((inner, inner), Image.Resampling.LANCZOS)
        atlas.alpha_composite(fitted, (index * GLYPH_CELL + 1, 1))
    destination.mkdir(parents=True, exist_ok=True)
    atlas.save(destination / "ps2_button_glyphs.png")
    encoded = rgb5a1(atlas)
    if len(encoded) != GLYPH_ATLAS[0] * GLYPH_ATLAS[1] * 2:
        raise ValueError("controller glyph atlas encoded to an unexpected size")
    (destination / "ps2_button_glyphs.rgb5a1").write_bytes(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", nargs="?", type=Path, help="Halo CE Xbox XISO")
    parser.add_argument("--out", type=Path, default=ROOT / "src" / "stream" / "assets")
    parser.add_argument("--package-out", type=Path,
                        help="write contiguous GS texture data for the PS2 runtime")
    parser.add_argument("--button-icons", type=Path, default=BUTTON_ICON_DIR,
                        help="directory of Playstation button SVGs")
    parser.add_argument("--glyphs-only", action="store_true",
                        help="write the controller glyph atlas and skip the Xbox disc")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.glyphs_only:
        write_button_glyphs(args.out, args.button_icons)
        return 0
    if args.iso is None:
        parser.error("iso is required unless --glyphs-only is set")
    with tempfile.TemporaryDirectory(prefix="hcu-menu-assets-") as folder:
        compressed = Path(folder) / "ui.map"
        decompressed = Path(folder) / "decompressed-ui.map"
        disc = XboxDisc(args.iso)
        try:
            disc.extract("maps/ui.map", compressed)
        finally:
            disc.close()
        mapinfo.decompress(compressed, decompressed)
        write_atlas(decode_group(decompressed, MAP_BITMAP), 13, 4, 4,
                    args.out, "halo_ce_map_atlas")
        write_atlas(decode_group(decompressed, GAME_TYPE_BITMAP), 6, 2, 4,
                    args.out, "halo_ce_gametype_atlas")
        write_ring_texture(decode_group(decompressed, RING_INNER_BITMAP)[0],
                           args.out, "halo_ce_ring_inner", (128, 8))
        write_ring_texture(decode_group(decompressed, RING_OUTER_BITMAP)[0],
                           args.out, "halo_ce_ring_outer", (128, 64))
        write_space_texture(decode_group(decompressed, SPACE_BITMAP)[0],
                            args.out, "halo_ce_space")
        write_space_texture(decode_group(decompressed, STARS_BITMAP)[0],
                            args.out, "halo_ce_stars", stars=True)
        write_title_art(decompressed, args.out)
        camera_path = write_menu_camera_path(decompressed, args.out)
        ring_mesh = write_menu_ring_mesh(decompressed, args.out)
        write_loading_backplate(args.out)
    write_button_glyphs(args.out, args.button_icons)
    if args.package_out:
        args.package_out.parent.mkdir(parents=True, exist_ok=True)
        names = ("halo_ce_ring_inner", "halo_ce_ring_outer", "halo_ce_map_atlas",
                 "halo_ce_gametype_atlas", "halo_ce_logo", "halo_ce_buttons",
                 "halo_ce_planet", "ps2_button_glyphs", "halo_ce_space",
                 "halo_ce_stars", "halo_ce_ring_shadow")
        args.package_out.write_bytes(b"".join(
            (args.out / f"{name}.rgb5a1").read_bytes() for name in names) + camera_path + ring_mesh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
