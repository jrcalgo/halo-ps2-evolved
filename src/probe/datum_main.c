#include <debug.h>
#include <kernel.h>
#include <stdio.h>
#include <string.h>
extern int halo_datum_fixture_main(void);
int main(int argc, char **argv)
{
    int result;
    int negative = argc > 1 && !strcmp(argv[1], "negative");
    setvbuf(stdout, NULL, _IONBF, 0);
    init_scr();
    scr_printf("HALO PS2: original datum pool compatibility\n\n");
    result = halo_datum_fixture_main();
    if (negative && result == 1) {
        scr_printf("NEGATIVE CONTROL REJECTED\n\nStale identifier fault detected.\n");
        puts("HALO_PS2_DATUM negative_control=rejected");
    } else if (result || negative) {
        scr_printf("FAIL\n");
        printf("HALO_PS2_FAIL reason=datum-fixture result=%d\n", result);
    } else {
        scr_printf("PASS\n\nAllocation, exhaustion, stale handles, reuse,\niteration, reset and identifier rollover.\n\n");
        scr_printf("Bounded compatibility fixture; not Halo gameplay.\n");
        puts("HALO_PS2_DATUM outcome=passed");
    }
    for (;;) SleepThread();
}
