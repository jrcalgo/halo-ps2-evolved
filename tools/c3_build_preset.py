"""Resolve the standard C3 quiet/performance and diagnostic build presets.

The quiet preset keeps runtime diagnostics off while enabling the five C3
features required for the production one-view frame budget.  Explicit
environment overrides remain possible for controlled A/B builds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import MutableMapping


_PRESET_PATH = Path(__file__).with_name("c3_build_presets.json")
_PRESET_BYTES = _PRESET_PATH.read_bytes()
_PRESETS: dict[str, dict[str, str]] = json.loads(_PRESET_BYTES)
_MAKE_VALUE_ORDER = (
    "HCU_C3_REALTIME_SCHEDULER",
    "HCU_C3_OBJECT_FASTPATH",
    "HCU_C3_OBJECT_VIEW_CACHE",
    "HCU_C3_BINDING_SEAL",
    "HCU_C3_SNAPSHOT_INDEX",
    "HCU_C3_OBJECT_PREPARE_CACHE",
    "HCU_C3_TELEMETRY",
    "HCU_C3_TIMING",
    "HCU_C3_MOVEMENT_TRACE",
)


def make_preset_values(name: str) -> str:
    """Return ordered defaults for Make, sourced from the canonical preset file."""
    try:
        flags = _PRESETS[name]
    except KeyError as exc:
        raise ValueError(f"unknown HCU_C3_BUILD_PRESET {name!r}; choose quiet or diagnostic") from exc
    return " ".join(flags[key] for key in _MAKE_VALUE_ORDER)


def apply_c3_build_preset(env: MutableMapping[str, str]) -> dict[str, str] | None:
    """Fill unset C3 flags from the selected preset and return resolved values.

    Non-C3 commands are unchanged.  C3 builds default to ``quiet``; callers can
    request ``diagnostic`` or override individual flags for a deliberate A/B.
    """
    if env.get("HCU_C3") != "1":
        return None
    preset = env.setdefault("HCU_C3_BUILD_PRESET", "quiet")
    try:
        defaults = _PRESETS[preset]
    except KeyError as exc:
        raise ValueError(f"unknown HCU_C3_BUILD_PRESET {preset!r}; choose quiet or diagnostic") from exc
    for key, value in defaults.items():
        env.setdefault(key, value)
    # A trace is an explicit per-build diagnostic and is intentionally outside
    # the quiet/diagnostic preset matrix.
    env.setdefault("HCU_C3_LAG_TRACE", "0")
    flags = {key: env[key] for key in defaults}
    flags["HCU_C3_LAG_TRACE"] = env["HCU_C3_LAG_TRACE"]
    return {"name": preset,
            "flags": flags,
            "preset_config_sha256": hashlib.sha256(_PRESET_BYTES).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--make-values", metavar="PRESET",
                        help="print ordered preset values for tools/ee-world.mk")
    args = parser.parse_args()
    if args.make_values:
        try:
            print(make_preset_values(args.make_values))
        except ValueError as error:
            parser.error(str(error))


if __name__ == "__main__":
    main()
