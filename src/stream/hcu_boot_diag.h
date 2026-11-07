#pragma once

/* Stage numbers are an on-screen protocol. Do not renumber retained runs. */
enum hcu_boot_stage {
 HCU_BOOT_LIBC = 2, HCU_BOOT_MAIN = 3, HCU_BOOT_MEMORY = 4,
 HCU_BOOT_SIF = 5, HCU_BOOT_PAD = 6, HCU_BOOT_FILEXIO = 7,
 HCU_BOOT_DISC = 8, HCU_BOOT_MENU = 9, HCU_BOOT_HANDOFF = 10,
 HCU_BOOT_GAMEPLAY = 11, HCU_BOOT_FRAME = 12
};
#if defined(HALO_PS2_BOOT_DIAG) && HALO_PS2_BOOT_DIAG
void hcu_boot_diag_begin(void);
void hcu_boot_diag_stage(enum hcu_boot_stage stage, int result);
/* Labels/reasons must have static lifetime. Storage is a fixed 24-record ring. */
void hcu_boot_diag_note(const char *label, unsigned a, unsigned b, unsigned c);
void hcu_boot_diag_watch_iop(unsigned address);
void hcu_boot_diag_fail_at(int result, const char *reason, const char *file, unsigned line);
#define hcu_boot_diag_fail(result) \
 hcu_boot_diag_fail_at((result), "startup check failed", __FILE__, __LINE__)
#if defined(HALO_PS2_BOOT_COMPACT)
#define hcu_boot_diag_fail_reason(result, reason) \
 hcu_boot_diag_fail_at((result), "startup check failed", __FILE__, __LINE__)
#else
#define hcu_boot_diag_fail_reason(result, reason) \
 hcu_boot_diag_fail_at((result), (reason), __FILE__, __LINE__)
#endif
#else
#define hcu_boot_diag_begin() ((void)0)
#define hcu_boot_diag_stage(stage, result) ((void)0)
#define hcu_boot_diag_fail(result) ((void)0)
#define hcu_boot_diag_fail_reason(result, reason) ((void)0)
#define hcu_boot_diag_note(label, a, b, c) ((void)0)
#define hcu_boot_diag_watch_iop(address) ((void)0)
#endif
