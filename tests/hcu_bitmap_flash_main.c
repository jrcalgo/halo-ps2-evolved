#include "stream/hcu_bitmap_quad.h"
#include "render/gs.h"

#include <stdint.h>
#include <string.h>

/* Separate restore packet: DMA tag + VIF qword + GIF tag + 4 A+D registers. */
#define RESTORE_QW 7u

static int check_restore(const uint64_t *memory, unsigned flash_qw)
{
	const uint64_t *tag = memory + flash_qw * 2u;
	const uint32_t *words = (const uint32_t *)(tag + 2);
	const uint64_t *q = (const uint64_t *)(words + 4);
	uint32_t xo = (2048u * 16u) - 640u * 8u;
	uint32_t yo = (2048u * 16u) - 448u * 8u;
	if ((tag[0] & 0xFFFFu) != 6u || ((tag[0] >> 28) & 7u) != DMA_ID_CNT) return 14;
	if ((words[3] & 0xFFFFu) != 5u) return 15;
	if (q[0] != GIF_TAG(4, 1, 0, 0, GIFX_FLG_PACKED, 1) || q[1] != GIF_REGS_AD) return 16;
	if (q[2] != GS_TEST(0, 1, 0, 0, 0, 0, 1, 1) || q[3] != GS_A_TEST_1) return 17;
	if (q[4] != GS_ALPHA(0, 1, 0, 1, 0) || q[5] != GS_A_ALPHA_1) return 18;
	if (q[6] != ((uint64_t)xo | ((uint64_t)yo << 32)) || q[7] != 0x18u) return 19;
	if (q[8] != ((639ull << 16) | (447ull << 48)) || q[9] != 0x40u) return 20;
	return 0;
}

static int check_caps(void)
{
	uint64_t memory[96 * 2];
	chain_t chain;
	hcu_bitmap_rect rect = { 0, 0, 640, 448 };
	uint64_t *q;
	int rc;
	hcu_bitmap_quad_status status;
	memset(memory, 0xA5, sizeof memory);
	chain_init(&chain, memory, 96);
	status = hcu_bitmap_quad_emit_flash(&chain, 640, 448, &rect, 1u, 2, 0xFF000000u);
	if (status != HCU_BITMAP_QUAD_OK || chain.qw != 26u + RESTORE_QW) return 40;
	q = (uint64_t *)((uint8_t *)memory + 32);
	if (q[2] != GS_ALPHA(0, 1, 0, 1, 0) || (uint32_t)(q[13] >> 32) != 96u) return 41;
	if ((rc = check_restore(memory, 26u)) != 0) return rc;
	memset(memory, 0xA5, sizeof memory);
	chain_init(&chain, memory, 96);
	status = hcu_bitmap_quad_emit_flash(&chain, 640, 448, &rect, 1u, 1, 0xFF010000u);
	if (status != HCU_BITMAP_QUAD_OK || chain.qw != 26u + RESTORE_QW) return 44;
	q = (uint64_t *)((uint8_t *)memory + 32);
	if (q[12 + 36] == GIF_TAG(1, 1, 0, 0, GIFX_FLG_PACKED, 1)) return 45;
	if ((uint32_t)(q[13] >> 32) != 96u) return 46;
	memset(memory, 0xA5, sizeof memory);
	chain_init(&chain, memory, 96);
	status = hcu_bitmap_quad_emit_flash(&chain, 640, 448, &rect, 1u, 3, 0xFFFFFFFFu);
	if (status != HCU_BITMAP_QUAD_OK || chain.qw != 47u + RESTORE_QW) return 47;
	q = (uint64_t *)((uint8_t *)memory + 32);
	if ((uint32_t)q[12] != 96u || (uint32_t)(q[12] >> 32) != 96u) return 48;
	if ((uint32_t)q[13] != 96u || (uint32_t)(q[13] >> 32) != 96u) return 49;
	if (q[48 + 2] != GS_ALPHA(0, 2, 2, 1, 128)) return 50;
	return check_restore(memory, 47u);
}

int main(int argc, char **argv)
{
	uint64_t memory[96 * 2]; chain_t chain; uint64_t *q; uint32_t *words;
	hcu_bitmap_rect rect = { 320, 0, 320, 224 };
	const char *mode = argc > 1 ? argv[1] : "lighten";
	int16_t type = 1; unsigned flash_qw = 47u; unsigned expect_qw = 47u + RESTORE_QW;
	uint64_t alpha = GS_ALPHA(2, 1, 0, 1, 0);
	uint32_t expect_r = 96u;
	hcu_bitmap_quad_status status;
	int rc;
	memset(memory, 0xA5, sizeof memory); chain_init(&chain, memory, 96);
	if (!strcmp(mode, "darken")) {
		type = 2; flash_qw = 26u; expect_qw = 26u + RESTORE_QW;
		alpha = GS_ALPHA(0, 1, 0, 1, 0); expect_r = 128u;
	}
	if (!strcmp(mode, "tint")) {
		type = 6; flash_qw = 26u; expect_qw = 26u + RESTORE_QW;
		alpha = GS_ALPHA(0, 1, 0, 1, 0); expect_r = 128u;
	}
	if (!strcmp(mode, "invert")) {
		status = hcu_bitmap_quad_emit_flash(&chain, 640, 448, &rect, 0xFFFFFFu, 5, 0x80FF0000u);
		return status == HCU_BITMAP_QUAD_OK && chain.qw == 0 && ((uint8_t *)memory)[0] == 0xA5 ? 0 : 30;
	}
	if (!strcmp(mode, "overflow")) {
		chain.cap_qw = 40;
		status = hcu_bitmap_quad_emit_flash(&chain, 640, 448, &rect, 0xFFFFFFu, 1, 0x80FF0000u);
		return status == HCU_BITMAP_QUAD_CAPACITY && chain.qw == 0 && !chain.overflow &&
			((uint8_t *)memory)[0] == 0xA5 ? 0 : 31;
	}
	if (!strcmp(mode, "bad_rect")) {
		rect.w = 400;
		status = hcu_bitmap_quad_emit_flash(&chain, 640, 448, &rect, 0xFFFFFFu, 1, 0x80FF0000u);
		return status == HCU_BITMAP_QUAD_INVALID && chain.qw == 0 ? 0 : 32;
	}
	status = hcu_bitmap_quad_emit_flash(&chain, 640, 448, &rect, 0xFFFFFFu, type, 0x80FF4020u);
	if (status != HCU_BITMAP_QUAD_OK || chain.qw != expect_qw) return 1;
	if (((memory[0] >> 28) & 7u) != DMA_ID_CNT || (memory[0] & 0xFFFFu) != flash_qw - 1u) return 2;
	words = (uint32_t *)((uint8_t *)memory + 16);
	if ((words[3] & 0xFFFFu) != flash_qw - 2u) return 3;
	q = (uint64_t *)((uint8_t *)memory + 32);
	if (q[0] != GIF_TAG(4, 1, 0, 0, GIFX_FLG_PACKED, 1) || q[1] != GIF_REGS_AD) return 4;
	if (q[2] != alpha || q[3] != GS_A_ALPHA_1) return 5;
	if (q[4] != GS_TEST(0, 1, 0, 0, 0, 0, 1, 1) || q[5] != GS_A_TEST_1) return 6;
	/* full-framebuffer XYOFFSET, then scissor exactly the view rectangle */
	if (q[7] != 0x18u) return 7;
	if (q[8] != (320ull | 639ull << 16 | 0ull << 32 | 223ull << 48)) return 7;
	/* untextured (TME 0), alpha blending on */
	if (q[10] != GIF_TAG(6, 1, 1, GS_PRIM(GSX_PRIM_TRIANGLE, 1, 0, 0, 1, 0, 1, 0, 0), GIFX_FLG_PACKED, 3) || q[11] != 0x531) return 8;
	/* lighten/max cap full red at GS 96; alpha 0x80 stays 64. Depth is preserved. */
	if ((uint32_t)q[12] != expect_r || (uint32_t)(q[12] >> 32) != 32u || (uint32_t)q[13] != 16u ||
		(uint32_t)(q[13] >> 32) != 64u || q[17] != 0xFFFFFFu) return 9;
	/* the quad corner lands on the view's top-left in GS coordinates (48 + 320) * 16 */
	if ((uint32_t)q[16] != (uint32_t)((2048 - 320 + 320) * 16)) return 10;
	if (type == 1) {
		if (q[12 + 36] != GIF_TAG(1, 1, 0, 0, GIFX_FLG_PACKED, 1) || q[48 + 2] != GS_ALPHA(0, 2, 2, 1, 128)) return 11;
		if (memcmp(q + 12, q + 12 + 36 + 6, 36u * sizeof(uint64_t))) return 12;
	}
	if ((rc = check_restore(memory, flash_qw)) != 0) return rc;
	if (((uint8_t *)memory)[chain.qw * 16u] != 0xA5) return 13;
	if (type == 1 && (rc = check_caps()) != 0) return rc;
	return 0;
}
