/* M06 startup slice. Logging is established before the audited NTSC video setup.
 * This build does not execute the triangle, pad, or stability gates. */
#include <kernel.h>
#include <stdio.h>

#include "platform/timer.h"
#include "platform/video.h"

int main(void)
{
	video_t video;
	u32 start;

	setvbuf(stdout, NULL, _IONBF, 0);
	printf("HALO_PS2_PLATFORM log-before-graphics\n");
	start = timer_cycles();
	video_init(&video);
	printf("HALO_PS2_PLATFORM timer_delta=%u fb0=%u\n",
	       (unsigned)(timer_cycles() - start), (unsigned)video.fb[0].address);
	SleepThread();
	return 0;
}
