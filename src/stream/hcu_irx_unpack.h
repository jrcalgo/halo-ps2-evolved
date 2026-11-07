#pragma once
#include <stddef.h>
/* Shared boot-only scratch. The returned bytes remain valid until the next
 * unpack; the synchronous module loader must return before another call. */
const void *hcu_irx_unpack(const void *packed, size_t bytes, size_t raw_bytes);
