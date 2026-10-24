/* Native ILP32 test prefix for compiling the production CE validator. */
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <limits.h>

#undef LONG_MAX
#undef LONG_MIN
#undef CHAR_MAX
#undef CHAR_MIN

/* cseries.h redeclares this MSVC-era helper with a long-sized result. */
#define strnlen halo_cseries_strnlen

#define HALO_PS2 1
#define __inline static inline
#define _inline static inline
#define __forceinline static inline
#include "halo_ps2_limits.h"
