# BSP schema-unrepresented range synthetic retention checks — 2026-10-22

`tests/test_step7_unmapped_bsp_range_retention.py` now exercises every one of
the 54 compiler-inventory ranges classified `unclassified`. For each row it
uses the inventory's exact definition size, range offset, and byte extent,
places two distinct arbitrary payload patterns at that exact location in a
synthetic full-size record, runs the schema walker with a uniquely named opaque
scalar placeholder (definition ID, offset, and byte extent) at the same range,
and checks the complete record byte-for-byte. Nonzero guard context around each
range detects widened writes and off-by-one corruption. The only allowed
normalization is the synthetic root pointer.

The test passed: one host Python test and 54 range subcases. It also checks the
inventory's pinned schema ELF SHA-256 (`56cd9fb82c4729b6870972c8d8be36fab78916ff1fa2026c5e22bf7cfe263037`), confirms each range fits its compiled definition extent, and asserts all 54 inventory rows were traversed. Test source SHA-256:
`f52b6adb1c0f43d1b09a3cef87d7fd1b07a75663dca6e2f6d0378e367e40e80c`.

This is synthetic byte-retention evidence only. Scalar placeholders do not
recover retail member declarations, validate real nested data-block pointer
domains, prove that the production schema walker visits each nested record in
context, identify consumer behavior, or justify normalization/removal. All 54
semantic dispositions remain open. No range shape prevented an exact-offset
synthetic retention fixture.
