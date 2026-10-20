"""Validate the bounded player-mode frag smoke log against a live actor."""
import re


def parse_grenade_smoke(log: str, grenade_released: bool) -> dict:
    throws = re.findall(
        r"\[play\] grenade throw frag carried (\d+) slot (\d+) mode player eye "
        r"(-?[0-9.]+) (-?[0-9.]+) (-?[0-9.]+) aim (-?[0-9.]+) (-?[0-9.]+) (-?[0-9.]+)",
        log)
    explosions = re.findall(
        r"\[play\] grenade explosion frag slot (\d+) target (actor|probe)"
        r"(?: damage ([0-9.]+) distance ([0-9.]+) shield ([0-9.]+) "
        r"body (-?[0-9.]+) dead (\d+)| outside ([0-9.]+))", log)
    if (not grenade_released or len(throws) != 1 or not explosions or
            float(throws[0][7]) >= 0.0 or any(row[1] != "actor" for row in explosions) or
            "[play] freecam on" in log):
        raise RuntimeError(
            "EE grenade smoke did not throw from the collision player and detonate against the live scenario biped")
    return {
        "throws": len(throws), "carried_after_throw": int(throws[0][0]),
        "slot": int(throws[0][1]), "throw_origin_eye": [float(v) for v in throws[0][2:5]],
        "throw_aim": [float(v) for v in throws[0][5:8]],
        "control": "collision-resolved player (mover_tick_map); freecam disabled",
        "explosions": len(explosions), "target": "live scenario biped collision/vitality state",
    }
