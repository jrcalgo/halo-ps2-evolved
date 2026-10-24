"""ILP32 integration of exact CE draw to GS packets.

The extracted function and CE inline `sine`/`cosine` helpers are compiled from
the pinned source. Those helpers call host libm here, so this checks that CE's
actual draw transform reaches the capture and packet path, not console math
parity or a framebuffer result.
"""
import hashlib
import importlib.util
import json
import shutil
import signal
import struct
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
ENGINE = ROOT / "submodules/halo-ps2/engine"


def _bitmap_fixture(tmp_path):
    spec = importlib.util.spec_from_file_location("bitmap_fixture", ROOT / "tests/test_hcu_profile_bitmap.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    from hcu_profile_bitmap import serialize_bitmap
    sources, owner, schema = module.fixture(tmp_path)
    result = serialize_bitmap(sources, owner, schema)
    # The CE output datum in this tiny fixture is deliberately the source datum;
    # image index remains a separate identity within the bitmap tag.
    tex_path = tmp_path / "serializer-ui-bitmap.texs"
    tex_path.write_bytes(result["chunks"][0]["data"])
    ident = result["chunks"][0]["identity"]
    assert ident["group"] == "bitm" and ident["source_datum"] == 5 and ident["source_image_index"] == 0
    return tex_path, ident


def _real_ui_bitmap_fixture(tmp_path, path, datum):
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    sys.path.insert(0, str(HCU / "tools"))
    sys.path.insert(0, str(HCU / "tools/halo2ps2"))
    from hcu_profile_bitmap import serialize_bitmap
    from hcu_schema_manifest import Elf32, SchemaManifest
    from halo2ps2 import bitmaps, texconv

    source_path = ROOT / "build/retail-maps/decompressed/ui.map"
    schema_path = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"
    catalog_path = ROOT / "build/m2-c1-profiles-ui/bitmap-stage-ui-2026-10-23/catalog.json"
    catalog = json.loads(catalog_path.read_text())
    source = texconv.MapData.open(source_path)
    entry = source.by_id.get(datum)
    assert entry is not None and entry.group == "bitm" and entry.path == path
    images = bitmaps.parse_images(source.region, source.base, entry.data_address)
    assert images and images[0].is_2d and images[0].decodable
    root = entry.data_address - source.base
    image_count, image_address, _ = struct.unpack_from("<iII", source.region, root + 0x60)
    assert image_count == len(images) and image_count > 0
    bitmap_at = image_address - source.base
    registration_x, registration_y = struct.unpack_from("<hh", source.region, bitmap_at + 0x10)
    schema = SchemaManifest(Elf32(schema_path)).build()
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    assert catalog["source_maps"]["ui"]["sha256"] == source_sha
    staged = next(a for a in catalog["assets"] if a["source_key"] == "ui" and a["source_datum"] == datum)
    assert staged["path"] == path and staged["source_sha256"] == source_sha
    schema_sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    assert catalog["schema_elf_sha256"] == schema_sha
    owner = {"source_key": "ui", "group": "bitm", "path": path, "source_datum": datum}
    result = serialize_bitmap({"ui": source}, owner, schema, source_sha256=source_sha)
    chunk = next(c for c in result["chunks"] if c["identity"]["source_image_index"] == 0)
    assert chunk["identity"] == {
        "source_key": "ui", "source_sha256": source_sha, "group": "bitm", "path": path,
        "source_datum": datum, "source_image_index": 0,
    }
    tex_path = tmp_path / "actual-ui-bitmap.texs"
    tex_path.write_bytes(chunk["data"])
    metadata = {
        "source_map": str(source_path.relative_to(ROOT)), "source_map_sha256": source_sha,
        "schema_elf": str(schema_path.relative_to(ROOT)),
        "schema_elf_sha256": schema_sha,
        "source_path": path, "source_datum": datum, "source_image_index": 0,
        "image_width": images[0].width, "image_height": images[0].height,
        "registration_x": registration_x, "registration_y": registration_y,
        "source_pixel_offset": images[0].pixel_offset, "source_pixel_bytes": images[0].pixel_size,
        "source_pixel_sha256": hashlib.sha256(source.pixels(images[0])).hexdigest(),
        "serialized_texs_sha256": hashlib.sha256(chunk["data"]).hexdigest(),
        "serialized_texs_path": None,
        "serialized_width": chunk["width"], "serialized_height": chunk["height"],
        "serialized_image_sha256": chunk["sha256"],
        "stage_catalog": str(catalog_path.relative_to(ROOT)),
        "stage_catalog_sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
        "interface_source": "submodules/halo-ce-universal/source/interface/interface.c",
    }
    source_paths = [
        "tests/hcu_bitmap_pipeline_main.c",
        "tests/soundreq_host_prefix.h",
        "submodules/halo-ce-universal/source/interface/interface.c",
        "submodules/halo-ce-universal/port/ps2/src/ps2_bitmap_requests.c",
        "submodules/halo-ce-universal/port/ps2/include/halo_ps2_bitmap_requests.h",
        "src/stream/hcu_bitmap_quad.c", "src/stream/hcu_bitmap_quad.h",
        "submodules/halo-ps2/engine/src/render/chain.c",
        "submodules/halo-ps2/engine/src/world/tex.c",
        "tools/hcu_profile_bitmap.py", "tools/hcu_schema_manifest.py",
        "submodules/halo-ps2/tools/halo2ps2/bitmaps.py",
        "submodules/halo-ps2/tools/halo2ps2/texconv.py",
        "build/retail-maps/decompressed/ui.map",
        "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf",
        "build/m2-c1-profiles-ui/bitmap-stage-ui-2026-10-23/catalog.json",
    ]
    metadata["source_pins"] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_paths}
    return tex_path, metadata


def _compile_pipeline(tmp_path):
    compiler = shutil.which("gcc-13") or shutil.which("gcc")
    if not compiler:
        pytest.skip("GCC unavailable for CE ILP32 fixture")
    interface_path = HCU / "source/interface/interface.c"
    interface_text = interface_path.read_text()
    start = interface_text.index("void interface_draw_bitmap(")
    end = interface_text.index("\nstatic long interface_get_weapon_hud_index", start)
    exact_draw = interface_text[start:end].rstrip() + "\n"
    interface_sha = hashlib.sha256(exact_draw.encode()).hexdigest()
    blend_start = interface_text.index("enum\n{\n\t_shader_framebuffer_blend_function_alpha_blend")
    blend_end = interface_text.index("\n};", blend_start) + len("\n};")
    exact_blend = interface_text[blend_start:blend_end] + "\n"
    extracted = tmp_path / "interface_draw_bitmap_exact.c"
    extracted.write_text('''#include "cseries/cseries.h"\n#include "bitmaps/bitmap_group.h"\n#include "rasterizer/rasterizer.h"\n''' + exact_blend + exact_draw)
    include_dirs = [
        HCU / "source", HCU / "source/cseries", HCU / "source/math", HCU / "source/render",
        HCU / "source/tag_files", HCU / "source/bitmaps", HCU / "source/interface",
        HCU / "source/rasterizer", HCU / "source/rasterizer/common", HCU / "port/ps2/include",
        HCU / "port/linux/game", HCU / "port/include", HCU / "port/include/xdk",
        ENGINE / "src", ROOT / "src",
    ]
    exe = tmp_path / "bitmap-pipeline-fixture"
    compat = [compiler, "-m32", "-std=gnu99", "-fms-extensions", "-fshort-wchar", "-fwrapv",
              "-fno-strict-aliasing", "-w", "-ffunction-sections", "-fdata-sections",
              "-include", str(ROOT / "tests/soundreq_host_prefix.h")]
    for include in include_dirs:
        compat.extend(["-I", str(include)])
    plain = [compiler, "-m32", "-std=c11", "-Wall", "-Wextra", "-Werror"]
    for include in include_dirs:
        plain.extend(["-I", str(include)])
    sources = [ROOT / "tests/hcu_bitmap_pipeline_main.c", extracted,
               HCU / "port/ps2/src/ps2_bitmap_requests.c"]
    sources_plain = [ROOT / "src/stream/hcu_bitmap_quad.c", ENGINE / "src/render/chain.c",
                     ENGINE / "src/world/tex.c"]
    objects = []
    command_log = []
    for index, source in enumerate(sources + sources_plain):
        obj = tmp_path / f"unit-{index}.o"
        cmd = (compat if source in sources else plain) + ["-c", str(source), "-o", str(obj)]
        built = subprocess.run(cmd, capture_output=True, text=True)
        command_log.append({"command": cmd, "returncode": built.returncode, "stderr": built.stderr})
        if built.returncode:
            if "bits/libc-header-start.h" in built.stderr or "cannot find -lc" in built.stderr:
                pytest.skip("32-bit host C development files unavailable")
            pytest.fail(f"ILP32 integration compile failed ({source.name}):\n{built.stderr[-5000:]}")
        objects.append(obj)
    link_cmd = [compiler, "-m32", "-Wl,--gc-sections", "-o", str(exe), *(str(obj) for obj in objects), "-lm"]
    linked = subprocess.run(link_cmd, capture_output=True, text=True)
    command_log.append({"command": link_cmd, "returncode": linked.returncode, "stderr": linked.stderr})
    if linked.returncode:
        if "cannot find -lc" in linked.stderr:
            pytest.skip("32-bit host C development files unavailable")
        pytest.fail(f"ILP32 integration link failed:\n{linked.stderr[-5000:]}")
    compile_record = tmp_path / "compile.json"
    compile_record.write_text(json.dumps(command_log, indent=2) + "\n")
    return exe, interface_sha, command_log, compile_record


def _run_case(tmp_path, exe, tex_path, interface_sha, args, metadata=None):
    result = subprocess.run([str(exe), str(tex_path), args[0], interface_sha, *args[1:]], capture_output=True, text=True)
    if result.returncode == -signal.SIGSYS:
        pytest.skip("sandbox blocks native ILP32 execution with SIGSYS")
    log = tmp_path / ("run-" + (args[0] if args else "success") + ".log")
    log.write_text(result.stdout + result.stderr)
    if metadata is not None:
        metadata["execution_log"] = log.name
        metadata["execution_returncode"] = result.returncode
        metadata["execution_stdout"] = result.stdout.strip()
        def pin_path(path):
            try:
                return str(path.resolve().relative_to(ROOT))
            except ValueError:
                return str(path.resolve())
        run_command = [str(exe), str(tex_path), args[0], interface_sha, *args[1:]]
        metadata["native_fixture"] = {
            "executable": {"path": pin_path(exe), "sha256": hashlib.sha256(exe.read_bytes()).hexdigest()},
            "compile_record": {"path": pin_path(tmp_path / "compile.json"),
                               "sha256": hashlib.sha256((tmp_path / "compile.json").read_bytes()).hexdigest()},
            "command": run_command, "returncode": result.returncode,
            "log": {"path": pin_path(log), "sha256": hashlib.sha256(log.read_bytes()).hexdigest()},
            "source_pins": metadata.get("source_pins", {}),
        }
        metadata["serialized_texs_path"] = pin_path(tex_path)
        metadata["serialized_texs_file_sha256"] = hashlib.sha256(tex_path.read_bytes()).hexdigest()
        (tmp_path / "case-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return result


def test_exact_ce_bitmap_draw_capture_to_real_gs_packet(tmp_path):
    tex_path, identity = _bitmap_fixture(tmp_path)
    exe, interface_sha, command_log, compile_record = _compile_pipeline(tmp_path)
    identity["source_pins"] = {
        "tests/hcu_bitmap_pipeline_main.c": hashlib.sha256((ROOT / "tests/hcu_bitmap_pipeline_main.c").read_bytes()).hexdigest(),
        "submodules/halo-ce-universal/source/interface/interface.c": hashlib.sha256((HCU / "source/interface/interface.c").read_bytes()).hexdigest(),
        "submodules/halo-ce-universal/port/ps2/include/halo_ps2_bitmap_requests.h": hashlib.sha256((HCU / "port/ps2/include/halo_ps2_bitmap_requests.h").read_bytes()).hexdigest(),
        "submodules/halo-ce-universal/port/ps2/src/ps2_bitmap_requests.c": hashlib.sha256((HCU / "port/ps2/src/ps2_bitmap_requests.c").read_bytes()).hexdigest(),
        "src/stream/hcu_bitmap_quad.c": hashlib.sha256((ROOT / "src/stream/hcu_bitmap_quad.c").read_bytes()).hexdigest(),
        "src/stream/hcu_bitmap_quad.h": hashlib.sha256((ROOT / "src/stream/hcu_bitmap_quad.h").read_bytes()).hexdigest(),
        "submodules/halo-ps2/engine/src/render/chain.c": hashlib.sha256((ENGINE / "src/render/chain.c").read_bytes()).hexdigest(),
        "submodules/halo-ps2/engine/src/world/tex.c": hashlib.sha256((ENGINE / "src/world/tex.c").read_bytes()).hexdigest(),
    }
    results = {}
    for mode in ("success", "full", "bad_asset"):
        result = _run_case(tmp_path, exe, tex_path, interface_sha, [mode])
        assert result.returncode == 0, result.stderr + result.stdout
        results[mode] = result.stdout.strip()
    assert f"source_datum={identity['source_datum']} image_index={identity['source_image_index']}" in results["success"]
    assert f"interface_sha256={interface_sha}" in results["success"]
    assert "pipeline-ok" in results["success"] and "gs_alpha=64" in results["success"]
    assert "captured=128 full=1 emitted=0" in results["full"]
    assert "pipeline-bad-asset" in results["bad_asset"] and "emitted=0 rejected=1" in results["bad_asset"]
    assert f"interface_sha256={interface_sha}" in results["full"]
    assert f"interface_sha256={interface_sha}" in results["bad_asset"]


@pytest.mark.parametrize(("path", "datum"), [
    # The detail map formerly used here is dropped by the C1.4 consumer policy; use a kept HUD image.
    (r"ui\hud\bitmaps\combined\hud_reticles", 3797811434),
    (r"characters\cyborg\fp\bitmaps\cyborg hands", 3799318785),
])
def test_actual_retail_ui_bitmap_ce_draw_reaches_gs_packets(tmp_path, path, datum):
    tex_path, metadata = _real_ui_bitmap_fixture(tmp_path, path, datum)
    exe, interface_sha, compile_log, compile_record = _compile_pipeline(tmp_path)
    metadata["interface_source_sha256"] = interface_sha
    metadata["compiler_commands"] = compile_log
    metadata["compile_record_path"] = str(compile_record)
    extracted = tmp_path / "interface_draw_bitmap_exact.c"
    try:
        extracted_name = extracted.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        extracted_name = extracted.resolve().as_posix()
    metadata["source_pins"][extracted_name] = hashlib.sha256(extracted.read_bytes()).hexdigest()
    args = ["success", str(datum), "0", str(metadata["image_width"]), str(metadata["image_height"]),
            str(metadata["registration_x"]), str(metadata["registration_y"])]
    result = _run_case(tmp_path, exe, tex_path, interface_sha, args, metadata)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"source_datum={datum} image_index=0" in result.stdout
    assert "pipeline-ok" in result.stdout and "gs_alpha=64" in result.stdout
    assert "gs_mode=triangle" in result.stdout
