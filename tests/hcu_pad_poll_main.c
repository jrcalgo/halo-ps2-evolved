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

struct mock_pad
{
	int state;
	int forced_state;
	int forced_state_count;
	int request_state;
	int busy_polls;
	int fail_completion;
	int main_result;
	int press_result;
	int press_supported;
	int main_calls;
	int press_calls;
	int read_calls;
};

static struct mock_pad pads[PAD_MAX_PORTS][PAD_MAX_SLOTS];
static int port0_tap = PAD_TEST_PORT0_TAP;

static struct mock_pad *mock_pad_at(int port, int slot)
{
	assert(port >= 0 && port < PAD_MAX_PORTS);
	assert(slot >= 0 && slot < PAD_MAX_SLOTS);
	return &pads[port][slot];
}

void SifInitRpc(int mode) { (void)mode; }
int SifLoadModule(const char *name, int bytes, const char *arguments)
{
	(void)name; (void)bytes; (void)arguments; return 1;
}
void mtapInit(void) {}
int mtapPortOpen(int port) { return port0_tap ? port == 0 : port == 1; }
int mtapGetConnection(int port) { return mtapPortOpen(port); }
int padInit(int mode) { (void)mode; return 1; }
int padPortOpen(int port, int slot, void *buffer)
{
	(void)buffer;
	mock_pad_at(port, slot)->state = PAD_STATE_STABLE;
	return 1;
}
int padGetState(int port, int slot)
{
	struct mock_pad *pad = mock_pad_at(port, slot);
	if (pad->forced_state_count > 0) {
		--pad->forced_state_count;
		return pad->forced_state;
	}
	if (pad->request_state == PAD_RSTAT_BUSY) {
		if (pad->busy_polls > 0) {
			--pad->busy_polls;
			return PAD_STATE_EXECCMD;
		}
		pad->request_state = pad->fail_completion ?
			PAD_RSTAT_FAILED : PAD_RSTAT_COMPLETE;
		pad->fail_completion = 0;
	}
	return pad->state;
}
int padGetReqState(int port, int slot)
{
	return mock_pad_at(port, slot)->request_state;
}
int padSetMainMode(int port, int slot, int mode, int lock)
{
	struct mock_pad *pad = mock_pad_at(port, slot);
	(void)mode; (void)lock;
	++pad->main_calls;
	if (pad->main_result != 1)
		return pad->main_result;
	pad->request_state = PAD_RSTAT_BUSY;
	return 1;
}
int padInfoPressMode(int port, int slot)
{
	return mock_pad_at(port, slot)->press_supported;
}
int padEnterPressMode(int port, int slot)
{
	struct mock_pad *pad = mock_pad_at(port, slot);
	++pad->press_calls;
	if (pad->press_result != 1)
		return pad->press_result;
	pad->request_state = PAD_RSTAT_BUSY;
	return 1;
}
int padRead(int port, int slot, struct padButtonStatus *status)
{
	struct mock_pad *pad = mock_pad_at(port, slot);
	++pad->read_calls;
	memset(status, 0, sizeof(*status));
	status->btns = (unsigned short)~PAD_CROSS; /* libpad is active-low. */
	status->ljoy_h = (unsigned char)(64 + port * 32 + slot * 8);
	status->ljoy_v = 128;
	status->rjoy_h = 128;
	status->rjoy_v = 128;
	status->cross_p = 0;
	return 1;
}

static void init_mock_pads(void)
{
	int port, slot;
	memset(pads, 0, sizeof(pads));
	for (port = 0; port < PAD_MAX_PORTS; ++port) {
		for (slot = 0; slot < PAD_MAX_SLOTS; ++slot) {
			pads[port][slot].state = PAD_STATE_STABLE;
			pads[port][slot].request_state = PAD_RSTAT_COMPLETE;
			pads[port][slot].main_result = 1;
			pads[port][slot].press_result = 1;
			pads[port][slot].press_supported = 1;
		}
	}
}

static int sample_is_zero(const pad_sample *sample)
{
	int i;
	if (sample->connected || sample->buttons || sample->lx || sample->ly ||
		sample->rx || sample->ry)
		return 0;
	for (i = 0; i < 8; ++i)
		if (sample->analog[i])
			return 0;
	return 1;
}

static void test_multitap_mapping(void)
{
	static const int expected_ports[4] = { 0, 1, 1, 1 };
	static const int expected_slots[4] = { 0, 0, 1, 2 };
	pad_sample samples[4];
	int connected = 0, i, poll;

	assert(pad_init());
	for (poll = 0; poll < 8 && connected != 4; ++poll)
		connected = pad_poll_players(samples);
	assert(connected == 4);
	for (i = 0; i < 4; ++i) {
		int port = PAD_TEST_PORT0_TAP ? 0 : expected_ports[i];
		int slot = PAD_TEST_PORT0_TAP ? i : expected_slots[i];
		struct mock_pad *pad = mock_pad_at(port, slot);
		assert(samples[i].connected);
		assert(samples[i].buttons & PAD_CROSS);
		assert(samples[i].lx == (unsigned char)(64 + port * 32 + slot * 8));
		assert(samples[i].analog[0] == 0xff);
		assert(pad->main_calls == 1);
		assert(pad->press_calls == 1);
		assert(pad->read_calls == 1);
	}
}

static void test_async_setup_and_no_restart(void)
{
	pad_sample sample;
	struct mock_pad *pad;
	int i;
	init_mock_pads();
	assert(pad_init());
	pad = mock_pad_at(0, 0);
	pad->busy_polls = 3;
	assert(!pad_read_sample(0, 0, &sample) && sample_is_zero(&sample));
	assert(pad->main_calls == 1 && pad->press_calls == 0 && pad->read_calls == 0);
	for (i = 0; i < 3; ++i) {
		assert(!pad_read_sample(0, 0, &sample) && sample_is_zero(&sample));
		assert(pad->main_calls == 1 && pad->press_calls == 0);
	}
	/* Main command completes; only now may press mode be submitted. */
	assert(!pad_read_sample(0, 0, &sample) && sample_is_zero(&sample));
	assert(pad->main_calls == 1 && pad->press_calls == 1 && pad->read_calls == 0);
	pad->busy_polls = 2;
	for (i = 0; i < 2; ++i) {
		assert(!pad_read_sample(0, 0, &sample) && sample_is_zero(&sample));
		assert(pad->main_calls == 1 && pad->press_calls == 1 && pad->read_calls == 0);
	}
	assert(pad_read_sample(0, 0, &sample));
	assert(sample.connected && (sample.buttons & PAD_CROSS));
	assert(pad->main_calls == 1 && pad->press_calls == 1 && pad->read_calls == 1);
}

static void test_unsupported_press_mode(void)
{
	pad_sample sample;
	struct mock_pad *pad;
	init_mock_pads();
	assert(pad_init());
	pad = mock_pad_at(0, 0);
	pad->state = PAD_STATE_FINDCTP1;
	pad->press_supported = 0;
	assert(!pad_read_sample(0, 0, &sample));
	assert(pad_read_sample(0, 0, &sample));
	assert(sample.connected && pad->main_calls == 1);
	assert(pad->press_calls == 0 && pad->read_calls == 1);
}

static void test_failures_are_retried_with_backoff(void)
{
	pad_sample sample;
	struct mock_pad *pad;
	int i;
	init_mock_pads();
	assert(pad_init());
	pad = mock_pad_at(0, 0);
	pad->main_result = 0; /* Rejected submissions must not be accepted as ready. */
	assert(!pad_read_sample(0, 0, &sample));
	assert(pad->main_calls == 1 && pad->read_calls == 0);
	for (i = 0; i < 29; ++i) {
		assert(!pad_read_sample(0, 0, &sample));
		assert(pad->main_calls == 1 && pad->read_calls == 0);
	}
	assert(!pad_read_sample(0, 0, &sample));
	assert(pad->main_calls == 1);
	pad->main_result = 1;
	assert(!pad_read_sample(0, 0, &sample));
	assert(pad->main_calls == 2 && pad->press_calls == 0);
	pad->fail_completion = 1;
	assert(!pad_read_sample(0, 0, &sample));
	assert(pad->main_calls == 2 && pad->read_calls == 0);
	for (i = 0; i < 59; ++i) {
		assert(!pad_read_sample(0, 0, &sample));
		assert(pad->main_calls == 2 && pad->read_calls == 0);
	}
	assert(!pad_read_sample(0, 0, &sample));
	assert(pad->main_calls == 2);
	assert(!pad_read_sample(0, 0, &sample));
	assert(pad->main_calls == 3);
	assert(!pad_read_sample(0, 0, &sample));
	assert(pad->press_calls == 1);
	assert(pad_read_sample(0, 0, &sample));
	assert(sample.connected && pad->main_calls == 3 && pad->press_calls == 1);
}

static void test_press_mode_rejection_is_retried(void)
{
	pad_sample sample;
	struct mock_pad *pad;
	int i;
	init_mock_pads();
	assert(pad_init());
	pad = mock_pad_at(0, 0);
	pad->press_result = 0;
	assert(!pad_read_sample(0, 0, &sample));	/* Submit main mode. */
	assert(!pad_read_sample(0, 0, &sample));	/* Complete main, reject press mode. */
	assert(pad->main_calls == 1 && pad->press_calls == 1 && pad->read_calls == 0);
	for (i = 0; i < 30; ++i) {
		assert(!pad_read_sample(0, 0, &sample));
		assert(pad->press_calls == 1 && pad->read_calls == 0);
	}
	pad->press_result = 1;
	assert(!pad_read_sample(0, 0, &sample));
	assert(pad->press_calls == 2 && pad->read_calls == 0);
	assert(pad_read_sample(0, 0, &sample));
	assert(sample.connected && pad->main_calls == 1 && pad->press_calls == 2);
}

static void test_disconnect_reconnect_has_no_stale_sample(void)
{
	pad_sample sample;
	struct mock_pad *pad;
	int i, got_sample;
	init_mock_pads();
	assert(pad_init());
	pad = mock_pad_at(0, 0);
	pad->busy_polls = 4;
	assert(!pad_read_sample(0, 0, &sample));
	pad->forced_state = PAD_STATE_DISCONN;
	pad->forced_state_count = 1;
	assert(!pad_read_sample(0, 0, &sample) && sample_is_zero(&sample));
	assert(pad->main_calls == 1 && pad->read_calls == 0);
	got_sample = 0;
	for (i = 0; i < 12 && !got_sample; ++i)
		got_sample = pad_read_sample(0, 0, &sample);
	assert(got_sample && sample.connected && (sample.buttons & PAD_CROSS));
	assert(pad->main_calls == 2 && pad->press_calls == 1);
	/* A later real disconnect releases both button and analog state immediately. */
	pad->forced_state = PAD_STATE_DISCONN;
	pad->forced_state_count = 1;
	assert(!pad_read_sample(0, 0, &sample) && sample_is_zero(&sample));
	assert(pad->read_calls == 1);
	got_sample = 0;
	for (i = 0; i < 8 && !got_sample; ++i)
		got_sample = pad_read_sample(0, 0, &sample);
	assert(got_sample && sample.connected);
	assert(pad->main_calls == 3 && pad->press_calls == 2);
}

int main(int argc, char **argv)
{
	const char *scenario = argc > 1 ? argv[1] : "mapping";
	init_mock_pads();
	if (strcmp(scenario, "async") == 0)
		test_async_setup_and_no_restart();
	else if (strcmp(scenario, "unsupported") == 0)
		test_unsupported_press_mode();
	else if (strcmp(scenario, "failure") == 0)
		test_failures_are_retried_with_backoff();
	else if (strcmp(scenario, "pressfailure") == 0)
		test_press_mode_rejection_is_retried();
	else if (strcmp(scenario, "reconnect") == 0)
		test_disconnect_reconnect_has_no_stale_sample();
	else {
		test_multitap_mapping();
		puts("PS2 pad logical port/slot fixture passed");
		return 0;
	}
	puts("PS2 pad state-machine fixture passed");
	return 0;
}
