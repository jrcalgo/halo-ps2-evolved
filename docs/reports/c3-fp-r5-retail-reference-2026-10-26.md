# C3 first-person retail model identity and reference check (R5) — 2026-10-26

## Target and evidence boundary

The supplied retail image is `/home/ai/Documents/Halo/Halo - Combat Evolved.xiso.iso`; the conversational path `/home/ai/Documents/Halo/Halo ISO` does not exist. The image is 3,625,713,664 bytes and SHA-256 `43ec0813edadd592b7b489a930f108d289db9313ac337611110ffca8be0a7258`. Its Xbox XDVDFS volume descriptor begins at `0x10000` with `MICROSOFT*XBOX*MEDIA`. REA 6.5.0 does not support direct XISO inventory/open; 7-Zip recognizes only the 36 KiB ISO9660 shim and reports the Xbox payload as trailing data. I did not treat that listing as a retail file inventory. The prior same-image extraction review records a fresh XDVDFS `default.xbe` extraction and a direct REA rejection of the resulting XBE as an unsupported binary format; see [`m2-step7-retail-xbe-fog-rea-feasibility-2026-10-22.md`](m2-step7-retail-xbe-fog-rea-feasibility-2026-10-22.md). It provides no first-person semantics, so the asset/tag and rendering contracts here come from the map bytes and CE source.

The matching decompressed Blood Gulch map is `build/retail-maps/decompressed/bloodgulch.map`, SHA-256 `9eb0374cbe4571af640ae8b0e0ebf6119543cdbbece44d49543b4748c4cf0dc1` (the exact digest is also the profile package's `source_maps.bloodgulch` digest). This binds the map/tag observations below to the same XISO provenance recorded for the supplied image. The map was read with the repository's Halo tag index/map readers. The C3 HCP package was parsed and checked against its JSON manifest digest. Raw MODL chunks and this report are local analysis outputs; no retail image bytes were changed.

## Retail weapon references and packaged identities

In the retail map's tag index, `weapons\\assault rifle\\assault rifle` is WEAP tag ID `3798008045`. Its first-person model reference at the verified Halo CE field offset `0x45c` resolves to group `mode`, tag ID `3800629525`, path `weapons\\assault rifle\\fp\\fp`. Its first-person animation reference at `0x46c` resolves to group `antr`, tag ID `3800760599`, path `weapons\\assault rifle\\fp\\fp`.

The selected Blood Gulch package is HCP SHA-256 `23d41d49c5e755da415f068e6420745eca8d51a71474d40c7335cca834273aac`; its JSON manifest SHA-256 is `6ff0602c42cd538494780708a295b8e2bcae49df5947049480526834ae53954c`. The manifest preserves this source model identity and remaps its runtime model datum to `1142` (MODL chunk `637`, 5 nodes, 1,964 triangles at LOD0, radius `0.14758994`; chunk SHA-256 `7a6dce0875be6f16170ea8b03ebeade3d83a0e7aabfc78496ed19fd8d2584f4d`). The separate world-model binding is datum `1141`, chunk `625`, path `weapons\\assault rifle\\assault rifle`. The generated table documents that its third field is the CE runtime model index published in the pose snapshot.

The observed runtime trace reports gun model resource datum `1161`, 4 nodes (`launcher.log`, first pose sample around emulator time 103.3085; retained run `run-20261026T072022Z-e9d411d35bcd`). In the same exact package, datum `1161` is the **plasma pistol first-person model**, path `weapons\\plasma pistol\\fp\\fp`, source tag ID `3868001561`, MODL chunk `631`, 4 nodes, and radius `0.06570866` (chunk SHA-256 `6131e5e63ef1d758b94a4b64fb9d848c7947e7ffe5990528599021e8b1b0042e`). The runtime datum therefore identifies the actual packaged asset; it is not a generic rifle or the rifle world model.

The hand resource is separately reported as datum `1104`, 37 nodes, which the table maps to `characters\\cyborg\\fp\\fp` (chunk `674`). That identity agrees with the selected cyborg hands model.

## Rendering contract and limits

CE's `first_person_weapon_draw` obtains `weapon_definition->weapon.interface_definition.first_person_model.index`, checks the first-person remap table, remaps graph matrices for that model, and passes the model index to `render_model` (`submodules/halo-ce-universal/source/interface/first_person_weapons.c:553-581`). This supports selecting the weapon's authored FP model reference, distinct from its world model. The retail assault-rifle definition's expected FP model is therefore index `1142` after this package's remapping.

The earlier capture proved the gun model actually submitted was datum `1161` (the plasma-pistol FP asset), but its trace did not record the equipped weapon's WEAP tag or its `first_person_model.index`. At that point the screenshot's purple/open-ring appearance alone was insufficient to determine whether this was the expected plasma-pistol selection or a mismatch. The tick-300 identity follow-up below resolves that uncertainty and confirms the selection is consistent.

The initial I1 text and the inline comment in `build/c3/first-person-fix/i1/extract_assets.py` label MODL chunk `631` / datum `1161` as the assault-rifle world asset. The exact manifest and generated table show that label is wrong; the correct rifle world asset is chunk `625` / datum `1141`, and the rifle FP asset is chunk `637` / datum `1142`. The I1 report has since been corrected, but its retained geometry fixture still reads chunk `631`; revisit any rifle geometry or projection conclusions against the correct payload. The previous XISO direct-REA unsupported result remains a tool boundary; the exact retail tag field was still read from the map whose hash is bound above.

## First-person projection notes

The retained CE source audit in R1 found Xbox's model-render wrapper only changes viewmodel projection for an explicit `display.viewmodel_fov` override or widened display FOV; its stock/default path leaves the camera projection unchanged (`port/linux/game/view_fov.c:196-234`, CE model wrapper `rasterizer_xbox_models.c:615-654`). This gives no source support for changing the FOV to compensate for a model-identity uncertainty. The runtime identity follow-up below establishes the live equipped WEAP tag and selected model for this run. We still lack a retail Xbox frame capture with which to prescribe expected pixel framing.

## Runtime weapon identity follow-up (2026-10-26)

A fresh, isolated one-view Blood Gulch run captured the actual equipped-weapon selection at guest tick 300. The frozen diagnostic ELF SHA-256 was `8ca2d1501cde09e8c884225eecd23fe142075b8b95dafb6d30a3cf830a7e741c`; its manifest validated 47 archived source pins. The log row is:

```
HALO_PS2_FPPOSE selection target=300 game_time=300 unit=-492634060 weapon=-492437449 definition=1934:weaponsplasma pistolplasma pistol fp_model=1161:weaponsplasma pistolfpfp fp_nodes=4 graph=23:weaponsplasma pistolfpfp
```

This resolves the uncertainty above: the live WEAP definition is the plasma pistol, and its selected FP model is datum `1161`, the plasma-pistol model already identified from the package. This is a consistent selection, not evidence of a wrong weapon-model lookup. The screenshot at tick 300 is `build/c3/first-person-fix/runtime/quiet-baseline-v1-weapon-identity/run-20261026T153636Z-2476c7e986a5/tick300.png`, SHA-256 `0b61ebb9b3b4e78da2ee68d1575a69f0d68f1ddf480ac9475eeb4c73a3d9ef50`.

The earlier I1 labeling error concerned asset interpretation: MODL chunk `631` / datum `1161` is the plasma-pistol FP asset, not the assault-rifle world asset. The correct rifle world asset remains chunk `625` / datum `1141`, and its FP asset is chunk `637` / datum `1142`. That correction does not imply a runtime selection defect. The tick-300 sample had `state=0`, animation `2:50`, overlay `13`, and `until_pose=361`; it identifies the equipped asset but does not validate sniper zoom or resolve the separate world-weapon visibility issue.
