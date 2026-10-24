# M2 Step 9 CE tag-read failure/retry corroboration — 2026-10-21

## Finding

The recorded host lifecycle evidence is corroborated by the harness, test wrapper,
retained run log, and manifest. The test injects a malformed final relocation-table
entry after parent preflight and mount, drives the real CE `scenario_tags_load()`
path, verifies failure before tag publication, restores the entry, and retries on
the same mounted CTAG/source. It is evidence for the current whole-buffer
materializer only—not a streamed-read implementation or M2 acceptance.

## Source-backed sequence

1. The fixture first requires an active parent mount and source, with no CE tag
   publication, then obtains the retained CTAG payload and computes the final
   relocation-table word (`tests/hcu_ce_map_lifecycle_main.c:37-58`).
2. It changes that final word to `image_size`, calls real CE
   `scenario_tags_load("levels\\ui\\ui")`, and requires `NONE`; tag header,
   global tag instances/count, and `tags_loaded` stay unpublished. The entire tag
   cache remains at CE's `0xCD` poison, while the parent mount/source and cache
   map remain active (`tests/hcu_ce_map_lifecycle_main.c:59-76`).
3. The test restores the saved word, retries CE tag loading on the same mount,
   requires a valid tag header/global publication, then calls
   `scenario_tags_unload()` and verifies those globals clear without releasing
   the parent owner (`tests/hcu_ce_map_lifecycle_main.c:77-89`).
4. CE itself poisons the destination before its exact `cache_file_read()` call;
   it only publishes tag globals after read completion, cache-header validation,
   and full schema validation (`submodules/halo-ce-universal/source/cache/cache_files.c:1262-1314`).
5. The PS2 cache initializes completion to its failure sentinel, recognizes the
   exact tag-cache request, and only marks success when `ps2_ctag_materialize()`
   succeeds (`submodules/halo-ce-universal/port/ps2/src/ps2_cache.c:375-415`).
   Materialization validates every relocation field, target, and target address
   before copying the image to the destination (`submodules/halo-ce-universal/port/ps2/src/ps2_ctag.c:227-250`).

## Terminology correction

The test changes the last **relocation-table entry**, which stores the byte offset
of a field in the image. Setting it to `image_size` makes the field offset
out-of-image, so validation rejects it. It does not change the pointer value
(relocation target) stored at a valid field inside the image. Any plan/report
description calling this an invalid “relocation target” should say “invalid final
relocation entry/field offset” instead. The harness comment accurately describes
an aligned out-of-image field (`tests/hcu_ce_map_lifecycle_main.c:56-63`).

## Artifact corroboration

The retained report identifies the native ILP32 fixture and exact artifacts in
`build/m2-ce-map-lifecycle-host/`. The checked-in-at-runtime manifest matches
these SHA-256 values when recomputed:

| Artifact | SHA-256 |
|---|---|
| fixture ELF | `b0c78f83217de8bd02896cf11d63b24ecb6e2d1c3a956e0eb1f176bb2e463bfc` |
| runtime log | `342b33a064811f4ce906241fd86594dba04586855a1eee67deaa6ff22905bb74` |
| manifest | `76e7bb0173d897217d4ae3176e67c39e728690711b1dc3be583d65e49c789e89` |

The run log contains the expected failure/retry marker at line 30 and proceeds
to the full CE UI scenario load and same-process deferred reload
(`build/m2-ce-map-lifecycle-host/ce-lifecycle.log:30-83`). The test wrapper
requires that marker and writes the manifest including `native_ilp32`, late
relocation rejection, same-mount retry, and same-process retry fields
(`tests/test_hcu_ce_map_lifecycle.py:102-145`). The detailed original report is
[`m2-ce-map-lifecycle-host-2026-10-21.md`](m2-ce-map-lifecycle-host-2026-10-21.md).

## Evidence limits

- This is a **host native ILP32** fixture, not a PS2 EE or PCSX2 run.
- It uses the retail UI package and mutates the already-mounted CTAG bytes in
  memory after preflight. It does not exercise a changed package/source file or
  an actual CTAG transport error.
- `ps2_ctag_materialize()` validates before its first copy, so the test proves
  pre-copy rejection for this implementation. It does not test a streaming sink
  that has partially written the final tag-cache destination before an HP2 outer
  CRC, inner CTAG CRC, I/O, or sink failure.
- The retry restores the saved in-memory relocation word and repeats
  `scenario_tags_load()` on the still-active mount/source. It does not rerun
  parent preflight, unmount/remount the package, or prove recovery after a
  partially overwritten destination.
- It does not prove rollback for CE schema/BSP failures, real FileXio/OPL or
  optical behavior, gameplay-map memory capacity, guest rendering, or the M2
  exit gate. The independent report explicitly classifies the mutation as
  pre-copy atomicity and lists the untested partial-stream and target-storage
  cases (`m2-ce-map-lifecycle-host-2026-10-21.md:22,39-41`).

Accordingly, the plan's statement that **guest** fault injection remains
unproven is still correct. This host result strengthens the CE publication and
same-mounted-owner retry subchecks, but must not be promoted to guest, streamed
destination, or milestone acceptance evidence.
