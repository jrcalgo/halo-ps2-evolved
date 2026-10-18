"""Raw GS comparison rejects incomplete or unsuccessful readback evidence."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from compare_visibility import framebuffer


class FramebufferEvidence(unittest.TestCase):
    def test_complete_and_corrupt_records(self):
        head='[fb] begin frame=120 w=512 h=448 psm=10 addr=0 ret=1\n'
        rows='\n'.join('[fb] '+str(i)+' '+'00'*1024 for i in range(448))
        text='[fb] guards=ok bytes=458752\n'+head+rows+'\n[fb] end frame=120\n'
        self.assertEqual(len(framebuffer(text)),458752)
        for bad in (text.replace('ret=1','ret=0'),text.replace('[fb] 7 ','[fb] 8 '),text.replace('[fb] end','[unfinished]'),head+text,text.replace('[fb] guards=ok','[fb] guards=missing')):
            with self.assertRaises(RuntimeError):framebuffer(bad)
