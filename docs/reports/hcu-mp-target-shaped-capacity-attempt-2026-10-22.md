# HCU stock-MP target-shaped capacity attempt

## Result

The fixed profile was applied without enlarging any production region: 2 MiB
CTAG/tag cache, 4 MiB remaining BSP cache, 1 MiB map-owner, 512 KiB streaming
scratch, and the CE claims bitmap computed for the combined six-MiB address
space (786,432 bytes). All thirteen pinned retail multiplayer packages fail
the first real capacity gate: their compact CTAG images are 4.04–4.27 MiB, so
the streaming CTAG validator rejects them against the configured 2 MiB tag
capacity before map mount/publication. Consequently, CE BSP queries are not
reachable in this profile. This is a measured negative result, not a passing
map-load/query test.

I added [`tools/test_hcu_mp_target_capacity.py`](../../tools/test_hcu_mp_target_capacity.py),
an isolated package-backed runner. It imports the pinned package list and
hashes from `tests/test_hcu_mp_capacity.py`, parses HP2 with the repository
HP2 reader, checks CTAG against the actual 2 MiB bound, and decodes/rebases
each CBSP with a 4 MiB bound. It reports exact decoded CBSP image plus
relocation-tail bytes. It also computes conservative per-map allocation
envelopes for the actual HMAP/CRNG/CBIX/CTAG-relocation sequence and known
scratch bounds. It does not touch production budgets or the existing collision
fixture.

## Per-map capacity envelope

All byte figures are bytes. `CBSP peak` is the largest decoded CBSP image plus
its streamed 12-byte relocation records, which share the final BSP cache
destination. Each row has a 2,097,152-byte tag limit, 4,194,304-byte BSP
limit, 1,048,576-byte owner limit, 524,288-byte scratch limit, and
786,432-byte claims allocation. The owner figure is the conservative maximum
over the production allocation order and possible 16-byte-aligned base
phases. Because every map rejects before source-hash verification, the
reached-path scratch bound is 98,352 bytes (98,304-byte HP2 workspace plus
at most 48 bytes of address-alignment padding). If a future profile passes
the CTAG gate and reaches hash verification, the source-buffer high-water
bound is 262,192 bytes.

| Map | CTAG image | Owner peak bound | Reached scratch peak bound | Largest CBSP image + relocation tail | Admission outcome |
|---|---:|---:|---:|---:|---|
| Beaver Creek | 4,319,568 | 87,048 | 98,352 | 730,164 | CTAG exceeds 2 MiB |
| Blood Gulch | 4,477,116 | 89,212 | 98,352 | 1,303,056 | CTAG exceeds 2 MiB |
| Boarding Action | 4,358,612 | 86,852 | 98,352 | 1,354,120 | CTAG exceeds 2 MiB |
| Carousel | 4,277,864 | 85,896 | 98,352 | 515,212 | CTAG exceeds 2 MiB |
| Chillout | 4,252,432 | 85,340 | 98,352 | 573,380 | CTAG exceeds 2 MiB |
| Damnation | 4,345,868 | 87,792 | 98,352 | 1,326,780 | CTAG exceeds 2 MiB |
| Hang 'Em High | 4,246,076 | 84,680 | 98,352 | 595,812 | CTAG exceeds 2 MiB |
| Longest | 4,263,624 | 85,048 | 98,352 | 377,352 | CTAG exceeds 2 MiB |
| Prisoner | 4,241,088 | 84,812 | 98,352 | 888,300 | CTAG exceeds 2 MiB |
| Putput | 4,250,464 | 84,460 | 98,352 | 1,643,008 | CTAG exceeds 2 MiB |
| Ratrace | 4,270,452 | 86,036 | 98,352 | 550,768 | CTAG exceeds 2 MiB |
| Sidewinder | 4,378,160 | 88,008 | 98,352 | 1,993,704 | CTAG exceeds 2 MiB |
| Wizard | 4,259,188 | 85,476 | 98,352 | 556,908 | CTAG exceeds 2 MiB |

The largest CTAG is Blood Gulch at 4,477,116 bytes. The largest streamed
CBSP image-plus-tail is Sidewinder at 1,993,704 bytes, which fits alone in
4 MiB. Its pair with the CTAG is 6,371,864 bytes, 80,408 bytes above the
entire 6 MiB `current_bsp` region, before allocator alignment or other
overhead. Thus merely moving the tag/BSP boundary cannot make Sidewinder fit
in that region as currently packaged. Other maps' pairs may be below 6 MiB,
but the fixed 2 MiB/4 MiB partition blocks every map at CTAG.

## Ownership and source evidence

- Parent binding places the configured tag span at the start of
  `current_bsp`, then binds BSP to the remainder;
  [`hcu_memory_bind.c`](../../src/stream/hcu_memory_bind.c#L41) therefore gives
  this profile exactly 2 MiB + 4 MiB. Claims are calculated from the combined
  tag/BSP address space. CE uses 32-bit claim words, so
  `ceil(6,291,456 / 32) * 4 = 786,432` bytes. See
  [`tag_validate.c`](../../submodules/halo-ce-universal/port/linux/game/tag_validate.c#L244).
- The parent partitions streaming into a 1 MiB map-owner and separate 512 KiB
  section-scratch arena at [`hcu_main.c`](../../src/stream/hcu_main.c#L387).
- Map preflight's simultaneous owner allocations are HMAP, CRNG, CBIX, then
  the CTAG relocation list. The first three are allocated at 64-byte alignment
  and relocations at 4-byte alignment. The runner computes a conservative
  bound over all possible 16-byte-aligned base phases. The maximum is 89,212
  bytes (Blood Gulch), well under 1 MiB. Mount retains CRNG, CBIX, and CTAG
  relocation rows; its peak also fits. Sources:
  [`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L497) and
  [`ctag_mount.c`](../../src/stream/ctag_mount.c#L396).
- SHA verification requests at most 262,144 bytes in scratch; HP2 decode
  reserves 65,536 bytes of history plus 16,384-byte input/output windows, or
  98,304 bytes. Those uses are sequential and release scratch after use. Both
  bounds fit within 512 KiB. Sources:
  [`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L34) and
  [`section.c`](../../submodules/halo-ps2/engine/src/world/section.c#L95).
- The CBSP visitor streams the decoded image into final BSP storage and puts
  relocation records in its destination tail. The BSP capacity check must
  therefore include the tail. See
  [`ps2_cache.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L573).

## Reproduction and evidence identity

From the repository root:

```sh
python3 tools/test_hcu_mp_target_capacity.py
```

It emits JSON to stdout. Run on 2026-10-22: all 13 package hashes matched the
fixture pins. Summary: `all_13_ctag_fit=false`,
`all_13_cbsp_image_plus_tail_fit=true`, `all_13_map_owner_fits=true`,
`all_13_streaming_scratch_fits=true` (including the full-path 262,192-byte
bound),
`all_13_load_and_query_reached=false`. Also passed:
`python3 -m py_compile tools/test_hcu_mp_target_capacity.py` and
`git diff --check -- tools/test_hcu_mp_target_capacity.py`.

Identity at run time:

- Parent HEAD: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`
- HCU HEAD: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`
- halo-ps2 HEAD: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`
- Runner SHA-256: `e44bb2b8da66ba7311ef45fe902594afc7899ef4d228a5bdd5b76a64ee272595`
- Package pins/source-map identities are imported from
  `tests/test_hcu_mp_capacity.py`; any changed package hash aborts rather than
  silently skipping that map.

## Limits and next valid test

This is not a native HCU map-service run, collision-query run, or PCSX2/EE
evidence. It parses/rebases production wire envelopes and derives allocation
bounds, but does not invoke the C map service or record runtime `arena.high`
values. The reached scratch and owner figures are source-derived high-water
bounds, not sampled runtime high-water readings. The existing
`tests/test_hcu_mp_capacity.py` intentionally uses
16 MiB/8 MiB tag/BSP arrays for its successful CE semantic/collision matrix;
that cannot be recast as target capacity evidence. Native ILP32 execution is
blocked by the current sandbox's SIGSYS policy, and the 2 MiB CTAG limit
makes a production-sized CE query unreachable before there is any reason to
run it.

The valid next runtime seam is a permitted native ILP32 or PCSX2 run with
exactly the production-bound tag/BSP/owner/scratch/claims stores. Record the
map-service rejection, owner and scratch high-water marks, rollback, and no
published CE pointers for each map. To exercise relocation/query, first
choose and prove a separately justified capacity profile; do not resize
production budgets or call an oversized host-buffer pass target-shaped.
Sidewinder requires a measured representation/ownership design because its
current CTAG+largest-CBSP floor alone exceeds 6 MiB.
