# M0 source review: transport and packet-group bootstrap

## Scope and disposition

This review covers `transport_initialize`, `transport_dispose`, and `initialize_network_game_packets`. All three are unconditionally called from CE game lifecycle functions and remain pending. The platform exclusion of Xbox networking is not, by itself, evidence that every observable lifecycle effect is safe to omit.

## Source trace

`source/game/game.c:317-319` calls `transport_initialize`, `telnet_console_initialize`, then `initialize_network_game_packets` from game initialization. `game_dispose` later calls `transport_dispose` at `source/game/game.c:811`.

The native `transport_initialize` implementation in `source/bungie_net/network/transport_endpoint_set_winsock.c:252-326` is Xbox-specific: it configures XNet pools, checks Ethernet link status, optionally reads the bypass-security file, initializes XNet and Winsock, polls for a title address with a deadline, creates a nonce, and marks transport initialized. This is inappropriate for a local PS2 boot, and the no-op avoids an Xbox networking wait. However, this interface remains the lifecycle owner if a PS2 network profile is later introduced, and the error result is currently ignored by `game_initialize`; the audit must ensure generated/ported return semantics cannot influence callers.

`transport_dispose` at `transport_endpoint_set_winsock.c:361-378` conditionally runs Winsock/XNet cleanup and returns a distinct not-initialized status otherwise. The PS2 local profile may intentionally never acquire transport resources, but repeated init/dispose and future explicit transport ownership must be tested before this omission is approved.

`initialize_network_game_packets` is not an Xbox transport initializer. `source/networking/network_messages.c:603-610` initializes a `data_packet_group` using CE's declared network packet metadata. It may be inert when no network session runs, but it is invoked at every game initialization and the table is consumed by network encode/decode functions. The selected local runtime needs a source-backed check that no local path reads an uninitialized group and that repeated game lifecycle is safe.

## M0 disposition requirements

Keep all three rows pending. Add a local lifecycle fixture that runs game init/dispose twice, proves no Xbox transport calls or link polling occur, and verifies the packet-group table is either deliberately initialized or proven unreachable from every local menu/campaign/game path. A future PS2 network mode must add real transport and packet-table ownership and cannot treat the current omission as a reusable implementation.
