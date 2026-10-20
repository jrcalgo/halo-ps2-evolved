# M0 Xbox saved-game API caller review

Eight rooted XDK calls participate in Halo CE saved-game metadata/checksum
flows: `XCalculateSignatureBegin/Update/End`, `XCreateSaveGame`,
`XDeleteSaveGame`, and `XFindFirstSaveGame/Next/Close`. Their callers are in
`source/saved games/saved_game_files.c` and include checksum generation,
unique-name checks, metadata creation/rename/deletion, and enumeration of
saved profiles. These are not dead imports merely because the PS2 target does
not have an Xbox memory unit.

The current generated provider has failure-shaped behavior for some calls
(null first-enumeration handle; zero for create/delete) but success-shaped
zeros for signature update/end and close. CE's call sites interpret those
values differently: `XCreateSaveGame` zero may mean either “name absent” or a
failed metadata operation; `XDeleteSaveGame` zero is treated as success in
cleanup paths; checksum update/end zero is treated as success despite no bytes
being processed. The full cross-call flow therefore cannot be approved from
individual stub return values.

M1 explicitly leaves persistent saves and Xbox `z:` paths unavailable, but
that scope statement is not yet a proof that every UI/profile caller handles
the unavailable service without data loss or success-shaped state. Keep all
eight calls pending until there is a PS2-owned persistence design or a tested
no-device profile contract covering lookup, create, delete, checksum, and
enumeration failure. This report is a source/caller risk review, not approval
of saves or a decision to implement them in M1.
