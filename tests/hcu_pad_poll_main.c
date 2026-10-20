#include "platform/pad.h"
#include <libpad.h>
#include <libmtap.h>
#include <sifrpc.h>
#include <loadfile.h>

#include <assert.h>
#include <stdio.h>
#include <string.h>

#ifndef PAD_TEST_PORT0_TAP
#define PAD_TEST_PORT0_TAP 1
#endif

static int read_count;
static int read_ports[16];
static int read_slots[16];

void SifInitRpc(int mode) { (void)mode; }
int SifLoadModule(const char *name, int bytes, const char *arguments)
{
	(void)name; (void)bytes; (void)arguments; return 1;
}
void mtapInit(void) {}
int mtapPortOpen(int port)
{
	return PAD_TEST_PORT0_TAP ? port == 0 : port == 1;
}
int mtapGetConnection(int port)
{
	return PAD_TEST_PORT0_TAP ? port == 0 : port == 1;
}
int padInit(int mode) { (void)mode; return 1; }
int padPortOpen(int port, int slot, void *buffer)
{
	(void)port; (void)slot; (void)buffer; return 1;
}
int padGetState(int port, int slot)
{
	(void)port; (void)slot; return PAD_STATE_STABLE;
}
int padSetMainMode(int port, int slot, int mode, int lock)
{
	(void)port; (void)slot; (void)mode; (void)lock; return 1;
}
int padInfoPressMode(int port, int slot)
{
	(void)port; (void)slot; return 1;
}
int padEnterPressMode(int port, int slot)
{
	(void)port; (void)slot; return 1;
}
int padRead(int port, int slot, struct padButtonStatus *status)
{
	int i = read_count++;
	assert(i < 16);
	read_ports[i] = port;
	read_slots[i] = slot;
	memset(status, 0, sizeof(*status));
	status->btns = (unsigned short)~PAD_CROSS; /* libpad is active-low. */
	status->ljoy_h = (unsigned char)(64 + port * 32 + slot * 8);
	status->ljoy_v = 128;
	status->rjoy_h = 128;
	status->rjoy_v = 128;
	status->cross_p = 0;
	return 1;
}

int main(void)
{
	pad_sample samples[4];
	static const int expected_ports[4] = {
		PAD_TEST_PORT0_TAP ? 0 : 0,
		PAD_TEST_PORT0_TAP ? 0 : 1,
		PAD_TEST_PORT0_TAP ? 0 : 1,
		PAD_TEST_PORT0_TAP ? 0 : 1
	};
	static const int expected_slots[4] = {
		0, 0, 1, 2
	};
	int i;
	assert(pad_init());
	read_count = 0;
	assert(pad_poll_players(samples) == 4);
	assert(read_count == 4);
	for (i = 0; i < 4; ++i)
	{
		int expected_slot = PAD_TEST_PORT0_TAP ? i : expected_slots[i];
		assert(samples[i].connected);
		assert(samples[i].buttons & PAD_CROSS);
		assert(read_ports[i] == expected_ports[i]);
		assert(read_slots[i] == expected_slot);
		assert(samples[i].lx == (unsigned char)(64 + expected_ports[i] * 32 + expected_slot * 8));
		assert(samples[i].analog[0] == 0xff);
	}
	puts("PS2 pad logical port/slot fixture passed");
	return 0;
}
