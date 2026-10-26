"""Shared host link closure for CE symbols used by the ILP32 MP fixtures.

The MP host fixtures compile CE's object, sound and camera code, which call a
small set of definitions living in translation units the fixtures do not build
(observer.c, matrix_math.c, the PS2 render-interpolation stub, and the unit camera
accessors, which are shimmed; see below).
Rather than compiling those large units, this module copies the exact function
bodies out of the pinned submodule text at build time into one generated TU.
Each extracted body is copied verbatim and must occur exactly once in its source.
The only hand-written definitions are the two fail-loud unit accessor stubs in
c4_unit_camera_unreachable_shim.c.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
HCU = ROOT / "submodules/halo-ce-universal"

# (production file relative to the submodule, function names to extract)
CLOSURE_FUNCTIONS = (
    ("source/math/matrix_math.c", (
        "matrix4x3_rotation_from_vectors",
        "matrix4x3_from_point_and_vectors",
        "matrix4x3_multiply",
    )),
    ("source/camera/observer.c", (
        "observer_up_from_forward",
    )),
    # PS2 target body: NULL selects the CE object datum matrices. The host
    # fixtures never enter interpolation rendering, so this is the live path.
    ("port/ps2/src/ps2_render.c", (
        "render_interpolation_object_node_matrices",
    )),
)

# Functions previously extracted by individual fixtures; the shared TU now
# provides them, so those fixtures must not emit their own copies.
MATRIX_HELPERS_PROVIDED = ("matrix4x3_rotation_from_angles", "matrix4x3_to_point_and_vectors")


def extract_function(source, name):
    """Return the single definition of `name` (verbatim, braces balanced)."""
    pattern = re.compile(r"^[^;{}]*?\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*\{", re.M)
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise AssertionError(f"expected one definition of {name}, found {len(matches)}")
    start = matches[0].start()
    depth = 0
    for index in range(source.index("{", matches[0].start()), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unterminated definition of {name}")


# Unit camera accessors: the real bodies drag in the biped/model graph that no
# MP fixture needs. Fail-loud shim, see c4_unit_camera_unreachable_shim.c.
UNREACHABLE_UNIT_SHIM = Path(__file__).resolve().parent / "c4_unit_camera_unreachable_shim.c"


def write_closure_tu(directory):
    """Write the generated closure TU into `directory` and return its path."""
    parts = ['#include "cseries.h"\n#include "math/real_math.h"\n'
             '#include "objects/objects.h"\n#include "units/units.h"\n'
             '#include "units/unit_definitions.h"\n#include "camera/observer.h"\n'
             '#include "render/render.h"\n']
    for relative, names in CLOSURE_FUNCTIONS:
        source = (HCU / relative).read_text()
        for name in names:
            parts.append(extract_function(source, name) + "\n")
    output = Path(directory) / "c4_ce_host_link_closure.c"
    output.write_text("\n".join(parts))
    return [output, UNREACHABLE_UNIT_SHIM]
