from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest


class HcuMapCatalogTests(unittest.TestCase):
    def _compile(self, root, compiler, temporary, main):
        engine = root / "submodules/halo-ps2/engine/src"
        executable = Path(temporary) / main.stem
        subprocess.run([
            compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-Isrc", "-I" + str(engine), str(main),
            str(root / "src/stream/hcu_map_catalog.c"),
            str(root / "src/stream/hmap.c"),
            str(root / "src/stream/cbsp_catalog.c"),
            str(engine / "stream/hp2.c"), "-o", str(executable),
        ], check=True, capture_output=True, text=True)
        return executable

    def test_retail_catalog_identity_paths_and_bsp_metadata(self):
        root = Path(__file__).resolve().parents[1]
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._compile(root, compiler, temporary,
                                       root / "tests/hcu_map_catalog_main.c")
            subprocess.run([str(executable)], check=True,
                           capture_output=True, text=True)

    def test_real_ui_and_bloodgulch_hp2_hmap_and_cbix_records(self):
        root = Path(__file__).resolve().parents[1]
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        packages = [
            root / "build/hcu-parent-link-probe/maps/ui-with-bsp.hp2",
            root / "build/retail-maps/bloodgulch-with-bsps.hp2",
        ]
        missing = [str(path) for path in packages if not path.is_file()]
        if missing:
            self.skipTest("local retail package fixture unavailable: " + ", ".join(missing))
        with tempfile.TemporaryDirectory() as temporary:
            executable = self._compile(root, compiler, temporary,
                                       root / "tests/hcu_map_catalog_package_main.c")
            subprocess.run([str(executable), *(str(path) for path in packages)],
                           check=True, capture_output=True, text=True)

    def test_all_retail_hp2_packages_with_production_c_readers(self):
        root = Path(__file__).resolve().parents[1]
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        package_root_text = os.environ.get("HALO_HCU_M2_PACKAGE_ROOT")
        manifest_text = os.environ.get("HALO_HCU_M2_PACKAGE_MANIFEST")
        if not package_root_text or not manifest_text:
            self.skipTest("set HALO_HCU_M2_PACKAGE_ROOT and HALO_HCU_M2_PACKAGE_MANIFEST to run the full retail matrix")
        package_root = Path(package_root_text).resolve()
        manifest_path = Path(manifest_text).resolve()
        manifest = json.loads(manifest_path.read_text())
        rows = manifest.get("maps")
        if manifest.get("map_count") != 24 or manifest.get("bsp_count") != 82 or not isinstance(rows, list) or len(rows) != 24:
            self.fail("fresh package audit must identify exactly 24 maps and 82 BSPs")
        names = [row.get("map") for row in rows]
        if len(set(names)) != 24 or not all(isinstance(name, str) for name in names):
            self.fail("package audit has missing or duplicate map names")
        actual_names = {path.stem for path in package_root.glob("*.hp2")}
        if actual_names != set(names):
            self.fail("package directory does not exactly match the manifest map set")
        for row in rows:
            path = package_root / (row["map"] + ".hp2")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != row.get("package_sha256"):
                self.fail(f"package hash mismatch for {row['map']}")
            if path.stat().st_size != row.get("package_bytes"):
                self.fail(f"package size mismatch for {row['map']}")
        engine = root / "submodules/halo-ps2/engine/src"
        ps2_include = root / "submodules/halo-ce-universal/port/ps2/include"
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "hcu-map-catalog-package-matrix"
            subprocess.run([
                compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                "-Isrc", "-I" + str(engine), "-I" + str(ps2_include),
                str(root / "tests/hcu_map_catalog_package_matrix_main.c"),
                str(root / "src/stream/hcu_map_catalog.c"),
                str(root / "src/stream/hmap.c"),
                str(root / "src/stream/cbsp_catalog.c"),
                str(root / "src/stream/ctag_resource_index.c"),
                str(engine / "stream/hp2.c"),
                str(root / "submodules/halo-ce-universal/port/ps2/src/ps2_ctag.c"),
                str(root / "submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c"),
                "-o", str(executable),
            ], check=True, capture_output=True, text=True)
            result = subprocess.run([
                str(executable), str(package_root),
            ], check=True, capture_output=True, text=True,
                env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0"})
            self.assertIn("maps=24 scenario=24/24 scenario-bsp-refs=82/82 hmap=24/24 crng=24/24 cbix=24/24 cbsp=82/82",
                          result.stdout)

    def test_retail_scenario_bsp_references_match_tag_index_and_package_cbix(self):
        root = Path(__file__).resolve().parents[1]
        map_root_text = os.environ.get("HALO_HCU_M2_RETAIL_MAP_ROOT")
        package_root_text = os.environ.get("HALO_HCU_M2_PACKAGE_ROOT")
        schema_elf_text = os.environ.get("HALO_HCU_M2_SCHEMA_ELF")
        manifest_text = os.environ.get("HALO_HCU_M2_PACKAGE_MANIFEST")
        if not all((map_root_text, package_root_text, schema_elf_text, manifest_text)):
            self.skipTest("set retail map, package root, schema ELF and package audit manifest env vars")
        from tools.audit_retail_scenario_bsp_references import audit

        report = audit(Path(map_root_text), Path(package_root_text), Path(schema_elf_text))
        package_manifest = json.loads(Path(manifest_text).read_text())
        self.assertEqual((report["map_count"], report["scenario_bsp_reference_count"]),
                         (24, 82))
        self.assertEqual(report["schema_elf_sha256"],
                         "2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa")
        self.assertEqual(len(package_manifest["maps"]), 24)
        for actual, packaged in zip(report["maps"], package_manifest["maps"]):
            self.assertEqual(actual["map"], packaged["map"])
            self.assertEqual(actual["map_sha256"], packaged["source_sha256"])
            self.assertEqual(actual["package_sha256"], packaged["package_sha256"])
            self.assertTrue(actual["scenario_order_matches_cbix_extent_order"])
            self.assertEqual(len(actual["references"]), packaged["bsp_count"])
            self.assertTrue(all(reference["cbix_section_tag"] ==
                                f"B{reference['ordinal']:03d}"
                                for reference in actual["references"]))


if __name__ == "__main__":
    unittest.main()
