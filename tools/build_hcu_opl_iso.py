#!/usr/bin/env python3
"""Build an OPL boot ISO for the 13-map multiplayer menu.

The file list comes from tools/hcu_mp_map_table.py. Every partition pins the
shared a30, a50, and c40 maps, so those live under MAPS/ where the BIOS can
open them. Duplicate MAPS/<NAME>.MAP copies of the multiplayer maps are not
written. Each retail map,
profile package, and sound bank is stored under the 8.3 or level-2 name the
optical ELF opens. Guest ELFs are stored in /E because the BIOS caches
only the first sector of a directory. The image is rejected above a
single-layer DVD, and again if a file the BIOS must open falls outside
that first directory sector.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RETAIL_XISO = Path.home() / "Documents/Halo/Halo - Combat Evolved.xiso.iso"
sys.path.insert(0, str(ROOT / "tools"))
import hcu_mp_map_table as mp  # noqa: E402

SINGLE_LAYER_DVD_BYTES = 4_700_372_992
TMP = Path(os.environ.get("TMPDIR", "/tmp"))
SECTOR = 2048
# PCSX2's DoCDVDdetectDiskType treats an image of more than 453361 sectors as a
# DVD. That driver's ISO search reads the path table from sector 257 and ignores
# the PVD. The menu ELF used to occupy that sector, so the BIOS reported
# "open fail" for HPS2_000.01. ZZPAD.BIN holds sector 257 and this publisher
# copies the real path table there.
DVD_PATH_TABLE_LBA = 257
PAD_SECTORS = 512


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def _read_sector(handle, lba: int) -> bytes:
    handle.seek(lba * SECTOR)
    data = handle.read(SECTOR)
    if len(data) != SECTOR:
        raise RuntimeError(f"short read at LBA {lba}")
    return data


def _root_entries(handle) -> list[tuple[str, int, int]]:
    pvd = _read_sector(handle, 16)
    extent = int.from_bytes(pvd[158:162], "little")
    length = int.from_bytes(pvd[166:170], "little")
    handle.seek(extent * SECTOR)
    blob = handle.read(length)
    entries = []
    offset = 0
    while offset + 33 <= len(blob):
        record = blob[offset]
        if record == 0:
            offset = (offset + SECTOR - 1) // SECTOR * SECTOR
            continue
        name_len = blob[offset + 32]
        name = blob[offset + 33:offset + 33 + name_len].split(b";", 1)[0]
        if name not in (b"\x00", b"\x01"):
            entries.append((
                name.decode("ascii"),
                int.from_bytes(blob[offset + 2:offset + 6], "little"),
                int.from_bytes(blob[offset + 10:offset + 14], "little"),
            ))
        offset += record
    return entries


def publish_dvd_path_table(iso: Path) -> None:
    """Point the DVD cdvd driver at a real path table without covering a payload file."""
    with iso.open("r+b") as handle:
        pvd = bytearray(_read_sector(handle, 16))
        source = int.from_bytes(pvd[140:144], "little")
        table = _read_sector(handle, source)
        pad = next((item for item in _root_entries(handle) if item[0] == "ZZPAD.BIN"), None)
        if pad is None:
            raise RuntimeError("ZZPAD.BIN is missing from the ISO root")
        start, size = pad[1], pad[2]
        end = start + (size + SECTOR - 1) // SECTOR
        if not start <= DVD_PATH_TABLE_LBA < end:
            raise RuntimeError(
                f"ZZPAD.BIN occupies LBAs {start}..{end - 1}, not sector {DVD_PATH_TABLE_LBA}")
        for name, extent, file_size in _root_entries(handle):
            if name == "ZZPAD.BIN" or not file_size:
                continue
            last = extent + (file_size + SECTOR - 1) // SECTOR
            if extent <= DVD_PATH_TABLE_LBA < last:
                raise RuntimeError(f"{name} still covers DVD path table sector {DVD_PATH_TABLE_LBA}")
        handle.seek(DVD_PATH_TABLE_LBA * SECTOR)
        handle.write(table)
        pvd[140:144] = DVD_PATH_TABLE_LBA.to_bytes(4, "little")
        handle.seek(16 * SECTOR)
        handle.write(pvd)
        entries = _root_entries(handle)
    for name, extent, _size in entries:
        if name.startswith("HPS2_"):
            print(f"  {name} LBA {extent}")


def ps2_logo_checksum(data: bytes) -> int:
    """Return OPL's checksum for the scrambled first 12 PS2 disc sectors."""
    if len(data) != 12 * SECTOR:
        raise ValueError("PS2 logo data must be exactly 12 sectors")
    key = data[0]
    if key == 0:
        raise ValueError("PS2 logo first byte must be nonzero")
    return sum((((byte ^ key) << 3) | ((byte ^ key) >> 5)) & 0xff for byte in data)


def publish_ps2_logo(iso: Path, source: Path) -> int:
    """Copy a region-valid logo from a PS2 disc's first 12 sectors."""
    with source.open("rb") as handle:
        logo = handle.read(12 * SECTOR)
    checksum = ps2_logo_checksum(logo)
    if checksum not in (0x120519, 0x1555AB):
        raise ValueError(f"unsupported PS2 logo checksum 0x{checksum:06X}")
    with iso.open("r+b") as handle:
        if handle.seek(0, os.SEEK_END) < len(logo):
            raise ValueError("ISO is too short for PS2 logo sectors")
        handle.seek(0)
        handle.write(logo)
    return checksum
def _names_in_directory(handle, extent: int, size: int, first_sector_only: bool) -> set[str]:
    handle.seek(extent * SECTOR)
    blob = handle.read(size)
    if len(blob) != size:
        raise RuntimeError(f"short directory read at LBA {extent}")
    found = set()
    offset = 0
    while offset + 33 <= len(blob):
        record = blob[offset]
        if record == 0:
            offset = (offset + SECTOR - 1) // SECTOR * SECTOR
            continue
        if first_sector_only and (offset >= SECTOR or offset + record > SECTOR):
            break
        raw = blob[offset + 33:offset + 33 + blob[offset + 32]].split(b";", 1)[0]
        if raw not in (b"\x00", b"\x01"):
            found.add(raw.decode("ascii"))
        offset += record
    return found


def assert_bios_directory_window(iso: Path) -> None:
    """Fail if the BIOS one-sector directory cache would hide a file it must open."""
    table = mp.maps()
    with iso.open("rb") as handle:
        pvd = _read_sector(handle, 16)
        root_extent = int.from_bytes(pvd[158:162], "little")
        root_size = int.from_bytes(pvd[166:170], "little")
        root_all = _names_in_directory(handle, root_extent, root_size, False)
        root_visible = _names_in_directory(handle, root_extent, root_size, True)
        required = ["HPS2_000.01", "E", "MAPS", "PACKAGES"]
        required += [item.map_alias for item in table]
        required += [item.package_alias for item in table]
        required += ["MAPSUI.MAP", "PACKAGESLOAD.RGB", "PACKAGESMENU_AUDIO.HSB",
                     "PACKAGESMENU_TEXTURES.BIN"]
        if "MAPSUI.HP2" in root_all:
            required.append("MAPSUI.HP2")
        hidden = [name for name in required if name not in root_visible]
        if hidden:
            raise RuntimeError("BIOS root sector hides: " + ", ".join(hidden))
        root_map = {name: (extent, size) for name, extent, size in _root_entries(handle)}
        child_need = {
            "E": [item.elf_iso for item in table],
            "PACKAGES": [f"{item.name.upper()}.HSB" for item in table]
            + ["MENU_TEXTURES.BIN", "MENU_AUDIO.HSB", "LOAD.RGB"],
            "MAPS": ["UI.MAP", "A30.MAP", "A50.MAP", "C40.MAP"],
        }
        maps_extent, maps_size = root_map["MAPS"]
        if "UI.HP2" in _names_in_directory(handle, maps_extent, maps_size, False):
            child_need["MAPS"].append("UI.HP2")
        for dirname, needed in child_need.items():
            extent, size = root_map[dirname]
            visible = _names_in_directory(handle, extent, size, True)
            missing = [name for name in needed if name not in visible]
            if missing:
                raise RuntimeError(f"BIOS {dirname}/ sector hides: " + ", ".join(missing))
            print(f"  {dirname}/ {size} bytes, {len(visible)} names in the first sector")
            if dirname == "E":
                for name, file_extent, _file_size in _root_entries_at(handle, extent, size):
                    print(f"  E/{name} LBA {file_extent}")


def _root_entries_at(handle, extent: int, size: int) -> list[tuple[str, int, int]]:
    handle.seek(extent * SECTOR)
    blob = handle.read(size)
    entries = []
    offset = 0
    while offset + 33 <= len(blob):
        record = blob[offset]
        if record == 0:
            offset = (offset + SECTOR - 1) // SECTOR * SECTOR
            continue
        raw = blob[offset + 33:offset + 33 + blob[offset + 32]].split(b";", 1)[0]
        if raw not in (b"\x00", b"\x01"):
            entries.append((
                raw.decode("ascii"),
                int.from_bytes(blob[offset + 2:offset + 6], "little"),
                int.from_bytes(blob[offset + 10:offset + 14], "little"),
            ))
        offset += record
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, required=True, help="menu ELF stored as /HPS2_000.01")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--logo-source", type=Path,
                        default=ROOT / "assets/ps2/boot-logo-ntsc.bin",
                        help="12-sector PS2 logo source (default: bundled NTSC logo)")
    parser.add_argument("--retail-iso", type=Path,
                        help="Halo CE Xbox XISO the menu textures, audio and music are pulled from "
                             "(default: $HALO_RETAIL_XISO, else ~/Documents/Halo/Halo - Combat Evolved.xiso.iso "
                             "when any menu package is missing)")
    parser.add_argument("--menu-dir", type=Path,
                        default=ROOT / "build/halo-ps2-bloodgulch/packages",
                        help="directory with menu_textures.bin, menu_audio.hsb, and load.rgb")
    args = parser.parse_args()
    TMP.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TMPDIR", str(TMP))

    elf = args.elf.resolve()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output = output.resolve()
    if not elf.is_file():
        parser.error(f"missing menu ELF: {elf}")
    if not args.logo_source.is_file():
        parser.error(f"missing PS2 logo source: {args.logo_source}")
    menu_dir = args.menu_dir if args.menu_dir.is_absolute() else ROOT / args.menu_dir
    texture_path = menu_dir / "menu_textures.bin"
    audio_path = menu_dir / "menu_audio.hsb"
    music_path = menu_dir / "menu_music.hms"
    loading_path = menu_dir / "load.rgb"
    packages = (texture_path, audio_path, music_path)
    if args.retail_iso is None and not all(path.is_file() for path in packages):
        # Retail-derived art and audio are never tracked: pull them from the disc.
        candidates = [os.environ.get("HALO_RETAIL_XISO"), str(DEFAULT_RETAIL_XISO)]
        args.retail_iso = next((Path(c).expanduser() for c in candidates if c and Path(c).expanduser().is_file()), None)
        if args.retail_iso is None:
            missing = ", ".join(path.name for path in packages if not path.is_file())
            parser.error(f"missing menu packages ({missing}); pass --retail-iso or set HALO_RETAIL_XISO "
                         "to your Halo CE Xbox XISO")
    if args.retail_iso:
        if not args.retail_iso.is_file():
            parser.error(f"missing retail XISO: {args.retail_iso}")
        menu_dir.mkdir(parents=True, exist_ok=True)
        run("python3", "tools/build_hcu_menu_assets.py", str(args.retail_iso.resolve()),
            "--out", str(output.parent / "menu-assets"), "--package-out", str(texture_path))
        run("python3", "tools/build_hcu_menu_audio.py", str(args.retail_iso.resolve()), str(audio_path))
        run("python3", "tools/build_hcu_menu_music.py", str(args.retail_iso.resolve()), str(music_path))

    table = mp.maps()
    # (iso path, host path, sort weight). ELFs stay inside the BIOS loadelf window.
    sources: list[tuple[str, Path, int]] = [
        ("HPS2_000.01", elf, 300000),
        ("MAPS/UI.MAP", ROOT / "build/retail-maps/decompressed/ui.map", 100000),
        ("MAPS/A30.MAP", ROOT / "build/retail-maps/decompressed/a30.map", 100000),
        ("MAPS/A50.MAP", ROOT / "build/retail-maps/decompressed/a50.map", 100000),
        ("MAPS/C40.MAP", ROOT / "build/retail-maps/decompressed/c40.map", 100000),
    ]
    ui_hp2 = ROOT / "build/hcu-parent-link-probe/maps/ui.hp2"
    if ui_hp2.is_file():
        sources.append(("MAPS/UI.HP2", ui_hp2, 99999))
    for item in table:
        sources.append((f"E/{item.elf_iso}", ROOT / item.elf_path, 200000))
        sources.append((item.map_alias, ROOT / item.map_path, 0))
        sources.append((item.package_alias, ROOT / item.package_path, 0))
        sources.append((f"PACKAGES/{item.name.upper()}.HSB", ROOT / item.hsb_path, 0))
    sources += [
        ("PACKAGES/MENU_TEXTURES.BIN", texture_path, 0),
        ("PACKAGES/MENU_AUDIO.HSB", audio_path, 0),
        ("PACKAGES/LOAD.RGB", loading_path, 0),
    ]
    missing = [f"{iso} ({path})" for iso, path, _weight in sources if not path.is_file()]
    if missing:
        parser.error("missing ISO inputs: " + ", ".join(missing))
    payload = sum(path.stat().st_size for _iso, path, _weight in sources)
    if payload + 8 * 1024 * 1024 > SINGLE_LAYER_DVD_BYTES:
        parser.error(f"payload {payload} bytes cannot fit a single-layer DVD")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hcu-opl-iso-", dir=TMP) as folder:
        system_cnf = Path(folder) / "SYSTEM.CNF"
        system_cnf.write_text("BOOT2 = cdrom0:\\HPS2_000.01;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n",
                              encoding="ascii")
        pad_path = Path(folder) / "ZZPAD.BIN"
        pad_path.write_bytes(bytes(PAD_SECTORS * SECTOR))
        grafts = [f"SYSTEM.CNF={system_cnf}", f"ZZPAD.BIN={pad_path}"]
        weights: list[str] = ["--sort-weight", "500000", "ZZPAD.BIN"]
        for iso, path, weight in sources:
            grafts.append(f"{iso}={path.resolve()}")
            if weight:
                weights.extend(["--sort-weight", str(weight), iso])
        # Some CDVDMAN stacks drop separators. Keep flat names for the menu files.
        for iso, path, _weight in sources:
            if iso.startswith(("MAPS/UI.", "PACKAGES/MENU_", "PACKAGES/LOAD.")):
                grafts.append(f"{iso.replace('/', '')}={path.resolve()}")
        run("xorriso", "-as", "mkisofs", "-iso-level", "2", "--norock",
            "-graft-points", *weights, "-sysid", "PLAYSTATION",
            "-V", "HALO_PS2", "-o", str(output), *grafts)
    publish_dvd_path_table(output)
    try:
        logo_checksum = publish_ps2_logo(output, args.logo_source.resolve())
    except (OSError, ValueError) as error:
        parser.error(str(error))
    assert_bios_directory_window(output)
    size = output.stat().st_size
    print(f"{output}: {size} bytes; payload {payload}; {len(sources)} bundled assets; PS2 logo checksum 0x{logo_checksum:06X}")
    if size > SINGLE_LAYER_DVD_BYTES:
        parser.error(f"ISO is {size} bytes, above the single-layer DVD limit {SINGLE_LAYER_DVD_BYTES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
