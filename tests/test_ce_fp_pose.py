"""Assault rifle and shotgun first-person idles stay at the Halo CE camera pose.

The gun node is a child of the right wrist. Frame 0 of each retail idle places
the assault rifle 6.7 cm forward of the eye and the shotgun 17.9 cm. Both
meshes extend behind the port's 5 cm near plane, which is why the stock's
back faces the view. The port applies that idle with no added offset.
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))

from halo2ps2 import texconv  # noqa: E402
from halo2ps2.animconv import MapTags, decode, read_graph  # noqa: E402
from halo2ps2.modelconv import read_model  # noqa: E402
from halo2ps2.scenconv import Region, WEAPON_FP_ANIM, first_person_idle  # noqa: E402

MAPS = ROOT / "data/retail/weapon-audit-maps"
NEAR = 0.05


def _mul(a, b):
    return [[sum(a[i][j] * b[j][k] for j in range(4)) for k in range(4)] for i in range(4)]


def _trs(q, t):
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    k = 2.0 / n if n else 0.0
    xx, yy, zz = x * x * k, y * y * k, z * z * k
    xy, xz, yz = x * y * k, x * z * k, y * z * k
    wx, wy, wz = w * x * k, w * y * k, w * z * k
    return [
        [1.0 - yy - zz, xy + wz, xz - wy, 0.0],
        [xy - wz, 1.0 - xx - zz, yz + wx, 0.0],
        [xz + wy, yz - wx, 1.0 - xx - yy, 0.0],
        [t[0], t[1], t[2], 1.0],
    ]


def _pose(weapon: str, model_path: str, world_map: str):
    data = texconv.MapData.open(MAPS / world_map)
    region = Region(data)
    weap = next(e for e in data.index.entries if e.group == "weap" and e.path == weapon)
    _group, anim_id = region.tagref(region.block(weap) + WEAPON_FP_ANIM)
    entry = region.entry(anim_id)
    tags = MapTags(MAPS / world_map)
    graph = read_graph(tags, next(e for e in tags.idx.entries if e.tag_id == anim_id))
    anim = graph.anims[first_person_idle(region, region.block(entry))]
    decoded = decode(anim)
    rot = [decoded.rot[i][0] for i in range(anim.node_count)]
    trans = [decoded.trans[i][0] for i in range(anim.node_count)]
    parents = [(-1 if i == 0 else node.parent) for i, node in enumerate(graph.nodes)]
    world = [None] * anim.node_count
    pending = set(range(anim.node_count))
    while pending:
        ready = [i for i in pending if parents[i] < 0 or parents[i] not in pending]
        if not ready:
            raise AssertionError("cycle in " + weapon)
        for i in ready:
            local = _trs(rot[i], trans[i])
            parent = parents[i]
            world[i] = local if parent < 0 else _mul(local, world[parent])
            pending.remove(i)
    gun = next(i for i, node in enumerate(graph.nodes) if node.name == "frame gun")
    wrist = graph.nodes[gun].parent
    model = read_model(data, next(
        e for e in data.index.entries
        if e.group == "mode" and e.path == model_path
    ))
    xs = [p[0] for parts in model.geometries.values() for part in parts for p in part.pos]
    return world[gun][3][:3], world[wrist][3][:3], min(xs), max(xs)


class CeFirstPerson(unittest.TestCase):
    def test_rifle_and_shotgun_stay_on_the_idle(self):
        rifle, rifle_hand, rifle_min, rifle_max = _pose(
            r"weapons\assault rifle\assault rifle", r"weapons\assault rifle\fp\fp", "a10.map")
        shotgun, shotgun_hand, shotgun_min, shotgun_max = _pose(
            r"weapons\shotgun\shotgun", r"weapons\shotgun\fp\fp", "bloodgulch.map")
        self.assertLess(math.dist(rifle, (0.0674, -0.0396, -0.0889)), 0.001)
        self.assertLess(math.dist(shotgun, (0.1790, -0.0341, -0.0445)), 0.001)
        # The stock reaches behind the eye, so the 5 cm near plane cuts it.
        self.assertLess(rifle[0] + rifle_min, NEAR)
        self.assertLess(shotgun[0] + shotgun_min, NEAR)
        self.assertGreater(rifle_max, 0.15)
        self.assertGreater(shotgun_max, 0.15)
        self.assertLess(rifle_hand[0], rifle[0])
        self.assertLess(shotgun_hand[0], shotgun[0])


if __name__ == "__main__":
    unittest.main()
