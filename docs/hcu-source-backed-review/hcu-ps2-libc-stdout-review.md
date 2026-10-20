# M0 Newlib standard-output review

This review covers only the rooted `printf` and `puts` interfaces. Both resolve
to the exact pinned PS2 EE Newlib archive objects `libc.a(libc_a-printf.o)` and
`libc.a(libc_a-puts.o)` in `build/hcu-ps2-closure/all/halo-local.map`. The Newlib
4.6.0 source pin is `8881dc4b138f0561596980ac9a481c7e638aebd0` in
[`toolchain-sources.json`](../config/toolchain-sources.json#L19).

Newlib `printf` writes through `_stdout_r()` and `_vfprintf_r()`; `puts` writes
the string and newline to the same standard-output stream. PS2SDK EE libcglue
initializes stdout as descriptor 1 backed by `tty0:` (`ee/libcglue/src/fdman.c`
and `ee/libcglue/src/ps2sdkapi.c::__libcglue_init_stdio`) and routes writes
through the initialized file-operation table (`ee/libcglue/src/glue.c::_write`).
This is the console diagnostic path, not a filesystem write service. The current
guest log records multiple CE `HALO_PS2_LOCAL` markers, including
`game-initialize-done` and `m1-ui-map-request`, confirming that actual `printf`
output reaches the emulator console for the present image.

The disposition is limited to standard-output formatting and writing. It does
not approve `fprintf`/`fopen`/`fclose` or other file-backed stdio interfaces,
which remain pending and require their own source/call-path/device review. The
exact archive-member/source and guest-marker checks are in
`test_pinned_newlib_stdout_helpers_use_ps2_tty`.
