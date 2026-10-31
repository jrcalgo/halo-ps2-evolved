#!/usr/bin/env python3
"""Single multiplayer map table for the ISO builder and the menu chain-load.

Menu index order matches src/stream/hcu_main_menu.c labels. The generated
header src/stream/hcu_map_table.h is what the menu and hcu_main.c include.
Group B reads gametype_mask: bit 0 CTF, 1 King, 2 Slayer, 3 Oddball, 4 Race,
5 Team Slayer (the hcu_main_menu.h enum). Slayer and Team Slayer are always
set. The other bits come from scenario.netgame_flags at tag offset 0x378,
element stride 148, type field at +16.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))

# Bits match enum hcu_main_menu_game_type.
GAMETYPE_CTF = 1 << 0
GAMETYPE_KING = 1 << 1
GAMETYPE_SLAYER = 1 << 2
GAMETYPE_ODDBALL = 1 << 3
GAMETYPE_RACE = 1 << 4
GAMETYPE_TEAM_SLAYER = 1 << 5
FLAG_STRIDE = 148
FLAG_BLOCK = 0x378

# index, label, scenario stem, 8-char ELF token, map 8.3 alias, package 8.3 alias
ROWS = (
    (0, "BATTLE CREEK", "beavercreek", "BEAVERCR", "BEAVER.MAP", "BCPKG.HCP"),
    (1, "SIDEWINDER", "sidewinder", "SIDEWIND", "SIDEWI.MAP", "SWPKG.HCP"),
    (2, "DAMNATION", "damnation", "DAMNATIO", "DAMNAT.MAP", "DMPKG.HCP"),
    (3, "RAT RACE", "ratrace", "RATRACE", "RATRAC.MAP", "RRPKG.HCP"),
    (4, "PRISONER", "prisoner", "PRISONER", "PRISON.MAP", "PRPKG.HCP"),
    (5, "HANG 'EM HIGH", "hangemhigh", "HANGEMHI", "HANGEM.MAP", "HHPKG.HCP"),
    (6, "CHILL OUT", "chillout", "CHILLOUT", "CHILLO.MAP", "COPKG.HCP"),
    (7, "DERELICT", "carousel", "CAROUSEL", "CAROUS.MAP", "CAPKG.HCP"),
    (8, "BOARDING ACTION", "boardingaction", "BOARDING", "BOARDI.MAP", "BAPKG.HCP"),
    (9, "BLOOD GULCH", "bloodgulch", "BLOODGUL", "BGMAP.MAP", "BGMP.HCP"),
    (10, "WIZARD", "wizard", "WIZARD", "WIZARD.MAP", "WZPKG.HCP"),
    (11, "CHIRON TL-34", "putput", "PUTPUT", "PUTPUT.MAP", "PPPKG.HCP"),
    (12, "LONGEST", "longest", "LONGEST", "LONGEST.MAP", "LNPKG.HCP"),
)


class MpMap:
    def __init__(self, index, label, name, token, map_alias, package_alias, gametype_mask):
        self.index = index
        self.label = label
        self.name = name
        self.token = token
        self.map_alias = map_alias
        self.package_alias = package_alias
        self.gametype_mask = gametype_mask

    @property
    def row(self) -> str:
        return f"{self.name}_mounted_gunner_4p4bot"

    @property
    def scenario(self) -> str:
        return f"levels\\test\\{self.name}\\{self.name}"

    @property
    def map_path(self) -> str:
        return f"build/retail-maps/decompressed/{self.name}.map"

    @property
    def package_path(self) -> str:
        return f"build/c3/{self.name}/pkg/{self.row}/{self.row}.hcp"

    @property
    def hsb_path(self) -> str:
        return f"build/c3/{self.name}/{self.name}.hsb"

    @property
    def elf_iso(self) -> str:
        return f"HPS2_C3_{self.token}.ELF"

    @property
    def elf_path(self) -> str:
        return f"build/c3/{self.name}/{self.elf_iso}"

    @property
    def elf_cdrom(self) -> str:
        # The BIOS directory cache is one 2048-byte sector. The 13 guest ELFs
        # live in E/ so the root sector can hold every map and package alias.
        return f"cdrom0:\\E\\{self.elf_iso};1"


def _flag_types(map_path: Path) -> set[int]:
    from halo2ps2.tagcache import CacheMap

    data = map_path.read_bytes()
    cache = CacheMap(data)
    scenario = next(tag for tag in cache.tags if tag.group == "scnr")
    base = cache.off(scenario.data_addr)
    count, addr, _defin = struct.unpack_from("<III", cache.buf, base + FLAG_BLOCK)
    if not 0 < count <= 400:
        raise RuntimeError(f"{map_path.name} netgame_flags count {count}")
    element = cache.off(addr)
    types = set()
    for i in range(count):
        typ, _team = struct.unpack_from("<hh", cache.buf, element + i * FLAG_STRIDE + 16)
        if not 0 <= typ <= 8:
            raise RuntimeError(f"{map_path.name} flag {i} type {typ}")
        types.add(typ)
    return types


def gametype_mask_for(name: str) -> int:
    types = _flag_types(ROOT / f"build/retail-maps/decompressed/{name}.map")
    mask = GAMETYPE_SLAYER | GAMETYPE_TEAM_SLAYER
    if 0 in types:
        mask |= GAMETYPE_CTF
    if 8 in types:
        mask |= GAMETYPE_KING
    if 2 in types:
        mask |= GAMETYPE_ODDBALL
    if 3 in types:
        mask |= GAMETYPE_RACE
    return mask


def maps() -> list[MpMap]:
    return [MpMap(*row, gametype_mask_for(row[2])) for row in ROWS]


def optical_path(relative: str) -> str:
    return "cdrom:\\" + relative.replace("/", "\\").upper()


def new_alias_rows(table: list[MpMap]) -> list[tuple[str, str]]:
    """Alias rows that are not already in the legacy iso9660 table."""
    rows = []
    for item in table:
        rows.append((optical_path(item.package_path), f"cdrom:\\{item.package_alias}"))
        if item.map_alias not in ("BEAVER.MAP", "BGMAP.MAP"):
            rows.append((optical_path(item.map_path), f"cdrom:\\{item.map_alias}"))
    return rows


def _c_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def render_header(table: list[MpMap]) -> str:
    lines = [
        "/* Generated by tools/hcu_mp_map_table.py. Do not edit. */",
        "/* Group B: gametype_mask bits match enum hcu_main_menu_game_type. */",
        "/* bit0 CTF, bit1 King of the Hill, bit2 Slayer, bit3 Oddball, bit4 Race, bit5 Team Slayer. */",
        "/* Slayer and Team Slayer are always set. Other bits require a scenario netgame flag */",
        "/* (scenario + 0x378, stride 148; type 0 CTF, 8 hill, 2 oddball, 3 race). */",
        "#ifndef HCU_MAP_TABLE_H",
        "#define HCU_MAP_TABLE_H",
        "",
        "#include <stdint.h>",
        "",
        "#define HCU_MP_MAP_COUNT 13",
        "#define HCU_MP_GAMETYPE_CTF (1u << 0)",
        "#define HCU_MP_GAMETYPE_KING (1u << 1)",
        "#define HCU_MP_GAMETYPE_SLAYER (1u << 2)",
        "#define HCU_MP_GAMETYPE_ODDBALL (1u << 3)",
        "#define HCU_MP_GAMETYPE_RACE (1u << 4)",
        "#define HCU_MP_GAMETYPE_TEAM_SLAYER (1u << 5)",
        "",
        "typedef struct hcu_mp_map {",
        "\tconst char *label;",
        "\tconst char *name;",
        "\tconst char *scenario;",
        "\tconst char *elf; /* cdrom0:\\\\E\\\\HPS2_C3_<TOKEN>.ELF;1 */",
        "\tuint32_t gametype_mask;",
        "} hcu_mp_map;",
        "",
        "static const hcu_mp_map hcu_mp_maps[HCU_MP_MAP_COUNT] = {",
    ]
    for item in table:
        lines.append(
            f'\t{{ "{_c_string(item.label)}", "{item.name}", "{_c_string(item.scenario)}", '
            f'"{_c_string(item.elf_cdrom)}", {item.gametype_mask}u }},'
        )
    lines += [
        "};",
        "",
        "static inline int hcu_mp_map_supports(unsigned map, unsigned game_type)",
        "{",
        "\tif (map >= HCU_MP_MAP_COUNT || game_type > 5u)",
        "\t\treturn 0;",
        "\treturn (hcu_mp_maps[map].gametype_mask & (1u << game_type)) != 0;",
        "}",
        "",
        "#endif",
        "",
    ]
    return "\n".join(lines)


def check_iso9660(table: list[MpMap]) -> None:
    header = (ROOT / "submodules/halo-ps2/engine/src/stream/iso9660_name.h").read_text()
    missing = []
    for src, dst in new_alias_rows(table):
        c_src = src.replace("\\", "\\\\")
        c_dst = dst.replace("\\", "\\\\")
        if c_src not in header or c_dst not in header:
            missing.append(f"{src} -> {dst}")
    if missing:
        raise SystemExit("iso9660_name.h is missing alias rows:\n" + "\n".join(missing))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-header", type=Path,
                        default=ROOT / "src/stream/hcu_map_table.h")
    parser.add_argument("--check", action="store_true",
                        help="verify the generated header and iso9660 aliases, then print the table")
    args = parser.parse_args()
    table = maps()
    text = render_header(table)
    if args.check:
        current = args.write_header.read_text()
        if current != text:
            raise SystemExit(f"{args.write_header} does not match the map table")
        check_iso9660(table)
    else:
        args.write_header.write_text(text)
    for item in table:
        print(f"{item.index:2} {item.name:16} mask=0x{item.gametype_mask:02x} "
              f"{item.elf_iso} {item.map_alias} {item.package_alias}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
