from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_hcu_opl_iso import (
    assert_diagnostic_elves_have_live_telemetry,
    assert_release_omits_live_telemetry,
)


def test_release_iso_rejects_live_telemetry(tmp_path):
    elf = tmp_path / "HPS2_000.01"
    elf.write_bytes(b"ELF HALO_PS2_OPL_DIAG_TELEMETRY ready")
    with pytest.raises(RuntimeError, match="OPL diagnostic ISO"):
        assert_release_omits_live_telemetry([elf])


def test_release_iso_accepts_a_play_elf(tmp_path):
    elf = tmp_path / "BLOODGUL.ELF"
    elf.write_bytes(b"ELF play")
    assert_release_omits_live_telemetry([elf])


def test_diagnostic_iso_requires_live_telemetry(tmp_path):
    elf = tmp_path / "HPS2_000.01"
    elf.write_bytes(b"ELF play")
    with pytest.raises(RuntimeError, match="requires live telemetry"):
        assert_diagnostic_elves_have_live_telemetry([elf])
    elf.write_bytes(b"ELF HALO_PS2_OPL_DIAG_TELEMETRY ms=0")
    assert_diagnostic_elves_have_live_telemetry([elf])
