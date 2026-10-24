# M2 C2 r2 segments-alloc lane evidence (2026-10-23)

Scope: C2.4 and C2.5, lane segments-alloc. Partial: only task (a) is done.

## Done: (a) per-segment residency

- `src/stream/hcu_asset_profile.{c,h}`: the residency unit is now one HCP2 segment
  (logical chunk, segment index). `hcu_asset_profile_segment_info` reads a segment's
  stored size and logical offset from its directory row. `hcu_asset_profile_read_segment`
  copies one segment and verifies its own SHA-256 against its row. A segment over
  65,536 B is refused. Pin, unpin, lease, release, gameplay_ref, evict and state take a
  segment index. Evict is still refused while any count is nonzero. The table has a
  fixed slot count and a `refused_pins` counter.
- `tests/hcu_asset_residency_main.c` and `tests/test_hcu_asset_residency.py` now pin
  every segment, check lifetime rules per segment, hash the concatenated segments
  against the chunk digest, and check a one-slot table refusal.

Command: `python3 -m pytest -q tests/test_hcu_asset_residency.py` gives 4 passed.
Driver output on `build/m2-c2-hcp2-primary/bots-bloodgulch.hcp` (profile 4 for the
package): `PIN 1:0 bytes=4767713 segments=73`, `PIN 3:0 segments=1`, and
`REFUSED 222 evictions 148 verify_failures 0 refused_pins 0 segments 74`.

## Not done

- (b) No live caller. `hcu_profile_mount.c` does not call the residency table, so
  `tests/test_hcu_profile_mount.py` was not rerun with the segment pins.
- (c) The labels in `build/m2-c2-chunks-alloc/classify.py` are not yet moved into
  `tools/audit_hcu_postload_allocations.py`, and the 22 post-load-candidate sites are
  not yet examined.
- (d) The malloc diagnostic, endless-malloc and MP bind capacity tests were not run.
- The EE cross-compile was not run.
