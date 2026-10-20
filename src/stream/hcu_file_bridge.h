#pragma once

/* Fixed-slot, read-only bridge from HCU's Win32 cache API to the parent
 * machine's bounded PS2 file reader. Tokens are valid until close. */
int hcu_file_bridge_open(const char *path, unsigned long *size_out);
int hcu_file_bridge_close(int token);
int hcu_file_bridge_read(int token, void *buffer, unsigned long count,
	unsigned long *read_out);
int hcu_file_bridge_size(int token, unsigned long *size_out);
long hcu_file_bridge_seek(int token, long distance, unsigned long origin);
int hcu_file_bridge_stat(const char *path, unsigned long *size_out,
	int *directory_out);
