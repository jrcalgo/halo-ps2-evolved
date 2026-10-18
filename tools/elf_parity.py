"""Compare loaded ELF32 little-endian sections, excluding debug/path metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def loaded(path):
    data = Path(path).read_bytes()
    if len(data) < 52 or data[:6] != b"\x7fELF\x01\x01":
        raise ValueError("Expected an ELF32 little-endian file: " + str(path))
    header = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
    offset, size, count, names_index = header[6], header[11], header[12], header[13]
    if size < 40 or offset + size * count > len(data) or names_index >= count:
        raise ValueError("Invalid section table: " + str(path))
    sections = [struct.unpack_from("<10I", data, offset + i * size) for i in range(count)]
    names = sections[names_index]
    strings = data[names[4]:names[4] + names[5]]
    result = {}
    for section in sections:
        if not section[2] & 2:
            continue
        end = strings.find(b"\0", section[0])
        if end < 0:
            raise ValueError("Unterminated section name")
        name = strings[section[0]:end].decode("ascii")
        if name in result:
            raise ValueError("Repeated allocated section name: " + name)
        if section[1] != 8 and section[4] + section[5] > len(data):
            raise ValueError("Section extends beyond its file: " + name)
        result[name] = {
            "type": section[1], "flags": section[2], "address": section[3],
            "size": section[5], "alignment": section[8],
            "sha256": None if section[1] == 8 else hashlib.sha256(data[section[4]:section[4] + section[5]]).hexdigest(),
        }
    return {"type": header[1], "machine": header[2], "entry": header[4], "flags": header[7], "sections": result}


def compare(left, right):
    a, b = loaded(left), loaded(right)
    return {"status": "passed" if a == b else "failed", "left": str(left), "right": str(right),
            "normalized": a if a == b else {"left": a, "right": b},
            "limits": "ELF header and allocatable section identity only; no execution was performed."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = compare(args.left, args.right)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"] + ": normalized ELF parity")
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
