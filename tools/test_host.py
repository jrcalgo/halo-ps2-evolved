"""Run the upstream synthetic converter baseline, with no retail inputs."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
tests = ROOT / "submodules/halo-ps2/tools/tests"
if not tests.is_dir():
    sys.exit("Missing halo-ps2 tests; run bootstrap first.")
env = {key: value for key, value in os.environ.items()
       if key not in ("BSP_FIXTURE", "HP2_FIXTURE", "MODEL_FIXTURE", "ANIM_FIXTURE", "SCEN_FIXTURE", "TEX_FIXTURE")}
env["PYTHONDONTWRITEBYTECODE"] = "1"
for path in sorted(tests.glob("test_*.py")):
    print(f"Running {path.name}", flush=True)
    subprocess.run([sys.executable, "-I", "-B", str(path)], cwd=ROOT, env=env, check=True)
print("Upstream synthetic converter baseline passed; no PS2 runtime was tested.")
