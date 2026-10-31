#!/usr/bin/env python3
"""Build HALO_PS2.iso from the 13-map table.

One guest is compiled fully. That object tree is the seed. The other guests
reuse it: --reuse-closure skips the shared engine rebuild, and
--reuse-objects-from recompiles only hcu_main.o (the partition header and the
per-map object table). Parent objects still rebuild when their sources are
newer than the seeded .o files. The CE closure (decals, objects, ps2_render,
main, the scheduler header) is rebuilt first when any of those sources is
newer than rooted.o, so a reused closure cannot drop gameplay fixes. All 13
links then run at the same time, and the ISO is packed with
tools/build_hcu_opl_iso.py.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hcu_mp_map_table as mp  # noqa: E402

SEED_LINK = ROOT / "build/c3/guest-seed"
C3_ENV = {
    "TMPDIR": "/home/ai/.cache/hbtmp",
    "HCU_C3": "1",
    "HCU_C3_TELEMETRY": "0",
    "HCU_C3_TIMING": "0",
    "HCU_C3_LAG_TRACE": "0",
    "HCU_C3_OBJECTS": "1",
    "HCU_C3_BITMAP_RESIDENT": "1",
    "HCU_C3_BUILD_PRESET": "quiet",
    "HCU_C3_REALTIME_SCHEDULER": "1",
}


def guest_elf(link: Path, item: mp.MpMap) -> Path:
    name = (f"hcu-gameplay-machine-optical-partition-{item.row}"
            "-headless-runtime-guest.elf")
    return link / name


def base_env(item: mp.MpMap | None) -> dict[str, str]:
    env = dict(os.environ)
    env.update(C3_ENV)
    # Workload headers are identical across maps, so every link resolves the
    # same closure directory and --reuse-closure stays read-only.
    env["C_INCLUDE_PATH"] = str(ROOT / "build/c3/beavercreek/inc")
    if item is not None:
        env["HCU_C3_OBJECTS_GEN"] = str(ROOT / "build/c3" / item.name / "objects-gen")
    else:
        env["HCU_C3_OBJECTS_GEN"] = str(ROOT / "build/c3/bloodgulch/objects-gen")
    return env


def run_probe(args: list[str], env: dict[str, str], log: Path) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as handle:
        subprocess.run(args, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT, check=True)


# CE units linked through rooted.o. Parent stream and engine objects are not in
# this set; ee-world.mk rebuilds those when the seeded .o is older than the source.
CLOSURE_SOURCE_ROOTS = (
    ROOT / "submodules/halo-ce-universal/source",
    ROOT / "submodules/halo-ce-universal/port/ps2",
)
_CLOSURE_SUFFIXES = {".c", ".h"}


def production_closure_dir() -> Path:
    """The rooted.o directory the production guest links. Matches hcu_ps2_closure.py."""
    from c3_build_preset import apply_c3_build_preset
    env = base_env(None)
    apply_c3_build_preset(env)
    suffix = "-production-runtime-guest-hcu-c3"
    if env.get("HCU_C3_TELEMETRY") == "1":
        suffix += "-telemetry"
    if env.get("HCU_C3_TIMING") == "1" or env.get("HCU_C3_TELEMETRY") == "1":
        suffix += "-timing"
    if env.get("HCU_C3_LAG_TRACE") == "1":
        suffix += "-lag-trace"
    if env.get("HCU_C3_REALTIME_SCHEDULER") == "1":
        suffix += "-realtime"
    if env.get("HCU_C3_SNAPSHOT_INDEX") == "1":
        suffix += "-snapshot-index"
    if env.get("HCU_C3_MOVEMENT_TRACE") == "1":
        suffix += "-movement-trace"
    if env.get("HCU_C3_SESSION_TRACE") == "1":
        suffix += "-session-trace"
    if env.get("HCU_C3_PHASE_PROBE") == "1":
        suffix += "-phase-probe"
    if env.get("HCU_C3_BITMAP_DEFER_PROBE") == "1":
        suffix += "-bitmap-defer-probe"
    header = Path(env["C_INCLUDE_PATH"].split(":")[0]) / "hcu_c3_workload.h"
    if header.is_file():
        suffix += "-workload-" + hashlib.sha256(header.read_bytes()).hexdigest()[:12]
    return ROOT / "build/hcu-ps2-closure" / ("all-no-bootstrap-memory" + suffix)


def closure_is_stale(closure: Path) -> bool:
    rooted = closure / "rooted.o"
    if not rooted.is_file():
        return True
    rooted_mtime = rooted.stat().st_mtime
    for base in CLOSURE_SOURCE_ROOTS:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix in _CLOSURE_SUFFIXES and path.stat().st_mtime > rooted_mtime:
                return True
    return False


def ensure_fresh_closure() -> None:
    closure = production_closure_dir()
    if not closure_is_stale(closure):
        print(f"closure fresh {closure}", flush=True)
        return
    print(f"closure stale {closure}", flush=True)
    import rebuild_hcu_closure
    code = rebuild_hcu_closure.run_closure(
        rebuild_hcu_closure.closure_overrides(),
        rebuild_hcu_closure.closure_argv())
    if code != 0:
        raise SystemExit(f"CE closure rebuild failed with exit {code}")


def refresh_object_tables(table: list[mp.MpMap]) -> None:
    """Regenerate per-map object headers when generator logic changes, not only when manifests change."""
    generator = ROOT / "tools/hcu_c3_objects_table.py"
    for item in table:
        package_json = ROOT / "build/c3" / item.name / "pkg" / item.row / f"{item.row}.json"
        output = ROOT / "build/c3" / item.name / "objects-gen" / "hcu_c3_objects_table.h"
        if not package_json.is_file():
            raise SystemExit(f"missing package manifest for {item.name}: {package_json}")
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            sys.executable, "-I", str(generator), "--package-json", str(package_json),
            "--sky-from-scenario", "--output", str(output),
        ], cwd=ROOT, check=True)


def seed_from(link: Path) -> None:
    if SEED_LINK.exists():
        shutil.rmtree(SEED_LINK)
    SEED_LINK.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(link, SEED_LINK, symlinks=True)


def full_guest(item: mp.MpMap) -> None:
    link = ROOT / "build/c3" / item.name / "link"
    run_probe([
        sys.executable, "tools/hcu_parent_link_probe.py",
        "--asset-profile", "optical",
        "--partition-profile", item.row,
        "--profile-package-root", str(ROOT / "build/c3" / item.name / "pkg"),
        "--headless-runtime-guest",
        "--output-dir", str(link),
    ], base_env(item), ROOT / "build/c3" / item.name / "link-full.log")
    built = guest_elf(link, item)
    if not built.is_file():
        raise SystemExit(f"seed guest missing: {built}")
    shutil.copy2(built, ROOT / "build/c3" / item.name / item.elf_iso)
    seed_from(link)


def link_menu() -> None:
    link = ROOT / "build/c3/menu/link"
    run_probe([
        sys.executable, "tools/hcu_parent_link_probe.py",
        "--asset-profile", "optical",
        "--output-dir", str(link),
        "--reuse-closure",
        "--reuse-objects-from", str(SEED_LINK),
    ], base_env(None), ROOT / "build/c3/menu/link-reuse.log")
    built = link / "hcu-gameplay-machine-optical.elf"
    if not built.is_file():
        raise RuntimeError(f"menu missing: {built}")
    shutil.copy2(built, ROOT / "build/c3/menu/HPS2_000.01")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build/halo-ps2-bloodgulch/HALO_PS2.iso")
    parser.add_argument("--logo-source", type=Path,
                        default=ROOT / "assets/ps2/boot-logo-ntsc.bin",
                        help="12-sector PS2 logo source (default: bundled NTSC logo)")
    parser.add_argument("--full-seed", action="store_true",
                        help="compile Beaver Creek from scratch before the parallel links")
    parser.add_argument("--seed-link", type=Path,
                        help="finished probe output to copy as the shared object seed")
    args = parser.parse_args()
    ensure_fresh_closure()
    table = mp.maps()
    refresh_object_tables(table)
    seed_map = table[0]
    seed_objects = (args.seed_link if args.seed_link is None or args.seed_link.is_absolute()
                    else ROOT / args.seed_link) if args.seed_link else ROOT / "build/c3" / seed_map.name / "link"
    if args.full_seed or not (seed_objects / "parent-sections-os").is_dir():
        print(f"full seed {seed_map.name}", flush=True)
        full_guest(seed_map)
    else:
        print(f"seed from {seed_objects}", flush=True)
        seed_from(seed_objects)

    procs: list[tuple[mp.MpMap, subprocess.Popen[bytes]]] = []
    for item in table:
        log = ROOT / "build/c3" / item.name / "link-reuse.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        handle = log.open("w")
        command = [
            sys.executable, "tools/hcu_parent_link_probe.py",
            "--asset-profile", "optical",
            "--partition-profile", item.row,
            "--profile-package-root", str(ROOT / "build/c3" / item.name / "pkg"),
            "--headless-runtime-guest",
            "--output-dir", str(ROOT / "build/c3" / item.name / "link"),
            "--reuse-closure",
            "--reuse-objects-from", str(SEED_LINK),
        ]
        print(f"link {item.name}", flush=True)
        procs.append((item, subprocess.Popen(
            command, cwd=ROOT, env=base_env(item), stdout=handle, stderr=subprocess.STDOUT)))
    failed = []
    for item, proc in procs:
        code = proc.wait()
        if code != 0:
            failed.append(f"{item.name} exit {code}")
            continue
        built = guest_elf(ROOT / "build/c3" / item.name / "link", item)
        if not built.is_file():
            failed.append(f"{item.name} produced no elf")
            continue
        shutil.copy2(built, ROOT / "build/c3" / item.name / item.elf_iso)
        print(f"linked {item.name}", flush=True)
    if failed:
        raise SystemExit("guest links failed: " + ", ".join(failed))

    print("menu", flush=True)
    link_menu()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    subprocess.run([
        sys.executable, "tools/build_hcu_opl_iso.py",
        "--elf", str(ROOT / "build/c3/menu/HPS2_000.01"),
        "--output", str(output),
        "--logo-source", str(args.logo_source.expanduser().resolve()),
    ], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
