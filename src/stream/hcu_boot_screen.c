/* Diagnostic-only extension of the pinned SDK debug renderer. Keeping this
 * in one translation unit shares its font state and GIF setup packet without
 * copying its implementation. The SDK source retains its original license. */
#include "../../submodules/ps2sdk/ee/debug/src/scr_printf.c"

void hcu_boot_scr_hold_init(void)
{
    static struct t_setupscr setup __attribute__((aligned(16)));
    *((struct t_setupscr *)UNCACHED_SEG(&setup)) = g_setupscr_template;
    X = Y = 0;
    scr_setbgcolor(0);
    scr_setfontcolor(0xffffff);
    scr_setCursor(0);
    /* Reclaim GIF only. In particular do not reset GS/CRT timing, D_CTRL,
     * D_STAT, D_PCR, or any SIF channel while a loadfile RPC is outstanding. */
    *R_EE_D2_CHCR = 0;
    *(volatile u32 *)0x10003000 = 1; /* GIF_CTRL: reset drawing paths */
    *R_EE_D2_QWC = 0;
    *R_EE_D2_TADR = 0;
    SetVideoMode();
    progdma(&setup, 15);
    Dma02Wait();
}
