#ifndef HALO_HYBRID_REPLAY_H
#define HALO_HYBRID_REPLAY_H
#include "hybrid/protocol.h"
/* Deterministic command script. Presentation is a read of a copied snapshot. */
typedef void (*hybrid_present_fn)(const struct hybrid_snapshot *snapshot, void *user);
int hybrid_replay(unsigned cadence, unsigned *hash_out, struct hybrid_snapshot *final,
                  hybrid_present_fn present, void *user);
#endif
