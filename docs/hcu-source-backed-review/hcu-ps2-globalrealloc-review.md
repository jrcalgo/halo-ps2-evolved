# M0 rooted `GlobalReAlloc` extent/lifetime review

The exact CE caller is `system_realloc` in `source/cseries/cseries_windows.c`.
The rooted use comes from `debug_realloc` in `source/cseries/debug_memory.c`,
which passes a `debug_memory_header` pointer and a new total allocation size
(header + requested user bytes + trailing signature). The old user size is
tracked in that header, but that bound is not passed to the PS2 allocator.

`port/ps2/src/ps2_memory.c::GlobalReAlloc` allocates a new block and copies
exactly the new requested `size` from `pointer`. On growth, the new size may
exceed the prior allocation extent, so this reads past the old block. The
current arena is a bump allocator: `__wrap_free` deliberately does not reclaim
blocks within the arena, so each reallocation also retains the old block and
can consume the bounded dynamic arena over repeated growth.

Keep the symbol pending. Approval requires a safe old-size source/allocator
metadata, copy-min(old,new) behavior with CE realloc failure semantics, and an
exhaustion test that checks no out-of-bounds reads and measures repeated
growth/shrink retention. It also needs a plan for debug-memory's failure path,
which removes/marks the old header before requesting reallocation. A passing
link or a one-shot realloc test is insufficient. The current risk is locked by
`test_globalrealloc_copy_extent_and_bump_arena_retention_remain_pending`.
