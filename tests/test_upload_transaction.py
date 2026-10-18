"""Exercise actual chain/cache code with every pair-capacity boundary."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT/'submodules/halo-ps2/engine/src'

class UploadTransaction(unittest.TestCase):
    def test_pair_rollback_and_claim_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp)/'upload'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I'+str(ENGINE), str(ROOT/'tests/upload_transaction.c'),
                            *[str(ENGINE/'render'/name) for name in ('upload.c', 'chain.c', 'texcache.c')],
                            '-o', str(exe)], check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)
