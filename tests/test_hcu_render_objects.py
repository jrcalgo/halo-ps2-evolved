"""Host tests for the C3.objects pure core (synthetic builder, selection, pin/unpin, parity)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_render_objects_host_contract(tmp_path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    exe = tmp_path / "hcu_render_objects_test"
    subprocess.run([
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
        "-Isrc", "-I" + str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
        "tests/hcu_render_objects_main.c",
        "src/stream/hcu_render_objects.c",
        "src/stream/hcu_render_content.c",
        "src/stream/hcu_snapshot_bank.c",
        "-lm", "-o", str(exe),
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hcu_render_objects tests passed" in result.stdout


def test_objects_table_generator_is_exact(tmp_path):
    package = ROOT / "build/c3/render-tree/pkg/bloodgulch_mounted_gunner_4p4bot/bloodgulch_mounted_gunner_4p4bot.json"
    if not package.exists():
        pytest.skip("Blood Gulch render package not built")
    out = tmp_path / "hcu_c3_objects_table.h"
    subprocess.run(["python3", "-I", str(ROOT / "tools/hcu_c3_objects_table.py"),
                    "--package-json", str(package), "--output", str(out)],
                   cwd=ROOT, check=True, capture_output=True, text=True)
    text = out.read_text()
    assert "HCU_C3_OBJECTS_TABLE_COUNT 69u" in text
    assert "characters\\\\cyborg\\\\cyborg" in text
    assert "vehicles\\\\ghost\\\\ghost" in text


BLOODGULCH_SKY_MODEL_TAG = 3782606850   # skyconv.read_sky(bloodgulch.map)["model_tag"]; the sky MODL of the Blood Gulch package


def test_objects_table_sky_index_is_selected_by_tag(tmp_path):
    package = ROOT / "build/m2-c2-r3-selected-packages/pkg/bloodgulch_mounted_gunner_4p4bot/bloodgulch_mounted_gunner_4p4bot.json"
    if not package.exists():
        pytest.skip("Blood Gulch package not built")
    out = tmp_path / "hcu_c3_objects_table.h"
    subprocess.run(["python3", "-I", str(ROOT / "tools/hcu_c3_objects_table.py"), "--package-json", str(package),
                    "--output", str(out), "--sky-model-datum", str(BLOODGULCH_SKY_MODEL_TAG)],
                   cwd=ROOT, check=True, capture_output=True, text=True)
    text = out.read_text()
    assert "#define HCU_C3_OBJECTS_SKY_INDEX 32u" in text
    assert "sky\\\\mp clear afternoon\\\\mp clear afternoon" in text
    # Without the option the header is unchanged (no sky define), so the C side keeps its fallback.
    plain = tmp_path / "plain.h"
    subprocess.run(["python3", "-I", str(ROOT / "tools/hcu_c3_objects_table.py"), "--package-json", str(package),
                    "--output", str(plain)], cwd=ROOT, check=True, capture_output=True, text=True)
    assert "SKY_INDEX" not in plain.read_text()
    # A datum that is not a table entry is refused, never drawn as a wrong model.
    bad = subprocess.run(["python3", "-I", str(ROOT / "tools/hcu_c3_objects_table.py"), "--package-json", str(package),
                          "--output", str(tmp_path / "bad.h"), "--sky-model-datum", "1"],
                         cwd=ROOT, capture_output=True, text=True)
    assert bad.returncode != 0 and "expected 1" in bad.stderr


RENDER_TREE_PACKAGE = ROOT / "build/c3/render-tree/pkg/bloodgulch_mounted_gunner_4p4bot/bloodgulch_mounted_gunner_4p4bot.json"


def _load_generator():
    import importlib.util
    spec = importlib.util.spec_from_file_location("hcu_c3_objects_table", ROOT / "tools/hcu_c3_objects_table.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_objects_table_sky_comes_from_scenario_map(tmp_path):
    if not RENDER_TREE_PACKAGE.exists() or not (ROOT / "build/retail-maps/decompressed/bloodgulch.map").exists():
        pytest.skip("Blood Gulch package or map not built")
    out = tmp_path / "from_scenario.h"
    subprocess.run(["python3", "-I", str(ROOT / "tools/hcu_c3_objects_table.py"), "--package-json",
                    str(RENDER_TREE_PACKAGE), "--sky-from-scenario", "--output", str(out)],
                   cwd=ROOT, check=True, capture_output=True, text=True)
    text = out.read_text()
    assert "#define HCU_C3_OBJECTS_SKY_INDEX 32u" in text
    assert "sky\\\\mp clear afternoon\\\\mp clear afternoon" in text  # the sky MODL is still a table entry


def test_objects_table_sky_disabled_when_map_has_no_sky(tmp_path, monkeypatch):
    if not RENDER_TREE_PACKAGE.exists():
        pytest.skip("Blood Gulch render package not built")
    import sys
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
    from halo2ps2 import skyconv
    monkeypatch.setattr(skyconv, "read_sky", lambda path: None)  # a map with no scenario sky
    gen = _load_generator()
    out = tmp_path / "no_sky.h"
    assert gen.main(["--package-json", str(RENDER_TREE_PACKAGE), "--sky-from-scenario", "--output", str(out)]) == 0
    text = out.read_text()
    assert "SKY_INDEX" not in text
    assert "HCU_C3_OBJECTS_TABLE_COUNT 69u" in text  # objects still load with the sky disabled


def test_objects_table_sky_refuses_mismatched_map(tmp_path):
    if not RENDER_TREE_PACKAGE.exists():
        pytest.skip("Blood Gulch render package not built")
    import json
    manifest = json.loads(RENDER_TREE_PACKAGE.read_text())
    manifest["source_maps"][manifest["profile"]["map"]]["sha256"] = "00" * 32
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(manifest))
    result = subprocess.run(["python3", "-I", str(ROOT / "tools/hcu_c3_objects_table.py"), "--package-json", str(bad),
                             "--sky-from-scenario", "--output", str(tmp_path / "x.h")],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0 and "sha256 mismatch" in result.stderr
