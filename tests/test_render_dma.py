"""C2.6/C2.7 renderer DMA evidence: exact chain layout, packet workspace spans, the idle-chain rule,
renderer owner samplers, and the snapshot emit wiring in the attach hook."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "submodules/halo-ps2/engine/src"


def _build_and_run(sources, name, temp):
    executable = Path(temp) / name
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I" + str(ROOT / "src"), "-I" + str(ENGINE),
        *[str(s) for s in sources], "-o", str(executable),
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    subprocess.run([str(executable)], check=True, capture_output=True, text=True)


def test_renderer_chain_layout_workspace_and_idle_rule_host():
    with tempfile.TemporaryDirectory(prefix="render-dma-storage-") as temp:
        _build_and_run([ROOT / "tests/bsp_render_storage_main.c"], "storage-test", temp)


def test_renderer_owner_samplers_and_registry_host():
    with tempfile.TemporaryDirectory(prefix="render-dma-telemetry-") as temp:
        _build_and_run([
            ROOT / "tests/render_dma_telemetry_main.c",
            ROOT / "src/stream/hcu_render_telemetry.c",
            ROOT / "src/stream/hcu_owner_telemetry.c",
        ], "telemetry-test", temp)


def test_owner_registry_separates_ee_and_gs_domains_and_rejects_cross_domain_parent():
    with tempfile.TemporaryDirectory(prefix="owner-domain-telemetry-") as temp:
        _build_and_run([
            ROOT / "tests/hcu_owner_telemetry_main.c",
            ROOT / "src/stream/hcu_owner_telemetry.c",
        ], "owner-domain-test", temp)


def test_bsp_render_counts_chains_and_refuses_inflight_build():
    text = (ENGINE / "render/bsp_render.c").read_text()
    # The build redirects off the in-flight chain and the emit is gated by the same rule.
    assert "if (!bsp_render_chain_is_idle(s_build, s_inflight, s_kick_index)) {" in text
    assert "s_idle_violations++;" in text
    assert "s_kick_index = (u32)s_build;" in text
    assert "s_geom_stat[s_build].resets++;" in text
    assert "int bsp_render_dma_counters(bsp_render_owner_counters *g, bsp_render_owner_counters *u)" in text
    assert "int bsp_render_texcache_counters(bsp_render_owner_counters *out)" in text
    assert "_Static_assert(CACHE_FIRST_PAGE == 17u" in text
    header = (ENGINE / "render/bsp_render.h").read_text()
    assert "u32  bsp_render_idle_violations(void);" in header


def test_snapshot_emit_is_wired_before_bitmap_drain_and_reports_failure():
    attach = (ROOT / "src/stream/hcu_bitmap_attach.c").read_text()
    assert '#include "stream/hcu_render_snapshot.h"' in attach
    body = attach[attach.index("static int32_t attach_emit("):attach.index("static void attach_submit(")]
    assert "hcu_render_snapshot_emit_chain(geometry) < 0" in body
    assert body.index("hcu_render_snapshot_emit_chain(geometry)") < body.index("hcu_bitmap_renderer_hook_emit(")
    assert "HCU_BITMAP_FRAME_E_QUEUE : status" in body


def test_telemetry_module_has_the_three_owner_samplers():
    header = (ROOT / "src/stream/hcu_render_telemetry.h").read_text()
    source = (ROOT / "src/stream/hcu_render_telemetry.c").read_text()
    for name in ("hcu_render_telemetry_sample_dma",
                 "hcu_render_telemetry_sample_render_chunks",
                 "hcu_render_telemetry_sample_gs_window",
                 "hcu_render_telemetry_sample_gs_texture"):
        assert name + "(void *ctx, hcu_owner_sample_t *out)" in header
        assert name + "(void *ctx, hcu_owner_sample_t *out)" in source
