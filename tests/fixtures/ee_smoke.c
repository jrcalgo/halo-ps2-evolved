/* Build-environment fixture, not the graphics/platform acceptance test. */
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <kernel.h>

#if !defined(__mips__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error This fixture requires the little-endian MIPS EE toolchain
#endif
_Static_assert(CHAR_BIT == 8, "8-bit bytes required");
_Static_assert(sizeof(void *) == 4, "32-bit pointers required");
_Static_assert(sizeof(long) == 4, "32-bit long required");
_Static_assert(sizeof(float) == 4, "32-bit float required");

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("HALO_PS2_BUILD_SMOKE pointers=%u long=%u float=%u\n",
           (unsigned)sizeof(void *), (unsigned)sizeof(long), (unsigned)sizeof(float));
    SleepThread();
    return 0;
}
