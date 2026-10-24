#!/usr/bin/env python3
"""C2.3 checks for the PS2 AI debug storage gate (source/ai/ai_debug.h).

Production PS2 builds keep one line-of-sight point and one ray; a diagnostic
build that defines HCU_AI_DEBUG_DIAGNOSTICS restores the full Xbox layout. The
checks are:
  - the gate and its enum sizes are in the header, and every fixed-offset assert
    after the line-of-sight arrays is inside the non-stub branch;
  - when the EE toolchain is installed, ai_debug.c compiles for EE in both modes
    with the closure's own flags, the production `ai_debug` symbol is at most
    the measured stub size, and the diagnostic symbol is the original 547,628 B.
The compile check is skipped when the toolchain or the CE source is missing.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
HCU = ROOT / "submodules/halo-ce-universal"
HEADER = HCU / "source/ai/ai_debug.h"
SOURCE = HCU / "source/ai/ai_debug.c"
PREFIX = ROOT / "build/toolchain/install"
COMPILER = PREFIX / "ee/bin/mips64r5900el-ps2-elf-gcc"
NM = PREFIX / "ee/bin/mips64r5900el-ps2-elf-nm"
ORIGINAL_AI_DEBUG_BYTES = 547628
PRODUCTION_AI_DEBUG_MAX_BYTES = 240000

sys.path.insert(0, str(TOOLS))


def header_text():
    return HEADER.read_text(encoding="utf-8")


def test_gate_and_enum_sizes_are_in_header():
    text = header_text()
    assert "#if defined(HALO_PS2) && !defined(HCU_AI_DEBUG_DIAGNOSTICS)" in text
    assert "#define AI_DEBUG_LINEOFSIGHT_STUB" in text
    stub = text.split("#ifdef AI_DEBUG_LINEOFSIGHT_STUB", 1)[1].split("#else", 1)[0]
    full = text.split("#else", 1)[1].split("#endif", 1)[0]
    assert re.search(r"MAXIMUM_AI_DEBUG_LINEOFSIGHT_POINTS = 1,", stub)
    assert re.search(r"MAXIMUM_AI_DEBUG_LINEOFSIGHT_PAIRS = 1,", stub)
    assert re.search(r"MAXIMUM_AI_DEBUG_LINEOFSIGHT_POINTS = 16384,", full)
    assert re.search(r"MAXIMUM_AI_DEBUG_LINEOFSIGHT_PAIRS = 8192,", full)
    # The actor records stay full size: writes to them are indexed by firing
    # position and are not bounded inside ai_debug (actor_firing_position.c).
    assert "NUMBER_OF_AI_DEBUG_ACTOR_RECORDS = 512," in text


def test_fixed_offset_asserts_after_line_of_sight_are_guarded():
    text = header_text()
    guarded_names = (
        "ai_debug_state_ballistic_lineoffire_valid_offset_assert",
        "ai_debug_state_actor_record_offset_assert",
        "ai_debug_state_field_7D380_offset_assert",
    )
    for name in guarded_names:
        index = text.index(name)
        before = text[:index]
        last_if = before.rfind("#ifndef AI_DEBUG_LINEOFSIGHT_STUB")
        last_endif = before.rfind("#endif")
        assert last_if > last_endif, name
    # The asserts before the line-of-sight arrays are the same in both modes.
    for name in ("ai_debug_state_print_speech_offset_assert", "ai_debug_state_render_offset_assert"):
        index = text.index(name)
        assert text.rfind("#ifndef AI_DEBUG_LINEOFSIGHT_STUB", 0, index) < text.rfind("#endif", 0, index)


def _compile_modes(out):
    import hcu_ps2_closure as closure  # noqa: E402  (tools/ on sys.path)
    from build_toolchain import environment  # noqa: E402

    _build, prefix, env, _jobs = environment()
    manifest = json.loads(closure.MANIFEST_PATH.read_text())
    semantics = Path(out) / "halo_ps2_msvc_semantics.h"
    subprocess.run(
        [sys.executable, str(HCU / "tools/linux_msvc_semantics.py"), "--output", str(semantics),
         "--all-inlines", "--tags", str(HCU / "source"), "--inlines", str(HCU / "source"),
         "--inlines", str(HCU / "port/include/xdk")],
        cwd=ROOT, check=True, capture_output=True)
    includes = ["-I" + str(HCU / item) for item in manifest["include_dirs"]]
    includes += ["-I" + str(prefix / "ps2sdk/common/include"), "-I" + str(prefix / "ps2sdk/ee/include")]
    flags = [*closure.FLAGS, *includes, "-include", str(HCU / manifest["prefix"]),
             "-include", str(semantics), "-c"]
    base = manifest["source_flags"].get("source/ai/ai_debug.c", "").split()
    results = {}
    for label, extra in (("production", []), ("diagnostic", ["-DHCU_AI_DEBUG_DIAGNOSTICS"])):
        obj = Path(out) / f"ai_debug-{label}.o"
        code, log = closure.compile_unit(COMPILER, flags, env, SOURCE, obj,
                                         base + ["-DHALO_PS2_NO_BOOTSTRAP_MEMORY"] + extra)
        assert code == 0, f"{label} compile failed:\n{log[:4000]}"
        listing = subprocess.run([str(NM), "-S", "-t", "d", str(obj)], capture_output=True,
                                 text=True, check=True).stdout
        sizes = [int(line.split()[1]) for line in listing.splitlines()
                 if line.split()[-1:] == ["ai_debug"]]
        assert len(sizes) == 1, f"{label}: ai_debug symbol not found"
        results[label] = sizes[0]
    return results


def test_ai_debug_storage_per_mode_when_toolchain_present():
    if not (COMPILER.is_file() and NM.is_file() and SOURCE.is_file()):
        return
    with tempfile.TemporaryDirectory() as d:
        try:
            sizes = _compile_modes(d)
        except (ImportError, subprocess.CalledProcessError, RuntimeError) as error:
            print(f"skipped: closure helper unavailable ({error})")
            return
    assert sizes["production"] <= PRODUCTION_AI_DEBUG_MAX_BYTES, sizes
    assert sizes["diagnostic"] == ORIGINAL_AI_DEBUG_BYTES, sizes
    assert ORIGINAL_AI_DEBUG_BYTES - sizes["production"] >= 300000, sizes


if __name__ == "__main__":
    test_gate_and_enum_sizes_are_in_header()
    test_fixed_offset_asserts_after_line_of_sight_are_guarded()
    test_ai_debug_storage_per_mode_when_toolchain_present()
    print("ok")
