"""Stress cache key reuse, eviction and cancelled upload claims."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT/'submodules/halo-ps2/engine'
class TextureChurn(unittest.TestCase):
    def test_long_deterministic_churn(self):
        with tempfile.TemporaryDirectory() as temp:
            exe=Path(temp)/'churn'
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',
                            '-I'+str(ENGINE/'src'),str(ROOT/'tests/texture_churn.c'),
                            str(ENGINE/'src/render/texcache.c'),'-o',str(exe)],
                           check=True,capture_output=True)
            subprocess.run([str(exe)],check=True,capture_output=True,timeout=10)
