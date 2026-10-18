"""Topology validation must reject broken links and inconsistent portal planes."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_visibility import topology


def fixture():
    clusters=[{'first_batch':0,'batch_count':0,'first_portal':i,'portal_count':1} for i in range(2)]
    return SimpleNamespace(clusters=clusters,batches=[],cluster_batches=[],cluster_portals=[0,0],
        portals=[{'a':0,'b':1,'first_vertex':0,'vertex_count':4,'plane':(1,0,0,0)}],
        portal_vertices=[(0,-1,-1),(0,1,-1),(0,1,1),(0,-1,1)],
        nodes=[(0,0x80000000,0x80000001)],planes=[(1,0,0,0)],leaves=[0,1])


class VisibilityTopology(unittest.TestCase):
    def test_reciprocal_connected_portal(self):
        r=topology(fixture())
        self.assertEqual(r['errors'],[])
        self.assertEqual(r['components'],[[0,1]])

    def test_missing_reciprocal_link(self):
        s=fixture();s.clusters[1]['portal_count']=0
        self.assertIn('nonreciprocal_portal',[e[0] for e in topology(s)['errors']])

    def test_bad_plane_and_reversed_sides_are_rejected(self):
        for kind in ('plane','sides'):
            s=fixture()
            if kind=='plane':s.portals[0]['plane']=(1,0,0,1)
            else:s.portals[0].update(a=1,b=0)
            self.assertTrue(topology(s)['errors'])
