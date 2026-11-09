/* Host test of the SPU2 music stream: a simulated SPU2 (RAM, two voices that play a ring of blocks and honour the
 * loop-end flag) is fed by hcu_spu_stream_tick from an in-memory stream file; what the voices play must be the
 * pieces in the order queued, block for block, with silence after the last. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "stream/hcu_spu_hw.h"
#include "stream/hcu_spu_playback.h"
#include "stream/hcu_spu_stream.h"

#define CHECK(x) do { if (!(x)) { printf("FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)

#define SLICE 16384u
#define PIECES 3u
static const uint32_t k_blocks[PIECES] = { 1500u, 2500u, 1100u };

static uint8_t g_ram[0x200000];
static uint8_t g_file[1u << 20];
static uint32_t g_file_size;
static uint32_t g_piece_offset[PIECES];
static unsigned g_reads, g_fail_read_at;
static uint32_t g_voice_addr[24], g_voice_ssa[24];
static int g_voice_on[24];
static uint32_t g_key_on_mask, g_key_ons;

static uint8_t sample_byte(uint32_t piece, uint32_t channel, uint32_t byte)
{
	if ((byte & 15u) == 1u) return 0; /* a block's flags byte: the stream file carries none */
	return (uint8_t)((byte * 131u + piece * 17u + channel * 59u + (byte >> 7)) ^ 0x5Au);
}

static void put32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }

static void build_file(void)
{
	uint32_t i, at = 32u + PIECES * 16u;
	memset(g_file, 0, sizeof(g_file));
	memcpy(g_file, "HMS1", 4);
	put32(g_file + 4, 1); put32(g_file + 8, 44100); put32(g_file + 12, 2); put32(g_file + 16, PIECES);
	put32(g_file + 20, 32); put32(g_file + 24, at);
	for (i = 0; i < PIECES; ++i) {
		uint32_t bytes = k_blocks[i] * 16u, slice, c;
		g_piece_offset[i] = at;
		put32(g_file + 32 + i * 16, at); put32(g_file + 36 + i * 16, k_blocks[i]);
		put32(g_file + 40 + i * 16, k_blocks[i] * 28u);
		for (slice = 0; slice * SLICE < bytes; ++slice) {
			uint32_t n = bytes - slice * SLICE < SLICE ? bytes - slice * SLICE : SLICE;
			for (c = 0; c < 2u; ++c) {
				uint32_t b;
				for (b = 0; b < n; ++b) g_file[at + c * n + b] = sample_byte(i, c, slice * SLICE + b);
			}
			at += 2u * n;
		}
	}
	g_file_size = at;
	put32(g_file + 28, g_file_size);
}

static int file_read(void *context, uint32_t offset, void *destination, uint32_t bytes)
{
	(void)context;
	g_reads++;
	if (g_fail_read_at && g_reads == g_fail_read_at) return -1;
	if ((uint64_t)offset + bytes > g_file_size) return -1;
	memcpy(destination, g_file + offset, bytes);
	return 0;
}

static void h_param(uint16_t e, uint16_t v) { (void)e; (void)v; }
static void h_addr(uint16_t e, uint32_t v)
{
	uint32_t voice = (e >> 1) & 31u;
	if ((e & 0xFF00u) == 0x2000u) g_voice_ssa[voice] = v;
}
static void h_switch(uint16_t e, uint32_t v)
{
	uint32_t i;
	if ((e & 0xFF00u) == 0x1500u) {
		g_key_on_mask = v; g_key_ons++;
		for (i = 0; i < 24u; ++i) if (v & (1u << i)) { g_voice_on[i] = 1; g_voice_addr[i] = g_voice_ssa[i]; }
	} else if ((e & 0xFF00u) == 0x1600u) {
		for (i = 0; i < 24u; ++i) if (v & (1u << i)) g_voice_on[i] = 0;
	}
}
static uint32_t h_get(uint16_t e) { (void)e; return 0; }
static uint32_t h_get_addr(uint16_t e) { return g_voice_addr[(e >> 1) & 31u]; }
static int h_upload_raw(const void *data, uint32_t bytes, uint32_t addr)
{
	if (addr + bytes > sizeof(g_ram)) return -1;
	memcpy(g_ram + addr, data, bytes);
	return 0;
}
static const hcu_spu_hw hw = { h_param, h_addr, h_switch, h_get, 0, 0, h_get_addr, h_upload_raw };

static uint8_t g_play[2][1u << 20];
static uint32_t g_played[2];

/* The voices play `blocks` blocks: a block's bytes are collected (but for its flags byte) and a loop-end flag sends
 * the voice back to its start address. */
static void play_blocks(uint32_t blocks)
{
	uint32_t v, n;
	for (v = 0; v < 2u; ++v) {
		uint32_t voice = HCU_STREAM_VOICE_L + v;
		for (n = 0; n < blocks; ++n) {
			const uint8_t *block = g_ram + g_voice_addr[voice];
			memcpy(g_play[v] + g_played[v], block, 16u);
			g_play[v][g_played[v] + 1u] = 0;
			g_played[v] += 16u;
			g_voice_addr[voice] = (block[1] & 1u) ? g_voice_ssa[voice] : g_voice_addr[voice] + 16u;
		}
	}
}

static int run(uint32_t step_blocks, uint32_t steps, int late_queue)
{
	uint32_t expected_bytes = 0, i, v, step;
	static uint8_t expected[2][1u << 20];
	hcu_spu_stream_stats stats;
	memset(g_ram, 0, sizeof(g_ram)); memset(g_voice_on, 0, sizeof(g_voice_on));
	g_played[0] = g_played[1] = 0; g_key_ons = 0; g_reads = 0;
	memset(g_voice_addr, 0, sizeof(g_voice_addr)); memset(g_voice_ssa, 0, sizeof(g_voice_ssa));
	for (i = 0; i < PIECES; ++i) {
		uint32_t b;
		for (v = 0; v < 2u; ++v)
			for (b = 0; b < k_blocks[i] * 16u; ++b) expected[v][expected_bytes + b] = sample_byte(i, v, b);
		expected_bytes += k_blocks[i] * 16u;
	}
	for (v = 0; v < 2u; ++v) memset(expected[v] + expected_bytes, 0, 65536u);
	for (i = 0; i < expected_bytes; i += 16u) { expected[0][i + 1u] = 0; expected[1][i + 1u] = 0; }
	/* the blocks of a piece have no flags in the real file; the test file's bytes at flag positions are masked */
	CHECK(hcu_spu_stream_queue(0) == 0 && hcu_spu_stream_queue(1) == 0);
	CHECK(hcu_spu_stream_start(8191) == 0);
	CHECK(g_key_ons == 1 && g_key_on_mask == HCU_STREAM_VOICE_MASK);
	for (step = 0; step < steps; ++step) {
		play_blocks(step_blocks);
		if (late_queue && step == 3) CHECK(hcu_spu_stream_queue(2) == 0);
		hcu_spu_stream_tick();
		hcu_spu_stream_tick();
	}
	hcu_spu_stream_get_stats(&stats);
	CHECK(stats.underruns == 0);
	CHECK(g_played[0] > expected_bytes);
	for (v = 0; v < 2u; ++v) {
		uint32_t compare = late_queue ? expected_bytes : (k_blocks[0] + k_blocks[1]) * 16u;
		uint32_t at;
		for (at = 0; at < compare && at < g_played[v]; at += 16u) {
			uint32_t b;
			for (b = 0; b < 16u; ++b)
				if (b != 1u && g_play[v][at + b] != expected[v][at + b]) {
					printf("mismatch channel %u at byte %u (block %u): %02x != %02x\n", v, at + b, at / 16u,
						g_play[v][at + b], expected[v][at + b]);
					return 1;
				}
		}
	}
	return 0;
}

int main(void)
{
	hcu_spu_stream_source source;
	hcu_spu_stream_stats stats;
	build_file();
	source.read = file_read; source.context = 0; source.size = g_file_size;
	CHECK(hcu_spu_stream_open(&hw, &source) == 0);
	CHECK(hcu_spu_stream_piece_count() == PIECES);
	CHECK(hcu_spu_stream_piece_ms(0) == (uint32_t)((uint64_t)k_blocks[0] * 28u * 1000u / 44100u));
	CHECK(hcu_spu_stream_queue(PIECES) == -1);
	CHECK(hcu_spu_stream_start(8191) == -1); /* nothing queued */
	/* 52 blocks a tick is 33 ms of 44.1 kHz; the late queue adds a third piece while the second plays */
	CHECK(run(52u, 130u, 1) == 0);
	hcu_spu_stream_get_stats(&stats);
	CHECK(stats.pieces_started == 3u && stats.refills > 4u && stats.read_fails == 0);
	hcu_spu_stream_stop();
	CHECK(!hcu_spu_stream_playing());
	/* a bigger step (a stalled frame, 150 ms) still keeps up */
	CHECK(hcu_spu_stream_open(&hw, &source) == 0);
	CHECK(run(236u, 40u, 1) == 0);
	hcu_spu_stream_stop();
	/* a failed read plays silence for that segment and is counted, the stream goes on */
	CHECK(hcu_spu_stream_open(&hw, &source) == 0);
	g_reads = 0; g_fail_read_at = 5;
	CHECK(hcu_spu_stream_queue(1) == 0 && hcu_spu_stream_queue(2) == 0 && hcu_spu_stream_start(8191) == 0);
	{
		unsigned i;
		for (i = 0; i < 20; ++i) { play_blocks(52u); hcu_spu_stream_tick(); hcu_spu_stream_tick(); }
	}
	hcu_spu_stream_get_stats(&stats);
	CHECK(stats.read_fails >= 1u);
	/* a corrupt header is refused */
	g_fail_read_at = 0;
	g_file[0] = 'X';
	CHECK(hcu_spu_stream_open(&hw, &source) != 0 && !hcu_spu_stream_ready());
	printf("spu-stream-ok reads=%u\n", g_reads);
	return 0;
}
