"""Native ILP32 CE request -> pinned final HCP BITM -> real PS2 cache/upload/quad."""
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
ENGINE = ROOT / "submodules/halo-ps2/engine"


def _compile(tmp_path):
    compiler = shutil.which("gcc-13") or shutil.which("gcc")
    if not compiler:
        pytest.skip("GCC unavailable for ILP32 bitmap dispatcher")
    source = HCU / "source/interface/interface.c"
    text = source.read_text()
    start = text.index("void interface_draw_bitmap(")
    end = text.index("\nstatic long interface_get_weapon_hud_index", start)
    exact = text[start:end].rstrip() + "\n"
    mod_start = text.index("void interface_draw_bitmap_modulated(")
    mod_end = text.index("\nvoid interface_draw_screen", mod_start)
    exact += text[mod_start:mod_end].rstrip() + "\n"
    enum_start = text.index("enum\n{\n\t_shader_framebuffer_blend_function_alpha_blend")
    enum_end = text.index("\n};", enum_start) + 3
    extracted = tmp_path / "interface_draw_bitmap_exact.c"
    extracted.write_text('#include "cseries/cseries.h"\n#include "bitmaps/bitmap_group.h"\n#include "rasterizer/rasterizer.h"\n' + text[enum_start:enum_end] + "\n" + exact)
    includes = [HCU / "source", HCU / "source/cseries", HCU / "source/math",
        HCU / "source/render", HCU / "source/tag_files", HCU / "source/bitmaps",
        HCU / "source/interface", HCU / "source/rasterizer", HCU / "source/rasterizer/common",
        HCU / "port/ps2/include", HCU / "port/linux/game", HCU / "port/include",
        HCU / "port/include/xdk", ENGINE / "src", ROOT / "src", ROOT / "tests"]
    compat = [compiler, "-m32", "-std=gnu99", "-fms-extensions", "-fshort-wchar",
        "-fwrapv", "-fno-strict-aliasing", "-ffunction-sections", "-fdata-sections",
        "-include", str(ROOT / "tests/soundreq_host_prefix.h"), "-w"]
    plain = [compiler, "-m32", "-std=c11", "-Wall", "-Wextra", "-Werror"]
    for include in includes:
        compat += ["-I", str(include)]
        plain += ["-I", str(include)]
    sources = [ROOT / "tests/hcu_bitmap_dispatch_main.c", extracted,
        HCU / "port/ps2/src/ps2_bitmap_requests.c", ROOT / "src/stream/hcu_bitmap_dispatch.c",
        ROOT / "src/stream/hcu_bitmap_quad.c", ROOT / "src/stream/hcu_asset_profile.c",
        ENGINE / "src/render/chain.c", ENGINE / "src/render/texcache.c",
        ENGINE / "src/render/upload.c", ENGINE / "src/world/tex.c", ROOT / "src/util/sha256.c"]
    # Keep sources in-tree; locate SHA implementation if this checkout uses the alternate path.
    if not sources[-1].is_file():
        candidates = list((ROOT / "src").rglob("sha256.c"))
        assert candidates, "SHA-256 implementation source missing"
        sources[-1] = candidates[0]
    objects, commands = [], []
    for i, path in enumerate(sources):
        obj = tmp_path / f"unit-{i}.o"
        cmd = (compat if path in sources[:3] else plain) + ["-c", str(path), "-o", str(obj)]
        built = subprocess.run(cmd, capture_output=True, text=True)
        commands.append({"command": cmd, "returncode": built.returncode, "stderr": built.stderr})
        if built.returncode:
            if "bits/libc-header-start.h" in built.stderr or "cannot find -lc" in built.stderr:
                pytest.skip("32-bit host C development files unavailable")
            pytest.fail(f"ILP32 compile failed for {path}:\n{built.stderr[-5000:]}")
        objects.append(obj)
    exe = tmp_path / "hcu-bitmap-dispatch-fixture"
    link = [compiler, "-m32", "-Wl,--gc-sections", "-o", str(exe), *(str(p) for p in objects), "-lm"]
    built = subprocess.run(link, capture_output=True, text=True)
    commands.append({"command": link, "returncode": built.returncode, "stderr": built.stderr})
    assert built.returncode == 0, built.stdout + built.stderr
    record = tmp_path / "compile.json"
    record.write_text(json.dumps(commands, indent=2) + "\n")
    return exe, extracted, commands, record


def _source_info(source_map, datum):
    sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "submodules/halo-ps2/tools"),
                    str(ROOT / "submodules/halo-ps2/tools/halo2ps2")]
    from halo2ps2 import bitmaps, texconv
    entry_map = texconv.MapData.open(source_map)
    entry = entry_map.by_id[datum]
    images = bitmaps.parse_images(entry_map.region, entry_map.base, entry.data_address)
    root = entry.data_address - entry_map.base
    import struct
    count, address, _ = struct.unpack_from("<iII", entry_map.region, root + 0x60)
    assert count == len(images) and images
    reg_x, reg_y = struct.unpack_from("<hh", entry_map.region, address - entry_map.base + 0x10)
    return entry.path, images[0].width, images[0].height, reg_x, reg_y


def test_actual_ce_ui_request_runs_through_final_profile_and_real_upload_pipeline(tmp_path):
    from tools.hcu_bitmap_bindings import build as build_bindings
    from tools.hcu_profile_validate import parse_package
    profile_dir = ROOT / os.environ.get("HCU_C1_PROFILES", "build/m2-c1-corpus-primary-v3")
    package = profile_dir / "ui.hcp"
    manifest_path = profile_dir / "ui.json"
    if not package.is_file() or not manifest_path.is_file():
        pytest.skip("primary UI profile package unavailable")
    bindings = build_bindings(manifest_path, package)
    source_map = ROOT / "build/retail-maps/decompressed/ui.map"
    row = next(b for b in bindings["bindings"]
               if b["path"] == r"characters\cyborg\fp\bitmaps\cyborg hands" and
               b["source_image_index"] == 0)
    path, width, height, reg_x, reg_y = _source_info(source_map, row["source_datum"])
    assert path == row["path"]
    exe, extracted, commands, compile_record = _compile(tmp_path)
    run = [str(exe), str(package), str(row["bitmap_output_datum"]), str(row["bitmap_index"]),
           str(row["chunk_id"]), str(row["cache_key"]), str(width), str(height), str(reg_x), str(reg_y),
           str(row["source_datum"]), row["chunk_sha256"]]
    result = subprocess.run(run, capture_output=True, text=True)
    if result.returncode == -signal.SIGSYS:
        pytest.skip("sandbox blocks native ILP32 execution with SIGSYS")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "bitmap-dispatch-ok" in result.stdout
    assert "ctag_reader=end-hook" in result.stdout
    assert "leases=held" in result.stdout and "upload_qw=16" in result.stdout and "geometry_qw=102" in result.stdout
    assert bindings["package"]["sha256"] == hashlib.sha256(package.read_bytes()).hexdigest()
    artifact_dir = Path(os.environ.get("HCU_BITMAP_DISPATCH_ARTIFACTS",
                                       ROOT / "build/m2-c1-bitmap-live-dispatch")).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    durable_exe = artifact_dir / "hcu-bitmap-dispatch-fixture"
    durable_compile = artifact_dir / "compile.json"
    durable_interface = artifact_dir / "interface_draw_bitmap_exact.c"
    durable_bindings = artifact_dir / "ui-bitmap-bindings.json"
    durable_log = artifact_dir / "run.log"
    shutil.copy2(exe, durable_exe)
    shutil.copy2(compile_record, durable_compile)
    shutil.copy2(extracted, durable_interface)
    durable_bindings.write_text(json.dumps(bindings, sort_keys=True, indent=2) + "\n")
    run = [str(durable_exe), *run[1:]]
    result = subprocess.run(run, capture_output=True, text=True)
    if result.returncode == -signal.SIGSYS:
        pytest.skip("sandbox blocks native ILP32 execution with SIGSYS")
    assert result.returncode == 0, result.stdout + result.stderr
    durable_log.write_text(result.stdout + result.stderr)
    package_info = parse_package(package.read_bytes(),
        expected_package_sha256=bindings["package"]["sha256"], expected_profile_id=1)
    source_pins = {}
    source_paths = [
        "submodules/halo-ce-universal/source/interface/interface.c",
        "submodules/halo-ce-universal/port/ps2/src/ps2_bitmap_requests.c",
        "submodules/halo-ce-universal/port/ps2/include/halo_ps2_bitmap_requests.h",
        "submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox.c",
        "src/stream/hcu_bitmap_dispatch.c", "src/stream/hcu_bitmap_dispatch.h",
        "src/stream/hcu_bitmap_quad.c", "src/stream/hcu_bitmap_quad.h",
        "src/stream/hcu_asset_profile.c", "src/stream/hcu_asset_profile.h",
        "tools/hcu_profile_bitmap.py", "tools/hcu_profile_package.py",
        "tools/hcu_profile_chunks.py", "tools/hcu_profile_validate.py",
        "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf",
        "submodules/halo-ps2/tools/halo2ps2/texconv.py",
        "submodules/halo-ps2/tools/halo2ps2/bitmaps.py",
        "submodules/halo-ps2/engine/src/render/chain.c",
        "submodules/halo-ps2/engine/src/render/texcache.c",
        "submodules/halo-ps2/engine/src/render/upload.c",
        "submodules/halo-ps2/engine/src/world/tex.c",
        "tools/hcu_bitmap_bindings.py", "tests/hcu_bitmap_dispatch_main.c",
        "tests/test_hcu_bitmap_dispatch.py",
    ]
    source_pins = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_paths}
    source_pins[str(durable_interface.relative_to(ROOT))] = hashlib.sha256(durable_interface.read_bytes()).hexdigest()
    source_pins[str(durable_bindings.relative_to(ROOT))] = hashlib.sha256(durable_bindings.read_bytes()).hexdigest()
    source_pins[str(durable_compile.relative_to(ROOT))] = hashlib.sha256(durable_compile.read_bytes()).hexdigest()
    source_pins[str(durable_exe.relative_to(ROOT))] = hashlib.sha256(durable_exe.read_bytes()).hexdigest()
    source_pins[str(durable_log.relative_to(ROOT))] = hashlib.sha256(durable_log.read_bytes()).hexdigest()
    source_pins[str(package.relative_to(ROOT))] = hashlib.sha256(package.read_bytes()).hexdigest()
    source_pins[str(manifest_path.relative_to(ROOT))] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    source_pins[str(source_map.relative_to(ROOT))] = hashlib.sha256(source_map.read_bytes()).hexdigest()
    # Retain exact final CE and BITM chunk identities alongside the run evidence.
    source_pins["ui_ctag_chunk_sha256"] = hashlib.sha256(package_info["chunks"][(1, 0)]).hexdigest()
    media_blob = package_info["chunks"][(2, row["chunk_id"])]
    assert hashlib.sha256(media_blob).hexdigest() == row["chunk_sha256"]
    # Keep exact inputs, commands, executable, output chains, and the test's live binding pinned.
    result_record = {"schema": "hcu-c1-bitmap-live-dispatch-v1",
        "status": "host_qualified", "runtime_admitted": False,
        "actual_ce_frame_bound": False,
        "limitation": "host ILP32 queue-end dispatch and command construction; no EE, GS execution, framebuffer, or hardware fence was observed",
        "package": bindings["package"], "manifest": bindings["manifest"],
        "binding": row, "media_chunk_sha256": hashlib.sha256(media_blob).hexdigest(),
        "ui_ctag_sha256": source_pins["ui_ctag_chunk_sha256"],
        "source_map_sha256": hashlib.sha256(source_map.read_bytes()).hexdigest(),
        "source_path": path, "source_datum": row["source_datum"],
        "source_width_height_registration": [width, height, reg_x, reg_y],
        "interface_body_sha256": hashlib.sha256(durable_interface.read_bytes()).hexdigest(),
        "dispatcher_sha256": source_pins["src/stream/hcu_bitmap_dispatch.c"],
        "binding_table_sha256": hashlib.sha256(json.dumps(bindings, sort_keys=True).encode()).hexdigest(),
        "live_consumer_evidence": {"registration": "halo_ps2_bitmap_requests_register_consumer",
            "dispatch_hook": "halo_ps2_bitmap_requests_end -> hcu_bitmap_dispatch_reader",
            "actual_ce_calls": ["interface_draw_bitmap", "interface_draw_bitmap_modulated(shader_type=0)",
                "interface_draw_bitmap_modulated(shader_type=3)"],
            "ce_blend_table_source": "submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox.c:rasterizer_set_framebuffer_blend_function",
            "asserted_modes": {"0": "source-alpha/inverse-source-alpha", "3": "one/one additive",
                "7": "one/inverse-source-alpha"},
            "covered_roles": ["CE interface_draw_bitmap screen quads",
                "CE interface_draw_bitmap_modulated screen quads"],
            "not_covered": ["HUD atlas/material OTEX consumers", "render_sprite/effect-world consumers",
                "production ps2_render.render_frame binding"],
            "host_packets": {"requests": 3, "upload_qwords": 16, "geometry_qwords": 102,
                "cache_hits": 2, "cache_misses": 1,
                "fail_closed": ["profile id", "request generation", "source datum", "chunk SHA-256", "mutated chunk"],
                "atomic_rollback": ["geometry capacity", "upload-chain capacity"]}},
        "executable_sha256": hashlib.sha256(durable_exe.read_bytes()).hexdigest(),
        "compile_commands": commands,
        "compile_record_sha256": hashlib.sha256(durable_compile.read_bytes()).hexdigest(),
        "run_command": run, "returncode": result.returncode, "stdout": result.stdout.strip(),
        "stderr": result.stderr, "pre_fence_evidence": True,
        "completion": "explicit fixture completion call; real GPU fence not available in host harness",
        "source_pins": source_pins,
        "artifacts": {"executable": str(durable_exe.relative_to(ROOT)),
            "compile_record": str(durable_compile.relative_to(ROOT)),
            "interface_body": str(durable_interface.relative_to(ROOT)),
            "bindings": str(durable_bindings.relative_to(ROOT)),
            "log": str(durable_log.relative_to(ROOT))}}
    out = artifact_dir / "result.json"
    out.write_text(json.dumps(result_record, sort_keys=True, indent=2) + "\n")
    assert result_record["returncode"] == 0
