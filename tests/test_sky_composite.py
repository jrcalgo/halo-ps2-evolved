"""Static sky composition must preserve colour, alpha, and repeated layer UVs."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'submodules/halo-ps2/tools'))
from halo2ps2.objtex import composite_chicago


class SkyComposite(unittest.TestCase):
    def test_cloud_mask_modulates_colour_and_alpha(self):
        layers = [(1,1,bytes((255,255,255,64)),1,1,2,2),
                  (1,1,bytes((160,180,200,255)),1,1,0,0)]
        self.assertEqual(composite_chicago(layers,1).pixels,bytes((160,180,200,64)))

    def test_stars_multiply_then_add_to_base_sky(self):
        layers = [(1,1,bytes((128,128,128,200)),12,12,2,0),
                  (1,1,bytes((40,20,0,255)),8,8,4,0),
                  (1,1,bytes((50,100,240,255)),1,1,0,0)]
        self.assertEqual(composite_chicago(layers,1).pixels,bytes((70,110,240,200)))

    def test_repeat_scale_is_applied_before_combining(self):
        layer = (2,1,bytes((10,20,30,255,40,50,60,255)),2,1,0,0)
        out = composite_chicago([layer],4).pixels
        self.assertEqual(list(out[0:16:4]),[10,40,10,40])

    def test_unknown_operation_is_rejected(self):
        layers = [(1,1,bytes((0,0,0,0)),1,1,99,0)]*2
        with self.assertRaisesRegex(ValueError,'unsupported'):
            composite_chicago(layers,1)
