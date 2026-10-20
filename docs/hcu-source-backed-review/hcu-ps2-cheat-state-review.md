# M0 CE cheat gameplay-state ownership review

The rooted `cheat` symbol is a CE gameplay-state datum, not a callable cheat
feature that can be excluded. `source/game/cheats.h` defines
`struct cheat_globals` and declares the global. Although no selected source
translation unit defines the original retail global, the PS2 closure generator
emits `struct cheat_globals cheat;` in the target-owned platform storage; its
static storage begins zeroed at startup.

The state is behaviorally live: rooted CE units/damage/weapon/AI code read
fields such as `jetpack`, `infinite_ammo`, `bottomless_clip`, `deathless_player`,
and `medusa`; `cheats_network_client_enforce` compares and clears the complete
datum; and HaloScript external definitions point directly at its fields so
scripts can mutate them. `cheats_initialize()` clears only cheat-controller
strings, while new-map initialization loads cheat strings; the gameplay datum
must therefore retain its normal global lifetime and must not be cleared on
each map transition.

Disposition: `implemented`, owned by HCU PS2 CE global-state storage. The
generated declaration provides writable CE storage, not a no-op and not a
policy disabling cheats. The PS2-incompatible cheat-controller text file
loading path is a separate file-service concern; this row covers only the
global state datum. `test_hcu_cheat_state_is_owned_writable_ce_gameplay_state`
locks the header fields, live consumers, HS references, and emitted storage.
