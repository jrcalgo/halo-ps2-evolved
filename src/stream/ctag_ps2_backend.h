#ifndef HALO_CTAG_PS2_BACKEND_H
#define HALO_CTAG_PS2_BACKEND_H

#include "stream/ctag_mount.h"

/* Production adapter from the parent CTAG owner to HCU's PS2 cache API. */
const ctag_mount_backend *ctag_ps2_cache_backend(void);

#endif
