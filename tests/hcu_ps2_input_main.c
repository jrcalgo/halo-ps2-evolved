#define DEBUG_KEYBOARD
#include "halo_ps2_input.h"
#include <assert.h>
#include <string.h>

XPP_DEVICE_TYPE XDEVICE_TYPE_GAMEPAD_TABLE;
XPP_DEVICE_TYPE XDEVICE_TYPE_MEMORY_UNIT_TABLE;
XPP_DEVICE_TYPE XDEVICE_TYPE_DEBUG_KEYBOARD_TABLE;

void SetLastError(unsigned long error)
{
	(void)error;
}

int main(void)
{
	struct _XINPUT_STATE state;
	unsigned long inserted, removed;
	unsigned char analog[8] = { 0xFF, 0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02 };
	void *device;

	assert(!XGetDeviceChanges(XDEVICE_TYPE_GAMEPAD, &inserted, &removed));
	assert(!XGetDeviceChanges(XDEVICE_TYPE_MEMORY_UNIT, &inserted, &removed));
	assert(!XGetDeviceChanges(XDEVICE_TYPE_DEBUG_KEYBOARD, &inserted, &removed));
	assert(XInputOpen(XDEVICE_TYPE_MEMORY_UNIT, 0, XDEVICE_NO_SLOT, 0) == 0);
	assert(XInputOpen(XDEVICE_TYPE_DEBUG_KEYBOARD, 0, XDEVICE_NO_SLOT, 0) == 0);
	ps2_input_publish_dualshock(0, 1,
		0x0010 | 0x0020 | 0x0008 | 0x0001 | 0x0002 | 0x0004,
		255, 0, 128, 255, analog);
	assert(XGetDeviceChanges(XDEVICE_TYPE_GAMEPAD, &inserted, &removed));
	assert(inserted == 1 && removed == 0);
	device = XInputOpen(XDEVICE_TYPE_GAMEPAD, 0, XDEVICE_NO_SLOT, 0);
	assert(device != 0);
	assert(XInputGetState(device, &state) == ERROR_SUCCESS);
	assert(state.Gamepad.wButtons == (XINPUT_GAMEPAD_DPAD_UP |
		XINPUT_GAMEPAD_DPAD_RIGHT | XINPUT_GAMEPAD_START |
		XINPUT_GAMEPAD_BACK | XINPUT_GAMEPAD_LEFT_THUMB |
		XINPUT_GAMEPAD_RIGHT_THUMB));
	assert(memcmp(state.Gamepad.bAnalogButtons, analog, sizeof(analog)) == 0);
	assert(state.Gamepad.sThumbLX == 32512);
	assert(state.Gamepad.sThumbLY == 32767);
	assert(state.Gamepad.sThumbRX == 0);
	assert(state.Gamepad.sThumbRY == -32512);
	++state.dwPacketNumber;
	assert(XInputGetState(device, &state) == ERROR_SUCCESS);
	assert(state.dwPacketNumber == 1);

	ps2_input_publish_dualshock(0, 1,
		0x0010 | 0x0020 | 0x0008 | 0x0001 | 0x0002 | 0x0004,
		255, 0, 128, 255, analog);
	assert(XInputGetState(device, &state) == ERROR_SUCCESS);
	assert(state.dwPacketNumber == 1); /* unchanged state does not advance packet */

	ps2_input_publish_dualshock(0, 0, 0, 0, 0, 0, 0, 0);
	assert(XGetDeviceChanges(XDEVICE_TYPE_GAMEPAD, &inserted, &removed));
	assert(inserted == 0 && removed == 1);
	assert(XInputGetState(device, &state) == ERROR_DEVICE_NOT_CONNECTED);
	XInputClose(device);
	return 0;
}
