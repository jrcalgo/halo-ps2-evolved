/* Presentation and diagnostic boundary for the frozen, unchanged integer-math fixture. */
#include <debug.h>
#include <kernel.h>
#include <stdio.h>
#include <string.h>

extern int halo_integer_fixture_main(void);

int main(int argc, char **argv)
{
    int calls = 0, result;
    int negative = argc > 1 && !strcmp(argv[1], "negative");
    init_scr();
    setvbuf(stdout, NULL, _IONBF, 0);
    scr_printf("HALO PS2: R5900 integer-math compatibility probe\n\n");
    scr_printf("Original Halo algorithms; explicit ILP32 boundary.\n\n");
    if (argc > 1 && !strcmp(argv[1], "assert")) {
        scr_printf("Expected assertion failure: checking diagnostics.\n");
        match_assert("probe-diagnostics", __LINE__, 0);
        printf("HALO_PS2_FAIL reason=silent-assertion\n");
        for (;;) SleepThread();
    }
    match_assert("probe-diagnostics", __LINE__, ++calls == 1);
    match_vwarn("probe-diagnostics", __LINE__, ++calls == 2, "expression was not evaluated");
    match_vwarn("probe-diagnostics", __LINE__, 0, "expected diagnostic fixture warning");
    if (calls != 2) {
        printf("HALO_PS2_FAIL reason=diagnostic-expression-evaluation\n");
        for (;;) SleepThread();
    }
    result = halo_integer_fixture_main();
    if (negative && result == 1) {
        scr_printf("NEGATIVE CONTROL REJECTED\n\nRectangle boundary fault detected.\n");
        printf("HALO_PS2_PROBE negative_control=rejected diagnostics_calls=%d\n", calls);
    } else if (!negative && result == 0) {
        scr_printf("PASS\n\nInteger operations match the host fixture.\n\n");
        scr_printf("This is a compatibility test, not Halo gameplay.\n");
        printf("HALO_PS2_PROBE outcome=passed diagnostics_calls=%d\n", calls);
    } else {
        scr_printf("FAIL\n");
        printf("HALO_PS2_FAIL reason=unexpected-probe-result result=%d negative=%d\n", result, negative);
    }
    for (;;) SleepThread();
}
