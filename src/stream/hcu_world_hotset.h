#ifndef HCU_WORLD_HOTSET_H
#define HCU_WORLD_HOTSET_H
#include <stdint.h>

#define HCU_WH_MAX_CANDIDATES 256
#define HCU_WH_MAX_PREFETCH 64
#define HCU_WH_MAX_CORE 128
enum { HCU_WH_OTHER=0, HCU_WH_VEHICLE=1, HCU_WH_GROUND_WEAPON=2 };
enum { HCU_WH_OK=0, HCU_WH_INVALID=1, HCU_WH_NON_FIT=2, HCU_WH_OVERFLOW=3, HCU_WH_PARTIAL=4 };
typedef struct { uint32_t generation, id, bytes; uint8_t kind, mandatory, current_visible, predicted_visible; } hcu_wh_candidate;
typedef struct { uint32_t generation; uint16_t count; uint32_t ids[HCU_WH_MAX_CORE]; } hcu_wh_core;
typedef struct { uint32_t generation; uint16_t core_count, prefetch_count; uint32_t core_ids[HCU_WH_MAX_CORE], prefetch_ids[HCU_WH_MAX_PREFETCH]; uint64_t core_bytes, mandatory_bytes, reserve_bytes, prefetch_bytes; uint64_t vehicle_coverage_bytes, weapon_coverage_bytes; uint32_t vehicle_coverage_permille, weapon_coverage_permille; int status; } hcu_wh_plan;
/* Stable core is retained in state while generation/signature remain unchanged. */
typedef struct { uint32_t generation, signature; uint16_t count; uint32_t ids[HCU_WH_MAX_CORE]; uint8_t valid; } hcu_wh_state;
int hcu_wh_plan_build(const hcu_wh_candidate *items, uint32_t count, uint32_t generation, uint64_t pool_bytes, uint64_t transient_reserve, hcu_wh_state *state, hcu_wh_plan *out);
#endif
