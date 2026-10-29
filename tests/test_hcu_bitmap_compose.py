"""ILP32 integration of the retail two-map HUD compositor and its fence lease."""
from __future__ import annotations

import hashlib
import json
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine"
HCU = ROOT / "submodules/halo-ce-universal"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))


def _hcp2_media_chunk(package: bytes, chunk_id: int) -> bytes:
    from hcu_profile_chunks import HEADER, V2_RECORD
    magic, version, header_size, _profile, count, directory, directory_bytes, total = HEADER.unpack_from(package)
    assert (magic, version, header_size, total) == (b"HCP2", 2, HEADER.size, len(package))
    assert directory_bytes == count * V2_RECORD.size
    segments = []
    for i in range(count):
        row = V2_RECORD.unpack_from(package, directory + i * V2_RECORD.size)
        kind, cid, offset, size, logical_offset, logical_size, index, segment_count, segment_sha, whole_sha = row
        if kind != 2 or cid != chunk_id:
            continue
        blob = package[offset:offset + size]
        assert hashlib.sha256(blob).digest() == segment_sha
        segments.append((index, segment_count, logical_offset, logical_size, whole_sha, blob))
    assert segments
    segments.sort()
    logical = b"".join(row[5] for row in segments)
    assert len(segments) == segments[0][1] and len(logical) == segments[0][3]
    assert all(row[2] == sum(len(s[5]) for s in segments[:row[0]]) for row in segments)
    assert hashlib.sha256(logical).digest() == segments[0][4]
    return logical


def _decode_psmt4(texs: bytes, source_id: int):
    from halo2ps2.texconv import parse_clut, parse_texs
    view = parse_texs(texs)
    image = next(row for row in view.textures if row["source_id"] == source_id)
    width, height, packed = view.mip(image, 0)
    palette_data = view.data[image["clut_offset"]:image["clut_offset"] + image["clut_entries"] * 4]
    palette = parse_clut(palette_data, image["clut_entries"])
    pixels = []
    for n in range(width * height):
        nibble = (packed[n >> 1] >> (4 if n & 1 else 0)) & 15
        red, green, blue, alpha128 = palette[nibble]
        pixels.append((red, green, blue, min(255, (alpha128 * 255 + 64) // 128)))
    return width, height, pixels


def _sample(pixels, width, height, u, v, wrap_u=False, wrap_v=False, point=False):
    def axis(value, size, wrap):
        if wrap:
            value %= 1.0
        else:
            value = min(max(value, 0.0), 0.99999994)
        if point:
            return int(value * size)
        coord = value * size - 0.5
        floor = int(coord // 1)
        frac = coord - floor
        a, b = floor, floor + 1
        if wrap:
            a %= size
            b %= size
        else:
            a = min(max(a, 0), size - 1)
            b = min(max(b, 0), size - 1)
        return a, b, frac
    if point:
        def point_axis(value, size, wrap):
            if wrap:
                value %= 1.0
            else:
                value = min(max(value, 0.0), 0.99999994)
            return int(value * size)
        return pixels[point_axis(v, height, wrap_v) * width + point_axis(u, width, wrap_u)]
    x0, x1, ax = axis(u, width, wrap_u)
    y0, y1, ay = axis(v, height, wrap_v)
    c00 = pixels[y0 * width + x0]
    c10 = pixels[y0 * width + x1]
    c01 = pixels[y1 * width + x0]
    c11 = pixels[y1 * width + x1]
    return tuple(((c00[c] + (c10[c] - c00[c]) * ax) * (1.0 - ay) +
                  (c01[c] + (c11[c] - c01[c]) * ax) * ay) for c in range(4))


def _measure_native_p4_error(base, overlay, packed_palette, transform):
    width, height = 8, 512
    packed, palette, _entries = packed_palette
    maximum = 0
    squared = 0
    samples = 0
    for y in range(height):
        v = (y + 0.5) / height
        for x in range(width):
            u = (x + 0.5) / width
            a = _sample(base[2], base[0], base[1], u, v, point=True)
            b = _sample(overlay[2], overlay[0], overlay[1],
                        u * transform[0] + transform[2], v * transform[1] + transform[3],
                        transform[4], transform[4], point=True)
            pixel = y * width + x
            index = ((packed[pixel >> 1] >> 4) & 15) if (pixel & 1) else (packed[pixel >> 1] & 15)
            actual = palette[index]
            actual = (*actual[:3], min(255, (actual[3] * 255 + 64) // 128))
            for c in range(4):
                expected = int(a[c] * b[c] / 255.0 + 0.5)
                error = abs(actual[c] - expected)
                maximum = max(maximum, error)
                squared += error * error
                samples += 1
    from math import sqrt
    return maximum, sqrt(squared / samples)


def _retail_angle_ticks_transforms():
    from halo2ps2.texconv import MapData
    retail_path = ROOT / "build/retail-maps/decompressed/bloodgulch.map"
    if not retail_path.is_file():
        pytest.skip("decompressed retail Blood Gulch map unavailable for WPHI transform validation")
    retail = MapData.open(retail_path)
    wphi = retail.by_id[3860989102]
    region = retail.region
    wphi_offset = retail.tag_off(wphi)
    static_count, static_address, _ = __import__("struct").unpack_from("<III", region, wphi_offset + 0x60)
    assert static_count == 3
    import struct
    transforms = []
    for static_index, expected_overlay_id in ((1, 3861185713), (2, 3861251250)):
        static_offset = static_address - retail.base + static_index * 0xB4
        overlay_count, overlay_address, _ = struct.unpack_from("<III", region, static_offset + 0x7C)
        assert overlay_count == 1
        overlay_offset = overlay_address - retail.base
        blend = struct.unpack_from("<2h", region, overlay_offset + 0x2E)
        assert blend[0] == 2  # CE's Xbox-compatible multiply mode
        map_scales = struct.unpack_from("<6f", region, overlay_offset + 0x34)
        map_offsets = struct.unpack_from("<6f", region, overlay_offset + 0x4C)
        wrapped = struct.unpack_from("<3h", region, overlay_offset + 0x94)
        map_ids = [struct.unpack_from("<I", region, overlay_offset + 0x64 + i * 16 + 12)[0]
                   for i in range(2)]
        assert map_ids == [3861120176, expected_overlay_id]
        texture_scales = []
        for tag_id in map_ids:
            images = retail.images(tag_id)
            assert images
            image = images[0]
            texture_scales.append((image.width, image.height) if image.flags & 0x10 else (1.0, 1.0))
        scale_u = (1.0 / map_scales[2] if map_scales[2] else 1.0) * texture_scales[1][0]
        scale_v = (1.0 / map_scales[3] if map_scales[3] else 1.0) * texture_scales[1][1]
        offset_u = map_offsets[2] * texture_scales[1][0]
        offset_v = map_offsets[3] * texture_scales[1][1]
        transforms.append((scale_u, scale_v, offset_u, offset_v, bool(wrapped[1])))
    assert transforms[0] == transforms[1]
    return transforms[0]


def _compile(tmp_path: Path) -> Path:
    compiler = shutil.which("gcc-13") or shutil.which("gcc")
    if not compiler:
        pytest.skip("GCC unavailable for ILP32 HUD compositor fixture")
    includes = [ROOT / "src", ENGINE / "src", HCU / "port/ps2/include"]
    sources = [
        ROOT / "tests/hcu_bitmap_compose_main.c",
        ROOT / "src/stream/hcu_bitmap_dispatch.c",
        ROOT / "src/stream/hcu_bitmap_quad.c",
        ROOT / "src/stream/hcu_asset_profile.c",
        ENGINE / "src/render/chain.c",
        ENGINE / "src/render/texcache.c",
        ENGINE / "src/render/upload.c",
        ENGINE / "src/render/hud_effect.c",
        ENGINE / "src/world/tex.c",
        ROOT / "src/stream/sha256.c",
    ]
    objects = []
    for index, source in enumerate(sources):
        obj = tmp_path / f"compose-{index}.o"
        cmd = [compiler, "-m32", "-std=c11", "-Wall", "-Wextra", "-Werror",
               "-ffunction-sections", "-fdata-sections"]
        for include in includes:
            cmd.extend(["-I", str(include)])
        cmd.extend(["-c", str(source), "-o", str(obj)])
        built = subprocess.run(cmd, capture_output=True, text=True)
        if built.returncode:
            if "bits/libc-header-start.h" in built.stderr or "cannot find -lc" in built.stderr:
                pytest.skip("32-bit host C development files unavailable")
            pytest.fail(f"ILP32 compositor compile failed for {source}:\n{built.stderr[-4000:]}")
        objects.append(obj)
    exe = tmp_path / "bitmap-compose-fixture"
    link = [compiler, "-m32", "-Wl,--gc-sections", "-o", str(exe),
            *(str(obj) for obj in objects), "-lm"]
    built = subprocess.run(link, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    return exe


def test_retail_sniper_multiply_composition_generation_and_fence(tmp_path):
    profile_dir = ROOT / "build/m2-c2-r3-selected-packages/pkg/bloodgulch_mounted_gunner_4p4bot"
    package = profile_dir / "bloodgulch_mounted_gunner_4p4bot.hcp"
    manifest_path = profile_dir / "bloodgulch_mounted_gunner_4p4bot.json"
    if not package.is_file() or not manifest_path.is_file():
        pytest.skip("verified Blood Gulch profile package unavailable")
    manifest = json.loads(manifest_path.read_text())
    resources = {}
    for datum, suffix in ((455, "angle_ticks_mask"), (452, "angle_ticks")):
        matches = [entry for entry in manifest["chunk_bindings"]
                   if entry["kind"] == "BITM"
                   and entry["owner"]["output_datum"] == datum
                   and entry["owner"]["path"].endswith(suffix)]
        assert len(matches) == 1
        resources[datum] = matches[0]
    original_package_data = package.read_bytes()
    assert hashlib.sha256(original_package_data).hexdigest() == manifest["package_sha256"]
    # Rebuild just the two real sniper texture chunks from retail mip 0. The
    # checked-in profile package predates the targeted quality exception and
    # intentionally contains the general-purpose half-resolution conversion.
    from hcu_profile_chunks import encode
    from halo2ps2.texconv import CLASS_BLEND, MapData, build_texs, convert_texture
    retail = MapData.open(ROOT / "build/retail-maps/decompressed/bloodgulch.map")
    regenerated = {}
    for resource in resources.values():
        source_id = resource["owner"]["source_datum"]
        image = retail.images(source_id)[resource["source_image_index"]]
        texture = convert_texture(retail, image, source_id, CLASS_BLEND,
                                  preserve_source_resolution=True)
        assert (texture.width, texture.height) == (image.width, image.height)
        regenerated[resource["chunk_id"]] = build_texs([texture], [])
    package_data = encode(int(manifest["profile"]["id"]), {
        (1, 0): b"\0", (3, 0): b"\0",
        **{(2, chunk_id): payload for chunk_id, payload in regenerated.items()},
    })
    package = tmp_path / "sniper-angle-ticks-mip0.hcp"
    package.write_bytes(package_data)
    transform = _retail_angle_ticks_transforms()
    assert transform[:3] == (1.0, 0.5, 0.0)
    assert transform[3] == pytest.approx(-0.232, abs=1e-7)
    assert transform[4] is False
    exe = _compile(tmp_path)
    base, overlay = resources[455], resources[452]
    output_path = tmp_path / "retail-angle-ticks-composite.rgba"
    run = [str(exe), str(package), str(manifest["profile"]["id"]), "9001",
           str(base["owner"]["output_datum"]), str(base["source_image_index"]),
           str(base["chunk_id"]), str(base["owner"]["source_datum"]),
           str(overlay["owner"]["output_datum"]), str(overlay["source_image_index"]),
           str(overlay["chunk_id"]), str(overlay["owner"]["source_datum"]),
           hashlib.sha256(regenerated[overlay["chunk_id"]]).hexdigest(), str(output_path)]
    result = subprocess.run(run, capture_output=True, text=True)
    if result.returncode == -signal.SIGSYS:
        pytest.skip("sandbox blocks native ILP32 execution with SIGSYS")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "bitmap-compose-ok output=8x512 bytes=2112 gs_pages=4 double_buffer_slots=16" in result.stdout
    assert "sources=verified-indexed" in result.stdout
    assert "source_cache_generation=9002 fence=held-and-released" in result.stdout
    assert "native-grid-p4-ok size=8x512 destination=8x512 palette=6 bytes=2048" in result.stdout
    base_tex = _decode_psmt4(_hcp2_media_chunk(package_data, base["chunk_id"]),
                             base["owner"]["source_datum"])
    overlay_tex = _decode_psmt4(_hcp2_media_chunk(package_data, overlay["chunk_id"]),
                                overlay["owner"]["source_datum"])
    assert (base_tex[0], base_tex[1]) == (8, 256)
    assert (overlay_tex[0], overlay_tex[1]) == (8, 512)
    packed_palette_data = Path(str(output_path) + ".p4").read_bytes()
    assert len(packed_palette_data) == 8 * 512 // 2 + 16 * 4 + 1
    p4 = packed_palette_data[:8 * 512 // 2]
    palette_bytes = packed_palette_data[8 * 512 // 2:8 * 512 // 2 + 64]
    entries = packed_palette_data[-1]
    assert entries == 6
    palette = [tuple(palette_bytes[i:i + 4]) for i in range(0, 64, 4)]
    p4_error_max, p4_error_rms = _measure_native_p4_error(
        base_tex, overlay_tex, (p4, palette, entries), transform)
    print(f"native-grid-p4-error max={p4_error_max}/255 rms={p4_error_rms:.4f}/255")
    assert p4_error_max <= 1, f"native-grid PSMT4 error exceeds GS alpha quantization: max={p4_error_max} rms={p4_error_rms:.4f}"
