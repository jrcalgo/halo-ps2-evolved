"""Host tests for the MODL strip vertex format (halo-ps2 modelconv.FORMAT_STRIP).

The strip format packs each batch as one triangle strip with degenerate stitches (20 B per strip vertex instead
of 60 B per triangle). The synthetic cases check the greedy stripifier and its decoder on meshes. The retail case
converts the Slayer needed set of the Blood Gulch 4-player package in both formats and asserts that every batch
decodes to the same oriented triangles with the same vertex attributes (position, uv, skin nodes, weight, normal).
It also writes the byte accounting to build/c3/object-strip/. The case skips when the retail maps or the package
manifest are not staged. The engine refuses FORMAT_STRIP until the VU1 model program draws it (see the report).
"""
import importlib.util
import json
import random
import struct
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
sys.path.insert(0, str(ROOT / "tools"))
from halo2ps2 import modelconv as mc  # noqa: E402
from halo2ps2 import texconv  # noqa: E402

spec = importlib.util.spec_from_file_location("hcu_c3_objects_measure", ROOT / "tools/hcu_c3_objects_measure.py")
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)

MANIFEST = ROOT / "build/m2-c2-r3-selected-packages/pkg/bloodgulch_mounted_gunner_4p4bot/bloodgulch_mounted_gunner_4p4bot.json"
OUT_DIR = ROOT / "build/c3/object-strip"


def grid(n):
    """2 n*n consistently oriented triangles on an (n+1) x (n+1) vertex grid."""
    v = lambda i, j: i * (n + 1) + j
    tris = []
    for i in range(n):
        for j in range(n):
            a, b, c, d = v(i, j), v(i, j + 1), v(i + 1, j), v(i + 1, j + 1)
            tris += [(a, b, d), (a, d, c)]
    return tris


def canon(t):
    k = t.index(min(t))
    return tuple(t[k:] + t[:k])


class StripSyntheticTest(unittest.TestCase):
    def test_grid_meshes_round_trip_in_any_order(self):
        for n in (1, 2, 3, 4, 5):
            for seed in range(3):
                tris = grid(n)
                random.Random(seed).shuffle(tris)
                for s in range(0, len(tris), mc.MAX_BATCH_TRIS):
                    chunk = tris[s:s + mc.MAX_BATCH_TRIS]
                    pieces = mc.strip_split(chunk)
                    got = []
                    for sub, seq in pieces:
                        self.assertLessEqual(len(seq), mc.MAX_STRIP_VERTS)
                        self.assertEqual(sorted(map(canon, mc.strip_windows(seq))), sorted(map(canon, sub)))
                        got += sub
                    self.assertEqual(sorted(map(canon, got)), sorted(map(canon, chunk)))

    def test_strip_is_shorter_than_expanded(self):
        tris = grid(4)[:mc.MAX_BATCH_TRIS]
        self.assertLess(len(mc.strip_sequence(tris)), 3 * len(tris))

    def test_packet_sizes(self):
        for tris in range(1, mc.MAX_BATCH_TRIS + 1):
            self.assertEqual(mc.strip_packet_bytes(3 * tris), mc.bspconv.packet_bytes(tris))


def _vertex_key(v):
    return (v["pos"], v["uv"], v["nodes"], v["weight"], v["normal"])


def _batch_key(tris):
    return Counter(canon(tuple(_vertex_key(v) for v in t)) for t in tris)


def _packet_scale(sec, batch):
    """The quantization step of a batch packet (position = centre + s16 * scale)."""
    return struct.unpack_from("<f", sec.vif, batch["vif_offset"] + 16)[0]


def _same_triangles(old, new, tol):
    """Same oriented triangles up to the position quantization. uv, nodes, weight and normal must match exactly
    (identical encoding in both formats); positions match within tol (a split strip packet has its own centre and
    scale). A triangle matches a candidate under one of its three cyclic rotations (winding is kept)."""
    def attrs(v):
        return (v["uv"], v["nodes"], v["weight"], v["normal"])

    def matches(t, cand):
        for r in range(3):
            ok = True
            for k in range(3):
                a, b = t[(k + r) % 3], cand[k]
                if attrs(a) != attrs(b) or any(abs(x - y) > tol for x, y in zip(a["pos"], b["pos"])):
                    ok = False
                    break
            if ok:
                return True
        return False

    if len(old) != len(new):
        return False
    pool = list(new)
    for t in old:
        hit = next((j for j, cand in enumerate(pool) if matches(t, cand)), None)
        if hit is None:
            return False
        pool.pop(hit)
    return True


@unittest.skipUnless(MANIFEST.is_file(), "Blood Gulch 4p package manifest not staged")
class RetailStripRoundTripTest(unittest.TestCase):
    def test_slayer_needed_set_decodes_identically(self):
        manifest = json.loads(MANIFEST.read_text())
        maps = {}
        for key, row in manifest["source_maps"].items():
            path = ROOT / row["path"]
            if not path.is_file():
                self.skipTest(f"retail map {row['path']} not staged")
            maps[key] = texconv.MapData.open(path)
        models = [b for b in manifest["chunk_bindings"] if b["kind"] == "MODL" and b["owner"]["group"] == "mode"
                  and b["owner"]["path"] in measure.SLAYER_NEEDED]
        self.assertEqual(len(models), 28)
        report = {"models": [], "totals": {}}
        n_batches = n_tris = 0
        old_pk = new_pk = 0
        for b in models:
            owner = b["owner"]
            tags = [int(owner["source_datum"])]
            old = mc.parse_section(mc.convert_map(maps[owner["source_key"]], tags,
                                                  object_profile=mc.C3_OBJECT_PROFILE).modl)
            res_new = mc.convert_map(maps[owner["source_key"]], tags, object_profile=mc.C3_OBJECT_PROFILE,
                                     vertex_format=mc.FORMAT_STRIP)
            new = mc.parse_section(res_new.modl)
            self.assertEqual(new.vertex_format, mc.FORMAT_STRIP)
            self.assertEqual(old.vertex_format, mc.FORMAT_EXPANDED)
            keep = ("shader_id", "triangles", "uv_shift", "rigid_node", "flags", "centre", "radius")
            self.assertEqual([{k: p[k] for k in keep} for p in old.parts], [{k: p[k] for k in keep} for p in new.parts])
            self.assertEqual(old.perms, new.perms)
            per_part = {}
            for ob in old.batches:
                e = per_part.setdefault(ob["part"], [[], [], 0.0])
                e[0] += mc.batch_triangles(old, ob, old.parts[ob["part"]])
                e[2] = max(e[2], _packet_scale(old, ob))
            for nb in new.batches:
                e = per_part.setdefault(nb["part"], [[], [], 0.0])
                e[1] += mc.batch_triangles(new, nb, new.parts[nb["part"]])
                e[2] = max(e[2], _packet_scale(new, nb))
            for pi, (ot, nt, step) in per_part.items():
                self.assertEqual(len(ot), len(nt), f"{owner['path']} part {pi}")
                self.assertTrue(_same_triangles(ot, nt, 2.0 * step + 1e-6), f"{owner['path']} part {pi}")
                n_tris += len(ot)
            n_batches += len(new.batches)
            old_pk += sum(bt["vif_qwords"] * 16 for bt in old.batches)
            new_pk += sum(bt["vif_qwords"] * 16 for bt in new.batches)
            report["models"].append({"path": owner["path"], "old_packet_bytes": sum(bt["vif_qwords"] * 16 for bt in old.batches),
                                     "new_packet_bytes": sum(bt["vif_qwords"] * 16 for bt in new.batches),
                                     "old_model_bytes": len(mc.parse_section(res_new.modl).vif) and None})
        self.assertGreater(n_tris, 0)
        report["totals"] = {"batches": n_batches, "triangles": n_tris, "old_packet_bytes": old_pk,
                            "new_packet_bytes": new_pk, "ratio": round(old_pk / new_pk, 3)}
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "slayer_packets.json").write_text(json.dumps(report, indent=1))
        print(f"\nstrip format: {n_batches} batches, {n_tris} triangles identical; packets {old_pk} B -> {new_pk} B "
              f"({old_pk / new_pk:.2f}x smaller)")


if __name__ == "__main__":
    unittest.main()
