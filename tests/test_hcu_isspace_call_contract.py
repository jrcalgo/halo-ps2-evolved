"""Keep CE's direct isspace callers inside the C library's defined domain."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "submodules/halo-ce-universal/source/hs/hs.c"


def test_every_hal_script_isspace_call_converts_char_to_unsigned_char():
    source = SOURCE.read_text()
    calls = [line for line in source.splitlines()
             if "isspace(" in line and "int isspace(" not in line]
    assert len(calls) == 3
    assert all("isspace((unsigned char)" in line for line in calls)
