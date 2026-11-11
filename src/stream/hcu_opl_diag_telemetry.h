#ifndef HCU_OPL_DIAG_TELEMETRY_H
#define HCU_OPL_DIAG_TELEMETRY_H

/* Compiled only for OPL diagnostic ISO ELFs (WORLD_HCU_OPL_DIAG_TELEMETRY).
 * The release disc does not link this file. */
void hcu_opl_diag_telemetry_init(void);
void hcu_opl_diag_telemetry_tick(unsigned now_ms);

#endif
