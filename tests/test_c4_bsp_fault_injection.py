"""C4 item 5: fault injection at the PS2 CBSP decode/relocation/publication seams.

The C harness (tests/c4_bsp_fault_harness_main.c) links the production
ps2_cbsp.c decoder unmodified. Each case is a deliberately damaged copy of one
clean synthetic CBSP payload. Every case asserts the status classification
recorded before the run, that the previously published image is byte-identical,
that the candidate guard and neighbour-owner canaries are intact, and that a
clean retry into the same candidate reproduces the Python oracle's bytes.

Boundaries covered here are the C decoder ones: header/parse, section
directory (table sizing), per-section CRC, relocation rows (references and
domains), materialize/rebase writes (address/space), overlap, and streamed
short reads. Ownership/publication boundaries in ps2_cache.c and CE
scenario.c are covered by the existing suites named in the C4 report.
"""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.cbsp import CbspError, decode, encode  # noqa: E402

PORT = ROOT / "submodules/halo-ce-universal/port/ps2"
HARNESS = ROOT / "tests/c4_bsp_fault_harness_main.c"
DECODER = PORT / "src/ps2_cbsp.c"
BSP_BASE = 0x02000000
TAG_BASE = 0x01400000
HEADER_BYTES = 36

# Python oracle gaps against the C decoder, pinned so they cannot drift silently.
# tools/cbsp.py decode unpacks each relocation row with "<IB3xI" and ignores the
# three padding bytes; ps2_cbsp.c rejects nonzero padding with PS2_CBSP_ERR_BOUNDS.
KNOWN_PYTHON_GAPS = {
    "row_padding_nonzero": "tools/cbsp.py ignores relocation-row padding bytes",
}

# Status codes from include/ps2_cbsp.h, as printed by the harness.
OK, TRUNCATED, FORMAT, BOUNDS, CHECKSUM, SPACE, ADDRESS, OVERLAP = range(8)
NOT_REACHED = -1
STATUS_NAMES = {OK: "OK", TRUNCATED: "TRUNCATED", FORMAT: "FORMAT",
                BOUNDS: "BOUNDS", CHECKSUM: "CHECKSUM", SPACE: "SPACE",
                ADDRESS: "ADDRESS", OVERLAP: "OVERLAP", NOT_REACHED: "NOT_REACHED"}


def clean_image() -> bytes:
    image = bytearray(256)
    struct.pack_into("<I", image, 0, 64)      # dom0: BSP-internal pointer
    struct.pack_into("<I", image, 8, 16)      # dom1: CTAG string at 16
    struct.pack_into("<I", image, 16, 200)    # dom0: BSP-internal pointer
    struct.pack_into("<I", image, 28, 128)    # dom1: CTAG string at 128
    struct.pack_into("<I", image, 40, 0)      # dom0: null pointer, allowed
    image[20:24] = b"psbs"
    return bytes(image)


RELOCS = ((0, 64), (16, 200), (40, 0))       # (field, dom0 target)
TAG_RELOCS = ((8, 16), (28, 128))            # (field, dom1 target)


def clean_tag() -> bytes:
    tag = bytearray(256)
    tag[16:22] = b"tagA\0\0"
    tag[128:135] = b"shader\0"
    return bytes(tag)


def late_fail_tag() -> bytes:
    """Row for field 8 (target 16) terminates at once; row for field 28
    (target 128) has no NUL in its 128-byte window, so it is the late reject."""
    tag = bytearray(b"x" * 256)
    tag[16] = 0
    return bytes(tag)


def recrc(payload: bytearray) -> bytes:
    image_size = struct.unpack_from("<I", payload, 8)[0]
    struct.pack_into("<I", payload, 20, zlib.crc32(bytes(payload[36:36 + image_size])) & 0xFFFFFFFF)
    return bytes(payload)


def build_cases():
    """Return (name, mode, max_image, max_relocs, dest_size, payload, tag, expected)."""
    clean = encode(clean_image(), tuple(r[0] for r in RELOCS), TAG_RELOCS,
                   source_file_offset=2048, source_file_size=256)
    tag = clean_tag()
    cases = []

    def add(name, mode, payload, expected_open, expected_op, *, tag_bytes=None,
            max_image=4096, max_relocs=1000000, dest=512):
        cases.append(dict(name=name, mode=mode, payload=bytes(payload),
                          tag=tag_bytes or tag, max_image=max_image,
                          max_relocs=max_relocs, dest=dest,
                          expected_open=expected_open, expected_op=expected_op))

    # Header/parse boundary.
    add("truncated_header", "W", clean[:30], TRUNCATED, NOT_REACHED)
    add("truncated_header_stream", "S", clean[:30], TRUNCATED, NOT_REACHED)
    b = bytearray(clean); b[0:4] = b"CBSX"
    add("bad_magic", "W", recrc(b), FORMAT, NOT_REACHED)
    b = bytearray(clean); struct.pack_into("<I", b, 4, 2)
    add("bad_version", "W", recrc(b), FORMAT, NOT_REACHED)
    add("trailing_bytes", "W", clean + b"\0" * 4, FORMAT, NOT_REACHED)
    b = bytearray(clean); struct.pack_into("<I", b, 32, 1)
    add("reserved_header_nonzero", "W", recrc(b), FORMAT, NOT_REACHED)
    add("trailing_bytes_stream", "S", clean + b"\0" * 4, FORMAT, NOT_REACHED)

    # Section directory / counts / truncation.
    b = bytearray(clean); struct.pack_into("<I", b, 12, len(RELOCS) + len(TAG_RELOCS) + 1)
    add("count_plus_one", "W", b, TRUNCATED, NOT_REACHED)
    b = bytearray(clean); struct.pack_into("<I", b, 12, len(RELOCS) + len(TAG_RELOCS) + 1)
    add("count_plus_one_stream", "S", b, FORMAT, NOT_REACHED)
    add("count_over_maximum", "W", clean, BOUNDS, NOT_REACHED, max_relocs=1)
    add("count_over_maximum_stream", "S", clean, BOUNDS, NOT_REACHED, max_relocs=1)
    add("image_over_capacity", "W", clean, BOUNDS, NOT_REACHED, max_image=128)
    add("image_over_capacity_stream", "S", clean, BOUNDS, NOT_REACHED, max_image=128)
    b = bytearray(clean); struct.pack_into("<I", b, 8, 256 + 4)
    add("image_size_inflated", "W", b, TRUNCATED, NOT_REACHED)
    add("image_size_inflated_stream", "S", b, BOUNDS, NOT_REACHED)
    add("truncated_image_tail", "W", clean[:HEADER_BYTES + 128], TRUNCATED, NOT_REACHED)
    add("truncated_image_stream", "S", clean[:HEADER_BYTES + 128], TRUNCATED, NOT_REACHED)
    add("truncated_table_tail", "W", clean[:-12], TRUNCATED, NOT_REACHED)
    add("truncated_table_stream", "S", clean[:-12], FORMAT, NOT_REACHED)
    add("upload_half_stream", "S", clean[:len(clean) // 2], TRUNCATED, NOT_REACHED)
    add("upload_short_one_byte_stream", "S", clean[:-1], FORMAT, NOT_REACHED)

    # Per-section decode and CRC.
    b = bytearray(clean); b[100] ^= 1
    add("image_bitflip_crc", "W", b, CHECKSUM, NOT_REACHED)
    add("image_bitflip_crc_stream", "S", b, CHECKSUM, NOT_REACHED)
    b = bytearray(clean); b[HEADER_BYTES + 20:HEADER_BYTES + 24] = b"PSBS"
    add("image_magic_not_psbs", "W", recrc(b), FORMAT, NOT_REACHED)
    b = bytearray(clean); b[20] ^= 1
    add("header_crc_mismatch", "W", b, CHECKSUM, NOT_REACHED)
    b = bytearray(clean); struct.pack_into("<I", b, 28, 255)
    add("source_extent_mismatch", "W", b, BOUNDS, NOT_REACHED)
    add("source_extent_mismatch_stream", "S", b, BOUNDS, NOT_REACHED)
    b = bytearray(clean); struct.pack_into("<I", b, 24, 0xFFFFFFFF)
    add("source_extent_unknown_with_size", "W", b, FORMAT, NOT_REACHED)

    # Relocation rows: malformed references and domains (CRC kept valid).
    table = HEADER_BYTES + 256

    def row_mut(index, offset, value, size):
        b = bytearray(clean)
        at = table + index * 12 + offset
        b[at:at + size] = value.to_bytes(size, "little")
        return b

    b = row_mut(0, 4, 7, 1)
    add("domain_out_of_range", "W", b, BOUNDS, NOT_REACHED)
    add("domain_out_of_range_stream", "S", b, BOUNDS, NOT_REACHED)
    b = row_mut(0, 5, 1, 1)
    add("row_padding_nonzero", "W", b, BOUNDS, NOT_REACHED)
    b = row_mut(0, 0, 2, 4)
    add("field_unaligned", "W", b, BOUNDS, NOT_REACHED)
    b = row_mut(4, 0, 256, 4)
    add("field_past_image", "W", b, BOUNDS, NOT_REACHED)
    b = bytearray(clean)
    rows = [bytes(b[table + i * 12:table + (i + 1) * 12]) for i in range(5)]
    rows[0], rows[1] = rows[1], rows[0]
    b[table:table + 60] = b"".join(rows)
    add("rows_unsorted", "W", b, BOUNDS, NOT_REACHED)
    b = bytearray(clean); struct.pack_into("<I", b, HEADER_BYTES + 16, 201)
    add("reference_target_mismatch", "W", recrc(b), FORMAT, NOT_REACHED)
    b = bytearray(clean)
    struct.pack_into("<I", b, HEADER_BYTES + 16, 300)
    struct.pack_into("<I", b, table + 2 * 12 + 8, 300)
    add("dom0_target_outside_image", "W", recrc(b), BOUNDS, NOT_REACHED)
    b = bytearray(clean); struct.pack_into("<I", b, HEADER_BYTES + 40, 5)
    add("last_row_target_mismatch_stream", "S", recrc(b), FORMAT, NOT_REACHED)

    # Partial relocation: the rebase walk rejects the late CTAG row (row 3 of 5)
    # after rows 0-2 were valid. Validation precedes writes, so the candidate
    # must still hold the unrelocated image and the retry must succeed.
    add("late_row_unterminated_tag_stream", "S", clean, OK, BOUNDS,
        tag_bytes=late_fail_tag())
    add("late_row_unterminated_tag_whole", "W", clean, OK, BOUNDS,
        tag_bytes=late_fail_tag())

    # Capacity: materialize and rebase destinations too small for the image.
    add("destination_one_short", "W", clean, OK, SPACE, dest=255)
    add("destination_short_stream", "S", clean, OK, SPACE, dest=128)

    # Overlap and address ranges.
    add("table_aliases_image", "OT", clean, OVERLAP, NOT_REACHED)
    add("bsp_tag_address_overlap", "OB", clean, OK, ADDRESS)
    return cases, clean


def run_harness(binary, work, cases, clean, expected):
    (work / "clean.cbsp").write_bytes(clean)
    (work / "clean_tag.bin").write_bytes(clean_tag())
    (work / "expected.bin").write_bytes(expected)
    manifest_lines = []
    for index, case in enumerate(cases):
        payload_path = work / f"case{index}.cbsp"
        tag_path = work / f"case{index}_tag.bin"
        payload_path.write_bytes(case["payload"])
        tag_path.write_bytes(case["tag"])
        manifest_lines.append(
            f"{case['name']} {case['mode']} {case['max_image']} {case['max_relocs']} "
            f"{case['dest']} {payload_path} {tag_path}")
    (work / "manifest.txt").write_text("\n".join(manifest_lines) + "\n")
    run = subprocess.run([str(binary), str(work / "clean.cbsp"),
                          str(work / "clean_tag.bin"), str(work / "expected.bin"),
                          str(work / "manifest.txt")],
                         capture_output=True, text=True)
    return run


def parse_case_lines(stdout):
    results = {}
    for line in stdout.splitlines():
        if not line.startswith("CASE "):
            continue
        parts = line.split()
        fields = dict(part.split("=", 1) for part in parts[3:])
        results[parts[1]] = dict(
            mode=parts[2], open=int(fields["open"]), op=int(fields["op"]),
            raw=fields["raw"] == "1", pub=fields["pub"], guards=fields["guards"],
            retry=fields["retry"])
    return results


class C4BspFaultInjectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which("cc") or shutil.which("gcc")
        if not cc:
            raise unittest.SkipTest("no C compiler for the CBSP fault harness")
        cls.tmp = Path(tempfile.mkdtemp(prefix="c4-bsp-fault-"))
        cls.binary = cls.tmp / "c4_bsp_fault_harness"
        compiled = subprocess.run([
            cc, "-std=c89", "-Wall", "-Wextra", "-Werror", "-no-pie",
            "-I" + str(PORT / "include"), str(HARNESS), str(DECODER),
            "-o", str(cls.binary)], capture_output=True, text=True)
        if compiled.returncode != 0:
            raise AssertionError(compiled.stdout + compiled.stderr)
        cls.cases, cls.clean = build_cases()
        cls.expected = decode(cls.clean, max_image_size=4096).materialize(
            BSP_BASE, TAG_BASE, clean_tag())
        cls.harness_run = run_harness(cls.binary, cls.tmp, cls.cases, cls.clean, cls.expected)
        cls.results = parse_case_lines(cls.harness_run.stdout)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_harness_ran_every_case(self):
        self.assertEqual(self.harness_run.returncode, 0, self.harness_run.stdout + self.harness_run.stderr)
        self.assertEqual(sorted(self.results), sorted(c["name"] for c in self.cases))

    def test_each_fault_has_expected_classification_and_canaries(self):
        for case in self.cases:
            with self.subTest(case=case["name"]):
                got = self.results[case["name"]]
                self.assertEqual(got["open"], case["expected_open"],
                                 f"open status {STATUS_NAMES.get(got['open'])}")
                self.assertEqual(got["op"], case["expected_op"],
                                 f"op status {STATUS_NAMES.get(got['op'])}")
                # Previously published image unchanged (rollback target intact).
                self.assertEqual(got["pub"], "ok")
                # No write escaped the candidate range or the owner neighbour.
                self.assertEqual(got["guards"], "ok")
                # A same-candidate clean retry reproduces the Python oracle bytes.
                self.assertEqual(got["retry"], "ok")

    def test_streamed_partial_relocation_leaves_candidate_unrelocated(self):
        for name in ("late_row_unterminated_tag_stream", "destination_short_stream"):
            with self.subTest(case=name):
                self.assertTrue(self.results[name]["raw"],
                                "rejected rebase must not write relocated pointers")

    def test_python_oracle_rejects_payload_only_faults(self):
        # The Python decoder must refuse every payload-only fault that the C
        # decoder refuses at open time, except the harness-only capacity and
        # overlap seams, which are C-API concepts.
        skip = {"count_over_maximum", "count_over_maximum_stream",
                "image_over_capacity", "image_over_capacity_stream",
                "table_aliases_image", "destination_one_short",
                "destination_short_stream", "bsp_tag_address_overlap",
                "late_row_unterminated_tag_stream", "late_row_unterminated_tag_whole"}
        for case in self.cases:
            if case["name"] in skip or case["expected_open"] == OK:
                continue
            if case["name"] in KNOWN_PYTHON_GAPS:
                # Pinned gap: the oracle must still accept it, so a fix to
                # tools/cbsp.py forces this entry to be removed.
                decode(case["payload"], max_image_size=4096)
                continue
            with self.subTest(case=case["name"]):
                with self.assertRaises(CbspError):
                    decode(case["payload"], max_image_size=4096)

    def test_clean_retry_matches_oracle_for_every_mode(self):
        self.assertEqual(self.results["late_row_unterminated_tag_stream"]["retry"], "ok")
        self.assertEqual(self.results["bsp_tag_address_overlap"]["retry"], "ok")


if __name__ == "__main__":
    unittest.main()
