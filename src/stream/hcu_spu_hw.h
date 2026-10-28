#ifndef HALO_STREAM_HCU_SPU_HW_H
#define HALO_STREAM_HCU_SPU_HW_H

#include <stdint.h>

#include "stream/hcu_spu_playback.h"

#ifdef __cplusplus
extern "C" {
#endif

/* The four SPU2 register operations the player needs. sdrdrv remote calls on
 * the EE; a recording fake in the host test. `entry` uses libsd encoding. */
typedef struct {
	void (*set_param)(uint16_t entry, uint16_t value);
	void (*set_addr)(uint16_t entry, uint32_t value);
	void (*set_switch)(uint16_t entry, uint32_t value);
	uint32_t (*get_switch)(uint16_t entry);
} hcu_spu_hw;

void hcu_spu_attach(const hcu_spu_hw *hw, const hcu_spu_sample *samples, uint32_t count);
void hcu_spu_note_uploaded(uint32_t bytes);

#ifdef __cplusplus
}
#endif

#endif
