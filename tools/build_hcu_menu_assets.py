#!/usr/bin/env python3
"""Build the PS2 menu atlases from a user-owned Halo CE Xbox disc image."""

from __future__ import annotations

import argparse
import ctypes
import struct
import sys
import tempfile
from ctypes import Structure, byref, c_bool, c_char_p, c_double, c_int, c_void_p
from pathlib import Path

from PIL import Image
from PIL import ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules" / "halo-ps2" / "tools"))
sys.path.insert(0, str(ROOT / "submodules" / "halo-64"))

from halo2ps2 import bitmaps, mapinfo  # noqa: E402
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


def write_ring_texture(image: Image.Image, destination: Path, name: str) -> None:
    """Write one GS texture from the corresponding retail ring material."""
    texture = image.convert("RGBA").resize((128, 128), Image.Resampling.LANCZOS)
    texture.save(destination / f"{name}.png")
    (destination / f"{name}.rgb5a1").write_bytes(rgb5a1(texture))


def write_loading_backplate(ui_map: Path, destination: Path) -> None:
    """Build a PS2-sized backplate from CE's own Halo and Threshold bitmaps.

    The retail progress renderer expects a loose 320x240 loading.tga, which
    is absent from the supplied Xbox XISO. Keep the bitmap art source-authentic
    and let the PS2 progress renderer reproduce the retail blue sweep.
    """
    canvas = Image.new("RGBA", (512, 256), (2, 5, 16, 255))
    pixels = canvas.load()
    for y in range(256):
        shade = max(0, 16 - y // 24)
        for x in range(512):
            pixels[x, y] = (2, 4 + shade // 3, 15 + shade, 255)

    planet = decode_group(ui_map, PLANET_BITMAP)[0].convert("RGBA")
    planet.thumbnail((230, 230), Image.Resampling.LANCZOS)
    px = Image.new("RGBA", (230, 230), (0, 0, 0, 0))
    px.alpha_composite(planet, ((230 - planet.width) // 2, (230 - planet.height) // 2))
    alpha = Image.new("L", (230, 230), 0)
    ImageDraw.Draw(alpha).ellipse((3, 3, 227, 227), fill=255)
    px.putalpha(Image.composite(px.getchannel("A"), Image.new("L", (230, 230), 0), alpha))
    canvas.alpha_composite(px, (300, 10))

    outer = decode_group(ui_map, RING_OUTER_BITMAP)[0].convert("RGBA")
    inner = decode_group(ui_map, RING_INNER_BITMAP)[0].convert("RGBA")
    # The loading silhouette is a broad ring across the planet field. CE's
    # outer/inner material maps remain distinct, matching the retail model.
    for source, box, color in ((outer, (8, 65, 504, 220), (170, 190, 210)),
                               (inner, (20, 78, 492, 207), (135, 170, 205))):
        texture = source.resize((496, 155), Image.Resampling.LANCZOS)
        mask = Image.new("L", (496, 155), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, 495, 154), fill=155)
        draw.ellipse((22, 26, 473, 128), fill=0)
        # Preserve material luminance while tinting toward CE's cold space light.
        tint = Image.new("RGBA", texture.size, (*color, 255))
        texture = Image.blend(texture, tint, 0.45)
        texture.putalpha(mask)
        canvas.alpha_composite(texture, (box[0], box[1]))

    # A soft star field uses the same dark blue palette as the UI scene.
    draw = ImageDraw.Draw(canvas)
    for i in range(95):
        x = (i * 167 + 31) % 512
        y = (i * 83 + 17) % 256
        level = 40 + ((i * 37) % 100)
        draw.point((x, y), fill=(level // 2, level // 2, level, 180))
    canvas.convert("RGB").save(destination / "halo_ce_loading_backplate.png")
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
                           args.out, "halo_ce_ring_inner")
        write_ring_texture(decode_group(decompressed, RING_OUTER_BITMAP)[0],
                           args.out, "halo_ce_ring_outer")
        write_title_art(decompressed, args.out)
        write_loading_backplate(decompressed, args.out)
    write_button_glyphs(args.out, args.button_icons)
    if args.package_out:
        args.package_out.parent.mkdir(parents=True, exist_ok=True)
        names = ("halo_ce_ring_inner", "halo_ce_ring_outer", "halo_ce_map_atlas",
                 "halo_ce_gametype_atlas", "halo_ce_logo", "halo_ce_buttons",
                 "halo_ce_planet", "ps2_button_glyphs")
        args.package_out.write_bytes(b"".join(
            (args.out / f"{name}.rgb5a1").read_bytes() for name in names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
