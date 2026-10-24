#!/usr/bin/env python3
"""Exercise production MP texture sections through halo-ps2's host section loader.

This is an isolated diagnostic for candidate texture-cache capacity, not a PS2/EE test.
It writes temporary HP2 wrappers around exact halo-ps2 converter section bytes, then
loads TEXS, every LMn and scenario-selected OTEX with the actual C section loader.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine"
MAPS = (
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
    "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
    "sidewinder", "wizard",
)
TEXTURE_CAPACITY = 4_014_936
SCRATCH_CAPACITY = 524_288

sys.path.insert(0, str(ROOT / "tests"))
from test_hcu_mp_capacity import MP_SOURCE_SHA256  # noqa: E402

sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2 import hp2, modelconv, scenconv, skyconv, texconv  # noqa: E402


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def pin(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"],
                                   cwd=ROOT, text=True).strip()


def make_map_packs(name: str, source: Path, out: Path) -> dict:
    """Build actual converter sections, with only their enclosing HP2 pack narrowed."""
    bsp_result = texconv.convert_map(source, lightmaps=True, lm_gain=1.5)
    bsp_pack = hp2.parse(bsp_result.pack)
    texture_sections = [(s.tag, bsp_pack.read(s.tag)) for s in bsp_pack.sections
                        if s.tag == "TEXS" or (s.tag.startswith("LM") and s.tag[2:].isdigit())]
    if not texture_sections or texture_sections[0][0] != "TEXS":
        raise RuntimeError(f"{name}: converter did not emit TEXS first")
    texture_pack = hp2.build(name, texture_sections)
    tex_path = out / f"{name}.tex.hp2"
    tex_path.write_bytes(texture_pack)

    # Match objpack's scenario model selection exactly, including the sky model;
    # the OTEX section bytes themselves are the production model converter output.
    objects = scenconv.collect(source)
    model_tags = set(objects.model_tags)
    sky = skyconv.read_sky(source)
    if sky and sky["model_tag"]:
        model_tags.add(sky["model_tag"])
    model_result = modelconv.convert_map(source, sorted(model_tags))
    object_pack = hp2.build(name, [("OTEX", model_result.otex)])
    obj_path = out / f"{name}.obj.hp2"
    obj_path.write_bytes(object_pack)

    # Same valid container, but TEXS has a bad decoded-data CRC. The real loader
    # must roll its owner cursor back after writing the output section.
    parsed = hp2.parse(texture_pack)
    tex_index = next(i for i, section in enumerate(parsed.sections) if section.tag == "TEXS")
    corrupt = bytearray(texture_pack)
    crc_offset = hp2.HEADER_SIZE + tex_index * hp2.ENTRY_SIZE + 20
    crc, = struct.unpack_from("<I", corrupt, crc_offset)
    struct.pack_into("<I", corrupt, crc_offset, crc ^ 1)
    bad_path = out / f"{name}.bad.tex.hp2"
    bad_path.write_bytes(corrupt)

    return {
        "map": name,
        "source_map": str(source.relative_to(ROOT)),
        "source_map_sha256": sha_file(source),
        "texture_pack_sha256": sha_file(tex_path),
        "texture_pack_bytes": len(texture_pack),
        "texture_sections": [
            {"tag": tag, "raw_bytes": len(blob), "raw_sha256": sha_bytes(blob)}
            for tag, blob in texture_sections
        ],
        "object_pack_sha256": sha_file(obj_path),
        "object_pack_bytes": len(object_pack),
        "scenario_model_tag_count_including_sky": len(model_tags),
        "otex_raw_bytes": len(model_result.otex),
        "otex_sha256": sha_bytes(model_result.otex),
        "bad_crc_pack_sha256": sha_file(bad_path),
    }


def main() -> int:
    stamp = str(time.time_ns())
    out = ROOT / "build" / "mp-texture-runtime" / stamp
    assets = out / "assets"
    assets.mkdir(parents=True)
    sources = ROOT / "build/retail-maps/decompressed"
    expected_names = set(MAPS)
    if set(MP_SOURCE_SHA256) != expected_names:
        raise SystemExit("pinned 13-map source hash set drifted; review before running")
    map_records = []
    print("generating production-converter TEXS/LM and scenario OTEX sections", flush=True)
    for name in MAPS:
        source = sources / f"{name}.map"
        if not source.is_file():
            raise SystemExit(f"missing source map {source}")
        actual = sha_file(source)
        if actual != MP_SOURCE_SHA256[name]:
            raise SystemExit(f"{name}: source hash mismatch; expected {MP_SOURCE_SHA256[name]}, got {actual}")
        print(f"convert {name}", flush=True)
        map_records.append(make_map_packs(name, source, assets))

    compiler = shutil.which("cc")
    if not compiler:
        raise SystemExit("C host compiler unavailable")
    binary = out / "mp-texture-runtime"
    linkmap = out / "mp-texture-runtime.map"
    compile_command = [
        compiler, "-std=gnu11", "-O2", "-g", "-Wall", "-Wextra", "-Werror",
        "-ffunction-sections", "-fdata-sections",
        "-I" + str(ENGINE / "tests/hp2_world_shim"),
        "-I" + str(ENGINE / "src"),
        str(ROOT / "tests/mp_texture_runtime_main.c"),
        str(ENGINE / "src/world/section.c"),
        str(ENGINE / "src/world/tex.c"),
        str(ENGINE / "src/stream/hp2.c"),
        str(ENGINE / "src/stream/file.c"),
        str(ENGINE / "src/core/mem.c"),
        "-Wl,--gc-sections", "-Wl,-Map," + str(linkmap), "-o", str(binary),
    ]
    build = subprocess.run(compile_command, cwd=ROOT, capture_output=True, text=True)
    if build.returncode:
        (out / "compile.stdout.txt").write_text(build.stdout)
        (out / "compile.stderr.txt").write_text(build.stderr)
        raise SystemExit(f"host fixture compile failed ({build.returncode}); see {out}")

    relative_assets = assets.relative_to(ROOT).as_posix() + "/"
    run_command = [str(binary.relative_to(ROOT)), relative_assets]
    run = subprocess.run(run_command, cwd=ROOT, capture_output=True, text=True)
    run_log = out / "run.log"
    run_log.write_text(run.stdout + run.stderr)
    runtime_rows = {}
    row_pattern = re.compile(
        r"^mp-texture-runtime map=(\w+) texs=(\d+) otex=(\d+) "
        r"lm_section_bytes=(\d+) lm_sections=(\d+) lm_pages=(\d+) "
        r"lm_pixels=(\d+) raw_sections=(\d+) retained=(\d+) "
        r"alignment_overhead=(\d+) normal_peak=(\d+) rollback_peak=(\d+) "
        r"scratch_peak=(\d+)/(\d+) rollback=crc-rejected-safe$",
        re.MULTILINE)
    for match in row_pattern.finditer(run.stdout):
        values = [int(value) for value in match.groups()[1:]]
        runtime_rows[match.group(1)] = dict(zip((
            "texs_raw_bytes", "otex_raw_bytes", "lm_section_raw_bytes",
            "lm_section_count", "lm_page_count", "lm_pixel_bytes",
            "raw_section_sum", "retained_owner_used", "alignment_overhead",
            "normal_peak", "crc_failure_peak", "scratch_high_water",
            "scratch_capacity"), values))
    crc_failures = run.stdout.count("decoding TEXS failed (8)")
    expected_success = set(runtime_rows) == set(MAPS) and crc_failures == len(MAPS)
    if run.returncode == 0 and not expected_success:
        raise SystemExit(f"native fixture output incomplete: maps={sorted(runtime_rows)}, crc_failures={crc_failures}; see {run_log}")
    manifest = {
        "schema": "halo-ps2-mp-texture-runtime-capacity-v1",
        "scope": "13 stock MP maps; campaign excluded",
        "profile": {
            "texture_owner_bytes": TEXTURE_CAPACITY,
            "section_scratch_bytes": SCRATCH_CAPACITY,
        },
        "diagnostic_only": True,
        "not_ps2_ee_execution": True,
        "not_render_or_texture_safety_proof": True,
        "parents": {
            "halo_ps2": pin(ROOT / "submodules/halo-ps2"),
            "halo_ce_universal": pin(ROOT / "submodules/halo-ce-universal"),
            "parent": pin(ROOT),
        },
        "sources": {
            "runner": str(Path(__file__).relative_to(ROOT)),
            "runner_sha256": sha_file(Path(__file__).resolve()),
            "c_fixture": "tests/mp_texture_runtime_main.c",
            "c_fixture_sha256": sha_file(ROOT / "tests/mp_texture_runtime_main.c"),
            "section_loader_sha256": sha_file(ENGINE / "src/world/section.c"),
            "tex_reader_sha256": sha_file(ENGINE / "src/world/tex.c"),
            "hp2_streamer_sha256": sha_file(ENGINE / "src/stream/hp2.c"),
            "file_reader_sha256": sha_file(ENGINE / "src/stream/file.c"),
            "arena_sha256": sha_file(ENGINE / "src/core/mem.c"),
            "source_test_fixture_sha256": sha_file(ROOT / "tests/test_hcu_mp_capacity.py"),
        },
        "compile_command": compile_command,
        "run_command": run_command,
        "return_code": run.returncode,
        "runtime_rows": runtime_rows,
        "expected_crc_failure_rollbacks": crc_failures,
        "run_log": str(run_log.relative_to(ROOT)),
        "run_log_sha256": sha_file(run_log),
        "binary": str(binary.relative_to(ROOT)),
        "binary_sha256": sha_file(binary),
        "link_map": str(linkmap.relative_to(ROOT)),
        "link_map_sha256": sha_file(linkmap),
        "output": run.stdout,
        "maps": map_records,
        "prior_candidate_capacity_report": {
            "path": "docs/reports/mp-step8-tail-inclusive-candidate-2026-10-22.md",
            "sha256": "f8b8d25a8bc4c8b7accb95d73f09a7b886fca2eb996dcd370e5af4764e45a649",
        },
        "interpretation": [
            "Static converted section lengths are different from actual arena high-water; run output reports the latter.",
            "Each map's texture sections are simultaneously retained in the exact candidate-sized owner.",
            "Section HP2 wrappers contain exact converter raw section bytes; the OTEX wrapper is intentionally OTEX-only, not a full object pack.",
            "No DMA upload, GS residency, texture eviction, frame overlap, or R5900 placement is exercised.",
        ],
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(run.stdout, end="")
    print(f"MANIFEST {manifest_path.relative_to(ROOT)} SHA256 {sha_file(manifest_path)}")
    if run.returncode:
        print(f"runtime fixture failed with {run.returncode}; artifacts retained under {out}", file=sys.stderr)
        return run.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
