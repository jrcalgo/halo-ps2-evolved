import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_hcu_profile_media_coverage as audit  # noqa: E402


def test_model_texture_owner_is_explicitly_otex_covered():
    entry = SimpleNamespace(tag_id=7)
    row = audit.classify_bitmap(entry, [{"group": "soso"}], {7})
    assert row["status"] == "covered_by_model_OTEX"
    assert "world.c" in row["consumer"]


def test_effect_and_ui_bitmaps_remain_explicitly_blocked():
    entry = SimpleNamespace(tag_id=7)
    assert audit.classify_bitmap(entry, [{"group": "part"}], set())["status"] == "unsupported_effect_sprite_texture"
    assert audit.classify_bitmap(entry, [{"group": "font"}], set())["status"] == "unsupported_UI_texture"


def test_unowned_required_bitmap_is_not_admitted():
    row = audit.classify_bitmap(SimpleNamespace(tag_id=8), [], set())
    assert row == {"status": "unsupported_unbound_bitmap", "consumer": None}
