# M2 Step 7 — multiplayer bot fog attenuation remains blocked

Date: 2026-10-22. Source tracing found no defensible behavior oracle for the
CE `scenario_fog_at_point()` AI attenuation query. No test or production change
was added: asserting the current constant zero would only encode the known
stub, not establish retail parity.

## Source evidence

CE's implementation is exactly an unconditional `return 0.0f` at
[`scenario.c:803-809`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L803).
Halo-64's implementation is also an unconditional zero at
[`scenario.c:780-786`](../../submodules/halo-64/source/scenario/scenario.c#L780),
so it is not an independent behavior reference. The queried inputs
(`viewer_location`, `viewer_point`, `point`) are unused in both implementations.

CE does establish why the missing behavior matters to bots. In AI line-of-sight,
values above `0.8` take the collision-distance branch and values above `0.6`
take the occlusion branch ([`ai.c:2363-2372`](../../submodules/halo-ce-universal/source/ai/ai.c#L2363)). In actor perception, values above `0.8` force a reduced perception factor, while values above `0.2` scale it by `(0.8 - fog) * factor * 1.6666666` ([`actor_perception.c:2484-2503`](../../submodules/halo-ce-universal/source/ai/actor_perception.c#L2484)). Those thresholds reveal downstream use, not how CE integrates fog across a viewer-to-target path.

The 13-map host fixture already has raw-source-backed fog region inputs: its
plane→region→fog-tag cases are Beaver Creek (103), Chill Out (107), and
Damnation (108); ten other stock MP maps have representative cluster `NONE`
references. The retained all-map consumer evidence is
[`m2-step7-mp-fog-consumer-13-map-host-2026-10-22.md`](m2-step7-mp-fog-consumer-13-map-host-2026-10-22.md).
Those cases validate region/plane selection and weather fallback, but do not
provide independent expected fog-attenuation values. Fog density/distance/depth
tag fields likewise do not specify the missing path integration or boundary
behavior. A package-backed test could call this API without constructing an
actor, but the only output currently supported by source is the stub's zero;
that is not a useful parity assertion and must not be reported as coverage.

This matches the explicit project constraint in
[`plans/7.hcu-remake-m2-m4.md:844-848`](../../plans/7.hcu-remake-m2-m4.md#L844):
do not infer the formula; bots are in scope, and the unknown behavior is a
Step 7 gameplay parity blocker. The existing REA feasibility report found the
retail XBE code bytes but could not identify an authoritative fog routine or
attribute an unnamed stripped procedure to this call
([`m2-step7-retail-xbe-fog-rea-feasibility-2026-10-22.md`](m2-step7-retail-xbe-fog-rea-feasibility-2026-10-22.md)).

## Required next evidence; no acceptance closure

Before implementation or an expected-value test, obtain one of:

1. A defensibly identified retail CE function body/disassembly that implements
   `scenario_fog_at_point()`; or
2. Controlled retail CE outputs for in-scope multiplayer maps spanning no-fog,
   direct-fog and high-bit plane references; points on both plane sides;
   viewer/target paths crossing fog-region or cluster boundaries; and varied
   fog density/distance settings.

Then implement the CE-parity function and test its returned values plus the AI
caller thresholds using source-bound cases. Until that oracle exists, no
bot-fog attenuation test passes, no known-zero diagnostic is counted as a
subcheck, and this work closes no Step 7 acceptance criterion.

## Source identities

- CE `scenario.c` SHA-256: `22aef8353c6f4a1067d0e51e78565783d5f7c911e3b4d73f40ad49269a2546c0`.
- CE `ai.c` SHA-256: `9049813558d719d56017a7db70f7a4bf7561fabba89674ecdc42d7b3ad5d0e3c`.
- CE `actor_perception.c` SHA-256: `09987c7b42e98f137d317fad9d9e8660708b9f3e06d5ce8da41cfb2ed28c70e3`.
- Halo-64 `scenario.c` SHA-256: `0368b3bb31f8008f1ff2120f58c3d0c91e4c003a1009974d3f1cbd67810e1684`.
- Parent / HCU / halo-ps2 pins: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` / `6933490b2d16bb1c637295b6a0f3880ba23a7d56` / `71183bb0a9adc586cd267b2780c82bbc12cfd95b`.
