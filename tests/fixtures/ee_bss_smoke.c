/* EE CRT startup control with a BSS span matching the current HCU image. */
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <kernel.h>

#define LARGE_BSS_BYTES 2028808u

#if !defined(__mips__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error This fixture requires the little-endian MIPS EE toolchain
#endif
_Static_assert(CHAR_BIT == 8, "8-bit bytes required");
_Static_assert(sizeof(void *) == 4, "32-bit pointers required");
_Static_assert(sizeof(long) == 4, "32-bit long required");

static volatile unsigned char s_large_bss[LARGE_BSS_BYTES];

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    if (s_large_bss[0] != 0 || s_large_bss[LARGE_BSS_BYTES - 1] != 0) {
        printf("HALO_PS2_FAIL reason=bss-not-zeroed\n");
        for (;;) SleepThread();
    }
    s_large_bss[0] = 0x5A;
    s_large_bss[LARGE_BSS_BYTES - 1] = 0xA5;
    printf("HALO_PS2_BSS_SMOKE bytes=%u endpoints=ok\n", LARGE_BSS_BYTES);
    for (;;) SleepThread();
}
