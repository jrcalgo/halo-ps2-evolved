# M0 PS2 CRT ASCII case-insensitive comparison review

The rooted `_stricmp` and `_strnicmp` symbols are owned by
`port/ps2/src/ps2_crt.c`, not by Newlib. The implementation folds only ASCII
`A`–`Z`, converts input bytes to unsigned before comparison, and leaves all
other byte values unchanged. The CE callers use them for HaloScript names and
enumerations, plus cache tag-name matching; those identifiers are case-
insensitive ASCII tokens in the supported tag/script grammar. This is not a
locale-aware Unicode case-folding implementation. Unicode case mapping remains
the separate pending `tolower`/`towlower` review.

The source-backed M0 disposition is `implemented` by the PS2 CRT for this
ASCII identifier contract. `test_hcu_ps2_crt_ascii_compare` compiles and runs
the actual provider source on the host for mixed-case equality, prefix-length
behavior, unequal endings, and high-byte stability. The R5900 closure separately
confirms the exact provider source is selected. CE-wide script/parser parity
fixtures remain later product tests.

The similarly named `qsort` is intentionally not bundled into this approval.
Although the pinned Newlib implementation is linked, CE call sites include
ordering-sensitive gameplay/aim-assist and actor processing. Equal-key order
may differ from the Xbox CRT; it needs fixture comparison before a parity
disposition.
