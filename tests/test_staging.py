"""Exercise bounded buffer ownership with delayed and stale completions."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]

class Staging(unittest.TestCase):
    def test_lifetimes(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'staging'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I'+str(ROOT/'src'), str(ROOT/'tests/staging.c'),
                            str(ROOT/'src/stream/staging.c'), '-o', str(exe)],
                           check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)
