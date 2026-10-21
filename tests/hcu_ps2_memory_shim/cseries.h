#ifndef HCU_PS2_MEMORY_TEST_CSERIES_H
#define HCU_PS2_MEMORY_TEST_CSERIES_H

#include <stddef.h>
#include "halo_ps2_limits.h"
typedef unsigned char byte;
typedef unsigned char boolean;

#define FALSE 0
#define TRUE 1
#define NONE (-1)
#define __stdcall

void __wrap_free(void *block);

#endif
