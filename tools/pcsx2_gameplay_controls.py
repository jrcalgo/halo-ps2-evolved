#!/usr/bin/env python3
"""Apply the project's desktop gameplay keys to an isolated PCSX2 data path."""

import argparse
import json
from pathlib import Path


PAD1_BINDINGS = {
    # Arrow keys drive CE's look stick; leave the D-pad unbound to avoid overlap.
    "Up": "", "Right": "", "Down": "", "Left": "",
    "RUp": "Keyboard/Up", "RRight": "Keyboard/Right",
    "RDown": "Keyboard/Down", "RLeft": "Keyboard/Left",
    "L3": "Keyboard/Control",  # CE crouch: Xbox left thumb button.
    "R2": "Keyboard/F",        # CE primary fire: Xbox right trigger.
    "Cross": "Keyboard/G",     # CE jump: Xbox A.
}


def apply_gameplay_controls(data_dir: Path, *, show_fps: bool = False) -> Path:
    ini = data_dir / "PCSX2/inis/PCSX2.ini"
    original = ini.read_text()
    updates = {"Pad1": PAD1_BINDINGS}
    if show_fps:
        updates["EmuCore/GS"] = {
            "OsdShowFPS": "true", "OsdShowVPS": "true", "OsdShowSpeed": "true",
        }
    seen = set()
    section = ""
    lines = []
    for raw in original.splitlines(keepends=True):
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
        elif "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates.get(section, {}):
                newline = "\n" if raw.endswith("\n") else ""
                raw = f"{key} = {updates[section][key]}{newline}"
                seen.add((section, key))
        lines.append(raw)
    missing = [(section, key) for section, values in updates.items()
               for key in values if (section, key) not in seen]
    if missing:
        raise ValueError(f"PCSX2 profile is missing binding/settings keys: {missing}")
    backup = ini.with_suffix(".ini.before-gameplay-controls")
    if not backup.exists():
        backup.write_text(original)
    ini.write_text("".join(lines))
    return ini


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True,
                        help="isolated -datapath directory; PCSX2 must be stopped")
    parser.add_argument("--show-fps", action="store_true",
                        help="show PCSX2's FPS, VPS and emulation-speed overlay")
    args = parser.parse_args()
    ini = apply_gameplay_controls(args.data, show_fps=args.show_fps)
    print(json.dumps({"ini": str(ini), "bindings": PAD1_BINDINGS,
                      "show_fps": args.show_fps}, indent=2))


if __name__ == "__main__":
    main()
