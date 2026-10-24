import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools import hcu_profile_consumer_exclusions as rules
from tools.audit_hcu_c1_bitmap_roles import (
    CE_CLOSURE_ELF,
    CE_CLOSURE_ELF_SHA256,
    CE_STUB_SHA256,
    CE_STUB_SOURCE,
    CONSUMER_CLASSES,
    DEFERRED_TO,
    DISPOSITIONS,
    EXCLUSION_FILE,
    NON_GS_SINKS,
    PARENT_ELF,
    PARENT_ELF_SHA256,
    PS2_PORT_BITMAP_REQUESTS,
    PS2_PORT_GEOMETRY,
    PS2_PORT_RASTERIZER,
    PS2_PORT_SOUND_CACHE,
    REPORT,
    ROOT,
    UI_PACKAGE_SHA256,
    USER_DECISION,
    _linked_objects,
    _package_chunks,
    _port_stub_body,
    classify_role,
    consumer_exclusion_rows,
    exclusion_document,
    generated_stub_names,
    image_disposition,
    occurrence_disposition,
    qualify_consumer_classes,
    symbol_table,
    verify_elf_pins,
)
from tools.hcu_profile_chunks import encode

PROFILE_KINDS = {"ui", "bots", "survival"}

EE_WORLD_FIXTURE = """\
ENGINE = submodules/halo-ps2/engine
EE_OBJS = $(WORLD_OUTPUT)/render/bsp_render.o \\
\t$(WORLD_OUTPUT)/world/tex.o \\
\t$(WORLD_OUTPUT)/world/world.o
ifeq ($(WORLD_HCU_GAMEPLAY),1)
EE_OBJS += $(WORLD_OUTPUT)/stream/hcu_main.o \\
\t$(WORLD_OUTPUT)/stream/hcu_bitmap_frame.o
else
EE_OBJS += $(WORLD_OUTPUT)/main.o
endif
$(WORLD_OUTPUT)/main.o: EE_CFLAGS += -DX
"""


def validate_exclusions(rows, profile_names):
    """Checks the builder format: class, reason, profile_kinds, match (4 keys), counts {profile: int}."""
    assert isinstance(rows, list)
    for row in rows:
        assert set(row) == {"class", "reason", "profile_kinds", "match", "counts"}, row
        assert isinstance(row["class"], str) and row["class"]
        assert isinstance(row["reason"], str) and row["reason"]
        assert isinstance(row["profile_kinds"], list) and row["profile_kinds"]
        assert set(row["profile_kinds"]) <= PROFILE_KINDS
        match = row["match"]
        assert set(match) == {"definition", "field", "owner_group", "role"}, match
        for key in ("definition", "field", "owner_group"):
            assert match[key] is None or isinstance(match[key], str)
        assert match["role"] == row["class"]
        assert isinstance(row["counts"], dict)
        for profile, count in row["counts"].items():
            assert profile in profile_names, profile
            assert isinstance(count, int) and count >= 0


def _occ(profile, role, groups=(), disposition=None):
    return (profile, role, tuple(groups), disposition)


class ClassificationTests(unittest.TestCase):
    def test_selected_material_roles_take_precedence(self):
        owner = [{"owner_group": "soso", "field": "base_map"}]
        self.assertEqual(classify_role(owner, selected_model=True), "ps2_model_otex_base_selected")
        self.assertEqual(classify_role(owner, selected_bsp=True), "ps2_bsp_material_base_selected")

    def test_selected_material_is_live_even_without_a_schema_owner(self):
        self.assertEqual(classify_role([], selected_model=True), "ps2_model_otex_base_selected")
        self.assertEqual(classify_role([], selected_bsp=True), "ps2_bsp_material_base_selected")
        self.assertEqual(classify_role([]), "missing_owner_fail_closed")

    def test_interface_and_effect_roles(self):
        self.assertEqual(classify_role([{"owner_group": "wphi", "field": "bitmap"}]),
                         "ce_ui_hud_screenquad_source_only")
        self.assertEqual(classify_role([{"owner_group": "deca", "field": "shader.map"}]),
                         "ce_world_particle_sprite_decal_lens_effect_source_only")

    def test_predicted_resource_references_are_typed_readers_from_any_owner_group(self):
        predicted = [{"owner_group": "weap", "definition": "predicted_resource",
                      "field": "weapon.predicted_resources.tag_index", "schema_kind": "tag_index"}]
        self.assertEqual(classify_role(predicted), "ce_typed_index_resource_reference_source_only")
        self.assertEqual(classify_role([{"owner_group": "ant!", "field": "texture"}]),
                         "ce_world_widget_antenna_source_only")

    def test_shader_detail_and_unknown_groups_fail_closed(self):
        self.assertEqual(classify_role([{"owner_group": "soso", "field": "detail_map"}]),
                         "ce_shader_detail_or_helper_no_enabled_ps2_consumer")
        self.assertEqual(classify_role([{"owner_group": "zzzz", "field": "bitmap"}]),
                         "unknown_owner_group_fail_closed")

    def test_package_media_inventory_is_bound_to_real_hcp_chunks(self):
        media = b"one actual media payload"
        package = encode(7, {(1, 0): b"ctag", (2, 1): media, (3, 0): b"sound"})
        manifest = {"package_sha256": hashlib.sha256(package).hexdigest(),
                    "media": {"chunks": [{"bytes": len(media),
                                           "sha256": hashlib.sha256(media).hexdigest()}]}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.hcp"
            path.write_bytes(package)
            self.assertEqual(_package_chunks(path, manifest)[(2, 1)], media)
            manifest["media"]["chunks"][0]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "media row does not match package"):
                _package_chunks(path, manifest)


class DispositionTests(unittest.TestCase):
    def setUp(self):
        self.q = {
            "live": {"kind": "consumer", "live": True, "groups": None, "policy_proven": False, "reason": "r"},
            "dead": {"kind": "consumer", "live": False, "groups": None, "policy_proven": False, "reason": "dead r"},
            "effect": {"kind": "consumer", "live": False, "policy_proven": False, "reason": "effect r",
                       "groups": {"part": {"live": True, "reason": "p"},
                                  "pctl": {"live": False, "reason": "no PS2 reader: pctl"}}},
            "policy": {"kind": "policy", "live": False, "groups": None, "policy_proven": True,
                       "reason": "excluded by proven profile policy: x"},
            "unproven": {"kind": "policy", "live": False, "groups": None, "policy_proven": False, "reason": "u"},
            "no_owner": {"kind": "no_owner", "live": False, "groups": None, "policy_proven": False,
                         "reason": "fail closed"},
        }

    def test_each_outcome_is_decided_from_evidence(self):
        ref = lambda group: [{"owner_group": group}]
        self.assertEqual(occurrence_disposition("live", ref("x"), self.q), "live-consumer")
        self.assertEqual(occurrence_disposition("dead", ref("x"), self.q), "drop-no-ps2-reader")
        self.assertEqual(occurrence_disposition("policy", ref("soso"), self.q),
                         "excluded-by-proven-profile-policy")

    def test_group_decisions_and_mixed_references(self):
        self.assertEqual(occurrence_disposition("effect", [{"owner_group": "pctl"}], self.q),
                         "drop-no-ps2-reader")
        self.assertEqual(occurrence_disposition("effect", [{"owner_group": "part"}], self.q), "live-consumer")
        # A reference in a group the qualification does not know is never guessed.
        self.assertEqual(occurrence_disposition("effect", [{"owner_group": "soso"}], self.q), "undecided")

    def test_unknown_missing_owner_or_unproven_is_undecided_never_blocking(self):
        self.assertEqual(occurrence_disposition("never_seen", [], self.q), "undecided")
        self.assertEqual(occurrence_disposition("no_owner", [], self.q), "undecided")
        self.assertEqual(occurrence_disposition("unproven", [{"owner_group": "soso"}], self.q), "undecided")
        self.assertNotIn("blocking", DISPOSITIONS)


class ImageDispositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q = qualify_consumer_classes()
        cls.rows = [rules._check_row(row, i) for i, row in enumerate(consumer_exclusion_rows(cls.q))]

    def _ref(self, owner_group, definition="x", field="f"):
        schema_kind = "tag_index" if definition == "predicted_resource" else None
        return {"owner_group": owner_group, "definition": definition, "field": field, "schema_kind": schema_kind,
                "bitmap_output_datum": 1, "owner_output_datum": 2, "source_key": "m"}

    def _classified(self, refs):
        return [(ref, classify_role([ref])) for ref in refs]

    def test_only_metadata_references_drop_the_image(self):
        refs = self._classified([self._ref("weap", "predicted_resource", "weapon.predicted_resources.tag_index")])
        disposition, covering = image_disposition("ce_typed_index_resource_reference_source_only", refs,
                                                  self.q, self.rows, "bots")
        self.assertEqual(disposition, "drop-no-ps2-reader")
        self.assertEqual([r["class"] for r in covering], ["ce_typed_index_resource_reference_source_only"])

    def test_one_pixel_consuming_reference_keeps_the_image(self):
        refs = self._classified([self._ref("weap", "predicted_resource", "weapon.predicted_resources.tag_index"),
                                 self._ref("wphi", "hud", "bitmap")])
        disposition, covering = image_disposition("ce_typed_index_resource_reference_source_only", refs,
                                                  self.q, self.rows, "bots")
        self.assertEqual((disposition, covering), ("live-consumer", []))

    def test_selected_parent_material_is_always_live(self):
        refs = self._classified([self._ref("soso", "shader", "base_map")])
        self.assertEqual(image_disposition("ps2_model_otex_base_selected", refs, self.q, self.rows, "ui"),
                         ("live-consumer", []))

    def test_policy_only_references_are_excluded_by_proven_policy(self):
        refs = self._classified([self._ref("soso", "shader", "detail_map")])
        disposition, _ = image_disposition("ce_shader_detail_or_helper_no_enabled_ps2_consumer", refs,
                                           self.q, self.rows, "survival")
        self.assertEqual(disposition, "excluded-by-proven-profile-policy")

    def test_no_references_and_missing_rows_fail_closed(self):
        self.assertEqual(image_disposition("missing_owner_fail_closed", [], self.q, self.rows, "ui"),
                         ("undecided", []))
        refs = self._classified([self._ref("weap", "predicted_resource", "weapon.predicted_resources.tag_index")])
        with self.assertRaisesRegex(ValueError, "do not cover"):
            image_disposition("ce_typed_index_resource_reference_source_only", refs, self.q, [], "bots")

    def test_exclusion_rows_are_builder_format_and_carry_their_reasons(self):
        rows = consumer_exclusion_rows(self.q)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["match"]["role"], row["class"])
            self.assertEqual(row["counts"], {})
        classes = {r["class"] for r in rows}
        self.assertIn("ce_typed_index_resource_reference_source_only", classes)
        self.assertIn("ce_world_widget_antenna_source_only", classes)
        self.assertNotIn("ce_ui_hud_screenquad_source_only", classes)
        self.assertNotIn("ps2_model_otex_base_selected", classes)

    def test_exclusion_document_round_trips_through_the_loader(self):
        rows = [rules._check_row(dict(r, counts={"bots-beavercreek": 1}), i)
                for i, r in enumerate(consumer_exclusion_rows(self.q))]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.json"
            path.write_bytes(exclusion_document(rows))
            loaded = rules.load_exclusions(path)
            self.assertEqual(loaded["rows"], rows)
            self.assertEqual(loaded["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())


class EvidenceTests(unittest.TestCase):
    def test_world_parser_separates_base_and_gameplay_objects(self):
        base, gameplay = _linked_objects(EE_WORLD_FIXTURE)
        self.assertEqual(base, {"render/bsp_render.o", "world/tex.o", "world/world.o"})
        self.assertEqual(gameplay, {"stream/hcu_main.o", "stream/hcu_bitmap_frame.o"})

    def test_generated_stub_definitions_are_recognised_as_stubs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ps2_platform.c"
            path.write_text("void hud_draw_screen(void) {  }\n"
                            "int32_t antenna_render(int a, float b) { int32_t result; "
                            "memset(&result, 0, sizeof(result)); return result; }\n"
                            "unsigned char dsound_globals[30924];\n")
            self.assertEqual(generated_stub_names(path), {"hud_draw_screen", "antenna_render"})

    def test_port_stub_body_detects_discarding_return_false_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "port.c"
            path.write_text("boolean stub_fn(short a, long b)\n{\n\t(void)a;\n\t(void)b;\n\treturn FALSE;\n}\n"
                            "boolean real_fn(long b)\n{\n\tlong x = b;\n\treturn x != 0;\n}\n")
            self.assertTrue(_port_stub_body(path, "stub_fn"))
            self.assertFalse(_port_stub_body(path, "real_fn"))
        self.assertTrue(_port_stub_body(ROOT / PS2_PORT_RASTERIZER, "rasterizer_widget_set_texture"))

    def test_identity_passthrough_is_a_stub_and_dereference_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "port.c"
            path.write_text("void *passthrough(struct bitmap_data *bitmap, boolean block, boolean load)\n{\n"
                            "\t(void)block;\n\t(void)load;\n\treturn bitmap;\n}\n"
                            "void *dereference(struct bitmap_data *bitmap)\n{\n\treturn bitmap->pixels;\n}\n")
            self.assertTrue(_port_stub_body(path, "passthrough"))
            self.assertFalse(_port_stub_body(path, "dereference"))
        self.assertTrue(_port_stub_body(ROOT / PS2_PORT_SOUND_CACHE, "_texture_cache_bitmap_get_hardware_format"))

    def test_sprite_accumulator_is_a_declared_non_gs_sink(self):
        self.assertIn((PS2_PORT_GEOMETRY, "build_sprite"), NON_GS_SINKS)
        self.assertFalse(_port_stub_body(ROOT / PS2_PORT_GEOMETRY, "build_sprite"))  # sink, not a discard body

    def test_symbol_table_reads_defined_symbols_of_the_pinned_closure(self):
        table = symbol_table(CE_CLOSURE_ELF)
        for name in ("predicted_resources_precache", "hud_draw_screen", "antenna_render", "glow_render"):
            self.assertIn(name, table)
        self.assertNotIn("particle_systems_render", table)
        self.assertNotIn("render_particles", table)

    def test_current_elf_pins_match_files(self):
        pins = verify_elf_pins()
        self.assertEqual(pins["parent_renderer"]["sha256"], PARENT_ELF_SHA256)
        self.assertEqual(pins["hcu_closure"]["sha256"], CE_CLOSURE_ELF_SHA256)
        self.assertEqual(pins["closure_stub_source"]["sha256"], CE_STUB_SHA256)
        self.assertEqual(pins["parent_renderer"]["path"], "build/hcu-c1-final-default/world.elf")
        self.assertEqual(pins["hcu_closure"]["path"], "build/hcu-ps2-closure/all/halo-local.elf")
        self.assertEqual(pins["closure_stub_source"]["path"], "build/hcu-ps2-closure/all/ps2_platform.c")

    def test_ui_package_pin_matches_rebuild_package(self):
        rebuild = ROOT / "build/m2-c1-corpus-rebuild-v1/ui.hcp"
        if not rebuild.is_file():
            self.skipTest("rebuild corpus not present")
        self.assertEqual(hashlib.sha256(rebuild.read_bytes()).hexdigest(), UI_PACKAGE_SHA256)


class RealBuildQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q = qualify_consumer_classes()

    def test_parent_renderer_readers_make_model_bsp_and_lightmap_live(self):
        for name in ("ps2_model_otex_base_selected", "ps2_bsp_material_base_selected",
                     "ps2_bsp_lightmap_page_selected"):
            self.assertTrue(self.q[name]["live"], name)
            self.assertTrue(all(r["state"] == "real" for r in self.q[name]["readers"]), name)

    def test_hud_bitmap_path_is_live_through_the_real_request_capture(self):
        hud = self.q["ce_ui_hud_screenquad_source_only"]
        self.assertTrue(hud["live"])
        reader = hud["readers"][0]
        self.assertEqual((reader["symbol"], reader["state"]), ("hud_draw_bitmap_direct", "real"))
        self.assertEqual(reader["forward"]["file"], PS2_PORT_BITMAP_REQUESTS)
        self.assertEqual(reader["forward"]["state"], "real")

    def test_metadata_only_classes_are_not_live(self):
        predicted = self.q["ce_typed_index_resource_reference_source_only"]
        self.assertFalse(predicted["live"])
        self.assertEqual(predicted["readers"][0]["state"], "forward_stub")
        self.assertEqual(predicted["readers"][0]["forward"]["symbol"], "_texture_cache_bitmap_get_hardware_format")
        antenna = self.q["ce_world_widget_antenna_source_only"]
        self.assertFalse(antenna["live"])
        self.assertEqual(antenna["readers"][0]["state"], "forward_stub")
        self.assertEqual(antenna["readers"][0]["forward"]["state"], "stub")

    def test_effect_groups_are_decided_per_owner_group(self):
        groups = self.q["ce_world_particle_sprite_decal_lens_effect_source_only"]["groups"]
        for dropped in ("part", "cont", "deca", "glw!", "pctl", "lens", "mgs2"):
            self.assertFalse(groups[dropped]["live"], dropped)
        self.assertEqual(groups["part"]["readers"][0]["state"], "forward_absent")
        self.assertEqual(groups["cont"]["readers"][0]["state"], "forward_absent")
        self.assertEqual(groups["deca"]["readers"][0]["state"], "forward_absent")
        self.assertEqual(groups["glw!"]["readers"][0]["state"], "forward_stub")
        self.assertEqual(groups["mgs2"]["readers"][0]["state"], "forward_stub")
        self.assertEqual(groups["pctl"]["readers"][0]["state"], "absent")
        self.assertEqual(groups["lens"]["readers"][0]["state"], "absent")

    def test_detail_and_unselected_base_policies_are_proven_without_real_readers(self):
        detail = self.q["ce_shader_detail_or_helper_no_enabled_ps2_consumer"]
        self.assertFalse(detail["real_reader"])
        self.assertEqual(detail["token_scan"]["hits"], 0)
        self.assertTrue(detail["policy_proven"])
        self.assertTrue(self.q["shader_base_reference_not_selected_by_current_material_set"]["policy_proven"])

    def test_missing_owner_has_no_reader(self):
        self.assertFalse(self.q["missing_owner_fail_closed"]["real_reader"])
        self.assertEqual(self.q["missing_owner_fail_closed"]["readers"], [])

    def test_every_class_in_the_table_is_defined(self):
        self.assertEqual(set(CONSUMER_CLASSES), {k for k in self.q if not k.startswith("_")})


class CommittedReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not REPORT.is_file():
            raise unittest.SkipTest("report not generated")
        cls.report = json.loads(REPORT.read_text())

    def test_no_blocking_rows_and_every_occurrence_is_decided(self):
        counts = self.report["totals"]["disposition_occurrence_counts"]
        self.assertEqual(set(counts), set(DISPOSITIONS))
        self.assertNotIn("blocking", counts)
        self.assertEqual(counts["undecided"], 0)
        self.assertEqual(sum(counts.values()), self.report["totals"]["included_2d_profile_occurrences"])
        self.assertEqual(self.report["result"], "all_occurrences_decided")
        self.assertNotIn('"blocking"', REPORT.read_text())

    def test_rule_pins_and_deferral_are_recorded(self):
        self.assertEqual(self.report["rule"]["user_decision"], USER_DECISION)
        self.assertIn("CONSUMER RULE", self.report["rule"]["user_decision"])
        self.assertEqual(self.report["deferred_to"], DEFERRED_TO)
        self.assertEqual(self.report["elf_inputs"]["parent_renderer"]["sha256"], PARENT_ELF_SHA256)
        self.assertEqual(self.report["elf_inputs"]["hcu_closure"]["sha256"], CE_CLOSURE_ELF_SHA256)
        self.assertEqual(self.report["elf_inputs"]["closure_stub_source"]["sha256"], CE_STUB_SHA256)

    def test_exclusion_file_is_loadable_pinned_and_embedded(self):
        loaded = rules.load_exclusions(EXCLUSION_FILE)
        self.assertEqual(loaded["sha256"], self.report["consumer_exclusions"]["sha256"])
        self.assertEqual(self.report["consumer_exclusions"]["path"],
                         "docs/reports/m2-c1-consumer-exclusions-2026-10-23.json")
        self.assertEqual(len(loaded["rows"]), self.report["consumer_exclusions"]["row_count"])
        embedded = self.report["required_profile_exclusions"]
        self.assertEqual([{k: v for k, v in r.items() if k != "counts"} for r in loaded["rows"]],
                         [{k: v for k, v in r.items() if k != "counts"} for r in embedded])
        self.assertEqual(json.loads(EXCLUSION_FILE.read_text())["required_profile_exclusions"], embedded)

    def test_counts_are_distinct_dropped_images_per_profile(self):
        profiles = [p["profile"] for p in self.report["corpus"]["profiles"]]
        self.assertEqual(len(profiles), 27)
        for row in self.report["required_profile_exclusions"]:
            validate_exclusions([row], profiles)
            self.assertEqual(set(row["counts"]), set(profiles))
        dropped = self.report["dropped_images"]
        self.assertEqual(set(dropped["per_profile"]), set(profiles))
        self.assertEqual(sum(dropped["per_profile"].values()), dropped["total"])
        self.assertEqual(sum(dropped["per_kind"].values()), dropped["total"])
        for profile in profiles:
            images = dropped["per_profile"][profile]
            for row in self.report["required_profile_exclusions"]:
                self.assertLessEqual(row["counts"][profile], images, (row["class"], profile))

    def test_no_live_class_has_an_exclusion_row(self):
        classes = {r["class"] for r in self.report["required_profile_exclusions"]}
        for name in ("ps2_model_otex_base_selected", "ps2_bsp_material_base_selected",
                     "ps2_bsp_lightmap_page_selected", "ce_ui_hud_screenquad_source_only"):
            self.assertNotIn(name, classes)
        self.assertIn("ce_typed_index_resource_reference_source_only", classes)
        self.assertIn("ce_world_widget_antenna_source_only", classes)

    def test_report_inputs_are_pinned_in_inputs_map(self):
        pins = self.report["inputs_sha256"]
        for rel in (PARENT_ELF.relative_to(ROOT).as_posix(), CE_CLOSURE_ELF.relative_to(ROOT).as_posix(),
                    CE_STUB_SOURCE.relative_to(ROOT).as_posix(), "tools/ee-world.mk"):
            self.assertRegex(pins[rel], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
