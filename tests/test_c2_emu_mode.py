"""apply_emu_mode writes the four recompiler switches only in recompiler mode."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import c2_guest_run as g  # noqa: E402

INI = """[EmuCore]
Foo = 1

[EmuCore/CPU/Recompiler]
EnableEE = false
EnableIOP = false
EnableEECache = false
EnableVU0 = false
EnableVU1 = false

[Filenames]
BIOS = SCPH.bin
"""


def _data(tmp_path: Path, text: str = INI) -> Path:
    ini = tmp_path / "PCSX2/inis/PCSX2.ini"
    ini.parent.mkdir(parents=True)
    ini.write_text(text)
    return tmp_path


def _switches(data: Path) -> dict:
    values, section = {}, None
    for raw in (data / "PCSX2/inis/PCSX2.ini").read_text().splitlines():
        line = raw.strip()
        if line.startswith("["):
            section = line[1:-1]
        elif "=" in line and section == "EmuCore/CPU/Recompiler":
            k, v = (p.strip() for p in line.split("=", 1))
            values[k] = v
    return values


def test_interpreter_leaves_config_untouched(tmp_path):
    data = _data(tmp_path)
    before = (data / "PCSX2/inis/PCSX2.ini").read_text()
    g.apply_emu_mode(data, "interpreter")
    assert (data / "PCSX2/inis/PCSX2.ini").read_text() == before


def test_recompiler_sets_four_switches_only(tmp_path):
    data = _data(tmp_path)
    g.apply_emu_mode(data, "recompiler")
    sw = _switches(data)
    for key in ("EnableEE", "EnableIOP", "EnableVU0", "EnableVU1"):
        assert sw[key] == "true"
    assert sw["EnableEECache"] == "false"
    text = (data / "PCSX2/inis/PCSX2.ini").read_text()
    assert "Foo = 1" in text and "BIOS = SCPH.bin" in text


def test_recompiler_refuses_missing_keys(tmp_path):
    data = _data(tmp_path, "[EmuCore/CPU/Recompiler]\nEnableEE = false\n")
    with pytest.raises(RuntimeError):
        g.apply_emu_mode(data, "recompiler")


def test_unknown_mode_rejected(tmp_path):
    with pytest.raises(ValueError):
        g.apply_emu_mode(_data(tmp_path), "jit")
