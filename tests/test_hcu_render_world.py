"""Host tests for src/stream/hcu_render_world.c (C3.world).

Builds the C driver against the real BSPS v2 converter output for Blood Gulch
BSP0. The fixture is generated with halo2ps2 bspconv from the decompressed map
when it is not already present; the test skips when the map is absent."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine/src"
FIXTURE = ROOT / "build/c3/world/bsp0-bloodgulch.bsps"
MAP = ROOT / "build/retail-maps/decompressed/bloodgulch.map"
TOOLS = ROOT / "submodules/halo-ps2/tools"


def ensure_fixture() -> bool:
    if FIXTURE.exists():
        return True
    if not MAP.exists():
        return False
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path; "
            "from halo2ps2 import bspconv, hp2; "
            "pack = bspconv.convert_map(Path(sys.argv[2]), [0]); "
            "open(sys.argv[3], 'wb').write(hp2.parse(pack).read('BSP0'))")
    subprocess.run([sys.executable, "-c", code, str(TOOLS), str(MAP), str(FIXTURE)], check=True)
    return FIXTURE.exists()


class RenderWorldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not ensure_fixture():
            raise unittest.SkipTest("no decompressed Blood Gulch map to build the BSPS fixture")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.exe = Path(cls.tmp.name) / "hcu_render_world_host"
        subprocess.run(["cc", "-std=gnu11", "-D_EE", "-Wall", "-Wextra", "-Werror",
                        "-Wno-int-to-pointer-cast",
                        "-I", str(ROOT / "tests/hcu_ctag_mount_shim"),
                        "-I", str(ROOT / "tests/hcu_ps2_cache_shim"),
                        "-I", str(ENGINE), "-I", str(ROOT / "src"),
                        "-I", str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
                        "-I", str(ROOT / "submodules/ps2sdk/common/include"),
                        "-I", str(ROOT / "submodules/ps2sdk/ee/include"),
                        str(ROOT / "tests/hcu_render_world_main.c"),
                        str(ROOT / "src/stream/hcu_render_world.c"),
                        str(ENGINE / "world/bsp.c"),
                        "-o", str(cls.exe)], check=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_bind_unbind_reader_and_span_rules(self) -> None:
        result = subprocess.run([str(self.exe), str(FIXTURE)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("host_test=passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
