# M2 C2 CE cache owner telemetry — 2026-10-23

This change adds allocation-free counters at the PS2 cache adapter's actual
fixed CE cache destinations. The exact owner labels are `tag_cache` and
`structure_bsp_cache`; current and peak bytes count complete published images,
not encoded CTAG/CBSP source bytes or arena capacity.

`ps2_cache_get_owner_telemetry()` returns current/peak bytes, successful image
publication counts, failed target reads, rejected mounts, unmount/reset counts,
and BSP lease failures. A failed candidate read preserves the previous current
owner and peak. Tag map unmount and explicit BSP image unpublish clear current
bytes while retaining the peak. The explicit lifetime reset is accepted only
when the cache owners are unmounted.

The BSP read lease points at the fixed CE BSP cache image. It has a generation
and a non-reused lease ID, supports at most eight concurrent readers, rejects
stale/duplicate releases, and blocks cache writes and owner unmount while any
reader remains. Renderer consumers must hold it through their actual DMA/GS
completion fence. `ps2_cache_unmount_cbsp()` releases the encoded source package;
CE image lifetime ends through `ps2_cache_bsp_image_unpublish()`.

Verification run:

- `PYTHONPATH=.:submodules/halo-ps2/tools python3 tests/test_ctag.py` — 13 passed.
- `PYTHONPATH=.:submodules/halo-ps2/tools python3 tests/test_cbsp.py -k test_ps2_cache_serves_cbsp_only_at_audited_extent` — passed, including lease blocking, generation validity, stale release rejection, and image unpublish.

This covers the CE cache adapter owners only. It is not a full C2 workload
measurement and does not claim source-hit or steady-state workload coverage.
