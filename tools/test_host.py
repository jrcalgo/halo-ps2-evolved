"""Run the upstream synthetic converter baseline, with no retail inputs."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
selected = os.environ.get("BUILD_ENV", "native")
if selected == "container":
    from container_run import run
    run("test-host")
    sys.exit(0)
if selected != "native":
    sys.exit("BUILD_ENV must be native or container")
subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, check=True)
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
