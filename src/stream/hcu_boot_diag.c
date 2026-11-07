#include "stream/hcu_boot_diag.h"
#include <debug.h>
#include <kernel.h>
#include <delaythread.h>
#include <smem.h>

/* Fixed trace in ELF NOBITS, charged by the resident_gameplay static ledger.
 * No allocations or filesystem/network operations in the held error screen. */
static volatile unsigned s_stage;
static volatile int s_result;
struct boot_note { const char *label; unsigned a, b, c; };
static struct boot_note s_notes[24];
static unsigned s_note_count;
static volatile unsigned s_progress_cycles;
static volatile int s_watch_active;
static int s_main_thread;
static unsigned s_iop_trace;
void hcu_boot_diag_watch_iop(unsigned address) { s_iop_trace = address; }
static unsigned char s_watch_stack[8192] __attribute__((aligned(16)));
extern void *_gp;
static unsigned boot_cycles(void)
{
 unsigned value;
 __asm__ volatile("mfc0 %0,$9" : "=r"(value));
 return value;
}
void hcu_boot_diag_note(const char *label, unsigned a, unsigned b, unsigned c)
{
 struct boot_note *note = &s_notes[s_note_count % 24u];
 note->label = label; note->a = a; note->b = b; note->c = c;
 ++s_note_count;
 s_progress_cycles = boot_cycles();
}
static unsigned boot_reg(unsigned address)
{
 return *(volatile unsigned *)address;
}
static void boot_watchdog(void *unused)
{
 (void)unused;
 for (;;) {
  DelayThread(100000);
  if (s_watch_active && boot_cycles() - s_progress_cycles > 2949120000u) {
   int suspended;
   const char *operation;
   s_watch_active = 0;
   suspended = SuspendThread(s_main_thread);
   operation = s_note_count ? s_notes[(s_note_count - 1u) % 24u].label : "unknown";
#if !defined(HALO_PS2_BOOT_COMPACT)
   if (s_iop_trace && s_iop_trace < 0x200000u) {
    static const char *const labels[] = {"sdr entry not recorded", "sdr suspend intr", "sdr exports", "sdr resume intr", "sdr banner print", "sdr create thread", "sdr start thread", "sdr exit print", "sdr returning"};
    unsigned trace[16] __attribute__((aligned(16)));
    /* The IOP window is kernel-only on hardware. The SDK helper switches
     * privilege for the copy; never dereference its KSEG address here. */
    smem_read((void *)s_iop_trace, trace, sizeof(trace));
    unsigned step = trace[0];
    hcu_boot_diag_note("IOP start/RPC", step, trace[1], s_iop_trace);
    hcu_boot_diag_note("IOP exp/mag", trace[2], trace[3], trace[6]);
    hcu_boot_diag_note("IOP lc/head", trace[4], trace[5], trace[7]);
    hcu_boot_diag_note("IOP stub/j", trace[8], trace[9], trace[12]);
    hcu_boot_diag_note("IOP tgt/exp", trace[10], trace[11], 0);
    if (step < sizeof(labels) / sizeof(labels[0])) operation = labels[step];
    if (step == 2 && trace[12] == 1) operation = "sdr register; list and stub checked";
    if (step == 9) operation = "sdr get loadcore internals";
    if (step == 10) operation = "sdr checking library list";
    if (step == 20) operation = "sdr bad export magic";
    if (step == 21) operation = "sdr invalid library pointer";
    if (step == 22) operation = "sdr library list cycle";
    if (step == 23) operation = "sdr library list exceeds 256";
    if (step == 24) operation = "sdr export table already registered";
    if (step == 25) operation = "sdr registration import mismatch";
    if (step == 26) operation = "IOP diagnostic read self-test";
   }
#endif
   hcu_boot_diag_note("HANG tid/rc", (unsigned)s_main_thread, (unsigned)suspended, 0);
   hcu_boot_diag_note("Dctrl/stat", boot_reg(0x1000e000), boot_reg(0x1000e010), boot_reg(0x1000e020));
   hcu_boot_diag_note("GIF ch/qwc", boot_reg(0x1000a000), boot_reg(0x1000a020), boot_reg(0x10003020));
   hcu_boot_diag_note("GIF MA/TA", boot_reg(0x1000a010), boot_reg(0x1000a030), boot_reg(0x1000f590));
   hcu_boot_diag_note("VIF0/1 GS", boot_reg(0x10008000), boot_reg(0x10009000), boot_reg(0x12001000));
   hcu_boot_diag_note("SIF0/1/2", boot_reg(0x1000c000), boot_reg(0x1000c400), boot_reg(0x1000c800));
   hcu_boot_diag_fail_reason(-100, operation);
  }
 }
}
static void boot_trace_display(void)
{
 unsigned i, first = s_note_count > 24u ? s_note_count - 24u : 0;
 unsigned row;
 scr_printf("TRACE HEX: left column then right column\n");
 row = (unsigned)scr_getY();
 for (i = first; i < s_note_count; ++i) {
  const struct boot_note *n = &s_notes[i % 24u];
  unsigned slot = i - first;
  scr_setXY(slot < 12u ? 2 : 41, (int)(row + slot % 12u));
  scr_printf("%-10.10s %08x %08x %08x", n->label, n->a, n->b, n->c);
 }
}
extern void hcu_boot_exception_vector(void);
extern void hcu_boot_scr_hold_init(void);

/* CRT milestones work before debug text, controller or IOP service setup.
 * Each completed operation has a different colour from its entry marker. */
void __real_SetupHeap(void *start, int size);
void __wrap_SetupHeap(void *start, int size)
{
 DEBUG_BGCOLOR(0x008000); /* green: BSS clear and SetupThread completed */
 __real_SetupHeap(start, size);
 DEBUG_BGCOLOR(0x808000); /* cyan: heap completed, before FlushCache */
}
void __real__InitSys(void);
void __wrap__InitSys(void)
{
 DEBUG_BGCOLOR(0x800000); /* blue: CRT cache flush completed */
 __real__InitSys();
 DEBUG_BGCOLOR(0x800080); /* magenta: kernel setup completed */
}
/* Finer kernel-startup markers. Preserve every real SDK call and return. */
void __real_InitAlarm(void);
void __wrap_InitAlarm(void) { DEBUG_BGCOLOR(0x0000ff); __real_InitAlarm(); }
void __real__ps2sdk_init_timer(void);
void __wrap__ps2sdk_init_timer(void) { DEBUG_BGCOLOR(0x00ff00); __real__ps2sdk_init_timer(); }
int __real_InitThread(void);
int __wrap_InitThread(void) { DEBUG_BGCOLOR(0xffff00); return __real_InitThread(); }
void __real_InitExecPS2(void);
void __wrap_InitExecPS2(void) { DEBUG_BGCOLOR(0x00ffff); __real_InitExecPS2(); }
void __real_InitTLBFunctions(void);
void __wrap_InitTLBFunctions(void) { DEBUG_BGCOLOR(0xffffff); __real_InitTLBFunctions(); }
void __real__libcglue_args_parse(int argc, char **argv);
void __wrap__libcglue_args_parse(int argc, char **argv)
{
 DEBUG_BGCOLOR(0x004080); /* orange: argument/cwd initialization entered */
 __real__libcglue_args_parse(argc, argv);
 DEBUG_BGCOLOR(0x808080); /* white: argument/cwd initialization returned */
}

void __real__libcglue_init(void);
void __wrap__libcglue_init(void)
{
 DEBUG_BGCOLOR(0x404000);
 __real__libcglue_init();
 s_stage = HCU_BOOT_LIBC;
}

/* A dedicated exception stack is selected by the assembly vector. Capturing
 * only CP0 state keeps this fatal-only handler small and avoids touching the
 * interrupted stack or depending on filesystem/network services. */
void hcu_boot_diag_exception(unsigned cause, unsigned epc, unsigned badvaddr)
 __attribute__((noreturn));

void hcu_boot_diag_exception(unsigned cause, unsigned epc, unsigned badvaddr)
{
 /* Avoid stdout, FileXio and network RPC in a fault. Reclaim GS so errors
  * remain visible even after the renderer replaces the debug display. */
 hcu_boot_scr_hold_init();
 scr_setCursor(0);
 scr_setXY(2, 2);
 scr_printf("HALO BOOT EXCEPTION\nSTAGE %u RESULT %d\nCAUSE %08x EPC %08x\nBADVADDR %08x\n",
  s_stage, s_result, cause, epc, badvaddr);
 boot_trace_display();
 for (;;) __asm__ volatile("nop");
}

void hcu_boot_diag_begin(void)
{
 int cause;
 ee_thread_t thread = {0};
 int watcher;
 init_scr();
 scr_printf("HALO DIAGNOSTIC (not release)\n02 libc complete\n");
 /* Fatal handler only: we never resume an exception. Use SDK vector writers
  * directly to avoid the full interactive EEDEBUG stack/frames in this ELF. */
 for (cause = 1; cause <= 3; ++cause)
  SetVTLBRefillHandler(cause, hcu_boot_exception_vector);
 for (cause = 4; cause <= 7; ++cause)
  SetVCommonHandler(cause, hcu_boot_exception_vector);
 for (cause = 10; cause <= 13; ++cause)
  SetVCommonHandler(cause, hcu_boot_exception_vector);
 FlushCache(0);
 FlushCache(2);
 hcu_boot_diag_stage(HCU_BOOT_MAIN, 0);
 s_main_thread = GetThreadId();
 thread.func = boot_watchdog;
 thread.stack = s_watch_stack;
 thread.stack_size = sizeof(s_watch_stack);
 thread.gp_reg = &_gp;
 thread.initial_priority = 0;
 watcher = CreateThread(&thread);
 if (watcher < 0) hcu_boot_diag_fail_reason(watcher, "Cannot create diagnostic watchdog");
 s_watch_active = 1;
 if (StartThread(watcher, NULL) < 0)
  hcu_boot_diag_fail_reason(-101, "Cannot start diagnostic watchdog");
}

void hcu_boot_diag_stage(enum hcu_boot_stage stage, int result)
{
 s_stage = (unsigned)stage; s_result = result;
 if (stage == HCU_BOOT_MENU || stage == HCU_BOOT_FRAME)
  s_watch_active = 0;
 if (stage == HCU_BOOT_HANDOFF) s_watch_active = 1;
 hcu_boot_diag_note("STAGE/result", (unsigned)stage, (unsigned)result, 0);
 /* Runtime stages after GS ownership changes use background colour only.
  * Never reset the production renderer's GS state to print progress. */
 DEBUG_BGCOLOR(((unsigned)stage * 0x10101u) & 0xffffffu);
 if (stage <= HCU_BOOT_DISC)
  scr_printf("%02u result %d\n", (unsigned)stage, result);
}

void hcu_boot_diag_fail_at(int result, const char *reason, const char *file, unsigned line)
{
 unsigned status, cause, epc, bad, sp, gp;
 s_watch_active = 0;
 __asm__ volatile("mfc0 %0,$12" : "=r"(status));
 __asm__ volatile("mfc0 %0,$13" : "=r"(cause));
 __asm__ volatile("mfc0 %0,$14" : "=r"(epc));
 __asm__ volatile("mfc0 %0,$8" : "=r"(bad));
 __asm__ volatile("move %0,$sp" : "=r"(sp));
 __asm__ volatile("move %0,$gp" : "=r"(gp));
 s_result = result;
 hcu_boot_scr_hold_init();
 scr_setCursor(0);
 scr_setXY(2, 2);
 scr_printf("HALO BOOT FAILED - RICH1\nSTAGE %u ERROR %d\n", s_stage, result);
 if (result == -100) scr_printf("TIMEOUT 10 seconds in: %.40s\n", reason);
 else scr_printf("%.76s\n", reason);
 scr_printf("SITE %s:%u\n", file, line);
 scr_printf("Diagnostic SP %08x GP %08x\n", sp, gp);
 scr_printf("CP0 status %08x cause %08x\n", status, cause);
 scr_printf("Last CP0 EPC %08x badaddr %08x\n", epc, bad);
 scr_printf("CP0 values above may precede this check.\n");
 boot_trace_display();
 for (;;) __asm__ volatile("nop");
}
