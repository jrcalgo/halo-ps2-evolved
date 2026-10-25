"""Host tests for the C3 lower-detail object profile (halo-ps2 modelconv.C3_OBJECT_PROFILE).

The unit cases check the vertex clustering and the shared-LOD remap on synthetic parts. The fit case converts the
Slayer needed set of the Blood Gulch 4-player package from its retail source maps with the profile and pins that
the packets and textures fit the C3 objects residency pool with at least 10 % headroom. The fit case skips when the
retail maps or the package manifest are not staged.
"""
import importlib.util
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
sys.path.insert(0, str(ROOT / "tools"))
from halo2ps2 import modelconv as mc  # noqa: E402
from halo2ps2 import texconv  # noqa: E402

spec = importlib.util.spec_from_file_location("hcu_c3_objects_measure", ROOT / "tools/hcu_c3_objects_measure.py")
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)
spec = importlib.util.spec_from_file_location("hcu_c3_object_classes", ROOT / "tools/hcu_c3_object_classes.py")
classes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(classes)

MANIFEST = ROOT / "build/m2-c2-r3-selected-packages/pkg/bloodgulch_mounted_gunner_4p4bot/bloodgulch_mounted_gunner_4p4bot.json"
POOL_BYTES = classes.POOL_BYTES  # one constant: tools/hcu_c3_object_classes.py (budget v5)
HEADROOM = classes.HEADROOM


def synthetic_part(pos, tris):
    n = len(pos)
    return mc.SrcPart(7, list(pos), [(0.0, 0.0, 1.0)] * n, [(0.0, 0.0)] * n, [0] * n, [-1] * n, [32767] * n, list(tris))


class ClusterPartTest(unittest.TestCase):
    def test_zero_cell_is_identity(self):
        part = synthetic_part([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)])
        self.assertIs(mc.cluster_part(part, 0.0), part)

    def test_close_vertices_merge_and_collapsed_triangles_drop(self):
        pos = [(0.0, 0.0, 0.0), (0.01, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)]
        part = synthetic_part(pos, [(0, 2, 3), (1, 2, 4)])
        out = mc.cluster_part(part, 0.1)
        self.assertEqual(len(out.pos), 4)                       # vertices 0 and 1 share a cell
        self.assertEqual(len(out.tris), 2)
        for t in out.tris:
            self.assertEqual(len(set(t)), 3)
        degenerate = synthetic_part(pos, [(0, 1, 2)])           # 0 and 1 merge: the triangle collapses
        self.assertEqual(mc.cluster_part(degenerate, 0.1).tris, [])

    def test_different_skin_influences_never_merge(self):
        pos = [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]
        part = replace(synthetic_part(pos, [(0, 1, 2)]), node0=[0, 1, 0], node1=[-1, -1, -1])
        out = mc.cluster_part(part, 0.5)
        self.assertEqual(len(out.pos), 3)
        self.assertEqual(out.tris, [(0, 1, 2)])


class ObjectClassTest(unittest.TestCase):
    def test_tag_paths_map_to_classes(self):
        cases = {
            "characters\\cyborg\\cyborg": "biped",
            "characters\\cyborg\\fp\\fp": "fp",
            "weapons\\pistol\\fp\\fp": "fp",
            "weapons\\pistol\\pistol": "weapon",
            "equipment\\frag grenade\\frag grenade": "weapon",
            "vehicles\\warthog\\warthog": "vehicle",
            "sky\\mp clear afternoon\\mp clear afternoon": "sky",
            "scenery\\crate\\crate": "other",
        }
        for path, cls in cases.items():
            self.assertEqual(mc.object_class(path), cls, path)

    def test_classlod_validates_slots(self):
        mc.ClassLod((2, 2, 2, 4, 4), 0.02)
        with self.assertRaises(ValueError):
            mc.ClassLod((2, 2, 2, 4), 0.02)
        with self.assertRaises(ValueError):
            mc.ClassLod((2, 2, 2, 4, 5), 0.02)

    def test_missing_class_is_super_low_unclustered(self):
        prof = mc.ObjectProfile("t", 64, 2, (("fp", mc.ClassLod((0, 0, 0, 0, 0), 0.0)),))
        self.assertEqual(prof.class_lod("vehicles\\warthog\\warthog"), mc.ClassLod((4, 4, 4, 4, 4), 0.0))
        self.assertEqual(prof.class_lod("characters\\cyborg\\fp\\fp").slots, (0, 0, 0, 0, 0))


class LodPlanTest(unittest.TestCase):
    def test_plans_keep_every_slot_on_a_stored_lod(self):
        for label, slots in classes.lod_plans():
            self.assertEqual(len(slots), mc.MODEL_LODS, label)
            mc.ClassLod(slots, 0.0)  # validates the slot range
        self.assertIn((2, 2, 2, 4, 4), [s for _l, s in classes.lod_plans()])

    def test_choose_takes_fp_first_then_fits_the_rest(self):
        # (bytes, detail, candidate): fp prefers the big plan, which would starve the biped below its cheapest plan.
        options = {"fp": [(900, 50, 0), (300, 20, 1)], "biped": [(400, 10, 2), (100, 5, 3)], "other": [(50, 1, 4)]}
        picked = classes.choose(options, budget=1000)
        self.assertEqual(picked["fp"], (300, 20, 1))   # 300 + 100 (biped cheapest) + 50 fits; 900 does not
        self.assertEqual(picked["biped"], (400, 10, 2))  # 300 + 400 + 50 = 750 fits
        self.assertEqual(picked["other"], (50, 1, 4))
        with self.assertRaises(ValueError):
            classes.choose(options, budget=100)


class ProfileConstantsTest(unittest.TestCase):
    def test_profile_keeps_textures_at_the_c3_cap(self):
        prof = mc.C3_OBJECT_PROFILE
        self.assertEqual((prof.max_tex, prof.max_levels), (64, 2))
        self.assertEqual({c for c, _l in prof.classes}, set(mc.OBJECT_CLASSES))


@unittest.skipUnless(MANIFEST.is_file(), "Blood Gulch 4p package manifest not staged")
class NeededSetFitTest(unittest.TestCase):
    def test_slayer_needed_set_fits_pool_with_headroom(self):
        manifest = json.loads(MANIFEST.read_text())
        for row in manifest["source_maps"].values():
            if not (ROOT / row["path"]).is_file():
                self.skipTest(f"retail map {row['path']} not staged")
        maps = classes.load_maps(manifest)
        models = classes.model_list(manifest)
        self.assertEqual(len(models), 28)
        rows = classes.class_table(mc.C3_OBJECT_PROFILE, models, maps)
        total = sum(r["bytes"] for r in rows)
        print("\nC3 object profile, per class (slots = stored LOD per engine LOD 0..4, 0 = super high):")
        print(f"{'class':8} {'slots':>16} {'cluster':>8} {'models':>6} {'packets':>9} {'textures':>9} {'bytes':>9}")
        for r in rows:
            print(f"{r['class']:8} {str(r['slots']):>16} {r['cluster_fraction']:8.3f} {r['models']:6d} "
                  f"{r['packets']:9d} {r['textures']:9d} {r['bytes']:9d}")
        print(f"{'total':8} {'':>16} {'':>8} {sum(r['models'] for r in rows):6d} {sum(r['packets'] for r in rows):9d} "
              f"{sum(r['textures'] for r in rows):9d} {total:9d}")
        print(f"pool {POOL_BYTES} B, budget {classes.BUDGET} B, headroom "
              f"{100 * (1 - total / POOL_BYTES):.1f} % of the pool, near triangles "
              f"{sum(r['near_triangles'] for r in rows)}")
        self.assertLessEqual(total, classes.BUDGET, f"needed set {total} B")
        self.assertGreater(total, 0)


@unittest.skipUnless(MANIFEST.is_file(), "Blood Gulch 4p package manifest not staged")
class TwoLevelPickTest(unittest.TestCase):
    """A two-level plan keeps a near and a far geometry; every engine LOD slot must still name a stored geometry."""

    def test_two_level_plan_on_a_real_biped(self):
        manifest = json.loads(MANIFEST.read_text())
        for row in manifest["source_maps"].values():
            if not (ROOT / row["path"]).is_file():
                self.skipTest(f"retail map {row['path']} not staged")
        maps = classes.load_maps(manifest)
        model = next(m for m in classes.model_list(manifest) if m["path"] == "characters\\cyborg\\cyborg")
        prof = mc.ObjectProfile("two-level-test", 64, 2, (("biped", mc.ClassLod((2, 2, 2, 4, 4), 0.03)),))
        md = mc.convert_map(maps[model["key"]], [model["datum"]], object_profile=prof).models[0]
        self.assertTrue(md.perms)
        for p in md.perms:
            self.assertEqual(len(p.geometry), mc.MODEL_LODS)
            self.assertEqual(p.geometry[0], p.geometry[2])
            self.assertEqual(p.geometry[3], p.geometry[4])
            self.assertTrue(all(g >= 0 for g in p.geometry))
            self.assertTrue(all(g in md.geometries and md.geometries[g] for g in p.geometry))
        near = {p.geometry[0] for p in md.perms}
        far = {p.geometry[3] for p in md.perms}
        self.assertTrue(near and far)
        if near != far:
            self.assertFalse(near & far)


if __name__ == "__main__":
    unittest.main()


def test_c3_object_profile_v3_adds_far_first_person_level():
    """v3 = v2 plus a clustered far fp level (engine slots 2..4); v2 keeps its own table and name."""
    import sys
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
    from halo2ps2 import modelconv as mc
    v2, v3 = mc.C3_OBJECT_PROFILE, mc.C3_OBJECT_PROFILE_V3
    assert v2.name == "c3-ps2-object-v2" and v3.name == "c3-ps2-object-v3"
    fp2, fp3 = dict(v2.classes)["fp"], dict(v3.classes)["fp"]
    assert fp2.slots == (0, 0, 0, 0, 0) and fp2.far_cluster_fraction == 0.0
    assert fp3.slots == (0, 0, 2, 2, 2) and fp3.far_from == 2 and fp3.far_cluster_fraction == 0.20
    for name in ("biped", "vehicle", "weapon", "sky", "other"):
        assert dict(v2.classes)[name] == dict(v3.classes)[name]
