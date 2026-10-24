/* Test-only host schema capacity. Production PS2 limits remain 2 MiB. */
#include "hcu_scenario_host32_prefix.h"
#undef HALO_PORT_TAG_CACHE_SIZE
#define HALO_PORT_TAG_CACHE_SIZE (64UL * 1024UL * 1024UL)
