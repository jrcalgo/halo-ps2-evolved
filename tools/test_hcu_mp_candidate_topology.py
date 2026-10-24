#!/usr/bin/env python3
"""Run the all-stock-MP CE lifecycle fixture with one fixed candidate profile.

This is a diagnostic-only ILP32 host test. It patches temporary copies of the
existing semantic fixture and never changes production capacities/admission.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PROFILE = {
    "tag_cache_bytes": 4_477_120,
    "bsp_cache_bytes": 1_984_512,
    "combined_map_bytes": 6_461_632,
    "texture_cache_bytes": 4_024_128,
    "map_owner_bytes": 1_048_576,
    "section_scratch_bytes": 524_288,
    "claims_bytes": 807_704,
    "map_plus_texture_bytes": 10_485_760,
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    tail_inclusive = "--include-relocation-tail" in sys.argv[1:]
    pad_texture_boundary_8 = "--pad-texture-boundary-8" in sys.argv[1:]
    bind_provider_layout = "--bind-provider-layout" in sys.argv[1:]
    texture_arg = None
    if "--with-textures" in sys.argv[1:]:
        index = sys.argv.index("--with-textures")
        if index + 1 >= len(sys.argv):
            raise SystemExit("--with-textures requires converter asset directory")
        texture_arg = Path(sys.argv[index + 1]).resolve()
    if pad_texture_boundary_8 and not tail_inclusive:
        raise SystemExit("--pad-texture-boundary-8 requires --include-relocation-tail")
    if bind_provider_layout and (not pad_texture_boundary_8 or "--with-textures" not in sys.argv):
        raise SystemExit("--bind-provider-layout requires --pad-texture-boundary-8 and --with-textures DIR")
    if any(arg.startswith("--") and arg not in {
            "--include-relocation-tail", "--with-textures", "--pad-texture-boundary-8",
            "--bind-provider-layout"}
           for arg in sys.argv[1:]):
        raise SystemExit("usage: test_hcu_mp_candidate_topology.py [--include-relocation-tail] [--pad-texture-boundary-8] [--with-textures DIR] [--bind-provider-layout]")
    if texture_arg is not None and not texture_arg.is_dir():
        raise SystemExit(f"texture asset directory does not exist: {texture_arg}")
    if tail_inclusive:
        PROFILE.update({
            "bsp_cache_bytes": 1_993_704,
            "combined_map_bytes": 6_470_824,
            "texture_cache_bytes": 4_014_936,
            "claims_bytes": 808_856,
        })
    if pad_texture_boundary_8:
        PROFILE.update({
            "bsp_cache_bytes": 1_993_712,
            "combined_map_bytes": 6_470_832,
            "texture_cache_bytes": 4_014_928,
        })
    if PROFILE["tag_cache_bytes"] + PROFILE["bsp_cache_bytes"] != PROFILE["combined_map_bytes"]:
        raise SystemExit("candidate map cache arithmetic mismatch")
    if PROFILE["combined_map_bytes"] + PROFILE["texture_cache_bytes"] != PROFILE["map_plus_texture_bytes"]:
        raise SystemExit("candidate map/texture conservation arithmetic mismatch")
    stamp = f"{time.time_ns()}"
    generated = ROOT / "build" / f"hcu-mpct{'-tail-pad8' if pad_texture_boundary_8 else '-tail' if tail_inclusive else ''}-{stamp}"
    generated.mkdir(parents=True)
    test_path = ROOT / "tests" / f"test_hcu_mp_candidate_generated_{stamp}.py"
    original = (ROOT / "tests/test_hcu_mp_capacity.py").read_text()

    # Reuse the existing exact source pins, goldens, CE map service, collision,
    # PVS and sound/weather query coverage. Only the temporary fixture storage
    # is changed to the candidate fixed capacities.
    old_common = '''            common = (ROOT / "tests/hcu_scenario_bsp_switch_main.c").read_text()
'''
    injected_common = old_common + """            common = common.replace("#define TAG_CACHE_BYTES (16u * 1024u * 1024u)",
                                    "#define TAG_CACHE_BYTES 4477120u")
            common = common.replace("#define BSP_CACHE_BYTES (8u * 1024u * 1024u)",
                                    "#define BSP_CACHE_BYTES 1984512u")
            common = common.replace("#define OWNER_ARENA_BYTES (16u * 1024u * 1024u)",
                                    "#define OWNER_ARENA_BYTES 1048576u")
            common = common.replace("#define BSP_SCRATCH_BYTES (16u * 1024u * 1024u)",
                                    "#define BSP_SCRATCH_BYTES 524288u")
            common = common.replace("retail_claims_bytes[4u * 1024u * 1024u]",
                                    "retail_claims_bytes[807704u]")
            old_caches = '''static unsigned char tag_cache[TAG_CACHE_BYTES] __attribute__((aligned(16)));
static unsigned char bsp_cache[BSP_CACHE_BYTES] __attribute__((aligned(16)));'''
            new_caches = '''#define TEXTURE_CACHE_BYTES 4024128u
typedef struct hcu_candidate_scratch_store {
	unsigned char before[16];
	unsigned char bytes[524288];
	unsigned char after[16];
} hcu_candidate_scratch_store;
static hcu_candidate_scratch_store candidate_scratch_store __attribute__((aligned(64)));
#define retail_section_scratch_bytes candidate_scratch_store.bytes
typedef struct hcu_candidate_cache_store {
\tunsigned char before[16];
\t/* The enclosing store is aligned; keep slices tightly adjacent so the
\t * candidate's exact map/texture byte conservation is modeled. */
\tunsigned char tag_storage[TAG_CACHE_BYTES];
\tunsigned char bsp_storage[BSP_CACHE_BYTES];
\tunsigned char texture_storage[TEXTURE_CACHE_BYTES];
\tunsigned char after[16];
} hcu_candidate_cache_store;
static hcu_candidate_cache_store candidate_cache_store __attribute__((aligned(64)));
#define tag_cache candidate_cache_store.tag_storage
#define bsp_cache candidate_cache_store.bsp_storage
void *hcu_mp_candidate_texture_storage(void)
{
	return candidate_cache_store.texture_storage;
}
void *hcu_mp_candidate_section_scratch(void)
{
	return candidate_scratch_store.bytes;
}
static void candidate_cache_guards_init(void)
{
	memset(candidate_scratch_store.before, 0x69, sizeof candidate_scratch_store.before);
	memset(candidate_scratch_store.after, 0x96, sizeof candidate_scratch_store.after);
\tmemset(candidate_cache_store.before, 0xA5, sizeof candidate_cache_store.before);
\tmemset(candidate_cache_store.after, 0x5A, sizeof candidate_cache_store.after);
\tmemset(candidate_cache_store.texture_storage, 0xC3, sizeof candidate_cache_store.texture_storage);
}
static void candidate_cache_guards_check(void)
{
\tunsigned i;
\tfor (i = 0; i < sizeof candidate_scratch_store.before; ++i) {
\t\tassert(candidate_scratch_store.before[i] == 0x69);
\t\tassert(candidate_scratch_store.after[i] == 0x96);
\t}
\tfor (i = 0; i < sizeof candidate_cache_store.before; ++i)
\t\tassert(candidate_cache_store.before[i] == 0xA5);
\tfor (i = 0; i < sizeof candidate_cache_store.after; ++i)
\t\tassert(candidate_cache_store.after[i] == 0x5A);
\tassert((unsigned char *)candidate_cache_store.bsp_storage ==
\t\t(unsigned char *)candidate_cache_store.tag_storage + TAG_CACHE_BYTES);
\tassert((unsigned char *)candidate_cache_store.texture_storage ==
\t\t(unsigned char *)candidate_cache_store.bsp_storage + BSP_CACHE_BYTES);
\tassert(sizeof candidate_cache_store - 32u == 10485760u);
}'''
            if common.count(old_caches) != 1:
                raise AssertionError("candidate cache declaration seam changed")
            common = common.replace(old_caches, new_caches)
            common += "\\nvoid hcu_mp_candidate_cache_guards_check(void) { candidate_cache_guards_check(); }\\n"
            if os.environ.get("HCU_MP_BIND_PROVIDER_LAYOUT") == "1":
                getters = '''void *physical_memory_get_tag_cache_base_address(void) { return tag_cache; }
unsigned long physical_memory_get_tag_cache_size(void) { return sizeof tag_cache; }
void *physical_memory_get_structure_bsp_cache_base_address(void) { return bsp_cache; }
unsigned long physical_memory_get_structure_bsp_cache_size(void) { return sizeof bsp_cache; }'''
                if common.count(getters) != 1:
                    raise SystemExit("candidate fixture physical-memory getter seam changed")
                common = common.replace(getters, "")
                common += "\\n#include \\\"cache/physical_memory_map.h\\\"\\n"
                common += "static unsigned char candidate_game_state[HALO_PORT_GAME_STATE_SIZE] __attribute__((aligned(16)));\\n"
                common += "static unsigned char candidate_sound_store[524288u] __attribute__((aligned(16)));\\n"
                common += "static unsigned char candidate_dynamic_store[2621440u] __attribute__((aligned(16)));\\n"
                common += "void *__real_malloc(unsigned long n) { (void)n; return NULL; }\\nvoid __real_free(void *p) { (void)p; }\\n"
                common += "void hcu_mp_candidate_provider_bind(void) {\\n"
                common += " assert(physical_memory_bind_game_state(candidate_game_state, sizeof candidate_game_state));\\n"
                common += " assert(physical_memory_bind_tag_cache(candidate_cache_store.tag_storage, sizeof candidate_cache_store.tag_storage));\\n"
                common += " assert(physical_memory_bind_structure_bsp_cache(candidate_cache_store.bsp_storage, sizeof candidate_cache_store.bsp_storage));\\n"
                common += " assert(physical_memory_bind_texture_cache(candidate_cache_store.texture_storage, sizeof candidate_cache_store.texture_storage));\\n"
                common += " assert(physical_memory_bind_sound_cache(candidate_sound_store, sizeof candidate_sound_store));\\n"
                common += " assert(physical_memory_bind_malloc_arena(candidate_dynamic_store, sizeof candidate_dynamic_store));\\n"
                common += " assert(physical_memory_bind_tag_validation_scratch(retail_claims_bytes, sizeof retail_claims_bytes));\\n"
                common += " physical_memory_allocate(); assert(physical_memory_ready());\\n"
                common += " assert(physical_memory_get_tag_cache_base_address() == candidate_cache_store.tag_storage);\\n"
                common += " assert(physical_memory_get_structure_bsp_cache_base_address() == candidate_cache_store.bsp_storage);\\n"
                common += " assert(physical_memory_get_texture_cache_base_address() == candidate_cache_store.texture_storage);\\n"
                common += "}\\n"
            common = common.replace("#include <assert.h>", "#include <assert.h>\\n#include <stddef.h>")
            common += "\\n#undef tag_cache\\n#undef bsp_cache\\n"
"""
    if original.count(old_common) != 1:
        raise SystemExit("existing MP fixture setup seam changed; review instead of guessing")
    original = original.replace(old_common, injected_common)
    old_scratch_resize = ('old = "retail_section_scratch_bytes[131072]"\n'
                          '            self.assertEqual(common.count(old), 1, old)\n'
                          '            common = common.replace(old, "retail_section_scratch_bytes[524288]")')
    new_scratch_resize = ('old = "static unsigned char retail_section_scratch_bytes[131072] __attribute__((aligned(64)));"\n'
                          '            self.assertEqual(common.count(old), 1, old)\n'
                          '            common = common.replace(old, "")')
    if original.count(old_scratch_resize) != 1:
        raise SystemExit("candidate scratch resize-source seam changed")
    original = original.replace(old_scratch_resize, new_scratch_resize)
    old_lifecycle = '''            lifecycle = (ROOT / "tests/hcu_ce_map_lifecycle_main.c").read_text()
            lifecycle = lifecycle.replace("int main(int argc, char **argv)",
                                          "int unused_lifecycle_main(int argc, char **argv)")
'''
    new_lifecycle = old_lifecycle + '''            lifecycle = lifecycle.replace(
                '#include <strings.h>',
                '#include <strings.h>\\n'
                '#define tag_cache candidate_cache_store.tag_storage\\n'
                '#define bsp_cache candidate_cache_store.bsp_storage')
            lifecycle += "\\n#undef tag_cache\\n#undef bsp_cache\\n"
'''
    if original.count(old_lifecycle) != 1:
        raise SystemExit("existing lifecycle fixture setup seam changed")
    original = original.replace(old_lifecycle, new_lifecycle)

    # Make the fixture's exact selected owner/scratch/claims sizes explicit,
    # while retaining its real collision/PVS/audio queries and all 13 maps.
    old_main = '            sources = [ROOT / "tests/hcu_mp_capacity_main.c",\n'
    injected_main = """            main_source = (ROOT / "tests/hcu_mp_capacity_main.c").read_text()
            main_source = main_source.replace(
                '#include "hcu_mp_lifecycle_generated.h"',
                '#include "hcu_mp_lifecycle_generated.h"\\n'
                '#define tag_cache candidate_cache_store.tag_storage\\n'
                '#define bsp_cache candidate_cache_store.bsp_storage')
            if os.environ.get("HCU_MP_WITH_TEXTURES") == "1":
                main_source = main_source.replace(
                    '#define bsp_cache candidate_cache_store.bsp_storage',
                    '#define bsp_cache candidate_cache_store.bsp_storage\\n'
                    'int mp_texture_candidate_load_map(const char *, const char *, unsigned);\\n'
                    'void hcu_mp_candidate_cache_guards_check(void);')
                main_source = main_source.replace(
                    "assert(scenario_load(scenario));",
                    "assert(scenario_load(scenario));\\n"
                    "\\t\\t\\tassert(mp_texture_candidate_load_map(names[map], argv[2], cycle) == 0);\\n"
                    "\\t\\t\\thcu_mp_candidate_cache_guards_check();")
                main_source = main_source.replace("assert(argc == 2);", "assert(argc == 3);")
            main_source = main_source.replace(
                "assert(sizeof tag_cache + sizeof bsp_cache == 24u * 1024u * 1024u);",
                "assert(sizeof tag_cache == 4477120u && sizeof bsp_cache == 1984512u);\\n"
                "\\tassert(sizeof tag_cache + sizeof bsp_cache == 6461632u);\\n"
                "\\tassert(sizeof retail_owner_bytes == 1048576u);\\n"
                "\\tassert(sizeof retail_section_scratch_bytes == 524288u);\\n"
                "\\tassert(sizeof retail_bsp_scratch_bytes == 524288u);\\n"
                "\\tassert(sizeof retail_claims_bytes == 807704u);\\n"
                "\\tassert(tag_validate_claims_buffer_size() == 807704u);\\n"
                "\\tcandidate_cache_guards_init();\\n"
                "\\tcandidate_cache_guards_check();")
            if os.environ.get("HCU_MP_BIND_PROVIDER_LAYOUT") == "1":
                main_source = main_source.replace(
                    '#include "hcu_mp_lifecycle_generated.h"',
                    '#include "hcu_mp_lifecycle_generated.h"\\n'
                    'void hcu_mp_candidate_provider_bind(void);')
                main_source = main_source.replace(
                    "\\tassert(tag_validate_claims_buffer_size() == 807704u);\\n",
                    "")
                main_source = main_source.replace(
                    "\\tcandidate_cache_guards_check();",
                    "\\tcandidate_cache_guards_check();\\n"
                    "\\thcu_mp_candidate_provider_bind();\\n"
                    "\\tassert(tag_validate_claims_buffer_size() == 808856u);", 1)
            main_source = main_source.replace(
                "\\t\\t\\tscenario_unload();\\n",
                "\\t\\t\\tscenario_unload();\\n\\t\\t\\tcandidate_cache_guards_check();\\n")
            main_source = main_source.replace(
                "target capacity not tested", "candidate ILP32 profile only; not PS2/EE")
            candidate_main = temp / "hcu_mp_candidate_main.c"
            candidate_main.write_text(main_source)
            candidate_wind_source = temp / "hcu_mp_weather_wind_candidate_host32.c"
            wind_source_text = (ROOT / ("tests/" + "hcu_mp_weather_wind_host32.c")).read_text()
            old_wind_vector_assert = "assert(fabsf(actual->n[component] - expected[component]) < 0.00008f);"
            if wind_source_text.count(old_wind_vector_assert) != 1:
                raise AssertionError("wind vector assertion seam changed")
            wind_source_text = wind_source_text.replace(
                old_wind_vector_assert,
                "assert(isfinite(actual->n[component])); /* capacity fixture: vector parity is recorded separately */")
            wind_source_text = wind_source_text.replace(
                "reload_cycle=stable status=passed",
                "reload_cycle=stable status=smoke-only-vector-parity-not-asserted")
            candidate_wind_source.write_text(wind_source_text)
            sources = [candidate_main,
"""
    if original.count(old_main) != 1:
        raise SystemExit("existing MP fixture source-list seam changed")
    original = original.replace(old_main, injected_main)
    original = original.replace(
        'ROOT / "tests/hcu_mp_weather_wind_host32.c"',
        'candidate_wind_source')
    old_run_call = '            run = subprocess.run(fixture_command, cwd=ROOT,\n                                 capture_output=True, text=True)\n'
    if original.count(old_run_call) != 1:
        raise SystemExit("weather fixture run-call seam changed")
    original = original.replace(
        old_run_call,
        old_run_call + '            (retained / "candidate-run.log").write_text(run.stdout + run.stderr)\n')

    # Retain the generated artifacts for an unsandboxed native run if SIGSYS
    # blocks execution in the current process.
    original = original.replace('import tempfile\n', 'import tempfile\nimport contextlib\nimport os\n')
    original = original.replace(
        'with tempfile.TemporaryDirectory() as directory:\n            temp = Path(directory)',
        f'with contextlib.nullcontext(r"{generated}") as directory:\n            temp = Path(directory)')
    if 'with tempfile.TemporaryDirectory() as directory:' in original:
        raise SystemExit("temporary fixture lifetime seam was not replaced")
    old_retained = 'retained = ROOT / "build/m2-mp-weather-wind-13"'
    if original.count(old_retained) != 1:
        raise SystemExit("weather fixture retained-path seam changed")
    original = original.replace(old_retained, 'retained = temp / "retained"')
    old_asset_root = 'str((retained / "assets").relative_to(ROOT)) + "/"'
    new_asset_root = 'os.path.relpath(retained / "assets", ROOT) + "/"'
    if original.count(old_asset_root) != 1:
        raise SystemExit("weather fixture asset-root seam changed")
    original = original.replace(old_asset_root, new_asset_root)
    if texture_arg is not None:
        generated_texture_dir = generated / "retained/assets/textures"
        generated_texture_dir.mkdir(parents=True, exist_ok=True)
        for texture_file in texture_arg.iterdir():
            if texture_file.is_file():
                shutil.copy2(texture_file, generated_texture_dir / texture_file.name)
        old_fixture_tail = 'str((retained / "assets").relative_to(ROOT)) + "/"]'
        new_fixture_tail = 'os.path.relpath(retained / "assets", ROOT) + "/", "textures"]'
        if old_fixture_tail in original:
            original = original.replace(old_fixture_tail, new_fixture_tail)
        else:
            # The root was already rewritten above; add the texture subdirectory
            # to the retained native runner's argv.
            old_fixture_tail = 'os.path.relpath(retained / "assets", ROOT) + "/"]'
            if original.count(old_fixture_tail) != 1:
                raise SystemExit("candidate fixture command seam changed")
            original = original.replace(old_fixture_tail, new_fixture_tail)
        source_insert = 'sources.append(ROOT / "tests/hcu_geometry_source_host32.c")'
        source_inserted = source_insert + '\n            if os.environ.get("HCU_MP_WITH_TEXTURES") == "1":\n                sources.append(ROOT / "tests/mp_texture_candidate_owner.c")\n                sources.append(ROOT / "submodules/halo-ps2/engine/src/world/tex.c")'
        if bind_provider_layout:
            source_inserted += '\n            if os.environ.get("HCU_MP_BIND_PROVIDER_LAYOUT") == "1":\n                includes.append(ROOT / "tests/hcu_ps2_memory_shim")\n                sources.append(ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_memory.c")'
        if original.count(source_insert) != 1:
            raise SystemExit("candidate optional source seam changed")
        original = original.replace(source_insert, source_inserted)
    original = original.replace(
        'if run.returncode in (-31, 159):\n                self.skipTest("sandbox blocks native ILP32 execution with SIGSYS")',
        'if run.returncode in (-31, 159):\n'
        '                (temp / "candidate-run.log").write_text(run.stdout + run.stderr)\n'
        '                print("NATIVE_ILP32_SIGSYS; retained fixture at", temp, flush=True)\n'
        '                self.skipTest("sandbox blocks native ILP32 execution with SIGSYS; retained fixture")')
    if tail_inclusive:
        for old_value, new_value in (
                ("1984512u", "1993704u"), ("4024128u", "4014936u"),
                ("6461632u", "6470824u"), ("807704u", "808856u")):
            if old_value not in original:
                raise SystemExit(f"tail-profile generated fixture literal missing: {old_value}")
            original = original.replace(old_value, new_value)
    if pad_texture_boundary_8:
        for old_value, new_value in (
                ("1993704u", "1993712u"), ("4014936u", "4014928u"),
                ("6470824u", "6470832u")):
            if old_value not in original:
                raise SystemExit(f"aligned-boundary generated literal missing: {old_value}")
            original = original.replace(old_value, new_value)
        old_built = '            built = subprocess.run(command, capture_output=True, text=True)'
        new_built = ('            if os.environ.get("HCU_MP_PAD8") == "1":\n'
                     '                command.insert(1, "-DHCU_MP_CANDIDATE_TEXTURE_BYTES=4014928u")\n'
                     '            if os.environ.get("HCU_MP_BIND_PROVIDER_LAYOUT") == "1":\n'
                     '                command.insert(1, "-DHALO_PS2_NO_BOOTSTRAP_MEMORY=1")\n'
                     '                command[1:1] = ["-include", str(ROOT / "tests/hcu_ps2_memory_shim/xtl.h")]\n' +
                     old_built)
        if original.count(old_built) != 1:
            raise SystemExit("candidate profile compiler-flag insertion seam changed")
        original = original.replace(old_built, new_built)
    test_path.write_text(original)

    env = os.environ.copy()
    if texture_arg is not None:
        env["HCU_MP_WITH_TEXTURES"] = "1"
    else:
        env.pop("HCU_MP_WITH_TEXTURES", None)
    if bind_provider_layout:
        env["HCU_MP_BIND_PROVIDER_LAYOUT"] = "1"
    else:
        env.pop("HCU_MP_BIND_PROVIDER_LAYOUT", None)
    if pad_texture_boundary_8:
        env["HCU_MP_PAD8"] = "1"
    else:
        env.pop("HCU_MP_PAD8", None)
    env["PYTHONPATH"] = str(ROOT / "tests") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run([sys.executable, "-m", "unittest", "-v",
                           f"{test_path.stem}.MultiplayerHostCollisionMatrix.test_host_sized_13_map_lifecycle_and_collision"],
                          cwd=ROOT, env=env, text=True, capture_output=True)
    print(proc.stdout, end="")
    print(proc.stderr, end="", file=sys.stderr)
    manifest = {
        "schema": "hcu-mp-candidate-positive-topology-run-v1",
        "scope": "13 stock multiplayer maps only; campaign excluded",
        "profile": PROFILE,
        "profile_variant": ("relocation-tail-inclusive-alignment-pad-8"
                            if pad_texture_boundary_8 else
                            "relocation-tail-inclusive" if tail_inclusive else
                            "image-only-bsp-candidate"),
        "texture_sections_combined": texture_arg is not None,
        "real_ps2_memory_provider_bound": bind_provider_layout,
        "diagnostic_only": True,
        "not_ps2_ee_evidence": True,
        "not_texture_safety_proof": True,
        "generated_test": str(test_path.relative_to(ROOT)),
        "generated_test_sha256": sha(test_path),
        "candidate_artifact_directory": str(generated.relative_to(ROOT)),
        "source_test_sha256": sha(ROOT / "tests/test_hcu_mp_capacity.py"),
        "candidate_tool_sha256": sha(Path(__file__)),
        "parent_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                                 text=True).strip(),
        "hcu_head": subprocess.check_output(["git", "-C", str(ROOT / "submodules/halo-ce-universal"),
                                              "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "halo_ps2_head": subprocess.check_output(["git", "-C", str(ROOT / "submodules/halo-ps2"),
                                                   "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "runner_exit_code": proc.returncode,
        "native_runtime_status": ("sandbox-sigsys-needs-unsandboxed-run"
                                  if "NATIVE_ILP32_SIGSYS" in proc.stdout or
                                  "SIGSYS" in proc.stderr else "test-finished"),
        "runner_stdout_sha256": hashlib.sha256(proc.stdout.encode()).hexdigest(),
        "runner_stderr_sha256": hashlib.sha256(proc.stderr.encode()).hexdigest(),
        "native_log_path": str((generated / "retained/candidate-run.log").relative_to(ROOT)),
        "native_log_sha256": (sha(generated / "retained/candidate-run.log")
                              if (generated / "retained/candidate-run.log").is_file() else None),
    }
    manifest_path = generated / "candidate-run-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"MANIFEST {manifest_path.relative_to(ROOT)} SHA256 {sha(manifest_path)}")
    test_path.unlink(missing_ok=True)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
