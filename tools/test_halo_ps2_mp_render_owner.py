#!/usr/bin/env python3
"""Measure co-resident production MP render sections in the real PS2 section loader."""
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
CANDIDATE_TEXTURE_BYTES = 4_014_928
DIAGNOSTIC_OWNER_BYTES = 16 * 1024 * 1024
SCRATCH_BYTES = 524_288
sys.path.insert(0, str(ROOT / "tests"))
from test_hcu_mp_capacity import MP_SOURCE_SHA256  # noqa: E402
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2 import hp2, modelconv, scenconv, skyconv, texconv  # noqa: E402


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    if set(MP_SOURCE_SHA256) != set(MAPS):
        raise SystemExit("pinned MP map inventory changed")
    stamp = str(time.time_ns())
    out = ROOT / "build" / "mp-render-owner" / stamp
    assets = out / "assets"
    assets.mkdir(parents=True)
    rows = []
    for name in MAPS:
        source = ROOT / "build/retail-maps/decompressed" / f"{name}.map"
        raw_map = source.read_bytes()
        if sha(raw_map) != MP_SOURCE_SHA256[name]:
            raise SystemExit(f"{name}: source map hash mismatch")
        bsp = hp2.parse(texconv.convert_map(source, lightmaps=True, lm_gain=1.5).pack)
        texture_sections = [(s.tag, bsp.read(s.tag)) for s in bsp.sections
                            if s.tag == "TEXS" or (s.tag.startswith("LM") and s.tag[2:].isdigit())]
        (assets / f"{name}.tex.hp2").write_bytes(hp2.build(name, texture_sections))
        selected = set(scenconv.collect(source).model_tags)
        sky = skyconv.read_sky(source)
        if sky and sky["model_tag"]:
            selected.add(sky["model_tag"])
        converted = modelconv.convert_map(source, sorted(selected))
        object_pack = hp2.build(name, [("MODL", converted.modl), ("OTEX", converted.otex)])
        (assets / f"{name}.obj.hp2").write_bytes(object_pack)
        rows.append({"map": name, "source_sha256": sha(raw_map),
                     "texture_sections": [{"tag": tag, "bytes": len(data), "sha256": sha(data)}
                                          for tag, data in texture_sections],
                     "modl_bytes": len(converted.modl), "modl_sha256": sha(converted.modl),
                     "otex_bytes": len(converted.otex), "otex_sha256": sha(converted.otex),
                     "object_pack_sha256": sha(object_pack)})

    cc = shutil.which("cc")
    if not cc:
        raise SystemExit("C compiler not found")
    binary, linkmap = out / "mp-render-owner", out / "mp-render-owner.map"
    command = [cc, "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
               "-I" + str(ENGINE / "tests/hp2_world_shim"), "-I" + str(ENGINE / "src"),
               str(ROOT / "tests/mp_render_owner_main.c"),
               str(ENGINE / "src/world/section.c"), str(ENGINE / "src/world/tex.c"),
               str(ENGINE / "src/world/model.c"), str(ENGINE / "src/stream/hp2.c"),
               str(ENGINE / "src/stream/file.c"), str(ENGINE / "src/core/mem.c"),
               "-Wl,-Map," + str(linkmap), "-o", str(binary)]
    built = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if built.returncode:
        raise SystemExit("compile failed:\n" + built.stdout + built.stderr)
    run = subprocess.run([str(binary), str(assets) + "/"], cwd=ROOT,
                         capture_output=True, text=True)
    (out / "run.log").write_text(run.stdout + run.stderr)
    if run.returncode:
        raise SystemExit(f"render owner probe failed ({run.returncode}); see {out / 'run.log'}")
    if run.stdout.count("mp-render-owner map=") != 13:
        raise SystemExit("expected 13 completed map rows")
    manifest = {
        "schema": "hcu-mp-render-owner-co-residency-v1",
        "scope": "13 pinned stock MP maps; campaign excluded",
        "diagnostic_owner_bytes": DIAGNOSTIC_OWNER_BYTES,
        "candidate_texture_owner_bytes": CANDIDATE_TEXTURE_BYTES,
        "section_scratch_bytes": SCRATCH_BYTES,
        "production_budget_or_admission_changed": False,
        "source_map_pins": MP_SOURCE_SHA256,
        "generated_sections": rows,
        "run_exit_code": run.returncode,
        "run_output": run.stdout,
        "artifacts": {"binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                      "link_map_sha256": hashlib.sha256(linkmap.read_bytes()).hexdigest(),
                      "run_log_sha256": hashlib.sha256((out / "run.log").read_bytes()).hexdigest(),
                      "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      "fixture_sha256": hashlib.sha256((ROOT / "tests/mp_render_owner_main.c").read_bytes()).hexdigest()},
        "source_pins": {"halo_ce_universal": subprocess.check_output(
            ["git", "-C", str(ROOT / "submodules/halo-ce-universal"), "rev-parse", "HEAD"], text=True).strip(),
                        "halo_ps2": subprocess.check_output(
            ["git", "-C", str(ROOT / "submodules/halo-ps2"), "rev-parse", "HEAD"], text=True).strip()},
        "limits": ["Host loader execution, not R5900/PCSX2 or physical EE placement.",
                   "Measures MODL and texture sections only; SCEN, ANIM, SKY, match-time assets and live renderer state are excluded.",
                   "The 16 MiB diagnostic arena permits measurement; candidate comparison is reported separately and grants no capacity credit."],
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(run.stdout, end="")
    print(f"MANIFEST {manifest_path.relative_to(ROOT)} SHA256 {hashlib.sha256(manifest_path.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
