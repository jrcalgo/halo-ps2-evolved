# M0/M1 Bink-video exclusion review

The PS2 port manifest excludes `source/bink/`; it does not exclude Halo's
gameplay, script, or in-engine cutscene systems. The five rooted Bink playback
symbols are called from CE game initialization/disposal, the main loop, input
device-change handling, and the solo-map load path. Their callers need a
well-defined “no Bink movie active” state, but not a decoder, video surface,
audio track, or return-to-menu movie lifecycle on this target.

The current generated PS2 bodies are `bink_playback_active() -> FALSE` and
empty `initialize`, `dispose`, `stop`, and `update`. In `source/main/main.c`
and `source/scenario/scenario.c`, the `active` result only gates Bink/movie
state (not local game simulation); false permits normal map/UI work. The source
implementation in `source/bink/bink_playback.c` documents the omitted behavior:
it opens Bink streams, allocates texture/video resources, and updates playback.
Those resources do not exist in the PS2 M1 target. This review is intentionally
limited to Bink playback and does not bless Bink allocation/status calls as
general-purpose no-ops if the feature is later enabled.

`bink_playback_active` is a `state-adapter` whose required value is false;
`bink_playback_initialize`, `bink_playback_dispose`, `bink_playback_stop`, and
`bink_playback_update` are `excluded-proven` because no Bink object can be
created through the PS2 closure. M2+ content tests must revisit this if a map
or UI attempts to launch Bink. M14 sound integration does not itself add Bink
movie audio.

`test_bink_playback_is_a_nonactive_m1_feature` locks the manifest exclusion,
generated behavior, rooted callers, and distinct classification. This is not
evidence that a campaign movie plays.
