"""Host tests for the C5 deterministic Spartan bot core (src/stream/hcu_bot.c)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NEEDLES = (
    "config: ok", "rng: ok", "roster: ok", "combat: ok", "team: ok", "occlusion: ok",
    "pickup: ok", "weapons: ok", "death/respawn: ok", "determinism: ok", "hash: ok",
    "slots: ok", "hcu_bot tests passed",
)


def test_bot_host_contract(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    exe = tmp_path / "hcu_bot_test"
    subprocess.run([
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-Isrc", "tests/hcu_bot_main.c", "src/stream/hcu_bot.c", "-o", str(exe),
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    for needle in NEEDLES:
        assert needle in result.stdout, needle


def test_bot_module_is_c89_clean_and_heap_free():
    source = (ROOT / "src/stream/hcu_bot.c").read_text()
    header = (ROOT / "src/stream/hcu_bot.h").read_text()
    for banned in ("malloc(", "calloc(", "realloc(", "sqrt(", "sqrtf(", "#include <math.h>"):
        assert banned not in source, banned
    # Bot slots live after the four local slots, never inside them.
    assert "HCU_BOT_PLAYER_SLOT_BASE HCU_BOT_LOCAL_SLOTS" in header
    assert "HCU_BOT_MAX 8u" in header
    # No N64 capacity, throttle or cut is imported (Halo-64's MAXIMUM_BOTS, TICKS_BETWEEN_PATHS, SIGHT_RANGE).
    for banned in ("MAXIMUM_BOTS", "TICKS_BETWEEN_PATHS", "SIGHT_RANGE", "PATH_LIFETIME"):
        assert banned not in source, banned
