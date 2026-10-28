"""Host checks for the C5 guest build plumbing (no PS2 toolchain needed)."""
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_build_tool():
    spec = importlib.util.spec_from_file_location("c5_build_under_test", ROOT / "tools/c5_build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_boot_file_syntax_checks_on_host(tmp_path):
    # hcu_c5_boot.c includes the generated c5_lifecycle_variant.h. The header is written by the build tool's own
    # writer into a temp dir (its OUT is redirected; the build tree and the full build are not touched).
    build = load_build_tool()
    build.OUT = tmp_path / "c5-guest"
    path, _datum, _roster_path = build.lifecycle_variant(build.C5_BOOT_MAP)
    variant_dir = build.write_lifecycle_header(path)
    assert (variant_dir / "c5_lifecycle_variant.h").is_file()
    assert variant_dir == tmp_path / "c5-guest" / "variant"
    result = subprocess.run(
        ["cc", "-std=gnu89", "-Wall", "-Wextra", "-Wno-unused-parameter", "-fsyntax-only",
         "-I" + str(ROOT / "src"), "-I" + str(ROOT / "src/stream"), "-I" + str(variant_dir),
         str(ROOT / "src/stream/hcu_c5_boot.c")],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_parent_makefile_lists_c5_objects_and_leaves_shared_files_alone():
    text = (ROOT / "tools/c5-world.mk").read_text()
    for name in ("hcu_c5_session.o", "hcu_c5_boot.o", "hcu_coop_modes.o", "hcu_coop_ce_bind.o",
                 "hcu_bot.o", "hcu_survival.o", "hcu_survival_ce.o"):
        assert name in text
    assert "include tools/ee-world.mk" in text


def test_build_script_keeps_shared_closure_separate():
    text = (ROOT / "tools/c5_build.py").read_text()
    assert '"-c5"' in text
    assert "ps2_bots_update_actions" in text and "--wrap" in text
