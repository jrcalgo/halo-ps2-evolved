/* Host-only include order for C4 collision parity TUs: collision_features.c
 * includes collision_features.h before collision_bsp.h, so the bsp struct
 * must be declared first. */
#include "cseries/cseries.h"
#include "physics/collision_bsp.h"
#include "physics/collision_bsp_definitions.h"
