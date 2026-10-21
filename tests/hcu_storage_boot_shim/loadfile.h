#pragma once
#include <stdint.h>
typedef uint32_t u32;
int SifSearchModuleByName(const char *name);
int SifExecModuleBuffer(void *ptr, u32 size, u32 arg_len,
	const char *args, int *mod_res);
