"""Replace explicitly pinned files within a frozen ISO's existing extents."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from freeze_opl_baseline import iso_inventory
from build_hcu_opl_iso import assert_bios_directory_window, assert_diagnostic_elves_have_live_telemetry


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_records(stream, extent, size, replacements, prefix=""):
    stream.seek(extent * 2048)
    directory = bytearray(stream.read(size))
    cursor = 0
    found = set()
    while cursor + 33 <= size:
        length = directory[cursor]
        if not length:
            cursor = (cursor // 2048 + 1) * 2048
            continue
        record = directory[cursor:cursor + length]
        raw = record[33:33 + record[32]].split(b";", 1)[0]
        if raw not in (b"\x00", b"\x01"):
            name = prefix + raw.decode("ascii")
            lba = int.from_bytes(record[2:6], "little")
            old_size = int.from_bytes(record[10:14], "little")
            if record[25] & 2:
                found |= replace_records(stream, lba, old_size, replacements, name + "/")
            elif name in replacements:
                payload = replacements[name].read_bytes()
                if len(payload) > old_size:
                    raise RuntimeError(f"{name}: replacement exceeds frozen slot")
                stream.seek(lba * 2048)
                stream.write(payload)
                stream.write(bytes(old_size - len(payload)))
                directory[cursor + 10:cursor + 14] = len(payload).to_bytes(4, "little")
                directory[cursor + 14:cursor + 18] = len(payload).to_bytes(4, "big")
                found.add(name)
        cursor += length
    stream.seek(extent * 2048)
    stream.write(directory)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--replacements", required=True, type=Path,
                        help="JSON object mapping exact ISO paths to local files")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; select a fresh artifact path")
    replacements = {key: Path(value).resolve() for key, value in
                    json.loads(args.replacements.read_text()).items()}
    for path in replacements.values():
        if not path.is_file():
            parser.error(f"missing replacement {path}")
    work = args.output.parent / (args.output.stem + "-verification")
    work.mkdir(parents=True, exist_ok=False)
    before = iso_inventory(args.baseline, work / "before-elfs")
    old = {row["path"]: row for row in before}
    expected_elfs = {row["path"] for row in before if row["extracted_elf"]}
    if len(expected_elfs) != 14 or not expected_elfs <= replacements.keys():
        parser.error("all 14 frozen ELFs must be replaced")
    for name, path in replacements.items():
        if name not in old or path.stat().st_size > old[name]["bytes"]:
            parser.error(f"replacement does not fit frozen extent: {name}")
    diagnostic_elves = [path for name, path in replacements.items()
                        if name == "HPS2_000.01" or name.endswith(".ELF")]
    try:
        assert_diagnostic_elves_have_live_telemetry(diagnostic_elves)
    except RuntimeError as error:
        parser.error(str(error))
    subprocess.run(["cp", "--reflink=auto", "--", str(args.baseline), str(args.output)], check=True)
    args.output.chmod(0o644)
    with args.output.open("r+b") as stream:
        stream.seek(16 * 2048)
        pvd = bytearray(stream.read(2048))
        pvd[8:40] = b"PLAYSTATION".ljust(32, b" ")
        stream.seek(16 * 2048)
        stream.write(pvd)
        found = replace_records(stream, int.from_bytes(pvd[158:162], "little"),
                                int.from_bytes(pvd[166:170], "little"), replacements)
        assert found == replacements.keys(), (found, replacements.keys())
    after = iso_inventory(args.output, work / "after-elfs")
    assert len(before) == len(after)
    for row in after:
        prior = old[row["path"]]
        assert row["lba"] == prior["lba"]
        if row["path"] in replacements:
            assert row["sha256"] == sha(replacements[row["path"]])
        else:
            assert row == prior
    assert_bios_directory_window(args.output)
    report = {"baseline_sha256": sha(args.baseline), "iso_sha256": sha(args.output),
              "iso_bytes": args.output.stat().st_size, "release_image": False,
              "live_telemetry": True,
              "rebuilt_elf_count": 14, "unchanged_file_count": len(before) - len(replacements),
              "all_extents_preserved": True, "replacements": {
                  name: {"file": str(path), "sha256": sha(path)}
                  for name, path in replacements.items()}}
    (work / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
