"""Host check for the always-on PS2 CE owner counters (C2.6).

Builds tests/hcu_ce_owner_counters_main.c with the host compiler, runs it, and
compiles the producer as a 32-bit (ILP32) object, which the PS2 target uses.
No game data is needed.
"""
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUB = ROOT / "submodules/halo-ce-universal"
OUT = ROOT / "build/m2-c2-r7-objects-pool/ce-counters"
HARNESS = ROOT / "tests/hcu_ce_owner_counters_main.c"
PRODUCER = SUB / "port/ps2/src/ps2_owner_counters.c"
FLAGS = [
    "-DHALO_PS2=1",
    f"-I{SUB / 'port/ps2/include'}",
    f"-I{SUB / 'source'}",
]


def cc():
    for name in ("clang", "gcc", "cc"):
        path = shutil.which(name)
        if path:
            return path
    raise unittest.SkipTest("no host C compiler")


class OwnerCountersTest(unittest.TestCase):
    def test_host_counters(self):
        OUT.mkdir(parents=True, exist_ok=True)
        binary = OUT / "hcu_ce_owner_counters"
        build = subprocess.run(
            [cc(), "-std=gnu99", "-Wall", "-Wextra", "-Werror",
             "-Wno-unused-parameter", *FLAGS, str(HARNESS), "-o", str(binary)],
            capture_output=True, text=True)
        self.assertEqual(build.returncode, 0, build.stderr)
        run = subprocess.run([str(binary)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("pass", run.stdout)

    def test_producer_compiles_ilp32(self):
        OUT.mkdir(parents=True, exist_ok=True)
        obj = OUT / "owner_counters_ilp32.o"
        build = subprocess.run(
            [cc(), "-m32", "-std=gnu89", "-Wall", "-Werror",
             "-Wno-unused-parameter", *FLAGS, "-c", str(PRODUCER), "-o", str(obj)],
            capture_output=True, text=True)
        if build.returncode and "-m32" in build.stderr:
            self.skipTest("no 32-bit host compiler support")
        self.assertEqual(build.returncode, 0, build.stderr)


if __name__ == "__main__":
    unittest.main()
