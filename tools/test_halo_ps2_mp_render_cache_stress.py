#!/usr/bin/env python3
"""Exercise real PS2 map-section and GS texture-cache owners on all MP maps.

Host diagnostic only: uses retail converter sections, the real PS2 section parser and
the real texcache policy. It models the renderer's conservative all-resource demand;
it does not issue GS DMA or claim EE/PCSX2 rendering evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine"
MAPS = ("beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
        "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
        "sidewinder", "wizard")
sys.path.insert(0, str(ROOT / "tests"))
from test_hcu_mp_capacity import MP_SOURCE_SHA256  # noqa: E402
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2 import hp2, modelconv, scenconv, skyconv, texconv  # noqa: E402


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_pin(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"],
                                   cwd=ROOT, text=True).strip()


def main() -> int:
    if set(MP_SOURCE_SHA256) != set(MAPS):
        raise SystemExit("pinned multiplayer map inventory changed")
    stamp = str(time.time_ns())
    out = ROOT / "build" / "mp-render-cache-stress" / stamp
    assets = out / "assets"
    assets.mkdir(parents=True)
    sources = ROOT / "build/retail-maps/decompressed"
    input_rows = []
    for name in MAPS:
        src = sources / f"{name}.map"
        raw = src.read_bytes()
        if sha(raw) != MP_SOURCE_SHA256[name]:
            raise SystemExit(f"{name}: source map hash mismatch")
        bsp_pack = hp2.parse(texconv.convert_map(src, lightmaps=True, lm_gain=1.5).pack)
        tex_sections = [(s.tag, bsp_pack.read(s.tag)) for s in bsp_pack.sections
                        if s.tag == "TEXS" or (s.tag.startswith("LM") and s.tag[2:].isdigit())]
        (assets / f"{name}.tex.hp2").write_bytes(hp2.build(name, tex_sections))
        selected = set(scenconv.collect(src).model_tags)
        sky = skyconv.read_sky(src)
        if sky and sky["model_tag"]:
            selected.add(sky["model_tag"])
        models = modelconv.convert_map(src, sorted(selected))
        obj_pack = hp2.build(name, [("MODL", models.modl), ("OTEX", models.otex)])
        (assets / f"{name}.obj.hp2").write_bytes(obj_pack)
        input_rows.append({
            "map": name, "source_sha256": sha(raw),
            "texture_pack_sha256": sha((assets / f"{name}.tex.hp2").read_bytes()),
            "object_pack_sha256": sha(obj_pack),
            "texture_sections": [{"tag": tag, "bytes": len(body), "sha256": sha(body)}
                                 for tag, body in tex_sections],
            "model_bytes": len(models.modl), "model_sha256": sha(models.modl),
            "object_texture_bytes": len(models.otex), "object_texture_sha256": sha(models.otex),
        })

    cc = shutil.which("cc")
    if not cc:
        raise SystemExit("host C compiler unavailable")
    binary, linkmap = out / "mp-render-cache-stress", out / "mp-render-cache-stress.map"
    sources_c = [
        ROOT / "tests/mp_render_cache_stress_main.c",
        ENGINE / "src/world/section.c", ENGINE / "src/world/tex.c",
        ENGINE / "src/world/model.c", ENGINE / "src/render/texcache.c",
        ENGINE / "src/stream/hp2.c", ENGINE / "src/stream/file.c",
        ENGINE / "src/core/mem.c",
    ]
    command = [cc, "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
               "-I" + str(ENGINE / "tests/hp2_world_shim"),
               "-I" + str(ENGINE / "src"), *map(str, sources_c),
               "-Wl,-Map," + str(linkmap), "-o", str(binary)]
    built = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if built.returncode:
        (out / "compile.stderr").write_text(built.stderr)
        raise SystemExit("compile failed; see " + str(out / "compile.stderr"))
    run = subprocess.run([str(binary), str(assets) + "/"], cwd=ROOT,
                         capture_output=True, text=True)
    run_log = out / "run.log"
    run_log.write_text(run.stdout + run.stderr)
    lines = [line for line in run.stdout.splitlines() if line.startswith("mp-render-cache map=")]
    if run.returncode or len(lines) != len(MAPS):
        raise SystemExit(f"cache stress failed ({run.returncode}); rows={len(lines)}; see {run_log}")
    manifest = {
        "schema": "hcu-mp-render-cache-stress-v1",
        "scope": "13 stock multiplayer maps; campaign excluded",
        "classification": "host candidate diagnostic; not target execution or rendered scene",
        "profile": {"candidate_owner_bytes": 4014928, "section_scratch_bytes": 524288,
                    "gs_cache_pages": 270, "page_bytes": 8192,
                    "per_frame_upload_budget_bytes": 1536 * 1024},
        "source_pins": {"parent": git_pin(ROOT),
                        "halo_ce_universal": git_pin(ROOT / "submodules/halo-ce-universal"),
                        "halo_ps2": git_pin(ROOT / "submodules/halo-ps2")},
        "source_maps": MP_SOURCE_SHA256,
        "inputs": input_rows,
        "run": {"command": [str(binary.relative_to(ROOT)), str(assets.relative_to(ROOT)) + "/"],
                "exit_code": run.returncode, "rows": lines,
                "log": str(run_log.relative_to(ROOT)), "log_sha256": sha(run_log.read_bytes())},
        "artifacts": {
            "runner_sha256": sha(Path(__file__).read_bytes()),
            "fixture_sha256": sha((ROOT / "tests/mp_render_cache_stress_main.c").read_bytes()),
            "binary_sha256": sha(binary.read_bytes()),
            "link_map_sha256": sha(linkmap.read_bytes()),
            "assets_root": str(assets.relative_to(ROOT)),
        },
        "interpretation": [
            "The C fixture loads TEXS, all emitted LM sections, selected MODL and OTEX simultaneously into the exact 4,014,928-byte candidate owner, then checks owner/scratch canaries and teardown.",
            "The fixture calls the actual texcache implementation with the same cache page count, CLUT slot count, upload budget, key ordering, mip-0 byte count, and lightmap CLUT size as bsp_render.c.",
            "Demand intentionally enumerates every texture and every nonempty lightmap page, not a camera/PVS-visible frame; deferrals are conservative stress observations, not proof of a rendered-frame failure.",
            "No GS PATH3 transfer, DMA in-flight overlap, BSP visibility traversal, PS2/PCSX2 placement, or actual EE performance is exercised.",
        ],
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print("\n".join(lines))
    print(f"MANIFEST {manifest_path.relative_to(ROOT)} SHA256 {sha(manifest_path.read_bytes())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
