#!/usr/bin/env python3
"""Prepare per-map packages, sound banks, and headless guest ELFs.

prepare writes build/c3/<map>/{pkg,inc,objects-gen,<map>.hsb}.
link holds /tmp/hb/build.lock and runs tools/hcu_parent_link_probe.py.
The first guest builds the CE closure; later guests reuse it and the object trees.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hcu_mp_map_table as mp  # noqa: E402

TMP = Path("/home/ai/.cache/hbtmp")
LOCK = Path("/tmp/hb/build.lock")
CHAIN_INC = ROOT / "build/c3/chain/inc"
BLOODGULCH_HSB = (ROOT / "build/c3/chain/pkg/bloodgulch_mounted_gunner_4p4bot/bloodgulch.hsb")
SELECTED = ROOT / "build/m2-c2-r3-selected-packages/pkg"
SPU_BUDGET = "2076656"


def c3_base() -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "TMPDIR": str(TMP),
        "TMP": str(TMP),
        "TEMP": str(TMP),
        "HCU_C3": "1",
        "HCU_C3_TELEMETRY": "0",
        "HCU_C3_TIMING": "0",
        "HCU_C3_LAG_TRACE": "0",
        "HCU_C3_OBJECTS": "1",
        "HCU_C3_BITMAP_RESIDENT": "1",
        "HCU_C3_BUILD_PRESET": "quiet",
        "HCU_C3_REALTIME_SCHEDULER": "1",
        "HCU_C2_PROFILE_MAP_SOURCES_ONLY": "1",
    })
    return env


def prepare_map(name: str) -> str:
    item = next(row for row in mp.maps() if row.name == name)
    dest = ROOT / "build/c3" / name
    pkg_out = dest / "pkg" / item.row
    hcp = pkg_out / f"{item.row}.hcp"
    manifest_out = pkg_out / f"{item.row}.json"
    src = SELECTED / item.row
    env = c3_base()
    if not hcp.is_file() or not manifest_out.is_file():
        manifest = json.loads((src / f"{item.row}.json").read_text())
        subprocess.run([
            sys.executable, "tools/hcu_render_media.py",
            "--package", str(src / f"{item.row}.hcp"),
            "--manifest", str(src / f"{item.row}.json"),
            "--expected-sha256", manifest["package_sha256"],
            "--map", str(ROOT / item.map_path),
            "--bsp", "0",
            "--output-dir", str(pkg_out),
        ], cwd=ROOT, env=env, check=True)
    hsb = dest / f"{name}.hsb"
    if not hsb.is_file():
        if name == "bloodgulch":
            shutil.copy2(BLOODGULCH_HSB, hsb)
        else:
            subprocess.run([
                sys.executable, "tools/hcu_sound_bank.py",
                str(ROOT / item.map_path), str(hsb),
                "--budget", SPU_BUDGET, "--max-perms", "2",
            ], cwd=ROOT, env=env, check=True)
    inc = dest / "inc"
    inc.mkdir(parents=True, exist_ok=True)
    for header in ("hcu_c3_render.h", "hcu_c3_workload.h", "hcu_c2_cycles.h"):
        target = inc / header
        if not target.is_file() or target.read_bytes() != (CHAIN_INC / header).read_bytes():
            shutil.copy2(CHAIN_INC / header, target)
    objects = dest / "objects-gen" / "hcu_c3_objects_table.h"
    objects.parent.mkdir(parents=True, exist_ok=True)
    if not objects.is_file() or objects.stat().st_mtime < manifest_out.stat().st_mtime:
        subprocess.run([
            sys.executable, "-I", "tools/hcu_c3_objects_table.py",
            "--package-json", str(manifest_out),
            "--sky-from-scenario",
            "--output", str(objects),
        ], cwd=ROOT, env=env, check=True)
    return f"{name} package={hcp.stat().st_size} hsb={hsb.stat().st_size}"


def prepare_all(jobs: int) -> None:
    names = [item.name for item in mp.maps()]
    # Blood Gulch first so a guest link can start while the rest are still packing.
    print(prepare_map("bloodgulch"), flush=True)
    rest = [name for name in names if name != "bloodgulch"]
    failures = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        future_map = {pool.submit(prepare_map, name): name for name in rest}
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                print(future.result(), flush=True)
            except Exception as exc:  # noqa: BLE001 - report every map, keep going
                failures.append(f"{name}: {exc}")
                print(f"FAIL {name}: {exc}", flush=True)
    if failures:
        raise SystemExit("prepare failed:\n" + "\n".join(failures))


def _probe(cmd: list[str], env: dict[str, str], log_path: Path) -> None:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with log_path.open("w") as log:
            result = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            tail = log_path.read_text(errors="replace")[-2000:]
            raise RuntimeError(f"probe failed ({result.returncode}): {' '.join(cmd)}\n{tail}")


def link_guest(name: str, reuse_from: Path | None, reuse_closure: bool) -> Path:
    item = next(row for row in mp.maps() if row.name == name)
    link_dir = ROOT / "build/c3" / name / "link"
    env = c3_base()
    env["C_INCLUDE_PATH"] = str(ROOT / "build/c3" / name / "inc")
    env["HCU_C3_OBJECTS_GEN"] = str(ROOT / "build/c3" / name / "objects-gen")
    cmd = [
        sys.executable, "tools/hcu_parent_link_probe.py",
        "--asset-profile", "optical",
        "--partition-profile", item.row,
        "--profile-package-root", str(ROOT / "build/c3" / name / "pkg"),
        "--headless-runtime-guest",
        "--output-dir", str(link_dir),
    ]
    if reuse_closure:
        cmd.append("--reuse-closure")
    if reuse_from:
        cmd.extend(["--reuse-objects-from", str(reuse_from)])
    _probe(cmd, env, ROOT / "build/c3" / name / "link.log")
    produced = link_dir / (
        f"hcu-gameplay-machine-optical-partition-{item.row}-headless-runtime-guest.elf")
    if not produced.is_file():
        raise RuntimeError(f"missing guest ELF {produced}")
    dest = ROOT / item.elf_path
    shutil.copy2(produced, dest)
    return dest


def link_menu(reuse_from: Path) -> Path:
    link_dir = ROOT / "build/c3/menu/link"
    env = c3_base()
    env["C_INCLUDE_PATH"] = str(ROOT / "build/c3/bloodgulch/inc")
    env["HCU_C3_OBJECTS_GEN"] = str(ROOT / "build/c3/bloodgulch/objects-gen")
    cmd = [
        sys.executable, "tools/hcu_parent_link_probe.py",
        "--asset-profile", "optical",
        "--output-dir", str(link_dir),
        "--reuse-closure",
        "--reuse-objects-from", str(reuse_from),
    ]
    _probe(cmd, env, ROOT / "build/c3/menu/link.log")
    produced = link_dir / "hcu-gameplay-machine-optical.elf"
    if not produced.is_file():
        found = list(link_dir.glob("hcu-gameplay-machine-optical*.elf"))
        gameplay = [path for path in found if "headless" not in path.name and "parent-link" not in path.name]
        if len(gameplay) != 1:
            raise RuntimeError(f"menu ELF not found in {found}")
        produced = gameplay[0]
    dest = ROOT / "build/c3/menu/HPS2_000.01"
    shutil.copy2(produced, dest)
    return dest


def link_all() -> None:
    table = mp.maps()
    first = "bloodgulch"
    print(f"link {first}", flush=True)
    link_guest(first, None, False)
    reuse = ROOT / "build/c3" / first / "link"
    print("link menu", flush=True)
    link_menu(reuse)
    for item in table:
        if item.name == first:
            continue
        print(f"link {item.name}", flush=True)
        link_guest(item.name, reuse, True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("prepare", "link", "prepare-one"))
    parser.add_argument("name", nargs="?")
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    TMP.mkdir(parents=True, exist_ok=True)
    if args.step == "prepare-one":
        if not args.name:
            parser.error("prepare-one needs a map name")
        print(prepare_map(args.name))
    elif args.step == "prepare":
        prepare_all(args.jobs)
    else:
        link_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
