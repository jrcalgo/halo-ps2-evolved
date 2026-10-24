# M2 Step 9 resource-fault coverage review

Date: 2026-10-21  
Scope: report-only audit of the newly documented retained-resource EOF/retry case and deferred cache-capacity failure in `tests/ctag_mount_main.c` and `plans/7.hcu-remake-m2-m4.md`. This review does not change implementation or plan status.

## Summary

The retained-source resource EOF test is a meaningful, narrowly scoped check of the cache callback contract: it proves that a CRNG-authorized request reaches the file-backed source, that an injected partial transport read followed by EOF leaves CE's completion flag false, that the mounted owner/source stays available, and that retrying the same interval yields the expected bytes. It is not a CE resource-publication or scenario-replay test, as the plan now correctly caveats.

The new “late cache-capacity rejection” service test does **not** currently reach the HCU cache backend/mount boundary it claims to test. With `tag_cache_capacity` lowered before `cache_files_precache_map_begin()`, `map_loader()` performs deferred `hcu_map_service_preflight()` first; that preflight calls `ps2_ctag_open()` using the lowered capacity and rejects at `src/stream/hcu_map_service.c:296-310`. Consequently the test never enters `ctag_mount_hp2_verified_source_discover()` or `ps2_cache_mount_ctag_with_file_source()`. Its rollback/retry assertions still prove a useful post-unload *preflight-capacity rejection* path, but the location and semantics are mislabeled in the plan and test message. There is a separate direct mount-level undersized-capacity check later in `tests/ctag_mount_main.c` that does reach the adapter, but it is not this composed service/deferred-reload case.

## Evidence and assessment

### Retained-resource EOF and retry

`tests/ctag_mount_main.c:639-678` chooses the first CRNG interval from the already mounted service, clips its length to the 32-byte candidate buffer, and first reads expected bytes through `ctag_map_source_read()`. It then seeds `complete = TRUE`, makes the FileXio shim permit one byte before returning EOF (`tests/ctag_mount_main.c:312-330`), and calls `cache_file_read()` with `tag_index == 0`, the interval's file offset, and a non-BSP destination buffer.

The production path is relevant: [`ps2_cache.c`](../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L375-L456) initializes the completion flag to `_cache_file_read_failed`, checks request bounds, and sets it to `TRUE` only when `mounted_read_at()` succeeds. The service mount installs the CRNG-authorizing reader; [`ctag_resource_index_read()`](../src/stream/ctag_resource_index.c#L131-L141) rejects unauthorized ranges and delegates authorized ranges to the source callback. The partial-read shim verifies an actual positive `fread` call before the next read returns EOF (`tests/ctag_mount_main.c:312-330`). The test then checks that the map and source remain active, the descriptor and arena cursors remain stable, and file open/close counts do not change before immediately retrying and comparing the full output to the expected source bytes.

This is strong evidence for failure signaling, retained-source lifetime, and deterministic same-owner retry at the `cache_file_read()` callback seam. It does not show that the failed attempt wrote exactly one candidate byte (the shim/call count implies a positive read, but `resource[0]` is not asserted), nor that CE's caller discards or invalidates the partially modified receive buffer. Most importantly, it does not run the CE tag/resource loader that consumes the completion flag, test whether that loader retries, or assert scenario/global publication state after such a failure. The plan's qualification in `plans/7.hcu-remake-m2-m4.md:345` accurately preserves these limits.

Small tightening: assert that `resource[0] == expected_resource[0]` after the injected failure and that the remainder retains the `0xA5` sentinel (assuming the fixture's source read implementation is specified to stop after that first byte). This makes the intended partial write explicit and guards against the EOF injector firing before any bytes reach the caller buffer. If the reader's buffering semantics make the exact byte boundary intentionally non-contractual, rename the assertion/message to “partial transport progress observed” and retain the existing successful-read-call proof rather than promising one caller-buffer byte.

### Deferred capacity-failure test: actual path and false positive

At `tests/ctag_mount_main.c:830-868`, the test first preflights the currently mounted UI map (which only stages `reload_pending`), releases the old owner, then sets `tag_cache_capacity = 1 MiB` before calling `cache_files_precache_map_begin()`.

That begin callback enters [`map_loader()`](../src/stream/hcu_map_service.c#L95-L145). Because `reload_pending` is true and `preflight_ready` is false, lines 110-117 call `hcu_map_service_preflight()` before the mount attempt. Preflight rereads HMAP/CTAG/CRNG/CBIX and calls `physical_memory_get_tag_cache_size()` at line 296, then validates the CTAG with `ps2_ctag_open()` at lines 298-310. The UI CTAG's image exceeds 1 MiB, so it rejects there; the cleanup path closes the source and clears staging at lines 314-318 and the loader exits before its mount call at lines 131-135.

This means the test cannot support its claims that source/hash/sections have passed *and then* the backend refused CTAG, or that `ps2_cache_mount_ctag_with_file_source()` rejected at its adapter boundary. The captured state checks do prove that this earlier preflight rejection clears service ownership and leaves destination buffers unchanged, and the same-process retry after restoring capacity is useful. The comment/marker at `tests/ctag_mount_main.c:842-860` and the plan entry `plans/7.hcu-remake-m2-m4.md:345` should not be treated as adapter-mount evidence until the injection point is moved later.

The plan already describes a distinct direct adapter test accurately at `plans/7.hcu-remake-m2-m4.md:348`: a low-capacity value used while calling `ctag_mount_hp2()` directly reaches the unmodified HCU backend and should make `ps2_ctag_open()` reject before adapter publication. That does not substitute for a composed service failure after deferred preflight.

### Snapshot/assertion limitations

The capacity-failure snapshot compares map/scratch `used` cursors and bounds their high-water values, but does not compare the recorded arena base/capacity/object identity or unchanged mount/source callback/payload fields. Since the intended result is an empty owner after release, inactive flags and the zero cursors are central; nevertheless, if this test is retained as a transaction snapshot, comparing identity/base/capacity to the baseline would make it resistant to accidental arena replacement. It also proves no public UI cache mount via `cache_files_precache_map_loaded("ui")` and compares full tag/BSP destination hashes; those are useful but should be complemented by an explicit backend-entry/call-stage witness.

The resource read case uses `assert(cache_file_read(...) == NONE)` for both faulted and successful requests. This is not by itself an error: the port cache API intentionally returns `NONE` and communicates read failure through the completion flag. The meaningful assertions are the completion value and byte equality, not the return code.

## Smallest next in-scope test

Keep the current capacity fault as a clearly named deferred **preflight** capacity-rejection test, or move the fault one seam later so it actually covers the composed backend refusal. The smallest reliable later injection is to replace the test's fixed capacity scalar with a test-only scripted getter: during the deferred `map_loader()` call, return the full 2 MiB value for preflight's single `physical_memory_get_tag_cache_size()` read, then return 1 MiB for the two getter reads inside `ps2_cache_mount_ctag_with_file_source()`/`ps2_ctag_open()`. Record the getter call sequence and require evidence that `hcu_map_service_preflight()` returned success (or that `map_loader()` emitted the mount-begin/result trace) before the reduced capacity is served. Then assert mount/backend refusal, no adapter publication, parent/map/scratch rollback, source close, unchanged tag/BSP destination hashes, balanced handles, and a valid same-process retry after resetting the getter. This specifically covers `map_loader()` lines 131-145 and `ps2_cache_mount_ctag_with_file_source()` lines 131-159, rather than only `hcu_map_service_preflight()` lines 296-318.

To make the test fail for the right reason rather than merely pass on a no-map result, instrument a counter at the actual backend `mount` call or use a stage trace/callback witness in the host fixture. The counter should increment once for the injected attempt; an assertion that it remains zero should be used in the separate preflight-failure test. Avoid adding a production behavior hook solely for this host test if the scripted capacity getter plus existing observable stage trace is sufficient.

Run `python3 tests/test_retail_ui_ctag_mount.py -v` after the correction and preserve this host-only classification. Real FileXio/OPL, CE scenario-global teardown/publication, and PCSX2 failure/retry remain separate acceptance work.

## Verification

Ran `python3 tests/test_retail_ui_ctag_mount.py -v` in the current worktree: **1 passed** (8.5 s). This confirms the current fixture passes, not that its “late backend” interpretation is correct. Source-path review above shows the injected capacity is consumed earlier by deferred preflight.
