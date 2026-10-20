# M0 rooted CE sound-cache review

The eight rooted sound-cache symbols are part of CE's sound decision and
resource-lifetime layer, not merely the Xbox DirectSound backend that M1
excludes. `sound_cache_new` creates the cache datum/LRU and binds the CE sound
region; `sound_cache_open` validates per-map cache state; `sound_cache_close`
retires map sound/reference state before tag unload; `sound_cache_delete`
destroys the backing structures. `sound_cache_idle` advances cache work,
`sound_cache_flush` removes only unreferenced entries, and
`sound_cache_sound_finished` drops software reference counts.

Most importantly, `_sound_cache_sound_request` returns a boolean used by CE to
decide whether a permutation is resident/usable. It can initiate or block on
loads and update software/hardware ownership counts. In `sound_manager.c`, a
false result can force a channel to state zero; sound start/stop/queue logic
also releases references through `sound_cache_sound_finished`. The generated
PS2 stub always returns false and the other seven bodies are empty. This can
change CE sound-event state and cache lifecycle even when audio playback is a
separate platform service.

Keep all eight symbols pending for the M0 semantic owner review. M14's planned
SPU2 playback does not itself prove the CE sound-selection/cache interface is
correct. Closure needs a CE-to-PS2 audio request contract, ownership and
reference-count tests, map load/unload tests, and scheduling/high-water data for
the PS2 audio region. The Xbox DirectSound exclusions remain distinct and do
not authorize dropping these cache decisions. The exact source/provider
boundary is locked by
`test_ce_sound_cache_roots_carry_runtime_state_and_remain_pending`.
