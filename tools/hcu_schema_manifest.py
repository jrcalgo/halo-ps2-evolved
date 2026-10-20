"""Export the linked HCU tag schemas as a deterministic JSON manifest.

This reads the 32-bit little-endian PS2 ELF produced by the HCU closure build.
The manifest preserves compiler-derived offsets and nested schema definitions;
it is an input to the offline CTAG converter, not itself a relocation oracle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


FIELD_TYPES = {
    0: "block", 1: "data", 2: "file_data", 3: "reference",
    4: "tag_index", 5: "block_index", 6: "enum", 7: "string",
    8: "reset", 9: "struct", 10: "check", 11: "terminator",
}
FIELD_SIZE = 36
GROUP_SIZE = 16
DEFINITION_SIZE = 12


class SchemaElfError(ValueError):
    pass


class Elf32:
    def __init__(self, path: Path):
        self.path = path
        self.data = path.read_bytes()
        if len(self.data) < 52 or self.data[:7] != b"\x7fELF\x01\x01\x01":
            raise SchemaElfError("expected a 32-bit little-endian ELF")
        header = struct.unpack_from("<16sHHIIIIIHHHHHH", self.data)
        self.phoff, self.shoff = header[5], header[6]
        self.phentsize, self.phnum = header[9], header[10]
        self.shentsize, self.shnum, self.shstrndx = header[11], header[12], header[13]
        if self.phentsize != 32 or self.shentsize != 40:
            raise SchemaElfError("unexpected ELF32 header entry sizes")
        self.segments = []
        for i in range(self.phnum):
            values = struct.unpack_from("<IIIIIIII", self.data, self.phoff + i * 32)
            kind, offset, vaddr, _paddr, filesz, memsz, _flags, _align = values
            if kind == 1 and filesz:
                self.segments.append((vaddr, vaddr + filesz, offset))
        raw_sections = [struct.unpack_from("<IIIIIIIIII", self.data, self.shoff + i * 40)
                        for i in range(self.shnum)]
        names_section = raw_sections[self.shstrndx]
        names = self.data[names_section[4]:names_section[4] + names_section[5]]
        self.sections = {}
        for section in raw_sections:
            name_offset, kind, flags, address, offset, size, link, _info, _align, entsize = section
            end = names.find(b"\0", name_offset)
            name = names[name_offset:end].decode("ascii") if end >= 0 else ""
            self.sections[name] = (kind, flags, address, offset, size, link, entsize)
        self.symbols = self._symbols()

    def _symbols(self):
        section = self.sections.get(".symtab")
        if not section:
            raise SchemaElfError("ELF has no .symtab; linked schema symbols are required")
        _kind, _flags, _address, offset, size, link, entsize = section
        if entsize != 16 or ".strtab" not in self.sections:
            raise SchemaElfError("unsupported ELF symbol table")
        strings_section = self.sections[".strtab"]
        strings = self.data[strings_section[3]:strings_section[3] + strings_section[4]]
        symbols = {}
        for cursor in range(offset, offset + size, entsize):
            name_offset, value, symbol_size, _info, _other, shndx = struct.unpack_from("<IIIBBH", self.data, cursor)
            if not name_offset:
                continue
            end = strings.find(b"\0", name_offset)
            if end < 0:
                raise SchemaElfError("unterminated symbol name")
            name = strings[name_offset:end].decode("ascii", "replace")
            symbols[name] = {"address": value, "size": symbol_size, "section": shndx}
        return symbols

    def read(self, address: int, size: int) -> bytes:
        for start, end, file_offset in self.segments:
            if start <= address and size <= end - address:
                offset = file_offset + address - start
                return self.data[offset:offset + size]
        raise SchemaElfError(f"address {address:#x}+{size:#x} is outside file-backed ELF data")

    def u32(self, address: int) -> int:
        return struct.unpack("<I", self.read(address, 4))[0]

    def string(self, address: int) -> str:
        result = bytearray()
        for offset in range(4096):
            char = self.read(address + offset, 1)[0]
            if not char:
                return result.decode("utf-8", "replace")
            result.append(char)
        raise SchemaElfError(f"schema string at {address:#x} is not terminated")


class SchemaManifest:
    def __init__(self, elf: Elf32):
        self.elf = elf
        self.definitions = {}
        self.active = set()
        self.group_lists = []
        self.groups = []

    def group_codes(self, address: int):
        if not address:
            return None
        groups = []
        for index in range(16):
            value = self.elf.u32(address + index * 4)
            if not value:
                return groups
            groups.append(self.fourcc(value))
        raise SchemaElfError(f"group list at {address:#x} has no terminator")

    @staticmethod
    def fourcc(value: int) -> str:
        raw = value.to_bytes(4, "big")
        return "".join(chr(c) if 0x20 <= c < 0x7F else "?" for c in raw)

    def definition(self, address: int, depth: int = 0):
        if not address:
            raise SchemaElfError("schema field references a null definition")
        if address in self.active or depth > 64:
            raise SchemaElfError(f"recursive or excessively deep schema at {address:#x}")
        if address in self.definitions:
            return address
        self.active.add(address)
        name_ptr, size, fields_ptr = struct.unpack("<III", self.elf.read(address, DEFINITION_SIZE))
        if not size or size > 0x100000 or not fields_ptr:
            raise SchemaElfError(f"invalid schema definition at {address:#x}")
        definition = {"name": self.elf.string(name_ptr), "size": size, "fields": []}
        self.definitions[address] = definition
        for index in range(65536):
            raw = self.elf.read(fields_ptr + index * FIELD_SIZE, FIELD_SIZE)
            kind, field_size, count, flags = struct.unpack_from("<hhhh", raw)
            offset, maximum, target_level, target_offset = struct.unpack_from("<iiii", raw, 8)
            nested, check, name = struct.unpack_from("<III", raw, 24)
            if kind == 11:
                break
            if kind not in FIELD_TYPES or field_size < 0 or count < 0 or offset < 0:
                raise SchemaElfError(f"invalid field {index} in schema {definition['name']}")
            field = {"kind": FIELD_TYPES[kind], "size": field_size, "count": count,
                     "flags": flags & 0xFFFF, "offset": offset, "maximum": maximum,
                     "target_level": target_level, "target_offset": target_offset,
                     "name": self.elf.string(name) if name else ""}
            if kind in (0, 9):
                field["definition"] = self.definition(nested, depth + 1)
            elif kind in (3, 4):
                field["groups"] = self.group_codes(nested)
            end = offset + field_size * count
            if kind == 9 and count > 0:
                end = offset + field_size * (count - 1) + self.definitions[nested]["size"]
            if kind != 10 and (count < 1 or end > size):
                raise SchemaElfError(
                    f"field {field['name']} ({offset}+{field_size}*{count}) exceeds "
                    f"schema {definition['name']} ({size}) at {fields_ptr + index * FIELD_SIZE:#x}")
            definition["fields"].append(field)
        else:
            raise SchemaElfError(f"unterminated fields for schema {definition['name']}")
        self.active.remove(address)
        return address

    def read_group_array(self, name: str):
        symbol = self.elf.symbols.get(name)
        if not symbol or not symbol["address"] or not symbol["size"]:
            raise SchemaElfError(f"linked ELF is missing schema symbol {name}")
        result = []
        for index in range(symbol["size"] // GROUP_SIZE):
            address = symbol["address"] + index * GROUP_SIZE
            group_tag, parent_a, parent_b, definition = struct.unpack("<IIII", self.elf.read(address, GROUP_SIZE))
            if not group_tag:
                return result
            definition_id = self.definition(definition) if definition else None
            result.append({"group": self.fourcc(group_tag),
                           "parents": [self.fourcc(parent) if parent != 0xFFFFFFFF else None
                                       for parent in (parent_a, parent_b)],
                           "definition": definition_id})
        raise SchemaElfError(f"group array {name} has no terminator")

    def build(self):
        list_symbol = self.elf.symbols.get("tag_schema_group_lists")
        if not list_symbol:
            raise SchemaElfError("linked ELF is missing tag_schema_group_lists")
        names = ("tag_schema_object_groups", "tag_schema_model_groups",
                 "tag_schema_collision_groups", "tag_schema_render_groups",
                 "tag_schema_effect_groups", "tag_schema_scenario_groups")
        for index in range(list_symbol["size"] // 4):
            pointer = self.elf.u32(list_symbol["address"] + index * 4)
            if not pointer:
                break
            matches = [name for name in names if self.elf.symbols.get(name, {}).get("address") == pointer]
            if len(matches) != 1:
                raise SchemaElfError(f"schema list pointer {pointer:#x} has no unique linked group array")
            self.group_lists.append(matches[0])
        else:
            raise SchemaElfError("tag_schema_group_lists has no terminator")
        for name in self.group_lists:
            self.groups.extend(self.read_group_array(name))
        custom = self.read_group_array("tag_schema_custom_edition_groups")
        for group in custom:
            group["custom_edition_layout"] = True
        self.groups.extend(custom)
        return {
            "format": "hcu-schema-manifest-v1",
            "elf_sha256": hashlib.sha256(self.elf.data).hexdigest(),
            "group_lists": self.group_lists,
            "groups": self.groups,
            "definitions": {str(address): value for address, value in sorted(self.definitions.items())},
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path, help="linked 32-bit little-endian HCU PS2 ELF")
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = SchemaManifest(Elf32(args.elf)).build()
    except (OSError, SchemaElfError, struct.error) as error:
        parser.exit(2, f"schema export failed: {error}\n")
    output = json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        sys.stdout.write(output)
    print(f"exported {len(manifest['groups'])} groups and {len(manifest['definitions'])} definitions",
          file=sys.stderr)


if __name__ == "__main__":
    main()
