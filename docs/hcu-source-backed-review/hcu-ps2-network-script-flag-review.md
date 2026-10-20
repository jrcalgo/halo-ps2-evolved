# M0 `allow_out_of_sync` local-mode state review

`allow_out_of_sync` is declared by the CE HaloScript external-global table and
defined in `source/networking/network_client_manager.c` with the explicit
initializer `FALSE`. The sole rooted relocation in the selected closure is
the `allow_out_of_sync_definition` entry in
`source/hs/hs_globals_external.c`; no local-mode gameplay or map-loading source
reads it. The PS2 product profile excludes the network client manager, so the
generated `boolean allow_out_of_sync;` storage is the correct zero/false local
state for this datum. It must not be interpreted as enabling remote tolerance
or as a substitute network implementation.

Disposition: `state-adapter`, owned by HCU PS2 CE global storage, initialized
false. This is narrower than a blanket network-feature exclusion: the global
remains available to CE's script symbol table with its CE default, while its
network consumer is absent from local mode. M22/network work must revisit it.

`test_allow_out_of_sync_retains_ce_false_local_default` locks the source
initializer, sole rooted relocation, generated PS2 storage, and ledger row.
