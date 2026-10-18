/* Print the EE kernel, heap, and stack bounds once, then exit. */
#include <kernel.h>
#include <loadfile.h>
#include <sifrpc.h>
#include <stdio.h>
#include <stdint.h>

extern char _end;
extern char _stack_size;

static uintptr_t stack_pointer(void)
{
	uintptr_t value;
	__asm__ volatile("move %0, $29" : "=r"(value));
	return value;
}

static void report(const char *tag)
{
	printf("HALO_PS2_MEMMAP %s end=%p heap_end=%p sp=0x%08x stack_size=%u\n",
	       tag, (void *)&_end, EndOfHeap(), (unsigned)stack_pointer(),
	       (unsigned)(uintptr_t)&_stack_size);
}

int main(void)
{
	setvbuf(stdout, NULL, _IONBF, 0);
	report("before_sif");
	SifInitRpc(0);
	report("after_sif");
	SifLoadModule("rom0:SIO2MAN", 0, NULL);
	report("after_sio2man");
	SifLoadModule("rom0:PADMAN", 0, NULL);
	report("after_padman");
	return 0;
}
