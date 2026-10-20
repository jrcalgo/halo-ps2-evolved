/* Strong parent hook overriding the standalone HCU diagnostic no-op. */
#include "platform/pad.h"
#include "halo_ps2_input.h"

void ps2_parent_pad_poll(void)
{
	pad_sample samples[4];
	int player;
	(void)pad_poll_players(samples);
	for (player = 0; player < 4; ++player)
		ps2_input_publish_dualshock((unsigned long)player,
			samples[player].connected, samples[player].buttons,
			samples[player].lx, samples[player].ly,
			samples[player].rx, samples[player].ry,
			samples[player].analog);
}
