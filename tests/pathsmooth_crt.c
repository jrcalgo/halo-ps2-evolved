/*
 * Host CRT stand-ins for the Linux prefix renames. This file is compiled
 * without the CE prefix, so malloc, free, and fprintf stay libc.
 * debug_malloc/debug_free are the cseries.h malloc/free redirects. They do
 * not use the debug-header protocol in debug_memory.c; nothing in this
 * harness frees a pointer allocated by the other allocator.
 */

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int halo_linux_vsnprintf(char *buffer, size_t count, const char *format, va_list arguments)
{
	return vsnprintf(buffer, count, format, arguments);
}

int halo_linux_snprintf(char *buffer, size_t count, const char *format, ...)
{
	va_list arguments;
	int result;

	va_start(arguments, format);
	result = vsnprintf(buffer, count, format, arguments);
	va_end(arguments);
	return result;
}

int halo_linux_vsprintf(char *buffer, const char *format, va_list arguments)
{
	return vsprintf(buffer, format, arguments);
}

int halo_linux_sprintf(char *buffer, const char *format, ...)
{
	va_list arguments;
	int result;

	va_start(arguments, format);
	result = vsprintf(buffer, format, arguments);
	va_end(arguments);
	return result;
}

int halo_linux_vfprintf(FILE *stream, const char *format, va_list arguments)
{
	return vfprintf(stream, format, arguments);
}

int halo_linux_fprintf(FILE *stream, const char *format, ...)
{
	va_list arguments;
	int result;

	va_start(arguments, format);
	result = vfprintf(stream, format, arguments);
	va_end(arguments);
	return result;
}

int halo_linux_vprintf(const char *format, va_list arguments)
{
	return vfprintf(stdout, format, arguments);
}

int halo_linux_printf(const char *format, ...)
{
	va_list arguments;
	int result;

	va_start(arguments, format);
	result = vfprintf(stdout, format, arguments);
	va_end(arguments);
	return result;
}

FILE *halo_linux_fopen(const char *path, const char *mode)
{
	return fopen(path, mode);
}

void *debug_malloc(unsigned int size, int clear, const char *file, long line)
{
	void *pointer;

	(void)file;
	(void)line;
	pointer = malloc(size ? size : 1);
	if (pointer != NULL && clear)
		memset(pointer, 0, size);
	return pointer;
}

void debug_free(void *pointer, const char *file, long line)
{
	(void)file;
	(void)line;
	free(pointer);
}

void *debug_realloc(void *pointer, unsigned int size, const char *file, long line)
{
	(void)file;
	(void)line;
	return realloc(pointer, size ? size : 1);
}
