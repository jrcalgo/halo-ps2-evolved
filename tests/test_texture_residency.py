"""Host regression gates for the actual runtime cache implementation."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
ENGINE=ROOT/'submodules/halo-ps2/engine'


class TextureResidency(unittest.TestCase):
    def test_upload_cap_wrap_and_existing_invariants(self):
        with tempfile.TemporaryDirectory() as temp:
            for source in (ROOT/'tests/texture_residency.c',ENGINE/'tests/test_texcache.c'):
                exe=Path(temp)/source.stem
                subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I'+str(ENGINE/'src'),str(source),str(ENGINE/'src/render/texcache.c'),'-o',str(exe)],check=True,capture_output=True)
                subprocess.run([str(exe)],check=True,capture_output=True)
