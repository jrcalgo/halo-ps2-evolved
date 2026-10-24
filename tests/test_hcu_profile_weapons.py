import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))

from hcu_profile_weapons import (bitmap_image_record, find_weapon_root,
                                 validate_cube_record)  # noqa: E402
from halo2ps2.bitmaps import BitmapError, BitmapImage, parse_images  # noqa: E402


def test_bitmap_record_admits_decodable_2d_image():
    image = BitmapImage(32, 32, 1, 0, 14, 131, 5, 4096, 768, 0)
    row = bitmap_image_record("weapons\\fuel rod gun\\bitmaps\\shadow beam contrail", 7, image)
    assert row["decodable"] is True
    assert (row["width"], row["height"], row["mip_count"]) == (32, 32, 5)
    assert row["error"] is None
    assert row["extent"] == {"offset": 4096, "bytes": 768}


def test_bitmap_record_rejects_unsupported_cube_shape():
    image = BitmapImage(64, 64, 1, 2, 14, 131, 6, 8192, 16896, 0)
    row = bitmap_image_record("characters\\cyborg\\bitmaps\\reflection armor", 8, image)
    assert row["decodable"] is False
    assert "type=2" in row["error"]


def test_bitmap_parser_rejects_corrupt_tag_bounds():
    try:
        parse_images(b"\0" * 32, 0, 0)
    except BitmapError as exc:
        assert "outside the tag region" in str(exc)
    else:
        raise AssertionError("corrupt bitmap tag bounds were accepted")


def test_cube_payload_sizes_match_six_face_mip_layout():
    banshee = BitmapImage(64, 64, 1, 2, 14, 131, 6, 100, 16896, 0)
    grunt = BitmapImage(64, 64, 1, 2, 6, 137, 6, 200, 66048, 0)
    banshee_record = validate_cube_record(banshee)
    grunt_record = validate_cube_record(grunt)
    assert banshee_record["extent_valid"] is True
    assert banshee_record["face_mip_bytes_before_padding"] == 2744
    assert banshee_record["face_padding_bytes"] == 72
    assert grunt_record["extent_valid"] is True
    assert grunt_record["face_mip_bytes_before_padding"] == 10922
    assert grunt_record["face_padding_bytes"] == 86


def test_cube_payload_rejects_truncated_extent():
    truncated = BitmapImage(64, 64, 1, 2, 14, 131, 6, 100, 16895, 0)
    assert validate_cube_record(truncated)["extent_valid"] is False


def test_weapon_root_lookup_resolves_exact_path_and_fails_closed():
    class Entry:
        group = "weap"
        path = r"weapons\gravity rifle\gravity rifle"

    assert find_weapon_root([Entry()], Entry.path) is not None
    try:
        find_weapon_root([], Entry.path)
    except ValueError as exc:
        assert "found 0" in str(exc)
    else:
        raise AssertionError("missing weapon root did not fail closed")
