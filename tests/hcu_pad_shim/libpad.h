#pragma once

#define PAD_STATE_STABLE 6
#define PAD_STATE_FINDCTP1 2
#define PAD_STATE_DISCONN 0
#define PAD_STATE_FINDPAD 1
#define PAD_STATE_EXECCMD 5
#define PAD_STATE_ERROR 7
#define PAD_RSTAT_COMPLETE 0
#define PAD_RSTAT_FAILED 1
#define PAD_RSTAT_BUSY 2
#define PAD_MMODE_DUALSHOCK 1
#define PAD_MMODE_LOCK 3
#define PAD_CROSS 0x4000
#define PAD_CIRCLE 0x2000
#define PAD_SQUARE 0x8000
#define PAD_TRIANGLE 0x1000
#define PAD_R1 0x0800
#define PAD_L1 0x0400
#define PAD_L2 0x0100
#define PAD_R2 0x0200

struct padButtonStatus
{
	unsigned short btns;
	unsigned char ljoy_h, ljoy_v, rjoy_h, rjoy_v;
	unsigned char right_p, left_p, up_p, down_p;
	unsigned char triangle_p, circle_p, cross_p, square_p;
	unsigned char l1_p, r1_p, l2_p, r2_p;
};

int padInit(int mode);
int padPortOpen(int port, int slot, void *buffer);
int padGetState(int port, int slot);
int padGetReqState(int port, int slot);
int padSetMainMode(int port, int slot, int mode, int lock);
int padInfoPressMode(int port, int slot);
int padEnterPressMode(int port, int slot);
int padRead(int port, int slot, struct padButtonStatus *status);
