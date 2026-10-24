/* Native ILP32 compatibility prefix for compiling the real CE scenario unit. */
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

#define HALO_PS2 1
#define strnlen halo_cseries_strnlen
/* CE's inline helper is named random; rename it only after libc headers have
 * declared the host's unrelated random() API. */
#define random halo_ce_random
#define __inline static inline
#define _inline static inline
#define __forceinline static inline __attribute__((always_inline))
#define __cdecl
#define __stdcall
#define __fastcall
#define __declspec(x)
#define __int8 char
#define __int16 short
#define __int32 int
#define __int64 long long
#define __unaligned
#define __w64
#define __ptr32
#define DECLSPEC_SELECTANY __attribute__((weak))

#include "halo_ps2_limits.h"
