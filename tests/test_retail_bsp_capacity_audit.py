"""Synthetic cache fixture for the retail structure-BSP capacity audit."""
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"),
               str(ROOT / "submodules/halo-ps2/tools")]

from audit_retail_bsp_capacity import audit_map  # noqa: E402
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402


def _make_map(path: Path, bsp_size: int, *, declared_size: int | None = None) -> None:
    root_size = bsp.SCENARIO_BSPS + 8
    region = bytearray(tagindex.TagIndex.build([
        ("scnr", "levels/test/test", root_size),
        ("sbsp", "levels/test/test_bsp0", 0),
    ]))
    index = tagindex.TagIndex.parse_region(bytes(region), mapinfo.HEADER_SIZE)
    scenario_root = index.entries[0].data_address - index.base
    references_offset = len(region)
    region.extend(bytes(32))
    struct.pack_into("<II", region, scenario_root + 0x5A4,
                     1, index.base + references_offset)
    block_offset = mapinfo.HEADER_SIZE + len(region)
    actual_size = bsp_size if declared_size is None else declared_size
    struct.pack_into("<8I", region, references_offset,
                     block_offset, actual_size, 0x81000000, 0,
                     0x73627370, 0, 0, index.entries[1].tag_id)
    file_size = block_offset + bsp_size
    header = bytearray(mapinfo.HEADER_SIZE)
    struct.pack_into("<6I", header, 0, mapinfo.MAGIC_HEAD, 5, file_size,
                     0, mapinfo.HEADER_SIZE, len(region))
    struct.pack_into("<I", header, 0x7FC, mapinfo.MAGIC_FOOT)
    path.write_bytes(header + region + bytes(bsp_size))


def test_audit_uses_whole_bsp_size_and_capacity(tmp_path):
    capacity = 6 * 1024 * 1024
    _make_map(tmp_path / "large.map", capacity + 4096)
    row = audit_map(tmp_path / "large.map", capacity)
    assert row["structure_bsp_count"] == 1
    assert row["largest_structure_bsp_bytes"] == capacity + 4096
    assert row["raw_bsp_capacity_failures"] == 1
    bsp_row = row["structure_bsps"][0]
    assert bsp_row["file_offset"] > mapinfo.HEADER_SIZE
    assert bsp_row["file_size"] == capacity + 4096
    assert not bsp_row["fits_raw_current_bsp"]


def test_audit_rejects_bsp_extent_outside_map_file(tmp_path):
    _make_map(tmp_path / "truncated.map", 4096, declared_size=8192)
    try:
        audit_map(tmp_path / "truncated.map", 6 * 1024 * 1024)
    except bsp.BspError:
        return
    raise AssertionError("out-of-file BSP extent was accepted")
