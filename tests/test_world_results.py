"""Incomplete routes and resource failures must never qualify as M10 evidence."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from qualify_world import observe


def log():
    line='[prof] frames={frame} ee prep avg=7.0 tris=3000 batches=200 tex hit=80 up=1/64KB defer=0 fail=0 free=100pg chain=8000qw clip=20b/60/250 skip=0 drop=0'
    return '\n'.join(('[obj] sky model: drawn','[tex] 15 lightmap page slots',
                      '[cam] scripted path: 12 keys, 300.0 s loop',
                      line.format(frame=60),line.format(frame=9001),'[done] frames=9001 dropped=0'))


class WorldEvidence(unittest.TestCase):
    def test_full_route_records_resource_usage(self):
        out=observe(log(),'route')
        self.assertEqual(out['frames'],9001)
        self.assertEqual(out['chain_high_qwords'],8000)
        self.assertEqual(out['texture_upload_kb_max_window'],64)

    def test_truncation_and_missing_camera_are_rejected(self):
        for text in (log().replace('[done]','[unfinished]'),
                     log().replace('frames=9001','frames=180'),
                     log().replace('scripted path:','missing path:'),
                     log().replace('frames=9001 ee prep','frames=30 ee prep')):
            with self.assertRaises(RuntimeError): observe(text,'route')

    def test_renderer_resource_failures_are_rejected(self):
        for text in (log()+'\n[err] failed',log().replace('fail=0','fail=1'),
                     log().replace('skip=0','skip=2'),log().replace('drop=0','drop=1'),
                     log().replace('chain=8000','chain=32769')):
            with self.assertRaises(RuntimeError): observe(text,'route')

    def test_scripted_path_cannot_pass_as_pad_traversal(self):
        with self.assertRaisesRegex(RuntimeError,'scripted camera'):
            observe(log(),'freecam')
