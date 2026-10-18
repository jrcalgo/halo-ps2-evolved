import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from render_reference import clip_polygon,view_vertices,rasterize


class ReferenceGeometry(unittest.TestCase):
    def test_near_clipping_and_camera_convention(self):
        vertices=clip_polygon([(0,0,-1),(1,0,1),(0,1,1)],(0,0,1,-.05))
        self.assertEqual(len(vertices),4)
        self.assertTrue(all(v[2]>=.05-1e-12 for v in vertices))
        point=view_vertices([(2,3,4)],[1,1,1,0,0])[0]
        self.assertEqual(point,(-2,3,1))

    def test_depth_is_order_independent_for_occluding_surfaces(self):
        near=[(2,-1,-1),(2,1,-1),(2,0,1)]
        far=[(4,-2,-2),(4,2,-2),(4,0,2)]
        a,stats=rasterize([near,far],[0,0,0,0,0],32,32)
        b,_=rasterize([far,near],[0,0,0,0,0],32,32)
        self.assertEqual(a,b)
        self.assertGreater(stats['covered_pixels'],0)
        _,empty=rasterize([[(-2,-1,-1),(-2,1,-1),(-2,0,1)]],[0,0,0,0,0],32,32)
        self.assertEqual(empty['covered_pixels'],0)
