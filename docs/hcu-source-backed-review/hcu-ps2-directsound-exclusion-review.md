# M0/M1 DirectSound-root exclusion review

## Product boundary

The selected PS2 build has no DirectSound or SPU2 playback backend in M1. The
port explicitly sets `default_sound_preferences.platform` to `-1` under
`HALO_PS2` (`source/sound/sound_preferences.c`). In
`source/sound/sound_manager.c::sound_initialize`, CE sets `initialized` false,
then returns when the platform code is negative or outside `[0, 2)`, before it
selects `platform_definitions[]`, calls the backend `initialize`, or sets
`initialized` true. The public CE sound paths guard backend callback dispatch
with `sound_manager_globals.initialized` (including dispose, queue/update,
scene begin/end, flush and pause paths). The only non-null table entry is the
Xbox `platform_sound_dsound`; the second entry is null.

Therefore the following live rooted externals are link-reachable through the
compiled Xbox backend unit but are unreachable from the accepted PS2 runtime
configuration. This is an M1 exclusion, not a declaration that sound is
unimportant or permanently unsupported. M14 must add an SPU2 request/playback
backend and revisit these calls rather than enabling the Xbox backend.

## Exact reviewed symbol set

`DirectSoundCreate`, `DirectSoundDoWork`, `DirectSoundGetStreamVoiceStatus`,
`DirectSoundStopStream`, `DirectSoundUseFullHRTF`, `IDirectSoundBuffer_Play`,
`IDirectSoundBuffer_Release`, `IDirectSoundBuffer_SetBufferData`,
`IDirectSoundStream_SetConeAngles`, `IDirectSoundStream_SetConeOrientation`,
`IDirectSoundStream_SetConeOutsideVolume`, `IDirectSoundStream_SetFrequency`,
`IDirectSoundStream_SetI3DL2Source`, `IDirectSoundStream_SetMaxDistance`,
`IDirectSoundStream_SetMinDistance`, `IDirectSoundStream_SetMixBinVolumes`,
`IDirectSoundStream_SetMixBins`, `IDirectSoundStream_SetMode`,
`IDirectSoundStream_SetPosition`, `IDirectSoundStream_SetVelocity`,
`IDirectSoundStream_SetVolume`, `IDirectSound_CommitDeferredSettings`,
`IDirectSound_CreateSoundBuffer`, `IDirectSound_CreateSoundStream`,
`IDirectSound_DownloadEffectsImage`, `IDirectSound_GetCaps`,
`IDirectSound_GetSpeakerConfig`, `IDirectSound_Release`,
`IDirectSound_SetDistanceFactor`, `IDirectSound_SetI3DL2Listener`,
`IDirectSound_SetMixBinHeadroom`, `IDirectSound_SetOrientation`,
`IDirectSound_SetPosition`, `IDirectSound_SetRolloffFactor`,
`IDirectSound_SetVelocity`, `dsound_sdl_stream_set_stereo_position`,
`interrupt_result`, `sound_cache_sound_hardware_lock`,
`sound_cache_sound_hardware_unlock`, and `vsprintf`.

For the first 35 names, `dsound_sdl_stream_set_stereo_position`,
`interrupt_result`, and the two sound-cache hardware lock hooks, the current
ledger shows the sole rooted source candidate as
`source/sound/sound_dsound_xbox.c`; `vsprintf` also has only that rooted caller
in this closure (the DirectSound error-formatting path). Every entry is
dispositioned `excluded-proven` for this PS2 M1 configuration, owned by the
runtime platform-selection boundary. This does not approve generic use of
`vsprintf` or suppress future SPU2 owners.

## Evidence and regression

The source assertions and exact symbol/caller-source set are checked by
`test_ps2_sound_platform_disabled_before_directsound_dispatch` in
`tests/test_hcu_external_review.py`. The test rejects additions to this
exclusion set unless the source boundary is reviewed again. PCSX2 M1 startup
still has its separate sound-initialization marker, but no sound-output claim
is made. M14 acceptance must test an actual SPU2 request against the pinned
sound tags and playback mixer.
