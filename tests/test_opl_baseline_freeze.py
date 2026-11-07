"""Check retained ISO identities against bytes and reject invalid extents."""
import hashlib
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from freeze_opl_baseline import iso_inventory


def image(tmp_path, bad_extent=False):
    blob = bytearray(24 * 2048)
    pvd = 16 * 2048
    blob[pvd:pvd+7] = b'\x01CD001\x01'
    blob[pvd+158:pvd+162] = (20).to_bytes(4, 'little')
    blob[pvd+166:pvd+170] = (2048).to_bytes(4, 'little')
    name = b'HPS2_000.01;1'
    record = bytearray(34 + len(name))
    record[0] = len(record)
    record[2:6] = (25 if bad_extent else 21).to_bytes(4, 'little')
    record[10:14] = (3).to_bytes(4, 'little')
    record[32] = len(name)
    record[33:33+len(name)] = name
    blob[20*2048:20*2048+len(record)] = record
    blob[21*2048:21*2048+3] = b'elf'
    iso = tmp_path / 'fixture.iso'
    iso.write_bytes(blob)
    return iso


def test_inventory_extracts_exact_packaged_elf(tmp_path):
    rows = iso_inventory(image(tmp_path), tmp_path / 'extracted')
    assert rows == [{'path': 'HPS2_000.01', 'lba': 21, 'bytes': 3,
                     'sha256': hashlib.sha256(b'elf').hexdigest(), 'extracted_elf': True}]
    assert (tmp_path / 'extracted/HPS2_000.01').read_bytes() == b'elf'


def test_inventory_rejects_payload_past_end(tmp_path):
    with pytest.raises(ValueError, match='out of bounds'):
        iso_inventory(image(tmp_path, bad_extent=True), tmp_path / 'extracted')
