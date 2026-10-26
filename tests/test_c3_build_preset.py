import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from c3_build_preset import apply_c3_build_preset, make_preset_values

PRESETS = __import__("json").loads((ROOT / "tools/c3_build_presets.json").read_text())


def test_quiet_and_diagnostic_presets_match_make_values():
    for preset in ("quiet", "diagnostic"):
        env = {"HCU_C3": "1", "HCU_C3_BUILD_PRESET": preset}
        resolved = apply_c3_build_preset(env)
        assert resolved["flags"] == PRESETS[preset]
        cli = subprocess.check_output(
            [sys.executable, str(ROOT / "tools/c3_build_preset.py"), "--make-values", preset],
            text=True).strip()
        assert cli == make_preset_values(preset)
        assert len(cli.split()) == 9


def test_explicit_flag_override_wins_over_preset_default():
    env = {"HCU_C3": "1", "HCU_C3_OBJECT_FASTPATH": "0"}
    resolved = apply_c3_build_preset(env)
    assert resolved["name"] == "quiet"
    assert resolved["flags"]["HCU_C3_OBJECT_FASTPATH"] == "0"
    assert env["HCU_C3_OBJECT_VIEW_CACHE"] == "1"


def test_non_c3_environment_is_unchanged():
    env = {"HCU_C3": "0"}
    assert apply_c3_build_preset(env) is None
    assert env == {"HCU_C3": "0"}
