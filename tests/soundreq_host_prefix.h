/* ILP32 host prefix for the sound-request seam fixture. HALO_PS2 is NOT
 * defined here: the PS2 link adds it, and the drive link must not, so
 * sound_preferences.c keeps both of its real branches. */
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <stdint.h>
#include <limits.h>
#include <math.h>

#undef LONG_MAX
#undef LONG_MIN
#undef CHAR_MAX
#undef CHAR_MIN

#define strnlen halo_cseries_strnlen
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
