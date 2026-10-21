#ifndef TEST_HCU_PS2_MEMORY_XTL_H
#define TEST_HCU_PS2_MEMORY_XTL_H

#define __stdcall

struct _MEMORYSTATUS
{
	unsigned long dwLength;
	unsigned long dwMemoryLoad;
	unsigned long dwTotalPhys;
	unsigned long dwAvailPhys;
	unsigned long dwTotalPageFile;
	unsigned long dwAvailPageFile;
	unsigned long dwTotalVirtual;
	unsigned long dwAvailVirtual;
};

#endif
