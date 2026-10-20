# M0 rooted `XPhysicalFree` ownership review

The rooted symbol has exactly one caller, `game_state_free_buffer` in
`source/saved games/game_state_xbox.c`. Its matching allocator,
`game_state_allocate_buffer`, is the only CE routine that establishes this
buffer lifetime. Under `HALO_PS2`, that allocator returns the pointer from
`physical_memory_get_game_state_base_address()` and deliberately bypasses
the Xbox virtual-address equality and write-combine protection operations.
The game-state span is parent-bound storage, not an `XPhysicalAlloc` result.

Therefore `XPhysicalFree` must not call the C heap or unbind the shared memory
span. The CE free routine clears `buffer_allocated`; actual span lifetime is
owned by the PS2 provider and parent arena binding (`hcu_memory_bind_parent_v2`),
which releases all configured spans together through `physical_memory_free()`.
The current generated no-op is consistent with that ownership contract for the
sole rooted call domain. It is not a general implementation of Xbox physical
allocation APIs and must be revisited if another caller is added.

This is a state-adapter disposition, not proof that the parent arena is
physically placed correctly or that repeated map/save-buffer lifetimes have
been exercised on hardware. The M1 physical-memory and integration gates still
own those proofs. The focused source/contract regression is
`test_xphysicalfree_does_not_release_parent_owned_game_state_arena`.
