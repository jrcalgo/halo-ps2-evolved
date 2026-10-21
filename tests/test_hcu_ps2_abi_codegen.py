from pathlib import Path
import subprocess
import sys


def test_hcu_abi_layout_and_target_codegen():
	root = Path(__file__).resolve().parents[1]
	result = subprocess.run(
		[sys.executable, str(root / "tools/hcu_ps2_abi_host.py")],
		cwd=root, check=True, text=True, capture_output=True)
	assert "emits stores, loads, and comparisons" in result.stdout
