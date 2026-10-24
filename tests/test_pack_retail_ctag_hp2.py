"""Retail HP2 packaging smoke for required CTAG/CRNG plus optional PS2 sections."""
from pathlib import Path
import unittest

from tools import cbsp, ctag, ctag_resources, hmap
from tools.pack_retail_ctag_hp2 import pack_retail_map, parse_section


class RetailHp2PackageTests(unittest.TestCase):
    def test_packages_longest_ctag_and_selected_bsp_with_current_schema(self):
        root = Path(__file__).resolve().parents[1]
        retail = root / "build/retail-maps/decompressed/longest.map"
        elf = root / "build/hcu-ps2-closure/all/halo-local.elf"
        if not retail.is_file() or not elf.is_file():
            self.skipTest("decompressed Longest map and schema ELF are required")

        pack, summary = pack_retail_map(retail, elf, include_all_bsps=True)
        hp2 = ctag._hp2_module().parse(pack)
        self.assertEqual(hp2.name, "longest")
        self.assertEqual({section.tag for section in hp2.sections},
                         {"CTAG", "CRNG", "HMAP", "CBIX", "B000"})
        image = ctag.decode(hp2.read("CTAG"), max_image_size=summary["image_size"])
        self.assertEqual(len(image.image), 4_263_624)
        self.assertEqual(image.scenario_tag_index, summary["scenario_tag_index"])
        identity = hmap.decode(hp2.read("HMAP"), expected_map_name="longest")
        self.assertEqual(identity.source_sha256.hex(), summary["source_sha256"])
        self.assertEqual(identity.file_length, summary["file_size"])
        catalog = cbsp.decode_catalog(hp2.read("CBIX"),
                                      expected_file_length=summary["file_size"])
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0].section_tag, "B000")
        decoded_bsp = cbsp.decode(hp2.read("B000"),
                                  max_image_size=len(hp2.read("B000")))
        self.assertEqual(len(decoded_bsp.image), 374_784)
        self.assertEqual(summary["cbsp_section_bytes"], 377_388)
        self.assertEqual(summary["resource_interval_count"], 1_168)

        again, again_summary = pack_retail_map(retail, elf, include_all_bsps=True)
        self.assertEqual(pack, again)
        self.assertEqual(summary["hp2_sha256"], again_summary["hp2_sha256"])

    def test_packages_and_reopens_bloodgulch_ctag_and_crng(self):
        root = Path(__file__).resolve().parents[1]
        retail = root / "data/retail/weapon-audit-maps/bloodgulch.map"
        elf = root / "build/hcu-ps2-closure/all/halo-local.elf"
        if not retail.is_file() or not elf.is_file():
            self.skipTest("retail Blood Gulch map and schema ELF are required")
        pack, summary = pack_retail_map(retail, elf, presentation_sections=[
            ("BSP0", b"converted-render-fixture"),
        ], include_all_bsps=True)
        hp2 = ctag._hp2_module().parse(pack)
        self.assertEqual(hp2.name, "bloodgulch")
        self.assertEqual({section.tag for section in hp2.sections},
                         {"CTAG", "CRNG", "HMAP", "CBIX", "B000", "BSP0"})
        image = ctag.decode(hp2.read("CTAG"), max_image_size=summary["image_size"])
        self.assertEqual(image.scenario_tag_index, summary["scenario_tag_index"])
        resource = ctag_resources.decode(
            hp2.read("CRNG"), expected_file_length=summary["file_size"],
            expected_tag_data_offset=summary["tag_data_offset"],
            expected_tag_data_size=summary["tag_data_size"],
        )
        self.assertEqual(len(resource.intervals), 1200)
        self.assertEqual(summary["resource_interval_count"], 1200)
        identity = hmap.decode(hp2.read("HMAP"), expected_map_name="bloodgulch")
        self.assertEqual(identity.source_sha256.hex(), summary["source_sha256"])
        self.assertEqual(identity.file_length, summary["file_size"])
        self.assertEqual(hp2.read("BSP0"), b"converted-render-fixture")
        from tools.cbsp import decode as decode_cbsp
        decoded_bsp = decode_cbsp(hp2.read("B000"), max_image_size=len(hp2.read("B000")))
        self.assertEqual(len(decoded_bsp.image), 1_296_384)
        from tools.cbsp import decode_catalog
        catalog = decode_catalog(hp2.read("CBIX"), expected_file_length=summary["file_size"])
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0].section_tag, "B000")
        self.assertEqual(summary["cbsp_count"], 1)
        self.assertEqual(summary["cbsp_internal_relocation_fields"], 463)
        self.assertEqual(summary["cbsp_tag_name_relocation_fields"], 93)
        again, again_summary = pack_retail_map(retail, elf, presentation_sections=[
            ("BSP0", b"converted-render-fixture"),
        ], include_all_bsps=True)
        self.assertEqual(pack, again)
        self.assertEqual(summary["hp2_sha256"], again_summary["hp2_sha256"])

    def test_rejects_reserved_or_invalid_optional_section_specs(self):
        for spec in ("CTAG=file", "CRNG=file", "CBIX=file", "HMAP=file",
                     "TOOLONG=file", "BSP0"):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                parse_section(spec)


if __name__ == "__main__":
    unittest.main()
