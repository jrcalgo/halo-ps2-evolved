"""Snapshot presence cannot substitute for geometry submission by source kind."""
import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "c3_scene_matrix", Path(__file__).resolve().parents[1] / "tools/c2_profile_boot_matrix.py")
matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)


def scene(draws):
    return ["HALO_PS2_LOCAL c3-snapshot seq=300 active-views=4 biped=4 weapon=16 vehicle=8",
            "HALO_PS2_LOCAL c3-objects-final drawn=200 " + draws]


def test_an_unrelated_object_draw_cannot_qualify_required_players_and_vehicles():
    result = matrix.c3_3_scene_checks(scene(""), 4, 4)
    assert result["checks"]["drawn_objects_nonzero"]
    assert not result["checks"]["player_bodies_submitted"]
    assert not result["checks"]["weapons_submitted"]
    assert not result["checks"]["vehicles_submitted"]
    assert not result["c3_3_qualified"]


def test_repeated_draws_of_one_player_do_not_prove_four_players():
    result = matrix.c3_3_scene_checks(scene(
        "submitted-bipeds=200 unique-bipeds=1 unique-weapons=4 unique-vehicles=1 drawn-identity-overflow=0"), 4, 4)
    assert not result["checks"]["player_bodies_submitted"]
    assert not result["c3_3_qualified"]


def test_source_categories_and_identity_capacity_are_required():
    draws = "unique-bipeds=4 unique-weapons=4 unique-vehicles=1 drawn-identity-overflow=0"
    assert matrix.c3_3_scene_checks(scene(draws), 4, 4)["c3_3_qualified"]
    assert not matrix.c3_3_scene_checks(scene(draws.replace("overflow=0", "overflow=1")), 4, 4)["c3_3_qualified"]
