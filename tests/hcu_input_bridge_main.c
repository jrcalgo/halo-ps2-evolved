#include "halo_ps2_input.h"
#include "platform/pad.h"
#include "xdk/xdk_xbox.h"

#include <assert.h>
#include <string.h>

XPP_DEVICE_TYPE XDEVICE_TYPE_GAMEPAD_TABLE;
static int poll_count;
static int frame_number;

void SetLastError(unsigned long error) { (void)error; }

int pad_poll_players(pad_sample samples[4])
{
	++poll_count;
	memset(samples, 0, sizeof(pad_sample) * 4);
	if (frame_number == 0)
	{
		int i;
		for (i = 0; i < 4; ++i)
		{
			samples[i].connected = 1;
			samples[i].buttons = 0x0008u; /* Start, independently per logical port. */
			samples[i].lx = (unsigned char)(64 + i * 32);
			samples[i].ly = 128;
			samples[i].analog[0] = (unsigned char)(0x20 + i);
		}
	}
	else if (frame_number == 1)
	{
		/* Port 0 is held, port 1 releases, port 2 disconnects, port 3 remains. */
		samples[0].connected = 1;
		samples[0].buttons = 0x0008u;
		samples[0].lx = 64;
		samples[1].connected = 1;
		samples[1].lx = 96;
		samples[3].connected = 1;
		samples[3].buttons = 0x0008u;
		samples[3].lx = 160;
	}
	else
	{
		/* Port 2 reconnects while all other logical ports remain connected. */
		samples[0].connected = 1;
		samples[0].buttons = 0x0008u;
		samples[0].lx = 64;
		samples[1].connected = 1;
		samples[1].lx = 96;
		samples[2].connected = 1;
		samples[2].buttons = 0x0008u;
		samples[2].lx = 128;
		samples[3].connected = 1;
		samples[3].buttons = 0x0008u;
		samples[3].lx = 160;
	}
	++frame_number;
	return 1;
}

int main(void)
{
	struct _XINPUT_STATE state[4];
	unsigned long inserted = 0, removed = 0;
	void *device[4];
	int i;
	ps2_input_poll_devices();
	assert(poll_count == 1);
	assert(XGetDeviceChanges(XDEVICE_TYPE_GAMEPAD, &inserted, &removed));
	assert(inserted == 0xFu && removed == 0);
	for (i = 0; i < 4; ++i)
	{
		device[i] = XInputOpen(XDEVICE_TYPE_GAMEPAD, (unsigned long)i,
			XDEVICE_NO_SLOT, 0);
		assert(device[i] != 0);
		assert(XInputGetState(device[i], &state[i]) == ERROR_SUCCESS);
		assert(state[i].Gamepad.sThumbLX == (short)((-64 + i * 32) * 256));
		assert(state[i].Gamepad.wButtons & XINPUT_GAMEPAD_START);
		assert(state[i].Gamepad.bAnalogButtons[0] == (unsigned char)(0x20 + i));
	}
	/* A second frame exercises held state, release, removal, and stable ports. */
	ps2_input_poll_devices();
	assert(poll_count == 2);
	assert(XGetDeviceChanges(XDEVICE_TYPE_GAMEPAD, &inserted, &removed));
	assert(inserted == 0 && removed == (1u << 2));
	assert(XInputGetState(device[0], &state[0]) == ERROR_SUCCESS);
	assert(state[0].Gamepad.wButtons & XINPUT_GAMEPAD_START);
	assert(XInputGetState(device[1], &state[1]) == ERROR_SUCCESS);
	assert(!(state[1].Gamepad.wButtons & XINPUT_GAMEPAD_START));
	assert(XInputGetState(device[2], &state[2]) == ERROR_DEVICE_NOT_CONNECTED);
	assert(XInputGetState(device[3], &state[3]) == ERROR_SUCCESS);
	assert(state[3].Gamepad.wButtons & XINPUT_GAMEPAD_START);
	/* Reconnection is reported on the same logical port and updates its packet. */
	ps2_input_poll_devices();
	assert(poll_count == 3);
	assert(XGetDeviceChanges(XDEVICE_TYPE_GAMEPAD, &inserted, &removed));
	assert(inserted == (1u << 2) && removed == 0);
	assert(XInputGetState(device[2], &state[2]) == ERROR_SUCCESS);
	assert(state[2].Gamepad.wButtons & XINPUT_GAMEPAD_START);
	for (i = 0; i < 4; ++i)
		XInputClose(device[i]);
	return 0;
}
