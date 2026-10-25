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


def test_mutable_identity_inflation_from_the_146_biped_run_is_rejected():
    # Fixture shaped like the rejected baseline: 146 unique bipeds, 106 vehicles, identity overflow 3660.
    draws = "unique-bipeds=146 unique-weapons=16 unique-vehicles=106 drawn-identity-overflow=3660"
    result = matrix.c3_3_scene_checks(scene(draws), 4, 4)
    assert not result["checks"]["player_bodies_submitted"]
    assert not result["checks"]["draw_identity_set_complete"]
    assert not result["c3_3_qualified"]


def test_biped_identities_must_be_exactly_one_per_player():
    base = "unique-weapons=4 unique-vehicles=1 drawn-identity-overflow=0"
    assert matrix.c3_3_scene_checks(scene("unique-bipeds=4 " + base), 4, 4)["c3_3_qualified"]
    # One extra identity (respawn or churn) and one missing identity both fail closed.
    assert not matrix.c3_3_scene_checks(scene("unique-bipeds=5 " + base), 4, 4)["c3_3_qualified"]
    assert not matrix.c3_3_scene_checks(scene("unique-bipeds=3 " + base), 4, 4)["c3_3_qualified"]


def test_two_player_scene_has_one_enemy_identity_per_opposing_player():
    lines = ["HALO_PS2_LOCAL c3-snapshot seq=9 active-views=2 biped=2 weapon=2 vehicle=1",
             "HALO_PS2_LOCAL c3-objects-final drawn=40 unique-bipeds=2 unique-weapons=2 unique-vehicles=1 "
             "drawn-identity-overflow=0"]
    result = matrix.c3_3_scene_checks(lines, 2, 2)
    assert result["checks"]["enemies_present"]
    assert result["c3_3_qualified"]
