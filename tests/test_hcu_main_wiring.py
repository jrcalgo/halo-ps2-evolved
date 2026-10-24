"""Source-order and EE-compile checks for the C2.2/C2.6 production startup wiring.

The checks read src/stream/hcu_main.c, then compile it for the EE with the
flags tools/ee-world.mk uses, so a call moved out of order or a symbol that does
not exist fails here rather than at guest time.
"""
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/stream/hcu_main.c"
HCU = ROOT / "submodules/halo-ce-universal"
PREFIX = ROOT / "build/toolchain/install"
CC = PREFIX / "ee/bin/mips64r5900el-ps2-elf-gcc"
OUT = ROOT / "build/m2-c2-r8-runtime"


def main_body(source):
    start = source.index("int main(int argc, char **argv)")
    return source[start:]


def first(body, needle):
    index = body.find(needle)
    if index < 0:
        raise AssertionError(f"missing call: {needle}")
    return index


class HcuMainWiringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.body = main_body(cls.source)

    def test_partition_selected_before_ce_allocation(self):
        select = first(self.body, "hcu_select_and_bind_partition(&layout)")
        allocate = first(self.body, "\n\tphysical_memory_allocate();")
        self.assertLess(select, allocate)

    def test_partition_helper_selects_before_binding_profile(self):
        helper = self.source[self.source.index("static int hcu_select_and_bind_partition"):]
        helper = helper[:helper.index("\n}\n") + 3]
        select = helper.index("hcu_memory_partition_select_v2(")
        bind = helper.index("hcu_memory_bind_profile_v1(")
        self.assertLess(select, bind)
        self.assertIn("return -1", helper)
        self.assertIn("partition-selected", helper)

    def test_partition_guards_checked_after_allocate(self):
        allocate = first(self.body, "\n\tphysical_memory_allocate();")
        guard = first(self.body, "hcu_memory_partition_guards_intact(&layout, &s_partition)")
        self.assertGreater(guard, allocate)

    def test_telemetry_bound_before_first_map_service_and_shell(self):
        bind = first(self.body, "hcu_bind_owner_telemetry(&layout")
        service = first(self.body, "hcu_map_service_init_with_arenas(")
        shell = first(self.body, "halo_shell_main()")
        self.assertLess(bind, service)
        self.assertLess(bind, shell)
        self.assertGreater(bind, first(self.body, "\n\tphysical_memory_allocate();"))

    def test_every_named_owner_is_registered(self):
        helper = self.source[self.source.index("static void hcu_bind_owner_telemetry"):]
        helper = helper[:helper.index("\n}\n") + 3]
        for owner in ("HCU_OWNER_GAME_STATE", "HCU_OWNER_OBJECT_POOL",
                      "HCU_OWNER_DYNAMIC_SIM", "HCU_OWNER_TAGS", "HCU_OWNER_BSP",
                      "HCU_OWNER_RENDER_CHUNKS", "HCU_OWNER_STREAMING",
                      "HCU_OWNER_SCRATCH", "HCU_OWNER_DMA", "HCU_OWNER_AUDIO_REQUESTS"):
            self.assertRegex(helper, re.escape(owner))
        # Nested owners are declared with their backing parent in the static table,
        # so main must not sum them: the report sums BACKING rows only.
        self.assertIn("nested_within_parent", self.source)

    def test_renderer_fence_probe(self):
        helper = self.source[self.source.index("static int hcu_renderer_drained"):]
        helper = helper[:helper.index("\n}\n") + 3]
        self.assertIn("bsp_render_kick_seq()", helper)
        self.assertIn("bsp_render_fence_observed(", helper)
        self.assertIn("return 1", helper)

    def test_snapshot_printed_at_boundaries(self):
        for phase in ('"bound"', '"before-shell"', '"after-shell"', '"shutdown"'):
            self.assertIn(f"hcu_report_owner_telemetry({phase})", self.body)
        self.assertIn("HALO_PS2_LOCAL owner-telemetry", self.source)

    def test_legacy_renderer_drain_gate_installed_after_map_init(self):
        init = first(self.body, "hcu_map_service_init_with_arenas(&s_map_service")
        gate = first(self.body, "hcu_map_service_set_legacy_renderer_drained(&s_map_service,")
        asset_probe = first(self.body, "hcu_file_bridge_probe(\"D:\\\\maps\\\\ui.map\"")
        self.assertGreater(gate, init)
        self.assertLess(gate, asset_probe)
        self.assertIn("hcu_renderer_drained, NULL)", self.body)

    def test_hcu_main_compiles_for_ee(self):
        if not CC.exists():
            self.skipTest("EE toolchain not installed")
        OUT.mkdir(parents=True, exist_ok=True)
        ps2sdk = PREFIX / "ps2sdk"
        cmd = [
            str(CC), "-std=gnu11", "-Wall", "-Wextra", "-Wno-unused-parameter",
            "-G0", "-D_EE", "-fshort-wchar",
            f"-I{ROOT}/src", f"-I{HCU}/port/ps2/include", f"-I{HCU}/source",
            f"-I{HCU}/port/include", f"-I{HCU}/source/cseries",
            f"-I{ps2sdk}/common/include", f"-I{ps2sdk}/ee/include",
            f"-I{ps2sdk}/ee/rpc/filexio/include",
            "-DHALO_PS2=1", "-DHALO_HCU_TAG_CACHE_BYTES=2097152",
            '-DHALO_HCU_ASSET_ROOT="host:/"',
            f"-include{HCU}/port/ps2/include/halo_ps2_prefix.h",
            f"-I{ROOT}/submodules/halo-ps2/engine/src",
            "-c", str(MAIN), "-o", str(OUT / "hcu_main.o"),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        errors = [line for line in result.stderr.splitlines() if "error" in line]
        self.assertEqual(result.returncode, 0, msg="\n".join(errors))
        self.assertEqual(errors, [])


class HcuProfileImageTest(unittest.TestCase):
    """C2.4 production registration: the generated row image and its wiring."""

    ROW = "sidewinder_marine_shotgun_4p4bot"
    PACKAGE = ROOT / "build/m2-c2-r3-selected-packages/pkg" / ROW

    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.body = main_body(cls.source)
        cls.mk = (ROOT / "tools/ee-world.mk").read_text(encoding="utf-8")

    def register_body(self):
        start = self.source.index("static int hcu_register_selected_runtime")
        body = self.source[start:]
        return body[:body.index("\n}\n") + 3]

    def test_registration_refuses_without_image_and_names_the_gate(self):
        body = self.register_body()
        self.assertIn("#else", body)
        self.assertIn("no generated image header is built into this image", body)
        self.assertIn("return 0;", body[body.index("#else"):])

    def test_registration_takes_owner_and_scratch_arenas_from_main(self):
        body = self.register_body()
        self.assertIn("arena_t *owner, arena_t *scratch", body)
        self.assertIn("arena_alloc(owner, HCU_C2_IMAGE_METADATA_STORAGE_BYTES", body)
        self.assertIn("arena_alloc(owner, HCU_C2_IMAGE_RELOCATION_BYTES", body)
        self.assertIn("arena_alloc(scratch, HCU_C2_STREAM_SCRATCH_BYTES", body)
        self.assertIn("hcu_register_selected_runtime(&s_map_service, &map_owner_storage,",
                      self.body)
        self.assertIn("&render_section_scratch) != 1", self.body)

    def test_registration_wires_readers_gate_and_residency_span(self):
        body = self.register_body()
        for needle in (
            "runtime.package_read_at = hcu_c2_package_read_at",
            "runtime.source_read = hcu_c2_source_read",
            "runtime.compatibility = hcu_c2_compatible",
            "runtime.renderer_drained = hcu_renderer_drained",
            "runtime.residency_arena = s_partition.residency_base",
            "runtime.residency_arena_bytes = s_partition.residency_bytes",
            "hcu_map_service_register_runtime(service, HCU_C2_IMAGE_MAP, &runtime)",
            "strcmp(s_partition_name, HCU_C2_IMAGE_ROW) != 0",
        ):
            self.assertIn(needle, body)

    def test_image_readers_fail_closed_on_short_reads_and_unknown_datum(self):
        block = self.source[self.source.index("static int hcu_c2_read_at"):]
        block = block[:block.index("static int hcu_c2_compatible")]
        self.assertIn("got == size", block)
        self.assertIn("if (i == HCU_C2_IMAGE_DATUM_COUNT) return 0;", block)

    def test_generated_header_pins_the_manifest(self):
        if not (self.PACKAGE / f"{self.ROW}.hcp").is_file():
            self.skipTest("selected package row is not built")
        sys.path.insert(0, str(ROOT / "tools"))
        import c2_profile_image_header as gen
        import json
        out = OUT / "pin-check.h"
        OUT.mkdir(parents=True, exist_ok=True)
        text = gen.build_header(self.ROW, ROOT / "build/m2-c2-r3-selected-packages/pkg", ROOT)
        out.write_text(text, encoding="utf-8")
        manifest = json.loads((self.PACKAGE / f"{self.ROW}.json").read_text(encoding="utf-8"))
        self.assertIn(f'#define HCU_C2_IMAGE_ROW "{self.ROW}"', text)
        self.assertIn(f"#define HCU_C2_IMAGE_PROFILE_ID {manifest['profile']['id']}u", text)
        self.assertIn(f"#define HCU_C2_IMAGE_PACKAGE_BYTES {manifest['memory']['package_file_bytes']}u", text)
        digest = ", ".join(f"0x{b:02x}" for b in bytes.fromhex(manifest["package_sha256"]))
        self.assertIn(f"HCU_C2_IMAGE_PACKAGE_SHA256[32] = {{ {digest} }}", text)
        self.assertIn("HCU_C2_IMAGE_PACKAGE_PATH \"build/m2-c2-r3-selected-packages/pkg/", text)
        self.assertIn("#define HCU_C2_IMAGE_METADATA_BYTES 51124u", text)
        self.assertIn("#define HCU_C2_IMAGE_METADATA_STORAGE_BYTES 51092u", text)
        self.assertIn("#define HCU_C2_IMAGE_SOURCE_COUNT 5u", text)
        self.assertIn("#define HCU_C2_IMAGE_DATUM_COUNT 569u", text)

    def test_hcu_main_compiles_with_generated_image(self):
        if not CC.exists():
            self.skipTest("EE toolchain not installed")
        if not (self.PACKAGE / f"{self.ROW}.hcp").is_file():
            self.skipTest("selected package row is not built")
        sys.path.insert(0, str(ROOT / "tools"))
        import c2_profile_image_header as gen
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{self.ROW}.h").write_text(
            gen.build_header(self.ROW, ROOT / "build/m2-c2-r3-selected-packages/pkg", ROOT),
            encoding="utf-8")
        ps2sdk = PREFIX / "ps2sdk"
        cmd = [
            str(CC), "-std=gnu11", "-Wall", "-Wextra", "-Wno-unused-parameter",
            "-G0", "-D_EE", "-fshort-wchar",
            f"-I{ROOT}/src", f"-I{HCU}/port/ps2/include", f"-I{HCU}/source",
            f"-I{HCU}/port/include", f"-I{HCU}/source/cseries",
            f"-I{ps2sdk}/common/include", f"-I{ps2sdk}/ee/include",
            f"-I{ps2sdk}/ee/rpc/filexio/include", f"-I{OUT}",
            "-DHALO_PS2=1", "-DHALO_HCU_TAG_CACHE_BYTES=2097152",
            '-DHALO_HCU_ASSET_ROOT="host:/"',
            f'-DHALO_HCU_PARTITION_PROFILE="{self.ROW}"',
            f'-DHALO_HCU_PROFILE_IMAGE_HEADER="{self.ROW}.h"',
            f"-include{HCU}/port/ps2/include/halo_ps2_prefix.h",
            f"-I{ROOT}/submodules/halo-ps2/engine/src",
            "-c", str(MAIN), "-o", str(OUT / "hcu_main_image.o"),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        errors = [line for line in result.stderr.splitlines() if "error" in line]
        self.assertEqual(result.returncode, 0, msg="\n".join(errors))
        self.assertEqual(errors, [])

    def test_makefile_names_the_row_header_only_when_selected(self):
        self.assertIn("WORLD_HCU_PARTITION_PROFILE ?=", self.mk)
        self.assertIn("$(WORLD_OUTPUT)/c2/%.h: tools/c2_profile_image_header.py", self.mk)
        self.assertIn("-DHALO_HCU_PROFILE_IMAGE_HEADER=", self.mk)
        self.assertIn("$(if $(WORLD_HCU_PARTITION_PROFILE),-DHALO_HCU_PARTITION_PROFILE=", self.mk)


if __name__ == "__main__":
    unittest.main()
