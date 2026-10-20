# M0 source review: co-op spectator camera and HUD boundary

## Current local-profile disposition

`coop_spectating` is a `state-adapter`: the PS2 local-session owner (`port/ps2/game/ps2_coop.c`) returns false from `network_coop_active`, and the CE implementation of the predicate simply returns that state. `coop_spectate_unit` and `coop_spectate_camera` are `excluded-proven` for the current local profile because their only call chain is gated by this false predicate. All three dispositions must be revisited at M5 if network co-op is enabled; the exclusions do not claim CE co-op parity.

## CE call graph and behavior

In `source/camera/director.c:719-736`, a dead or waiting local player asks `coop_spectating()` first; only when true does it call `coop_spectate_unit()`. The returned non-`NONE` unit is passed into `dead_camera_new`, and `coop_spectate_camera()` is called only when that watched target exists. The normal local false path uses the stock dead camera, which watches the local player's body.

The referenced Linux CE port implementation (`port/linux/game/coop_spectate.c:105-163`) returns `network_coop_active()` and otherwise retains a per-local-player watched teammate, switches target on A/jump, and handles “no teammate alive” state. Its camera routine (`:185-221`) mutates dead-camera yaw, pitch, follow distance, and FOV according to teammate/vehicle/script state. These are substantial behaviors and must not be silently dropped once co-op is in scope.

In `source/interface/hud.c:1421-1422`, co-op spectator text is drawn only when `coop_spectating()` and the player has no unit. The PS2 false adapter selects ordinary local HUD presentation; it does not implement co-op hints. `coop_skip_vote_draw` is a separate external and remains independently reviewed.

## Regression guard and scope

The test asserts the source predicate delegates to the PS2 false local-session owner, the camera and HUD callers remain gated, and the ledger dispositions carry an explicit M5 revisit. It is a current-profile reachability proof, not a multiplayer behavior test. If the accepted product profile starts a network session, change `network_coop_active` and restore the Linux CE spectator semantics before accepting co-op play.
