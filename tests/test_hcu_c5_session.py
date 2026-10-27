"""Host tests for the C5 integration session (src/stream/hcu_c5_session.c) with fake CE hooks.

The C test (tests/hcu_c5_session_main.c) covers start order, refusals, the survival loop, the metrics and the
marker lines. Here the hash is recomputed in Python from the field dump the C test prints, to check the documented
order: FNV-1a 64 over little-endian u32/u64 fields in the order written in hcu_c5_session.h.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    "tests/hcu_c5_session_main.c",
    "src/stream/hcu_c5_session.c",
    "src/stream/hcu_bot.c",
    "src/stream/hcu_coop_ce_bind.c",
    "src/stream/hcu_coop_modes.c",
    "src/stream/hcu_local_setup.c",
    "src/stream/hcu_survival.c",
]
FNV_OFFSET = 0xCBF29CE484222325
FNV_PRIME = 0x100000001B3
MASK64 = (1 << 64) - 1


def fnv1a64(data: bytes) -> int:
    value = FNV_OFFSET
    for byte in data:
        value ^= byte
        value = (value * FNV_PRIME) & MASK64
    return value


def parse_dump(text: str, begin: str, end: str) -> dict:
    fields = {}
    body = text.split(begin, 1)[1].split(end, 1)[0]
    for line in body.strip().splitlines():
        name, _, rest = line.partition(" ")
        fields[name] = rest.split()
    return fields


def fold(fields: dict) -> int:
    """Hash order from hcu_c5_session.h: domain, mode, tick, bot hash u64, survival, budgets, metrics."""
    stream = bytearray()

    def u32(value: int) -> None:
        stream.extend((value & 0xFFFFFFFF).to_bytes(4, "little"))

    def u64(value: int) -> None:
        stream.extend((value & MASK64).to_bytes(8, "little"))

    u32(int(fields["domain"][0], 0))
    u32(int(fields["mode"][0]))
    u32(int(fields["tick"][0]))
    u64(int(fields["bot_hash"][0], 0))
    for name in ("survival_state", "wave", "living", "active", "reserved", "batch",
                 "intermission", "waves_cleared", "enemies_admitted", "humans_respawned"):
        u32(int(fields[name][0]))
    for value in fields["budgets"]:
        u32(int(value))
    for name in ("kills", "deaths", "respawns", "nav", "fights", "score"):
        u32(int(fields[name][0]))
    return fnv1a64(bytes(stream))


@pytest.fixture(scope="module")
def session_run(tmp_path_factory):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    exe = tmp_path_factory.mktemp("c5-session") / "hcu_c5_session_test"
    subprocess.run([
        compiler, "-std=gnu89", "-Wall", "-Wextra", "-Werror", "-Isrc",
        *SOURCES, "-o", str(exe),
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    return result


def test_session_host_contract(session_run):
    assert session_run.returncode == 0, session_run.stdout + session_run.stderr
    for needle in (
        "coop start: ok",
        "refusals: ok",
        "mapping: ok",
        "survival: ok",
        "hash-order: ok",
        "survival-hash: ok",
        "hcu_c5_session tests passed",
    ):
        assert needle in session_run.stdout, needle
    assert "FAIL" not in session_run.stdout


def test_coop_hash_follows_documented_order(session_run):
    fields = parse_dump(session_run.stdout, "hash-fields begin", "hash-fields end")
    assert int(fields["mode"][0]) == 1  # coop
    expected = int(fields["hash"][0], 0)
    assert fold(fields) == expected


def test_survival_hash_follows_documented_order(session_run):
    fields = parse_dump(session_run.stdout, "survival-hash-fields begin", "survival-hash-fields end")
    assert int(fields["mode"][0]) == 2  # survival
    assert int(fields["wave"][0]) == 1
    expected = int(fields["hash"][0], 0)
    assert fold(fields) == expected


def test_order_is_sensitive_to_field_position(session_run):
    """Swapping two adjacent survival fields must change the hash (the order is part of the contract)."""
    fields = parse_dump(session_run.stdout, "survival-hash-fields begin", "survival-hash-fields end")
    base = fold(fields)
    swapped = dict(fields)
    swapped["wave"], swapped["living"] = fields["living"], fields["wave"]
    assert fold(swapped) != base
