#include "stream/hcu_opl_diag_telemetry.h"

#include <stdio.h>

/* One line a second. OPL's in-game udptty, present only in an ingame-debug
 * OPL, broadcasts IOP tty writes to UDP port 18194. This object is not linked
 * into a release ELF, and the release ISO packer rejects the marker below. */
static int s_ready;

void hcu_opl_diag_telemetry_init(void)
{
	s_ready = 1;
	printf("HALO_PS2_OPL_DIAG_TELEMETRY ready\n");
}

void hcu_opl_diag_telemetry_tick(unsigned now_ms)
{
	static unsigned next_ms;
	if (!s_ready || now_ms < next_ms)
		return;
	next_ms = now_ms + 1000u;
	printf("HALO_PS2_OPL_DIAG_TELEMETRY ms=%u\n", now_ms);
}
