"""Host tests for the C3 content binding helpers (parity log, texture claims, fence reuse)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

MAIN = r"""
#include <stdio.h>
#include "stream/hcu_render_content.h"

static int32_t fence_value;
static uint32_t fence_calls;
static int32_t fake_fence(void *ctx, uint32_t frame) { (void)ctx; (void)frame; fence_calls++; return fence_value; }

int main(void) {
	hcu_render_parity_record store[2];
	hcu_render_parity_log log;
	hcu_render_parity_record r = { 1, 0, HCU_RENDER_PARITY_BSP, 7, 3, 0 };
	hcu_render_texture_claim c;
	if (hcu_render_parity_log_init(&log, store, 2) != 0) return 1;
	if (hcu_render_parity_log_append(&log, &r) != 0) return 2;
	if (log.count != 1 || store[0].surface_id != 7 || store[0].material_id != 3) return 3;
	r.kind = 99;
	if (hcu_render_parity_log_append(&log, &r) != HCU_RENDER_CONTENT_E_ARGUMENT) return 4;
	r.kind = HCU_RENDER_PARITY_SKY;
	if (hcu_render_parity_log_append(&log, &r) != 0) return 5;
	if (hcu_render_parity_log_append(&log, &r) != HCU_RENDER_CONTENT_E_FULL) return 6;
	if (log.dropped != 1 || log.count != 2) return 7;

	/* Claim order: publish is refused before the upload queued. */
	c.state = HCU_RENDER_CLAIM_FREE;
	if (hcu_render_claim_begin(&c, 42, 5) != 0) return 8;
	if (hcu_render_claim_publish(&c) != HCU_RENDER_CONTENT_E_STATE) return 9;
	if (hcu_render_claim_queued(&c, 0, 1) != HCU_RENDER_CONTENT_E_STATE) return 10;
	if (c.state != HCU_RENDER_CLAIM_FREE) return 11;
	if (hcu_render_claim_begin(&c, 42, 5) != 0) return 12;
	if (hcu_render_claim_queued(&c, 1, 9) != 0) return 13;
	if (hcu_render_claim_publish(&c) != 0) return 14;
	/* Source bytes may only be released after the fence reports completion. */
	if (hcu_render_claim_upload_complete(&c, 0) != HCU_RENDER_CONTENT_E_FENCE) return 15;
	if (hcu_render_claim_upload_complete(&c, -1) != HCU_RENDER_CONTENT_E_FENCE) return 16;
	if (hcu_render_claim_upload_complete(&c, 1) != 0) return 17;

	/* Reuse is refused while readers are in flight, and while the fence is pending or failed. */
	fence_calls = 0;
	fence_value = 1;
	if (hcu_render_content_reuse_allowed(fake_fence, 0, 3, 1)) return 18;
	if (fence_calls != 0) return 19;
	if (hcu_render_content_reuse_allowed(fake_fence, 0, 3, 0) != 1) return 20;
	fence_value = 0;
	if (hcu_render_content_reuse_allowed(fake_fence, 0, 3, 0)) return 21;
	fence_value = -1;
	if (hcu_render_content_reuse_allowed(fake_fence, 0, 3, 0)) return 22;
	if (hcu_render_content_reuse_allowed(0, 0, 3, 0)) return 23;
	printf("hcu_render_content ok\n");
	return 0;
}
"""


def test_render_content_binding(tmp_path):
    compiler = shutil.which("gcc")
    if not compiler:
        pytest.skip("GCC unavailable")
    main_c = tmp_path / "main.c"
    main_c.write_text(MAIN)
    exe = tmp_path / "hcu_render_content_test"
    cmd = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
           "-I", str(ROOT / "src"), str(main_c),
           str(ROOT / "src/stream/hcu_render_content.c"), "-o", str(exe)]
    subprocess.run(cmd, check=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
