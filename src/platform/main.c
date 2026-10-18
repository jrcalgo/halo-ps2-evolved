/* M06 platform slice. Logging precedes graphics. The pad, GIF/VIF DMA, VU1 upload, and
 * synthetic texture self-test are linked. This build has not been executed. */
#include <dma.h>
#include <kernel.h>
#include <packet2.h>
#include <packet2_utils.h>
#include <packet2_vif.h>
#include <stdio.h>

#include "platform/pad.h"
#include "platform/timer.h"
#include "platform/video.h"
#include "render/selftest.h"

extern u32 VU1Bsp_CodeStart __attribute__((section(".vudata")));
extern u32 VU1World_CodeEnd __attribute__((section(".vudata")));

static void upload_vu1(void)
{
	u32 bytes = (u32)&VU1World_CodeEnd - (u32)&VU1Bsp_CodeStart;
	u32 count = packet2_utils_get_packet_size_for_program(&VU1Bsp_CodeStart, &VU1World_CodeEnd) + 1;
	packet2_t *packet = packet2_create(count, P2_TYPE_NORMAL, P2_MODE_CHAIN, 1);

	packet2_vif_add_micro_program(packet, 0, &VU1Bsp_CodeStart, &VU1World_CodeEnd);
	packet2_utils_vu_add_end_tag(packet);
	dma_channel_send_packet2(packet, DMA_CHANNEL_VIF1, 1);
	dma_channel_wait(DMA_CHANNEL_VIF1, 0);
	packet2_free(packet);
	printf("HALO_PS2_PLATFORM vu1_bytes=%u\n", (unsigned)bytes);
}

int main(void)
{
	video_t video;
	fly_input input;
	u32 start;
	unsigned edges = 0;

	setvbuf(stdout, NULL, _IONBF, 0);
	printf("HALO_PS2_PLATFORM log-before-graphics\n");
	start = timer_cycles();
	if (pad_init())
		edges = pad_poll(&input);
	printf("HALO_PS2_PLATFORM pad_edges=%u\n", edges);
	dma_channel_initialize(DMA_CHANNEL_GIF, NULL, 0);
	dma_channel_fast_waits(DMA_CHANNEL_GIF);
	dma_channel_initialize(DMA_CHANNEL_VIF1, NULL, 0);
	dma_channel_fast_waits(DMA_CHANNEL_VIF1);
	video_init(&video);
	upload_vu1();
	selftest_draw(&video);
	printf("HALO_PS2_PLATFORM timer_delta=%u fb0=%u\n",
	       (unsigned)(timer_cycles() - start), (unsigned)video.fb[0].address);
	SleepThread();
	return 0;
}
