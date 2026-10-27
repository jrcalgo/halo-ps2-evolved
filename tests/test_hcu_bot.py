"""Host tests for the C5 deterministic Spartan bot core (src/stream/hcu_bot.c)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NEEDLES = (
    "config: ok", "rng: ok", "roster: ok", "combat: ok", "team: ok", "occlusion: ok",
    "pickup: ok", "weapons: ok", "death/respawn: ok", "determinism: ok", "hash: ok",
    "slots: ok", "roster writes: ok", "hcu_bot tests passed",
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
    # The roster bound is the single C5 seat count (16 - 4 humans), not a local number.
    assert '#include "hcu_c5_limits.h"' in header
    assert "#define HCU_BOT_MAX HCU_C5_BOT_SEATS_MAX" in header
    # No N64 capacity, throttle or cut is imported (Halo-64's MAXIMUM_BOTS, TICKS_BETWEEN_PATHS, SIGHT_RANGE).
    for banned in ("MAXIMUM_BOTS", "TICKS_BETWEEN_PATHS", "SIGHT_RANGE", "PATH_LIFETIME"):
        assert banned not in source, banned


def test_c5_bot_caps_agree_across_modules(tmp_path):
    """HCU_BOT_MAX, HCU_COOP_MAX_BOTS and HCU_LOCAL_BOT_SLOTS must all be the one seat count (12)."""
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    probe = tmp_path / "c5_caps_probe.c"
    probe.write_text(
        '#include <stdio.h>\n'
        '#include "stream/hcu_bot.h"\n'
        '#include "stream/hcu_coop_modes.h"\n'
        '#include "stream/hcu_local_setup.h"\n'
        '#include "stream/hcu_survival.h"\n'
        'int main(void) {\n'
        '  printf("%u %u %u %u %u %u %u\\n", (unsigned)HCU_BOT_MAX, (unsigned)HCU_COOP_MAX_BOTS,\n'
        '    (unsigned)HCU_LOCAL_BOT_SLOTS, (unsigned)HCU_C5_BOT_SEATS_MAX, (unsigned)HCU_COOP_MAX_PLAYERS,\n'
        '    (unsigned)HCU_LOCAL_HUMAN_SLOTS, (unsigned)HCU_BOT_LOCAL_SLOTS);\n'
        '  return 0;\n'
        '}\n'
    )
    exe = tmp_path / "c5_caps_probe"
    subprocess.run([
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Isrc", str(probe), "-o", str(exe),
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    assert result.stdout.split() == ["12", "12", "12", "12", "16", "4", "4"], result.stdout
    limits = (ROOT / "src/stream/hcu_c5_limits.h").read_text()
    assert "#define HCU_C5_BOT_SEATS_MAX (HCU_C5_PLAYER_SEATS - HCU_C5_LOCAL_HUMAN_SLOTS)" in limits
    assert "#define HCU_C5_BOT_MACHINES 3u" in limits and "#define HCU_C5_MACHINE_SEATS 4u" in limits
    for name in ("hcu_bot.h", "hcu_coop_modes.h", "hcu_local_setup.h", "hcu_survival.h"):
        assert '"hcu_c5_limits.h"' in (ROOT / "src/stream" / name).read_text(), name
