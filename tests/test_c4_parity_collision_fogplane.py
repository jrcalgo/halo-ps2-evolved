"""C4 structure_fog_plane.runtime_material_type consumer parity.

collision_cluster_fog_plane() (physics/collisions.c, verbatim splice) gates on
runtime_material_type == NONE (collisions.c:357) and exposes the material it
hands to collision->material_type (collisions.c:626). Expected results are an
independent Python restatement of that chain. Host-only fakes for tag blocks and
fog definitions.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
SRC = HCU / "source/physics/collisions.c"
MAIN = ROOT / "tests/c4_parity_collision_fogplane_main.c"
MARKER = "/* CE_COLLISION_FOG_PLANE */"
NONE = -1


def extract_function(text, signature):
    """Definition (not prototype): the occurrence whose body opens before any `;`."""
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if not line.startswith(signature):
            continue
        for opener in range(index, len(lines)):
            if lines[opener] == "{":
                break
            if lines[opener].rstrip().endswith(";"):
                opener = None
                break
        else:
            opener = None
        if opener is None:
            continue
        for end in range(index, len(lines)):
            if lines[end] == "}":
                return "\n".join(lines[index:end + 1]) + "\n"
    raise AssertionError(f"{signature} definition not found")


_EXE = {}


def _executable():
    if "exe" not in _EXE:
        cc = shutil.which(os.environ.get("CC", "gcc"))
        if not cc:
            raise unittest.SkipTest("no C compiler")
        body = extract_function(SRC.read_text(encoding="latin-1"), "static boolean collision_cluster_fog_plane(")
        directory = Path(tempfile.mkdtemp(prefix="c4-fogplane-"))
        source = directory / "main.c"
        source.write_text(MAIN.read_text().replace(MARKER, body))
        exe = directory / "fogplane"
        built = subprocess.run([cc, "-std=gnu99", "-Wall", "-Werror", "-Wno-unused-function",
                                "-Wno-unused-variable", str(source), "-o", str(exe)],
                               capture_output=True, text=True)
        if built.returncode != 0:
            raise AssertionError(built.stdout + built.stderr)
        _EXE["exe"] = exe
    return _EXE["exe"]


def run(fog_reference, material, region=0, palette=0):
    out = subprocess.run([str(_executable()), format(fog_reference & 0xFFFF, "x"), str(material),
                          str(region), str(palette)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    fields = dict(p.split("=") for p in out.stdout.split()[1:])
    return int(fields["found"]), int(fields["material"]), int(fields["fog"])


def oracle(fog_reference, material):
    """collisions.c:355-357 and :626: a NONE material yields no fog; otherwise the plane's material
    is what collision->material_type receives."""
    if not (fog_reference & 0x8000):
        return 0, -999, -999
    if material == NONE:
        return 0, material, -999
    return 1, material, 2


class C4FogPlaneRuntimeMaterialType(unittest.TestCase):
    def test_runtime_material_type_gate_and_material_follow_member(self):
        fog_reference = 0x8000  # bit 15 set, plane index 0
        # NONE gates the fog plane out (collisions.c:357)
        self.assertEqual(run(fog_reference, NONE), oracle(fog_reference, NONE))
        self.assertEqual(run(fog_reference, NONE), (0, NONE, -999))
        # alternative material values pass through to the consumer unchanged (collisions.c:626)
        for material in (0, 5, 28):
            self.assertEqual(run(fog_reference, material), oracle(fog_reference, material))
            self.assertEqual(run(fog_reference, material)[1], material)
        self.assertNotEqual(run(fog_reference, NONE)[0], run(fog_reference, 5)[0])


if __name__ == "__main__":
    unittest.main()
