#pragma once

/* Initialize the bounded direct-FileXio reader after SIF RPC is available.
 * Existing IOP modules are reused; this routine never resets the IOP. */
int hcu_storage_boot_init(void);
