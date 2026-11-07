# Directional lag spikes (Blood Gulch and other maps): assessment and v4 fix, 2026-11-06

## Symptom

At 30 FPS the game is smooth, then stutters or freezes for tens to hundreds of milliseconds when the player looks in
certain directions. Blood Gulch is worst.

## Measurements

All frame times come from the PINE frame ring (`g_hcu_c3_frame_probe_ring`, v5). The ring records
`frame_interval_cycles`, `obj_load_cycles`, `obj_load_bytes`, `cache_pool_used`, governor state and more per frame.
The EE runs 294,912 cycles per ms, so 30 FPS is 33.3 ms per frame.

* The user's own desktop session (v3 ISO, MTVU + instant VU1, fastCDVD=false) showed bursts of up to 50
  consecutive frames with object loads, up to 2.2 MB and about 2.6 s in total. Individual loading frames cost 14-127 ms.
* The object pool was about 99% full during these bursts.
* Fresh headless A/B on the same turn sweep (identical emulator config, first 20 s skipped):

| Build | Mean FPS | p99 ms | Frames >66 ms | Frames >100 ms | Max obj-load ms/frame | Obj MB loaded |
|---|---|---|---|---|---|---|
| prefetch OFF (v3 behaviour) | 23.0 | 155 | 364 | 257 | 217 | 19.3 |
| prefetch ON (v4) | 30.0 | 38 | 1 | 1 | 17 | 13.4 |

The same churn happens in both runs; only its cost on the frame path differs.

## Root cause

1. `hcu_render_objects.c`: `entry_request` and the residency pool `s_pool` (about 4.17 MB, ranks 0-3). When the view
   turns, newly visible objects need loading. `entry_request` evicts the LRU victim after
   `OBJ_EVICT_HYSTERESIS_FRAMES` (8) frames out of view, subject to `slot_victim_ok`. The pool sits near 99%, so every
   large heading change evicts a set of objects and reloads another set. That is the heading dependence: a given
   direction needs a given set of models, and that set does not fit alongside the set for the opposite direction.
2. Each load runs through `job_pump` / `entry_load`, which read 24 KB (48 KB for rank 0/1) slices per frame and hash them
   with SHA-256 before use.
3. Every read was synchronous: `hcu_asset_profile_read_range` -> `hcu_c2_package_read_at` -> `hcu_c2_read_at` ->
   `hcu_file_bridge_read` -> `file_reader_read_at` -> `fileXioRead`. That is an RPC to the IOP that blocks the EE for the
   emulated DVD read time (PCSX2 with fastCDVD=false), 14-127 ms per slice, plus the hash. One slice per frame is
   enough to turn a 33 ms frame into 50-160 ms, and a load burst is a stutter or freeze.
4. The `sceCdRead` "optical" branch in `engine/src/stream/file.c` is dead (descriptor flag never set), so there was no
   existing asynchronous path to fall back on.

## v4 fix

* `engine/src/stream/file.c`/`file.h`: `file_reader_prefetch()` issues an asynchronous `fileXioRead`
  (`FXIO_NOWAIT`) into a staging buffer; `file_reader_read_at()` settles any in-flight read first and serves the head
  of a request from the ready window by memcpy.
* `hcu_asset_profile.c`: `hcu_asset_profile_range_ready()` maps a logical range to its contiguous physical span and
  starts the prefetch; `hcu_main.c` registers the package readers for both the C2 and successor packages.
* `hcu_render_objects.c` `job_pump`: each frame polls whether the next 60 KB window (30 KB for scenery) is ready,
  hashes and copies it, then immediately issues the following window. The staging buffer is carved from the pool tail so
  no static memory is added (boot `_fbss` limit 0x370000 is unchanged).
* Result: load work stays on the frame path only for the memcpy and SHA-256, which is at most 17 ms.

## Not fixed (still open)

* Pool size and eviction policy are unchanged, so the churn still happens (now it is cheap).
* First-use FX texture resolves still block (up to about 79 ms each, seen at startup).
* SHA-256 verification is still per chunk on the frame path.
