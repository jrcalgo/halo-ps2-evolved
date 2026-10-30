#!/usr/bin/env python3
"""Build an OPL boot ISO containing the game ELF and Halo CE derived assets."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# sceCdSearchFile keeps only a short file name. These root names match
# iso9660_alias_cdrom_path() in the optical ELF.
PROFILE_SHORT_NAMES = {
    "build/m2-c2-r3-selected-packages/pkg/bloodgulch_mounted_gunner_4p4bot/bloodgulch_mounted_gunner_4p4bot.hcp": "BGPKG.HCP",
    "build/retail-maps/decompressed/a30.map": "A30.MAP",
    "build/retail-maps/decompressed/a50.map": "A50.MAP",
    "build/retail-maps/decompressed/beavercreek.map": "BEAVER.MAP",
    "build/retail-maps/decompressed/bloodgulch.map": "BGMAP.MAP",
    "build/retail-maps/decompressed/c40.map": "C40.MAP",
}
MAP_PACKAGES = {
    "beavercreek": "build/m2-mp-extra/beavercreek-all-bsps.hp2",
    "bloodgulch": "build/retail-maps/bloodgulch-with-bsps.hp2",
    "boardingaction": "build/m2-mp-all-map-packages/boardingaction-all-bsps.hp2",
    "carousel": "build/m2-mp-all-map-packages/carousel-all-bsps.hp2",
    "chillout": "build/m2-mp-all-map-packages/chillout-all-bsps.hp2",
    "damnation": "build/m2-mp-extra/damnation-wind-all-bsps.hp2",
    "hangemhigh": "build/m2-mp-all-map-packages/hangemhigh-all-bsps.hp2",
    "longest": "build/m2-artifacts/longest-2fba411b-hcu6933490-all-bsps.hp2",
    "prisoner": "build/m2-mp-extra/prisoner-all-bsps.hp2",
    "putput": "build/m2-mp-all-map-packages/putput-all-bsps.hp2",
    "ratrace": "build/m2-mp-all-map-packages/ratrace-all-bsps.hp2",
    "sidewinder": "build/m2-mp-all-map-packages/sidewinder-all-bsps.hp2",
    "wizard": "build/m2-mp-all-map-packages/wizard-all-bsps.hp2",
}


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("retail_iso", type=Path, help="user-owned Halo CE Xbox XISO")
    parser.add_argument("--elf", type=Path,
                        default=ROOT / "build/halo-ps2-iso/hcu-gameplay-machine-optical.elf")
    parser.add_argument("--output", type=Path, default=ROOT / "build/halo-ps2-iso/HALO_PS2.iso")
    parser.add_argument("--profile-header", type=Path,
                        help="generated C2 image header whose pinned package and sources must be on the disc")
    args = parser.parse_args()
    elf = args.elf.resolve()
    output = args.output.resolve()
    if not elf.is_file():
        parser.error(f"missing optical-profile game ELF: {elf}")
    if not args.retail_iso.is_file():
        parser.error(f"missing retail XISO: {args.retail_iso}")
    asset_dir = output.parent / "packages"
    texture_path = asset_dir / "menu_textures.bin"
    audio_path = asset_dir / "menu_audio.hsb"
    loading_path = output.parent / "menu-assets" / "loading.rgb5a1"
    run("python3", "tools/build_hcu_menu_assets.py", str(args.retail_iso.resolve()),
        "--out", str(output.parent / "menu-assets"), "--package-out", str(texture_path))
    run("python3", "tools/build_hcu_menu_audio.py", str(args.retail_iso.resolve()), str(audio_path))
    sources = [("MAPS/UI.MAP", ROOT / "build/retail-maps/decompressed/ui.map"),
               ("MAPS/UI.HP2", ROOT / "build/hcu-parent-link-probe/maps/ui.hp2")]
    for name, package in MAP_PACKAGES.items():
        upper = name.upper()
        sources.append((f"MAPS/{upper}.MAP", ROOT / f"build/retail-maps/decompressed/{name}.map"))
        sources.append((f"MAPS/{upper}.HP2", ROOT / package))
    if args.profile_header:
        header = args.profile_header.read_text()
        package_match = re.search(r'#define HCU_C2_IMAGE_PACKAGE_PATH "([^"]+)"', header)
        source_paths = re.findall(r'\{ "[^"]+", "(build/retail-maps/decompressed/[^"]+)"', header)
        if not package_match or not source_paths:
            parser.error("profile header has no pinned package or source paths")
        for relative in [package_match.group(1), *source_paths]:
            path = (ROOT / relative).resolve()
            if ROOT not in path.parents:
                parser.error(f"profile path escapes repository: {relative}")
            short = PROFILE_SHORT_NAMES.get(relative)
            if not short:
                parser.error(f"profile path has no short optical name: {relative}")
            sources.append((short, path))
    sources += [("PACKAGES/MENU_TEXTURES.BIN", texture_path),
                ("PACKAGES/MENU_AUDIO.HSB", audio_path),
                ("PACKAGES/LOAD.RGB", loading_path)]
    missing = [str(path) for _target, path in sources if not path.is_file()]
    if missing:
        parser.error("missing converted map assets: " + ", ".join(missing))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hcu-opl-iso-") as folder:
        system_cnf = Path(folder) / "SYSTEM.CNF"
        system_cnf.write_text("BOOT2 = cdrom0:\\HPS2_000.01;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n",
                              encoding="ascii")
        grafts = [f"SYSTEM.CNF={system_cnf}", f"HPS2_000.01={elf}"]
        grafts += [f"{target}={path.resolve()}" for target, path in sources]
        # The CDVDMAN path parser used by some PS2/PCSX2 boot stacks removes
        # nested separators from FileXio names. Include flat aliases for those
        # stacks while retaining the normal directory layout for OPL.
        grafts += [f"{target.replace('/', '')}={path.resolve()}"
                   for target, path in sources
                   if target.startswith(("MAPS/UI.", "PACKAGES/MENU_", "PACKAGES/LOAD."))]
        run("xorriso", "-as", "mkisofs", "-iso-level", "2", "--norock",
            "-graft-points",
            # BIOS loadelf rejects an ELF whose extent is past sector 65535.
            # Keep the boot file ahead of the multi-hundred-megabyte maps.
            "--sort-weight", "300000", "HPS2_000.01",
            "--sort-weight", "100000", "MAPS/UI.MAP",
            "--sort-weight", "99999", "MAPS/UI.HP2",
            "-V", "HALO_PS2", "-o", str(output), *grafts)
    print(f"{output}: {output.stat().st_size} bytes; {len(sources)} bundled assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
