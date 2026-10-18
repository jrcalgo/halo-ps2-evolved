# M08 synthetic hybrid proof preparation

M08 remains incomplete and depends on completed M06/M07 runtime gates. No hybrid scene has executed on EE.

`src/hybrid/protocol.h` defines tick-indexed commands, lifecycle events and copied presentation snapshots. The protocol contains scalar values and handles, with no DMA state, GS addresses or borrowed pointers. `src/hybrid/core.c` owns a fixed four-slot datum pool and uses the unchanged original Halo `data.c` implementation for creation, lookup, stale-handle rejection, iteration and destruction. Original integer-math point setters and offsets update a synthetic 2D position. This is not a Halo player, physics implementation or complete object system.

`python3 tools/build_hybrid_host.py` compiles and executes the bounded ILP32 preparation. Each replay covers 18,000 ticks, 30 creations, 30 destructions and 30 rejected stale commands. Normal, suppressed and every-seventh-tick presentation consumers produce the same canonical event/state hash, `1235839601`, and final counters. Mutating a copied snapshot does not change subsequent snapshots. The host currently reuses the probe diagnostic/allocation boundary; that reuse must be made explicit or replaced with a project service boundary before the visible EE integration is accepted.

Private reports and logs are under `build/hybrid-host32/`. This host replay does not establish real-time scheduling, rendering independence under actual EE load, visible motion, or the required full-duration integrated smoke. Those M08 gates remain pending.
