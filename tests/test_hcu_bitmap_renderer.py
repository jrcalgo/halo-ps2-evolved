"""Host test for the parent-renderer adapter, plus the DMA budget invariant of bsp_render.c."""
import json
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine/src"
BSP = ENGINE / "render/bsp_render.c"


def test_renderer_dma_budget_unchanged():
    text = BSP.read_text()
    # CHAIN_QW and UPLOAD_QW name the storage.h layout macros (or a literal at HEAD).
    storage = (ENGINE / "render/storage.h").read_text()
    chain_qw = int(re.search(r"#define BSP_RENDER_GEOMETRY_CHAIN_QW\s+(\d+)", storage).group(1))
    upload_qw = int(re.search(r"#define BSP_RENDER_UPLOAD_CHAIN_QW\s+(\d+)", storage).group(1))
    assert re.search(r"#define CHAIN_QW\s+BSP_RENDER_GEOMETRY_CHAIN_QW", text)
    assert re.search(r"#define UPLOAD_QW\s+BSP_RENDER_UPLOAD_CHAIN_QW", text)
    # Reshaped by submodule commit bc9044d: geometry 34816 qw, upload 2048 qw (same total as before).
    assert (chain_qw, upload_qw) == (34816, 2048)
    # Two geometry chains and two upload chains, 16-byte quadwords, must fill the dma_commands owner exactly.
    total = 2 * chain_qw * 16 + 2 * upload_qw * 16
    budget = json.loads((ROOT / "config/memory-budget.json").read_text())
    owner = next(r["bytes"] for r in budget["regions"] if r["name"] == "dma_commands")
    assert owner == 1179648
    assert total == owner
    assert text.count("alloc_uncached((size_t)CHAIN_QW * 16)") == 1
    assert text.count("alloc_uncached((size_t)UPLOAD_QW * 16)") == 1


def test_renderer_hooks_default_off():
    text = BSP.read_text()
    # With no hooks registered the static hook table is zero and emit/submit never run.
    assert "static bsp_render_frame_hooks s_hooks;" in text
    assert "s_hook_frame_emit = s_hooks.begin ? s_hooks.begin(s_hooks.user, frame) == 0 : 0;" in text
    assert "if (s_hooks.submit) s_hooks.submit(s_hooks.user, s_build_frame, s_kick_seq);" in text


def test_renderer_adapter_host(tmp_path):
    compiler = shutil.which("gcc")
    if not compiler:
        pytest.skip("GCC unavailable")
    import subprocess
    exe = tmp_path / "hcu-bitmap-renderer"
    cmd = [compiler, "-std=gnu89", "-Wall", "-Wextra", "-Werror",
           "-I", str(ROOT / "src"), "-I", str(ENGINE), "-I", str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
           str(ROOT / "tests/hcu_bitmap_renderer_main.c"), str(ROOT / "src/stream/hcu_bitmap_renderer.c"),
           str(ENGINE / "render/chain.c"), str(ENGINE / "render/texcache.c"), "-o", str(exe)]
    built = subprocess.run(cmd, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    ran = subprocess.run([str(exe)], capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "PASSED" in ran.stdout


def test_renderer_fence_skip_then_kick_host(tmp_path):
    compiler = shutil.which("gcc")
    if not compiler:
        pytest.skip("GCC unavailable")
    import subprocess
    exe = tmp_path / "hcu-bitmap-fence"
    cmd = [compiler, "-std=gnu89", "-Wall", "-Wextra", "-Werror",
           "-I", str(ROOT / "src"), "-I", str(ENGINE), "-I", str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
           str(ROOT / "tests/hcu_bitmap_fence_main.c"), str(ROOT / "src/stream/hcu_bitmap_renderer.c"),
           str(ROOT / "src/stream/hcu_bitmap_frame.c"), str(ROOT / "src/stream/hcu_render_frame.c"),
           str(ROOT / "src/stream/sha256.c"),
           str(ENGINE / "render/chain.c"), str(ENGINE / "render/texcache.c"), "-o", str(exe)]
    built = subprocess.run(cmd, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    ran = subprocess.run([str(exe)], capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "PASSED" in ran.stdout


def test_bsp_fence_model_wired_in_bsp_render():
    text = BSP.read_text()
    assert '#include "render/bsp_fence_seq.h"' in text
    assert "bsp_fence_seq_query(s_completed_kick_seq, s_kick_seq, kick_seq, s_vif_seen, s_gs_seen)" in text
    # The submit hook is a single-line call in bsp_render_kick (bsp_render.c:1320 at C3.10).
    assert "if (s_hooks.submit) s_hooks.submit(s_hooks.user, s_build_frame, s_kick_seq);" in text


def test_renderer_kick_retires_previous_before_clear():
    # bsp_render_kick polls and retires the previous kick before GS_CSR is cleared, with or without hooks (C3.10,
    # bsp_render.c:1288-1291), so a FINISH that was not yet recorded is observed instead of erased. The late retire
    # before the observation reset stays (bsp_render.c:1308-1311).
    text = BSP.read_text()
    kick = text[text.index("void bsp_render_kick(video_t *v)"):]
    kick = kick[:kick.index("\n}\n") + 3]
    early = kick.index("bsp_render_poll();")
    clear = kick.index("*GS_CSR = 2;")
    assert early < clear
    assert kick[early:clear].count("bsp_render_poll();") == 1
    assert "s_completed_kick_seq = bsp_fence_seq_retire(s_completed_kick_seq, s_kick_seq, s_vif_seen, s_gs_seen);" in kick[early:clear]
    # The early retire is not gated on the hook table.
    assert "s_hooks" not in kick[early:clear]
    late = kick.index("s_vif_seen = s_gs_seen = 0;")
    assert clear < late
    assert kick[clear:late].count("bsp_render_poll();") == 1
    assert "s_completed_kick_seq = bsp_fence_seq_retire(s_completed_kick_seq, s_kick_seq, s_vif_seen, s_gs_seen);" in kick[clear:late]
    assert kick.count("if (s_hooks.submit) s_hooks.submit(") == 1


def test_renderer_emit_failure_recorded_in_bsp():
    text = BSP.read_text()
    assert "s_emit_status = s_hooks.emit(s_hooks.user, frame, c, &s_upload[s_build], &s_tc);" in text
    # The DMA lane restructured the counting into a block; the same count must still follow the emit call.
    assert re.search(r"if \(s_emit_status\) \{\s*s_emit_failures\+\+;", text)
    assert text.count("s_hooks.emit(") == 1


def test_renderer_fence_failure_host(tmp_path):
    compiler = shutil.which("gcc")
    if not compiler:
        pytest.skip("GCC unavailable")
    import subprocess
    exe = tmp_path / "hcu-bitmap-fence-failure"
    cmd = [compiler, "-std=gnu89", "-Wall", "-Wextra", "-Werror",
           "-I", str(ROOT / "src"), "-I", str(ENGINE), "-I", str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
           str(ROOT / "tests/hcu_bitmap_fence_main.c"), str(ROOT / "src/stream/hcu_bitmap_renderer.c"),
           str(ROOT / "src/stream/hcu_bitmap_frame.c"), str(ROOT / "src/stream/hcu_render_frame.c"),
           str(ROOT / "src/stream/sha256.c"),
           str(ENGINE / "render/chain.c"), str(ENGINE / "render/texcache.c"), "-o", str(exe)]
    built = subprocess.run(cmd, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    ran = subprocess.run([str(exe)], capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "PASSED" in ran.stdout
