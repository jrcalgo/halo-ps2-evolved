# M4 render snapshot bridge: rooted external dispositions

## Scope and exact closure

This review covers the two weak parent hooks called by HCU's PS2 `render_frame`
adapter. They are intentionally unresolved in the standalone HCU closure and
are owned by the combined parent/HCU image. The current rooted HCU object is
`build/hcu-ps2-closure/all/rooted.o`; its SHA-256 is recorded by the adjacent
external ledger. The current combined host-profile machine image is
`build/hcu-parent-link-probe/hcu-gameplay-machine.elf`. It has zero undefined
imports and its link map contains both parent bridge definitions.

## `halo_ps2_render_snapshot_begin`

- Caller: `render_frame` in `submodules/halo-ce-universal/port/ps2/src/ps2_render.c`.
- Owner: `halo_ps2_render_snapshot_begin` in `src/stream/hcu_render_snapshot.c`.
- Contract: return the inactive fixed snapshot bank and clear only its header;
  do not allocate, keep CE pointers, or disturb the published bank.
- Disposition: `state-adapter`. HCU fills a pointer-free, bounded snapshot;
  parent memory owns the two banks. This is not a renderer or a claim that a
  retail scene is drawn.
- Evidence: `src/stream/hcu_render_snapshot.c` double-buffer implementation;
  `submodules/halo-ce-universal/port/ps2/include/halo_ps2_render_snapshot.h`
  fixed-capacity wire layout.
- Test: `tests/test_hcu_render_snapshot.py` and its compiled C fixture cover
  publication, monotonic sequence, retained prior-bank contents, malformed
  object-count rejection, and the CE-to-halo-ps2 matrix converter. The current
  combined link report binds the implementation into the production image.

## `halo_ps2_render_snapshot_commit`

- Caller and owner: the same HCU `render_frame` producer and parent snapshot
  implementation as above.
- Contract: reject invalid pointers, stale/non-writer banks, counts beyond the
  fixed capacities, non-finite camera/matrix values, and invalid camera planes;
  publish only a fully validated snapshot with a nonzero sequence number.
- Disposition: `state-adapter`. It is the publication half of the bounded
  HCU-to-parent state handoff, not an optional empty draw callback.
- Evidence and test: same source and fixture citations as
  `halo_ps2_render_snapshot_begin`.

The bridge hooks are the only newly reviewed snapshot externals. `memcpy`,
`rint`, and several compiler/libm rows remain independently governed by their
own reports and are not approved here. In particular, this report does not
close M0 while the current ledger has any pending or stale symbol rows.
