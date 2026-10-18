/* M06 synthetic EE/VIF1/VU1/GS fixture. No retail data or gameplay implementation. */
#include <dma.h>
#include <draw.h>
#include <kernel.h>
#include <packet2.h>
#include <packet2_utils.h>
#include <packet2_vif.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "platform/pad.h"
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

static _Noreturn void fail(const char *reason)
{
    printf("HALO_PS2_FAIL reason=%s\n", reason);
    for (;;) SleepThread();
}

static void upload_vu1(void)
{
    u32 count = packet2_utils_get_packet_size_for_program(&PlatformVu_Start, &PlatformVu_End) + 1;
    packet2_t *packet = packet2_create(count, P2_TYPE_NORMAL, P2_MODE_CHAIN, 1);
    if (!packet) { fail("microprogram-allocation"); return; }
    packet2_vif_add_micro_program(packet, 0, &PlatformVu_Start, &PlatformVu_End);
    packet2_utils_vu_add_end_tag(packet);
    dma_channel_send_packet2(packet, DMA_CHANNEL_VIF1, 1);
    dma_channel_wait(DMA_CHANNEL_VIF1, 0);
    packet2_free(packet);
    printf("HALO_PS2_PLATFORM vu1_bytes=%u\n", (unsigned)((uintptr_t)&PlatformVu_End - (uintptr_t)&PlatformVu_Start));
}

static void submit(chain_t *c, int channel)
{
    chain_end(c, 0);
    if (c->overflow || guarded.before[0] != CANARY || guarded.after[0] != CANARY ||
        guarded.before[1] != CANARY || guarded.after[1] != CANARY) {
        fail("dma-buffer-canary"); return;
    }
    if (c->qw > max_chain_qw) max_chain_qw = c->qw;
    SyncDCache(guarded.data, guarded.data + CHAIN_CAPACITY * 2);
    dma_channel_send_chain(channel, guarded.data, 0, 0, 0);
    dma_channel_wait(channel, 0);
}

static void texture_init(video_t *v)
{
    chain_t c;
    unsigned i;
    for (i = 0; i < 64; ++i)
        pixels[i] = ((i / 8 / 2 + i % 8 / 2) & 1) ? 0x80F0D030u : 0x8040F0F0u;
    SyncDCache(pixels, pixels + 64);
    chain_init(&c, guarded.data, CHAIN_CAPACITY);
    if (gs_upload(&c, pixels, sizeof pixels, v->tex_base / 64, 1, GS_PSMCT32, 8, 8)) {
        fail("texture-chain-overflow"); return;
    }
    submit(&c, DMA_CHANNEL_GIF);
}

static void draw_frame(video_t *v, packet2_t *state, unsigned frame)
{
    chain_t c;
    u32 *w;
    u64 *q;
    float *f;
    unsigned i;
    const float positions[3][2] = { {-0.9f, 0.75f}, {0.9f, 0.75f}, {0.0f, -0.9f} };
    const float uv[3][2] = { {0.0f, 1.0f}, {1.0f, 1.0f}, {0.5f, 0.0f} };
    packet2_reset(state, 0);
    video_add_setup_env(v, state);
    video_add_clear(v, state, 12, 22, 42);
    packet2_add_u64(state, GIF_TAG(5, 1, 0, 0, GIFX_FLG_PACKED, 1));
    packet2_add_u64(state, GIF_REGS_AD);
    packet2_add_u64(state, GS_TEX0(v->tex_base / 64, 1, GS_PSMCT32, 3, 3, 1, 0, 0, 0, 0, 0, 0));
    packet2_add_u64(state, GS_A_TEX0_1);
    packet2_add_u64(state, GS_TEX1(1, 0, 0, 0, 0, 0, 0)); packet2_add_u64(state, GS_A_TEX1_1);
    packet2_add_u64(state, GS_CLAMP(1, 1, 0, 0, 0, 0)); packet2_add_u64(state, GS_A_CLAMP_1);
    packet2_add_u64(state, GS_TEST(0, 1, 0, 0, 0, 0, 1, 1)); packet2_add_u64(state, GS_A_TEST_1);
    packet2_add_u64(state, 0); packet2_add_u64(state, GS_A_TEXFLUSH);
    dma_channel_send_packet2(state, DMA_CHANNEL_GIF, 1);
    dma_channel_wait(DMA_CHANNEL_GIF, 0);

    chain_init(&c, guarded.data, CHAIN_CAPACITY);
    w = chain_cnt(&c, 13, 0);
    if (!w) { fail("vertex-chain-overflow"); return; }
    w[0] = 0; w[1] = 0;
    w[2] = VIF_CODE(VIF_STCYCL, 0, 0x0101);
    w[3] = VIF_CODE(VIF_UNPACK_V4_32, 12, 0);
    f = (float *)(w + 4);
    f[0] = 190; f[1] = 155; f[2] = 1; f[3] = 1;
    f[4] = 2048;
    f[5] = 2048; f[6] = 65536; f[7] = 0;
    q = (u64 *)(f + 8);
    q[0] = GIF_TAG(3, 1, 1, GS_PRIM(3, 0, 1, 0, 0, 0, 0, 0, 0), 0, 3);
    q[1] = 0x512; /* ST, RGBAQ, XYZ2 */
    for (i = 0; i < 3; ++i) {
        float *vertex = f + 12 + 12 * i;
        u32 *colour = (u32 *)(vertex + 4);
        vertex[0] = uv[i][0]; vertex[1] = uv[i][1]; vertex[2] = 1; vertex[3] = 0;
        colour[0] = colour[1] = colour[2] = colour[3] = 0x80;
        vertex[8] = positions[i][0]; vertex[9] = positions[i][1]; vertex[10] = 0; vertex[11] = 1;
    }
    w = chain_cnt(&c, 4, 0);
    if (!w) { fail("finish-chain-overflow"); return; }
    w[0] = VIF_CODE(VIF_MSCAL, 0, 0); w[1] = VIF_CODE(VIF_FLUSHA, 0, 0);
    w[2] = 0; w[3] = VIF_CODE(VIF_DIRECT, 0, 2);
    q = (u64 *)(w + 4);
    q[0] = GIF_TAG(1, 1, 0, 0, 0, 1); q[1] = GIF_REGS_AD;
    q[2] = 1; q[3] = GS_A_FINISH;
    w[12] = w[13] = w[14] = w[15] = 0;
    submit(&c, DMA_CHANNEL_VIF1);
    draw_wait_finish();
    video_present(v);
}

int main(int argc, char **argv)
{
    video_t video;
    fly_input input;
    unsigned frame = 0, edges, pad_events = 0;
    u32 previous, now;
    u64 elapsed = 0;
    uintptr_t heap_start;
    unsigned duration = argc > 1 ? (unsigned)strtoul(argv[1], NULL, 10) : 600;
    packet2_t *state;
    if (duration < 1 || duration > 600) duration = 600;
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("HALO_PS2_PLATFORM log-before-graphics duration=%u\n", duration);
    guarded.before[0] = guarded.before[1] = guarded.after[0] = guarded.after[1] = CANARY;
    printf("HALO_PS2_PLATFORM pad_ready=%d\n", pad_init());
    dma_channel_initialize(DMA_CHANNEL_GIF, NULL, 0);
    dma_channel_initialize(DMA_CHANNEL_VIF1, NULL, 0);
    video_init(&video);
    upload_vu1();
    texture_init(&video);
    state = packet2_create(128, P2_TYPE_NORMAL, P2_MODE_NORMAL, 0);
    if (!state) { fail("state-allocation"); return 1; }
    heap_start = (uintptr_t)sbrk(0);
    previous = timer_cycles();
    do {
        edges = pad_poll(&input);
        if (edges) {
            ++pad_events;
            printf("HALO_PS2_PAD frame=%u edges=%u\n", frame, edges);
        }
        draw_frame(&video, state, frame++);
        now = timer_cycles(); elapsed += (u32)(now - previous); previous = now;
        if ((uintptr_t)sbrk(0) != heap_start) { fail("steady-state-heap-growth"); return 1; }
        if (frame == 1 || !(frame % 60))
            printf("HALO_PS2_FRAME frame=%u elapsed_ms=%u heap=%u chain_high=%u guards=ok\n",
                   frame, (unsigned)(elapsed / (EE_CLOCK_HZ / 1000)), (unsigned)heap_start, max_chain_qw);
    } while (elapsed < (u64)duration * EE_CLOCK_HZ);
    printf("HALO_PS2_DONE duration=%u frames=%u pad_events=%u heap=%u guards=ok\n",
           duration, frame, pad_events, (unsigned)heap_start);
    SleepThread();
    return 0;
}
