#ifndef SOUNDREQ_HOST_XBDM_H
#define SOUNDREQ_HOST_XBDM_H
/* Host stand-in for the Xbox debug-monitor header. CE's windows prologue
 * only needs the exception types named by its prototypes. */
typedef struct soundreq_exception_pointers soundreq_exception_pointers;
typedef soundreq_exception_pointers *PEXCEPTION_POINTERS;
typedef struct soundreq_context CONTEXT;
#endif
