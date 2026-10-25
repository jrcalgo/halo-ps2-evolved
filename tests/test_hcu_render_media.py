"""C3 render-media: producer chunks, validator hook, chunk-kind table and the C read path."""
import copy
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hcu_profile_chunks as chunks  # noqa: E402
import hcu_profile_validate as validate  # noqa: E402

MAPS = ROOT / "build/retail-maps/decompressed"
MAP = MAPS / "bloodgulch.map"
ENGINE = ROOT / "submodules/halo-ps2/engine/src"


def _sha(b):
    return hashlib.sha256(b).hexdigest()


@unittest.skipUnless(MAP.exists(), "decompressed bloodgulch.map is absent")
class RenderMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import hcu_render_media as rm
        cls.rm = rm
        cls.built = rm.build(MAP, 0)
        cls.base = {(1, 0): b"ce-image", (3, 0): b"{}", (2, 1): b"media"}

    def package(self, extra=True):
        typed = dict(self.base)
        if extra:
            typed.update(self.built["chunks"])
        return chunks.encode(7, typed)

    def test_producer_chunks_record_source_and_converter(self):
        man = self.built["manifest"]
        self.assertEqual(sorted(self.built["chunks"]), [(4, 0), (5, 0), (6, 0)])
        self.assertEqual(man["source_map_sha256"], _sha(MAP.read_bytes()))
        self.assertEqual(man["converter"]["bspconv_version"], self.rm.bspconv.VERSION)
        for row in man["chunks"]:
            blob = self.built["chunks"][(row["kind"], row["chunk_id"])]
            self.assertEqual((row["bytes"], row["sha256"]), (len(blob), _sha(blob)))
            self.assertEqual(row["source_map_sha256"], man["source_map_sha256"])
        self.assertEqual(self.built["chunks"][(4, 0)][:4], b"BSPS")
        self.assertEqual(man["total_bytes"], sum(len(b) for b in self.built["chunks"].values()))
        again = self.rm.build(MAP, 0)
        self.assertEqual(again["chunks"], self.built["chunks"])  # deterministic

    def test_chunk_kinds_in_hcp2_envelope(self):
        pkg = self.package()
        sha = _sha(pkg)
        parsed = validate.parse_package(pkg, expected_package_sha256=sha, expected_profile_id=7)
        self.assertEqual(sorted(k for k in parsed["chunks"] if k[0] >= 4), [(4, 0), (5, 0), (6, 0)])
        self.assertEqual(parsed["chunks"][(4, 0)], self.built["chunks"][(4, 0)])
        for bad in ({(7, 0): b"x"}, {(1, 3): b"x"}, {(3, 2): b"x"}):
            with self.assertRaises(chunks.ProfileError):
                chunks.encode(7, {**self.base, **bad})
        self.assertTrue(chunks.chunk_kind_valid(6, 12))
        self.assertFalse(chunks.chunk_kind_valid(0, 0))
        # a render-free package still parses (C2 behaviour unchanged)
        plain = self.package(False)
        validate.parse_package(plain, expected_package_sha256=_sha(plain), expected_profile_id=7)

    def test_validator_hook(self):
        man = {"render_media": self.built["manifest"]}
        pkg_chunks = dict(self.built["chunks"])
        out = self.rm.check_render_chunks(pkg_chunks, man, maps_dir=MAPS)
        self.assertEqual(out["chunks"], 3)
        self.assertIsNone(self.rm.check_render_chunks({(1, 0): b"x"}, {}))
        E = self.rm.RenderMediaError
        with self.assertRaises(E):  # chunks without a manifest record
            self.rm.check_render_chunks(pkg_chunks, {})
        with self.assertRaises(E):  # record without chunks
            self.rm.check_render_chunks({(1, 0): b"x"}, man)
        tampered = dict(pkg_chunks)
        tampered[(5, 0)] = bytearray(tampered[(5, 0)])
        tampered[(5, 0)][200] ^= 1
        tampered[(5, 0)] = bytes(tampered[(5, 0)])
        with self.assertRaises(E):
            self.rm.check_render_chunks(tampered, man)
        stale = copy.deepcopy(man)
        stale["render_media"]["converter"]["bspconv_version"] += 1
        for r in stale["render_media"]["chunks"]:
            r["converter"] = stale["render_media"]["converter"]
        with self.assertRaises(E):
            self.rm.check_render_chunks(pkg_chunks, stale)
        wrong = copy.deepcopy(man)
        wrong["render_media"]["source_map_sha256"] = "0" * 64
        with self.assertRaises(E):
            self.rm.check_render_chunks(pkg_chunks, wrong)
        with self.assertRaises(E):  # source map hash must match the map on disk
            wrong2 = copy.deepcopy(man)
            wrong2["render_media"]["source_map_sha256"] = "1" * 64
            for r in wrong2["render_media"]["chunks"]:
                r["source_map_sha256"] = "1" * 64
            self.rm.check_render_chunks(pkg_chunks, wrong2, maps_dir=MAPS)
        swapped = dict(pkg_chunks)
        swapped[(4, 0)] = b"XXXX" + swapped[(4, 0)][4:]
        with self.assertRaises(E):
            self.rm.check_render_chunks(swapped, man)

    def test_append_to_qualified_package(self):
        base_pkg = self.package(False)
        sha = _sha(base_pkg)
        original = {"format": "x", "memory": {"package_file_bytes": len(base_pkg)}}
        out, man = self.rm.append_to_package(base_pkg, original, MAP, 0, expected_package_sha256=sha)
        self.assertEqual(man["base_package_sha256"], sha)
        self.assertEqual(man["package_sha256"], _sha(out))
        self.assertEqual(man["memory"]["package_file_bytes"], len(out))
        self.assertEqual(original["memory"]["package_file_bytes"], len(base_pkg))
        parsed = validate.parse_package(out, expected_package_sha256=_sha(out), expected_profile_id=7)
        for key, blob in self.base.items():
            self.assertEqual(parsed["chunks"][key], blob)  # C2 chunks byte-identical
        self.rm.check_render_chunks(parsed["chunks"], man, maps_dir=MAPS)
        with self.assertRaises(validate.ProfileValidationError):  # pin: wrong input hash is refused
            self.rm.append_to_package(base_pkg, {}, MAP, 0, expected_package_sha256="0" * 64)
        with self.assertRaises(self.rm.RenderMediaError):  # already carries render chunks
            self.rm.append_to_package(out, {}, MAP, 0, expected_package_sha256=_sha(out))

    def test_c_runtime_kind_lookup_and_read_path(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            exe = td / "media_host"
            # The real bsp_render.h needs the ps2sdk GS headers. Host shim: the exact type block
            # (MAT_* .. tex_source_t) extracted from the real header, so it cannot drift.
            real = (ENGINE / "render/bsp_render.h").read_text()
            block = real[real.index("#define MAT_ALPHA_TEST"):real.index("} tex_source_t;") + len("} tex_source_t;")]
            (td / "shim/render").mkdir(parents=True)
            (td / "shim/render/bsp_render.h").write_text(
                "#pragma once\n#include <stdint.h>\n" + block + "\n")
            cc = ["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wno-int-to-pointer-cast",
                  "-I", str(td / "shim"), "-I", str(ENGINE), "-I", str(ROOT / "src"),
                  "-I", str(ROOT / "tests/hcu_ctag_mount_shim"), "-I", str(ROOT / "tests/hcu_ps2_cache_shim"),
                  "-I", str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
                  "-I", str(ROOT / "submodules/ps2sdk/common/include"),
                  "-I", str(ROOT / "submodules/ps2sdk/ee/include"), "-D_EE",
                  str(ROOT / "tests/hcu_render_media_main.c"),
                  str(ROOT / "src/stream/hcu_render_media.c"), str(ROOT / "src/stream/hcu_render_world.c"),
                  str(ROOT / "src/stream/hcu_asset_profile.c"), str(ROOT / "src/stream/sha256.c"),
                  str(ENGINE / "world/tex.c"), str(ENGINE / "world/bsp.c"), "-o", str(exe)]
            subprocess.run(cc, check=True)
            (td / "pkg.hcp").write_bytes(self.package())
            (td / "plain.hcp").write_bytes(self.package(False))
            for name, key in (("bsps", (4, 0)), ("texs", (5, 0)), ("lm", (6, 0))):
                (td / f"{name}.bin").write_bytes(self.built["chunks"][key])
            r = subprocess.run([str(exe), *(str(td / n) for n in
                                           ("pkg.hcp", "bsps.bin", "texs.bin", "lm.bin", "plain.hcp"))],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("render media host test OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
