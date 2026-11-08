# Low-detail stand-ins for map objects (2026-11-08)

Map objects (vehicles, rocks, trees, pickups, loose weapons) used to pop in: the object residency pool (about 4.1 MB) is
smaller than the full-detail set a map uses (about 6.9 MB on Blood Gulch), so models were evicted and reloaded as the
camera turned, and a model that was not resident was simply not drawn.

## What changed

* **Package.** For every vehicle, world-weapon and scenery/other model whose full pack is over 64 KB and whose stand-in is at most 60%
  of that size, the package also holds a low-detail MODL/OTEX pair (`modelconv.C3_OBJECT_PROXY_PROFILE`:
  the c3 v3 per-class LOD and clustering plan, 64 px textures). The chunk bindings carry `"variant": "proxy"`. Packages
  are built with stand-ins by default; `hcu_multiplayer_profiles.py --no-object-proxy` leaves them out.
  First-person, biped and sky models never get one. Blood Gulch: 22 stand-ins, about 0.7 MB more package.
* **Table.** `hcu_c3_objects_table.py` appends one row per stand-in after all full rows (`proxy = 1`, same source and tag
  datum, own chunk ids and hashes). Every row also carries `tex_keys`, its OTEX texture count, so texture cache keys are
  handed out by need instead of a fixed 32 per entry (the key budget stays 80 x 32).
* **Runtime (`hcu_render_objects.c`).** `hcu_render_objects_find_model` answers with the full model when it is resident and
  else its stand-in, so a frame always draws something. The *resident floor* is every stand-in plus every small model
  (at most 64 KB, not a viewmodel). Loaded floor slots have rank 0, so nothing displaces them, up to 45% of the pool.
  The floor is read into the empty pool at map load (`floor_preload`, before the first frame) and topped up by
  `floor_prefetch` at rank 1, one bounded sliced job at a time, dropping a stale job that only holds pool bytes.
  Full-detail loads, eviction and the 8-frame hysteresis work as before; the full model swaps in when its load finishes.
  `HCU_OBJECTS_MAX_MODELS` is 128 (largest table: 91). The prepared-object cache keeps its first 80 slots only;
  later slots (stand-ins past 80) draw through the unprepared path.

## Measured (headless PCSX2, a walk with random turns, per 10 s buckets of "referenced model not resident")

* Blood Gulch warm: 99.1% of referenced models resident at full detail, 0.9% drawn as stand-ins, 0.04% absent
  (first-person models only, which have no stand-in).
* Blood Gulch from boot: all floor models resident at the first frame; stand-ins in use for the first ~30 s while
  vehicles load at full detail.
* Wizard: 0 absent over 100 s.

## Open

* A model whose stand-in and full model are both absent is still not drawn; this only happens for viewmodels.
* Stand-ins are the c3 v3 detail, so a vehicle seen at a distance before its full model loads is blocky until it swaps.
* The pool is not larger: a bigger pool would need a budget change (not done).
