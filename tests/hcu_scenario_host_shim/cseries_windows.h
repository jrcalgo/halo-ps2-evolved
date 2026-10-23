#ifndef HCU_SCENARIO_HOST_CSERIES_WINDOWS_H
#define HCU_SCENARIO_HOST_CSERIES_WINDOWS_H

/* Host fixture stub: cache-load tests do not execute Xbox UI/debug services. */
typedef void CONTEXT;
typedef void *PEXCEPTION_POINTERS;
typedef void *HANDLE;
struct system_memory_information { long free; long total; };

#define XC_LANGUAGE_GERMAN 3
#define XC_LANGUAGE_FRENCH 4
#define XC_LANGUAGE_SPANISH 5
#define XC_LANGUAGE_ITALIAN 6
#define GENERIC_READ 0x80000000u
#define OPEN_EXISTING 3u
#define INVALID_HANDLE_VALUE ((HANDLE)(long)-1)

void display_debug_string(const char *string);
unsigned long system_milliseconds(void);
unsigned long system_seconds(void);
void *system_calloc(long count, long size);
void *system_malloc(long size);
void system_free(void *pointer);
void *system_realloc(void *pointer, long size);
void system_memory_information_get(struct system_memory_information *information);
long generic_exception_filter(unsigned long exception_code,
	PEXCEPTION_POINTERS exception_information);
HANDLE CreateFileA(const char *path, unsigned long access, unsigned long share,
	void *security, unsigned long creation, unsigned long flags, HANDLE template_file);
int ReadFile(HANDLE file, void *buffer, unsigned long count,
	unsigned long *read_count, void *overlapped);
int CloseHandle(HANDLE file);

#endif
