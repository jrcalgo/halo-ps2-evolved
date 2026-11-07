/* Diagnostic-only trampoline. Preserve loader arguments and use the installed
 * production CRT unchanged. No stack, GP, libc, SIF or BSS access here. */
.set noreorder
.section .text.hcu_boot_entry,"ax",@progbits
.globl hcu_boot_entry
.ent hcu_boot_entry
hcu_boot_entry:
 lui $k0, 0x1200
 ori $k1, $zero, 0x40
 sd $k1, 0x00e0($k0)
 j __start
 nop
.end hcu_boot_entry

/* Fatal exception entry. This deliberately abandons the interrupted context,
 * switches to private aligned EE memory, captures CP0 cause/EPC/BadVAddr, and
 * enters the no-return GS diagnostic without using IOP or filesystem state. */
.globl hcu_boot_exception_vector
.ent hcu_boot_exception_vector
hcu_boot_exception_vector:
 la $sp, hcu_boot_exception_stack_end
 la $gp, _gp
 mfc0 $a0, $13
 mfc0 $a1, $14
 mfc0 $a2, $8
 jal hcu_boot_diag_exception
 nop
1:
 b 1b
 nop
.end hcu_boot_exception_vector

.section .bss.hcu_boot_exception_stack,"aw",@nobits
.align 7
.globl hcu_boot_exception_stack
hcu_boot_exception_stack:
 .space 8192
.globl hcu_boot_exception_stack_end
hcu_boot_exception_stack_end:
