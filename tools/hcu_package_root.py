"""Locate pinned retail-derived HP2 packages without weakening their hash pins.

Search order: HALO_HCU_M2_PACKAGE_ROOT, the historical /tmp reproduction
directory, then persistent build/mp-fog-selection-*/assets/maps directories.
A directory is accepted only when every requested package exists there and its
SHA-256 equals the caller's pin; nothing is substituted or re-hashed to fit.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_DIR = Path("/tmp/hcu-m2-capacity-repro.P5qdmI/packages")
ENV = "HALO_HCU_M2_PACKAGE_ROOT"
_VERIFIED: dict[tuple[str, int, int], str] = {}


def _sha256(path: Path) -> str:
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    if key not in _VERIFIED:
        _VERIFIED[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _VERIFIED[key]


def candidate_dirs() -> list[Path]:
    dirs = []
    if os.environ.get(ENV):
        dirs.append(Path(os.environ[ENV]))
    dirs.append(LEGACY_DIR)
    dirs.extend(sorted((ROOT / "build").glob("mp-fog-selection-*/assets/maps")))
    return dirs


def resolve_package_dir(pins: dict[str, str]) -> Path | None:
    """Return the first directory whose <name>.hp2 files all match `pins`."""
    for directory in candidate_dirs():
        try:
            if all((directory / f"{name}.hp2").is_file()
                   and _sha256(directory / f"{name}.hp2") == digest
                   for name, digest in pins.items()):
                return directory
        except OSError:
            continue
    return None
