/* Platform side of the M08 hybrid proof. Gameplay snapshots arrive by value.
 * DMA, VIF, VU1, and GS stay in this file.
 */
#include <dma.h>
#include <draw.h>
#include <kernel.h>
#include <packet2.h>
#include <packet2_utils.h>
#include <packet2_vif.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "hybrid/replay.h"
#include "platform/timer.h"
#include "platform/video.h"
#include "render/chain.h"
#include "render/gs.h"
#include "render/upload.h"

extern u32 PlatformVu_Start, PlatformVu_End;
#define CHAIN_CAPACITY 64
#define CANARY 0xC0FFEE1234567890ULL
static struct {
    u64 before[2];
    u64 data[CHAIN_CAPACITY * 2];
    u64 after[2];
} guarded __attribute__((aligned(64)));
static u32 pixels[8 * 8] __attribute__((aligned(64)));
static unsigned max_chain_qw;
static video_t video;
static packet2_t *state;
static u64 paced_elapsed;
static u32 paced_previous;
static uintptr_t heap_start;
static int pacing;

static _Noreturn void fail(const char *reason)
{
    printf("HALO_PS2_FAIL reason=%s\n", reason);
    for (;;) SleepThread();
}

static void upload_vu1(void)
{
    u32 count = packet2_utils_get_packet_size_for_program(&PlatformVu_Start, &PlatformVu_End) + 1;
    packet2_t *packet = packet2_create(count, P2_TYPE_NORMAL, P2_MODE_CHAIN, 1);
    if (!packet) fail("microprogram-allocation");
    packet2_vif_add_micro_program(packet, 0, &PlatformVu_Start, &PlatformVu_End);
    packet2_utils_vu_add_end_tag(packet);
    dma_channel_send_packet2(packet, DMA_CHANNEL_VIF1, 1);
    dma_channel_wait(DMA_CHANNEL_VIF1, 0);
    packet2_free(packet);
}

static void submit(chain_t *chain, int channel)
{
    chain_end(chain, 0);
    if (chain->overflow || guarded.before[0] != CANARY || guarded.after[0] != CANARY ||
        guarded.before[1] != CANARY || guarded.after[1] != CANARY)
        fail("dma-buffer-canary");
    if (chain->qw > max_chain_qw) max_chain_qw = chain->qw;
    SyncDCache(guarded.data, guarded.data + CHAIN_CAPACITY * 2);
    dma_channel_send_chain(channel, guarded.data, 0, 0, 0);
    dma_channel_wait(channel, 0);
}

static void draw_snapshot(const struct hybrid_snapshot *snapshot, void *user)
{
    chain_t chain;
    u32 *words;
    u64 *quads;
    float *values;
    unsigned index;
    float shift_x = 0, shift_y = 0;
    const float positions[3][2] = { {-0.35f, 0.28f}, {0.35f, 0.28f}, {0.0f, -0.35f} };
    const float uv[3][2] = { {0.0f, 1.0f}, {1.0f, 1.0f}, {0.5f, 0.0f} };
    (void)user;
    if (pacing) {
        u64 need = ((u64)snapshot->tick + 1) * EE_CLOCK_HZ / 30;
        while (paced_elapsed < need) {
            u32 now = timer_cycles();
            paced_elapsed += (u32)(now - paced_previous);
            paced_previous = now;
        }
        if ((uintptr_t)sbrk(0) != heap_start) fail("steady-state-heap-growth");
    }
    if (snapshot->count) {
        shift_x = (float)snapshot->items[0].x * (1.0f / 40.0f);
        shift_y = (float)snapshot->items[0].y * (1.0f / 40.0f);
    }
    packet2_reset(state, 0);
    video_add_setup_env(&video, state);
    video_add_clear(&video, state, 12, 22, 42);
    packet2_add_u64(state, GIF_TAG(5, 1, 0, 0, GIFX_FLG_PACKED, 1));
    packet2_add_u64(state, GIF_REGS_AD);
    packet2_add_u64(state, GS_TEX0(video.tex_base / 64, 1, GS_PSMCT32, 3, 3, 1, 0, 0, 0, 0, 0, 0));
    packet2_add_u64(state, GS_A_TEX0_1);
    packet2_add_u64(state, GS_TEX1(1, 0, 0, 0, 0, 0, 0)); packet2_add_u64(state, GS_A_TEX1_1);
    packet2_add_u64(state, GS_CLAMP(1, 1, 0, 0, 0, 0)); packet2_add_u64(state, GS_A_CLAMP_1);
    packet2_add_u64(state, GS_TEST(0, 1, 0, 0, 0, 0, 1, 1)); packet2_add_u64(state, GS_A_TEST_1);
    packet2_add_u64(state, 0); packet2_add_u64(state, GS_A_TEXFLUSH);
    dma_channel_send_packet2(state, DMA_CHANNEL_GIF, 1);
    dma_channel_wait(DMA_CHANNEL_GIF, 0);
    chain_init(&chain, guarded.data, CHAIN_CAPACITY);
    words = chain_cnt(&chain, 13, 0);
    if (!words) fail("vertex-chain-overflow");
    words[0] = 0; words[1] = 0;
    words[2] = VIF_CODE(VIF_STCYCL, 0, 0x0101);
    words[3] = VIF_CODE(VIF_UNPACK_V4_32, 12, 0);
    values = (float *)(words + 4);
    values[0] = 190; values[1] = 155; values[2] = 1; values[3] = 1;
    values[4] = 2048; values[5] = 2048; values[6] = 65536; values[7] = 0;
    quads = (u64 *)(values + 8);
    quads[0] = GIF_TAG(3, 1, 1, GS_PRIM(3, 0, 1, 0, 0, 0, 0, 0, 0), 0, 3);
    quads[1] = 0x512;
    for (index = 0; index < 3; ++index) {
        float *vertex = values + 12 + 12 * index;
        u32 *colour = (u32 *)(vertex + 4);
        vertex[0] = uv[index][0]; vertex[1] = uv[index][1]; vertex[2] = 1; vertex[3] = 0;
        colour[0] = colour[1] = colour[2] = colour[3] = 0x80;
        vertex[8] = positions[index][0] + shift_x;
        vertex[9] = positions[index][1] + shift_y;
        vertex[10] = 0; vertex[11] = 1;
    }
    words = chain_cnt(&chain, 4, 0);
    if (!words) fail("finish-chain-overflow");
    words[0] = VIF_CODE(VIF_MSCAL, 0, 0); words[1] = VIF_CODE(VIF_FLUSHA, 0, 0);
    words[2] = 0; words[3] = VIF_CODE(VIF_DIRECT, 0, 2);
    quads = (u64 *)(words + 4);
    quads[0] = GIF_TAG(1, 1, 0, 0, 0, 1); quads[1] = GIF_REGS_AD;
    quads[2] = 1; quads[3] = GS_A_FINISH;
    words[12] = words[13] = words[14] = words[15] = 0;
    submit(&chain, DMA_CHANNEL_VIF1);
    draw_wait_finish();
    video_present(&video);
    if (pacing && (snapshot->tick <= 1 || (snapshot->tick % 30) == 0)) {
        int x = snapshot->count ? snapshot->items[0].x : 0;
        int y = snapshot->count ? snapshot->items[0].y : 0;
        printf("HALO_PS2_HYBRID_FRAME tick=%u x=%d y=%d elapsed_ms=%u heap=%u chain_high=%u guards=ok\n",
               (unsigned)snapshot->tick, x, y, (unsigned)(paced_elapsed / (EE_CLOCK_HZ / 1000)),
               (unsigned)heap_start, max_chain_qw);
    }
}

static unsigned finish_schedule(const char *name, unsigned cadence, hybrid_present_fn present, struct hybrid_snapshot *final)
{
    unsigned hash = 0;
    if (hybrid_replay(cadence, &hash, final, present, NULL)) fail(name);
    printf("HALO_PS2_HYBRID schedule=%s event_hash=%u ticks=%u created=%u destroyed=%u rejected=%u\n",
           name, hash, (unsigned)final->tick, (unsigned)final->created, (unsigned)final->destroyed, (unsigned)final->rejected);
    return hash;
}

int main(void)
{
    chain_t chain;
    unsigned index;
    unsigned suppressed, delayed, normal;
    struct hybrid_snapshot quiet, late, shown;
    unsigned elapsed_ms;
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("HALO_PS2_HYBRID log-before-graphics\n");
    guarded.before[0] = guarded.before[1] = guarded.after[0] = guarded.after[1] = CANARY;
    dma_channel_initialize(DMA_CHANNEL_GIF, NULL, 0);
    dma_channel_initialize(DMA_CHANNEL_VIF1, NULL, 0);
    video_init(&video);
    upload_vu1();
    for (index = 0; index < 64; ++index)
        pixels[index] = ((index / 8 / 2 + index % 8 / 2) & 1) ? 0x80F0D030u : 0x8040F0F0u;
    SyncDCache(pixels, pixels + 64);
    chain_init(&chain, guarded.data, CHAIN_CAPACITY);
    if (gs_upload(&chain, pixels, sizeof pixels, video.tex_base / 64, 1, GS_PSMCT32, 8, 8))
        fail("texture-chain-overflow");
    submit(&chain, DMA_CHANNEL_GIF);
    state = packet2_create(128, P2_TYPE_NORMAL, P2_MODE_NORMAL, 0);
    if (!state) fail("state-allocation");
    heap_start = (uintptr_t)sbrk(0);
    suppressed = finish_schedule("suppressed", 0, NULL, &quiet);
    delayed = finish_schedule("delayed", 7, NULL, &late);
    if (suppressed != delayed || memcmp(&quiet, &late, sizeof quiet)) fail("schedule-mismatch");
    pacing = 1;
    paced_previous = timer_cycles();
    paced_elapsed = 0;
    normal = finish_schedule("normal", 1, draw_snapshot, &shown);
    elapsed_ms = (unsigned)(paced_elapsed / (EE_CLOCK_HZ / 1000));
    if (normal != suppressed || memcmp(&quiet, &shown, sizeof quiet)) fail("render-dependence");
    if (elapsed_ms < 600000) fail("short-smoke");
    if ((uintptr_t)sbrk(0) != heap_start) fail("steady-state-heap-growth");
    printf("{\"fixture\":\"hybrid\",\"ticks\":18000,\"created\":30,\"destroyed\":30,\"stale_rejected\":30,\"event_hash\":%u,\"presentation_independent\":true,\"elapsed_ms\":%u,\"status\":\"passed\"}\n",
           normal, elapsed_ms);
    printf("HALO_PS2_HYBRID outcome=passed elapsed_ms=%u heap=%u chain_high=%u guards=ok\n",
           elapsed_ms, (unsigned)heap_start, max_chain_qw);
    for (;;) SleepThread();
}
