#include "stream/hcu_map_catalog.h"

#include "stream/cbsp_catalog.h"

#include <string.h>

/* Generated from the pinned stock-cache audits:
 * docs/reports/retail-ctag-compaction-2fba411b-v2.json (schema ELF
 * 2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa),
 * docs/reports/retail-bsp-capacity-2fba411b.json, and
 * docs/reports/retail-cbsp-catalog-package-audit-current.json. Runtime
 * still verifies the HMAP/CBIX bytes and opened source file hash. */
static const hcu_map_bsp_entry s_bsps[] = {
	{ 2048u, 6230016u, "B000", "levels\\a10\\a10a" },
	{ 6232064u, 8255488u, "B001", "levels\\a10\\a10b" },
	{ 14487552u, 6057984u, "B002", "levels\\a10\\a10c" },
	{ 20545536u, 5472256u, "B003", "levels\\a10\\a10d" },
	{ 26017792u, 7753728u, "B004", "levels\\a10\\a10e" },
	{ 33771520u, 8531968u, "B005", "levels\\a10\\a10f" },
	{ 42303488u, 8568832u, "B006", "levels\\a10\\a10g" },
	{ 50872320u, 1529856u, "B007", "levels\\a10\\a10_space" },
	{ 52402176u, 2760704u, "B008", "levels\\a10\\x10hangar" },
	{ 2048u, 6199296u, "B000", "levels\\a30\\a30_a" },
	{ 6201344u, 7174144u, "B001", "levels\\a30\\a30_b" },
	{ 2048u, 3835904u, "B000", "levels\\a50\\a50_exterior" },
	{ 3837952u, 6983680u, "B001", "levels\\a50\\a50_muster" },
	{ 10821632u, 7157760u, "B002", "levels\\a50\\a50_hangar" },
	{ 17979392u, 7159808u, "B003", "levels\\a50\\a50_control" },
	{ 2048u, 6608896u, "B000", "levels\\b30\\b30a" },
	{ 6610944u, 4022272u, "B001", "levels\\b30\\b30b" },
	{ 2048u, 5515264u, "B000", "levels\\b40\\b40_a" },
	{ 5517312u, 5838848u, "B001", "levels\\b40\\b40_b" },
	{ 11356160u, 3862528u, "B002", "levels\\b40\\b40_c" },
	{ 15218688u, 2209792u, "B003", "levels\\b40\\b40_a1" },
	{ 17428480u, 3956736u, "B004", "levels\\b40\\b40_a2" },
	{ 21385216u, 1396736u, "B005", "levels\\b40\\b40_a3" },
	{ 22781952u, 1294336u, "B006", "levels\\b40\\b40_b1" },
	{ 24076288u, 2551808u, "B007", "levels\\b40\\b40_b2" },
	{ 26628096u, 3930112u, "B008", "levels\\b40\\b40_b3" },
	{ 30558208u, 3074048u, "B009", "levels\\b40\\b40_b4" },
	{ 33632256u, 2992128u, "B010", "levels\\b40\\b40_b5" },
	{ 36624384u, 4048896u, "B011", "levels\\b40\\b40_c1" },
	{ 40673280u, 1288192u, "B012", "levels\\b40\\b40_c2" },
	{ 2048u, 724992u, "B000", "levels\\test\\beavercreek\\beavercreek" },
	{ 2048u, 1296384u, "B000", "levels\\test\\bloodgulch\\bloodgulch" },
	{ 2048u, 1343488u, "B000", "levels\\test\\boardingaction\\boardingaction" },
	{ 2048u, 5402624u, "B000", "levels\\c10\\c10_exteriora" },
	{ 5404672u, 4972544u, "B001", "levels\\c10\\c10_interiora" },
	{ 10377216u, 5443584u, "B002", "levels\\c10\\c10_interiorb" },
	{ 15820800u, 4757504u, "B003", "levels\\c10\\c10_interiorc" },
	{ 20578304u, 5988352u, "B004", "levels\\c10\\c10_interiord" },
	{ 26566656u, 4704256u, "B005", "levels\\c10\\c10_exteriorb" },
	{ 2048u, 7127040u, "B000", "levels\\c20\\c20_1" },
	{ 7129088u, 8574976u, "B001", "levels\\c20\\c20_2" },
	{ 15704064u, 9039872u, "B002", "levels\\c20\\c20_3" },
	{ 24743936u, 6864896u, "B003", "levels\\c20\\c20_4" },
	{ 2048u, 5515264u, "B000", "levels\\c40\\c40_a" },
	{ 5517312u, 6318080u, "B001", "levels\\c40\\c40_b" },
	{ 11835392u, 3862528u, "B002", "levels\\c40\\c40_c" },
	{ 15697920u, 2023424u, "B003", "levels\\c40\\c40_a1" },
	{ 17721344u, 3618816u, "B004", "levels\\c40\\c40_a2" },
	{ 21340160u, 1400832u, "B005", "levels\\c40\\c40_a3" },
	{ 22740992u, 1413120u, "B006", "levels\\c40\\c40_b1" },
	{ 24154112u, 2779136u, "B007", "levels\\c40\\c40_b2" },
	{ 26933248u, 3930112u, "B008", "levels\\c40\\c40_b3" },
	{ 30863360u, 3074048u, "B009", "levels\\c40\\c40_b4" },
	{ 33937408u, 2992128u, "B010", "levels\\c40\\c40_b5" },
	{ 36929536u, 4048896u, "B011", "levels\\c40\\c40_c1" },
	{ 40978432u, 1404928u, "B012", "levels\\c40\\c40_c2" },
	{ 2048u, 507904u, "B000", "levels\\test\\carousel\\carousel" },
	{ 2048u, 567296u, "B000", "levels\\test\\chillout\\chillout" },
	{ 2048u, 5408768u, "B000", "levels\\d20\\d20_start" },
	{ 5410816u, 5093376u, "B001", "levels\\d20\\d20_exterior" },
	{ 10504192u, 8396800u, "B002", "levels\\d20\\d20_muster" },
	{ 18900992u, 8517632u, "B003", "levels\\d20\\d20_hangar" },
	{ 27418624u, 3807232u, "B004", "levels\\d20\\d20_control" },
	{ 2048u, 4898816u, "B000", "levels\\d40\\d40a" },
	{ 4900864u, 7907328u, "B001", "levels\\d40\\d40b" },
	{ 12808192u, 7804928u, "B002", "levels\\d40\\d40c" },
	{ 20613120u, 5806080u, "B003", "levels\\d40\\d40d" },
	{ 26419200u, 7223296u, "B004", "levels\\d40\\d40e" },
	{ 33642496u, 6758400u, "B005", "levels\\d40\\d40f" },
	{ 40400896u, 3485696u, "B006", "levels\\d40\\d40g" },
	{ 43886592u, 7331840u, "B007", "levels\\d40\\d40h" },
	{ 51218432u, 2469888u, "B008", "levels\\d40\\d40_terrain" },
	{ 53688320u, 8192u, "B009", "levels\\d40\\d40_space" },
	{ 2048u, 1320960u, "B000", "levels\\test\\damnation\\damnation" },
	{ 2048u, 589824u, "B000", "levels\\test\\hangemhigh\\hangemhigh" },
	{ 2048u, 374784u, "B000", "levels\\test\\longest\\longest" },
	{ 2048u, 884736u, "B000", "levels\\test\\prisoner\\prisoner" },
	{ 2048u, 1638400u, "B000", "levels\\test\\putput\\putput" },
	{ 2048u, 544768u, "B000", "levels\\test\\ratrace\\ratrace" },
	{ 2048u, 1984512u, "B000", "levels\\test\\sidewinder\\sidewinder" },
	{ 2048u, 2048u, "B000", "levels\\ui\\ui" },
	{ 2048u, 552960u, "B000", "levels\\test\\wizard\\wizard" },
};

static const hcu_map_catalog_entry s_maps[] = {
	{
		.identity = { "a10", 274734080u, 260575744u, 14158000u, { 0x1c, 0xe3, 0x39, 0x54, 0xaa, 0x12, 0xa2, 0xe0, 0xc2, 0x1a, 0x07, 0xe2, 0x0d, 0x0d, 0xc6, 0x52, 0xb1, 0xb4, 0x03, 0xe4, 0xef, 0x1b, 0x98, 0xc0, 0x67, 0x43, 0x9a, 0x15, 0x54, 0x5d, 0x99, 0x71 } },
		.scenario_name = "levels\\a10\\a10",
		.hp2_path = "maps/a10.hp2",
		.map_path = "maps/a10.map",
		.bsp_catalog = &s_bsps[0], .bsp_count = 9u
	},
	{
		.identity = { "a30", 213065216u, 197711360u, 15353440u, { 0x28, 0x79, 0x59, 0xf3, 0x4a, 0x73, 0x79, 0xa1, 0xdb, 0xec, 0x5f, 0xec, 0x15, 0xb4, 0xd9, 0x4d, 0x17, 0xfe, 0x97, 0xcc, 0xd8, 0x61, 0xf5, 0xc0, 0xc8, 0xfc, 0x80, 0x14, 0x8b, 0x7e, 0xd2, 0x93 } },
		.scenario_name = "levels\\a30\\a30",
		.hp2_path = "maps/a30.hp2",
		.map_path = "maps/a30.map",
		.bsp_catalog = &s_bsps[9], .bsp_count = 2u
	},
	{
		.identity = { "a50", 250138624u, 234469376u, 15668928u, { 0xd7, 0xa3, 0xe8, 0x0a, 0x86, 0xf2, 0xb0, 0xf2, 0x3d, 0x85, 0x5c, 0xe3, 0x53, 0xae, 0xd3, 0xc0, 0xeb, 0x25, 0x21, 0x45, 0x69, 0x77, 0x97, 0xd8, 0x7f, 0x25, 0x62, 0x3d, 0xc4, 0x70, 0xf3, 0x8d } },
		.scenario_name = "levels\\a50\\a50",
		.hp2_path = "maps/a50.hp2",
		.map_path = "maps/a50.map",
		.bsp_catalog = &s_bsps[11], .bsp_count = 4u
	},
	{
		.identity = { "b30", 224887296u, 209169920u, 15716920u, { 0x74, 0x02, 0x02, 0x02, 0xd3, 0x93, 0x0e, 0xe5, 0x2c, 0x1e, 0xe9, 0x6a, 0x7d, 0x8e, 0x3e, 0xe4, 0x02, 0x0c, 0xe3, 0x1a, 0x43, 0x4b, 0x3f, 0x87, 0x0d, 0x71, 0xdf, 0x72, 0xb9, 0xc3, 0xe4, 0xdd } },
		.scenario_name = "levels\\b30\\b30",
		.hp2_path = "maps/b30.hp2",
		.map_path = "maps/b30.map",
		.bsp_catalog = &s_bsps[15], .bsp_count = 2u
	},
	{
		.identity = { "b40", 279763456u, 262767104u, 16995988u, { 0x8c, 0x5e, 0x4a, 0xec, 0xbd, 0x0b, 0xc7, 0xe0, 0x63, 0xfe, 0xb7, 0xd0, 0xc6, 0xa3, 0xf6, 0xd8, 0xcf, 0xf6, 0x5b, 0xf1, 0xab, 0xec, 0x75, 0x28, 0x60, 0x70, 0xef, 0x9c, 0x85, 0xfd, 0x92, 0x7b } },
		.scenario_name = "levels\\b40\\b40",
		.hp2_path = "maps/b40.hp2",
		.map_path = "maps/b40.map",
		.bsp_catalog = &s_bsps[17], .bsp_count = 13u
	},
	{
		.identity = { "beavercreek", 43565056u, 36354048u, 7210528u, { 0xea, 0xf9, 0x0b, 0x2a, 0xbc, 0x4f, 0xd2, 0x95, 0x46, 0x9e, 0xb2, 0xd6, 0x40, 0x06, 0x36, 0x18, 0xb0, 0xd1, 0x43, 0x96, 0xf2, 0x8e, 0x7d, 0x7f, 0x17, 0x58, 0xe8, 0x34, 0xc0, 0x61, 0xc5, 0x0a } },
		.scenario_name = "levels\\test\\beavercreek\\beavercreek",
		.hp2_path = "maps/beavercreek.hp2",
		.map_path = "maps/beavercreek.map",
		.bsp_catalog = &s_bsps[30], .bsp_count = 1u
	},
	{
		.identity = { "bloodgulch", 44328960u, 36943360u, 7385184u, { 0x9e, 0xb0, 0x37, 0x4c, 0xbe, 0x45, 0x71, 0xaf, 0x64, 0x0a, 0xe0, 0xd2, 0xe0, 0xeb, 0xf6, 0x11, 0x95, 0x43, 0xcd, 0xbb, 0xec, 0xe4, 0x4d, 0x49, 0x54, 0x3b, 0x47, 0x48, 0xc4, 0xcf, 0x0d, 0xc1 } },
		.scenario_name = "levels\\test\\bloodgulch\\bloodgulch",
		.hp2_path = "maps/bloodgulch.hp2",
		.map_path = "maps/bloodgulch.map",
		.bsp_catalog = &s_bsps[31], .bsp_count = 1u
	},
	{
		.identity = { "boardingaction", 45346304u, 38111232u, 7234856u, { 0x34, 0xdd, 0xf9, 0x61, 0x97, 0x3b, 0x6a, 0xaf, 0x05, 0xf4, 0x0f, 0x26, 0xbd, 0x9a, 0xd5, 0x36, 0xca, 0x97, 0xf8, 0xaf, 0x50, 0x39, 0x95, 0x61, 0x15, 0x35, 0xcc, 0xf6, 0xce, 0x91, 0x15, 0x22 } },
		.scenario_name = "levels\\test\\boardingaction\\boardingaction",
		.hp2_path = "maps/boardingaction.hp2",
		.map_path = "maps/boardingaction.map",
		.bsp_catalog = &s_bsps[32], .bsp_count = 1u
	},
	{
		.identity = { "c10", 252559360u, 235947008u, 16612248u, { 0x42, 0x3d, 0x50, 0xa4, 0xd7, 0xfb, 0x7b, 0x3c, 0x28, 0x0d, 0x7e, 0x08, 0x06, 0xd6, 0x7e, 0x13, 0x6b, 0x2b, 0x6a, 0x51, 0x46, 0x8e, 0xd0, 0xbe, 0x6e, 0xe9, 0x41, 0x5e, 0x5f, 0x12, 0x9e, 0x7d } },
		.scenario_name = "levels\\c10\\c10",
		.hp2_path = "maps/c10.hp2",
		.map_path = "maps/c10.map",
		.bsp_catalog = &s_bsps[33], .bsp_count = 6u
	},
	{
		.identity = { "c20", 142009856u, 133056512u, 8953344u, { 0x1c, 0x1c, 0x9a, 0x8c, 0xa8, 0x82, 0x63, 0x6a, 0x3e, 0x78, 0xcb, 0x1d, 0x14, 0xe2, 0x5a, 0x09, 0xc4, 0xa1, 0x13, 0x88, 0xf6, 0x38, 0x1c, 0x5f, 0x74, 0x21, 0x2d, 0x46, 0x8b, 0x70, 0xe6, 0x54 } },
		.scenario_name = "levels\\c20\\c20",
		.hp2_path = "maps/c20.hp2",
		.map_path = "maps/c20.map",
		.bsp_catalog = &s_bsps[39], .bsp_count = 4u
	},
	{
		.identity = { "c40", 255975936u, 239438848u, 16536628u, { 0xd7, 0x46, 0x5f, 0x07, 0xa6, 0x75, 0xa8, 0x67, 0x85, 0xa3, 0x29, 0xb9, 0xab, 0x3d, 0x8a, 0x5a, 0x20, 0xb2, 0x5b, 0x7c, 0xa7, 0xd0, 0x5b, 0xaf, 0xeb, 0x7c, 0xa8, 0x7b, 0x02, 0xb2, 0x0b, 0xe9 } },
		.scenario_name = "levels\\c40\\c40",
		.hp2_path = "maps/c40.hp2",
		.map_path = "maps/c40.map",
		.bsp_catalog = &s_bsps[43], .bsp_count = 13u
	},
	{
		.identity = { "carousel", 42367488u, 35288064u, 7079316u, { 0x3e, 0x4b, 0xe2, 0x9a, 0x79, 0x52, 0xaf, 0x0b, 0x3f, 0x19, 0xa7, 0x54, 0x0e, 0x45, 0x4f, 0xd0, 0xde, 0xec, 0xe6, 0xd6, 0x07, 0x8c, 0x25, 0x6c, 0xde, 0x70, 0xa7, 0x34, 0xbe, 0xba, 0x55, 0xe1 } },
		.scenario_name = "levels\\test\\carousel\\carousel",
		.hp2_path = "maps/carousel.hp2",
		.map_path = "maps/carousel.map",
		.bsp_catalog = &s_bsps[56], .bsp_count = 1u
	},
	{
		.identity = { "chillout", 41967104u, 34918400u, 7048280u, { 0x52, 0xbc, 0x3e, 0x23, 0xb9, 0x14, 0x2c, 0xf4, 0x79, 0x77, 0x0d, 0x1d, 0x60, 0x1f, 0xe0, 0x8b, 0x13, 0xd7, 0x8f, 0xe3, 0xeb, 0x05, 0xec, 0xa7, 0x2d, 0x31, 0x3b, 0x7e, 0xbb, 0xd2, 0x1f, 0xfb } },
		.scenario_name = "levels\\test\\chillout\\chillout",
		.hp2_path = "maps/chillout.hp2",
		.map_path = "maps/chillout.map",
		.bsp_catalog = &s_bsps[57], .bsp_count = 1u
	},
	{
		.identity = { "d20", 205501952u, 190977024u, 14524560u, { 0x30, 0xd8, 0xfc, 0x02, 0xbc, 0xd2, 0x09, 0xa7, 0xce, 0x03, 0x17, 0x4d, 0x8c, 0xf6, 0xcf, 0x77, 0x1d, 0xd3, 0x62, 0x18, 0x37, 0xd9, 0xa2, 0xd0, 0x21, 0x11, 0x71, 0x8d, 0xcc, 0x5e, 0x79, 0x2c } },
		.scenario_name = "levels\\d20\\d20",
		.hp2_path = "maps/d20.hp2",
		.map_path = "maps/d20.map",
		.bsp_catalog = &s_bsps[58], .bsp_count = 5u
	},
	{
		.identity = { "d40", 274594816u, 259576832u, 15017804u, { 0x43, 0x84, 0x52, 0xef, 0x18, 0x96, 0xdd, 0x5b, 0xc2, 0xd3, 0x21, 0x0b, 0x27, 0x9f, 0x76, 0xe7, 0x1b, 0x77, 0x5f, 0x7e, 0xb2, 0xb7, 0xa8, 0xf8, 0xe2, 0x9f, 0x4e, 0x54, 0x71, 0xd5, 0x9a, 0x76 } },
		.scenario_name = "levels\\d40\\d40",
		.hp2_path = "maps/d40.hp2",
		.map_path = "maps/d40.map",
		.bsp_catalog = &s_bsps[63], .bsp_count = 10u
	},
	{
		.identity = { "damnation", 47968768u, 40728576u, 7240148u, { 0x87, 0xbd, 0x92, 0xc1, 0x82, 0x1f, 0xf2, 0x0b, 0xed, 0x03, 0xc5, 0x59, 0xd7, 0xbe, 0x5a, 0xc4, 0x3b, 0xae, 0xb4, 0x4a, 0xa6, 0x83, 0x42, 0xff, 0xdb, 0xb5, 0xa8, 0xcd, 0x97, 0x8f, 0x71, 0x1c } },
		.scenario_name = "levels\\test\\damnation\\damnation",
		.hp2_path = "maps/damnation.hp2",
		.map_path = "maps/damnation.map",
		.bsp_catalog = &s_bsps[73], .bsp_count = 1u
	},
	{
		.identity = { "hangemhigh", 43700224u, 36659712u, 7040008u, { 0xe3, 0xe4, 0xb2, 0x5e, 0xd3, 0x61, 0x78, 0x92, 0x6f, 0x0d, 0xf1, 0x1f, 0x3c, 0xd8, 0x2b, 0x07, 0xe2, 0x07, 0x1f, 0x6a, 0xa0, 0xef, 0xaa, 0x77, 0xf0, 0xcf, 0xde, 0x8f, 0x84, 0x80, 0x98, 0x1f } },
		.scenario_name = "levels\\test\\hangemhigh\\hangemhigh",
		.hp2_path = "maps/hangemhigh.hp2",
		.map_path = "maps/hangemhigh.map",
		.bsp_catalog = &s_bsps[74], .bsp_count = 1u
	},
	{
		.identity = { "longest", 42141696u, 35062272u, 7079296u, { 0xe0, 0x45, 0xb0, 0x84, 0x3f, 0x4a, 0x16, 0x7a, 0x51, 0x6f, 0x05, 0x01, 0x61, 0xa6, 0x51, 0x61, 0x0f, 0xaf, 0xc9, 0x4c, 0xcc, 0x8c, 0x5f, 0x2c, 0x5d, 0x57, 0x25, 0xd1, 0x08, 0xd5, 0xd1, 0xb9 } },
		.scenario_name = "levels\\test\\longest\\longest",
		.hp2_path = "maps/longest.hp2",
		.map_path = "maps/longest.map",
		.bsp_catalog = &s_bsps[75], .bsp_count = 1u
	},
	{
		.identity = { "prisoner", 43974656u, 36940288u, 7034316u, { 0x85, 0xff, 0x2f, 0xdc, 0x11, 0x7b, 0x76, 0x40, 0xbd, 0xa8, 0x5a, 0x49, 0x0b, 0x30, 0xc6, 0x62, 0xf2, 0x62, 0x6b, 0xd6, 0xd0, 0x68, 0x5e, 0x41, 0x83, 0x29, 0x35, 0x42, 0x28, 0x91, 0xc3, 0x07 } },
		.scenario_name = "levels\\test\\prisoner\\prisoner",
		.hp2_path = "maps/prisoner.hp2",
		.map_path = "maps/prisoner.map",
		.bsp_catalog = &s_bsps[76], .bsp_count = 1u
	},
	{
		.identity = { "putput", 40668672u, 33634816u, 7033488u, { 0xef, 0xbe, 0x72, 0x31, 0x88, 0xf3, 0x40, 0x53, 0xd3, 0x18, 0x10, 0x5f, 0x20, 0xc7, 0x04, 0x6f, 0x26, 0x31, 0x71, 0xfb, 0xb9, 0x37, 0xfb, 0xad, 0x45, 0xe3, 0xd0, 0x0f, 0x84, 0x37, 0xf2, 0x43 } },
		.scenario_name = "levels\\test\\putput\\putput",
		.hp2_path = "maps/putput.hp2",
		.map_path = "maps/putput.map",
		.bsp_catalog = &s_bsps[77], .bsp_count = 1u
	},
	{
		.identity = { "ratrace", 47403008u, 40301568u, 7101136u, { 0x57, 0x78, 0x86, 0xf9, 0x49, 0xf2, 0x64, 0x8f, 0x04, 0xcf, 0x99, 0xe3, 0x54, 0xfb, 0x04, 0xca, 0x08, 0xd7, 0xb9, 0x19, 0x96, 0x36, 0xc2, 0xf9, 0xfe, 0x1a, 0x16, 0x1c, 0xcd, 0xaa, 0x4b, 0x1e } },
		.scenario_name = "levels\\test\\ratrace\\ratrace",
		.hp2_path = "maps/ratrace.hp2",
		.map_path = "maps/ratrace.map",
		.bsp_catalog = &s_bsps[78], .bsp_count = 1u
	},
	{
		.identity = { "sidewinder", 48048128u, 40683008u, 7364724u, { 0x99, 0x55, 0x61, 0xa6, 0x8c, 0x8c, 0x5b, 0x14, 0x2f, 0x13, 0xf1, 0x96, 0x77, 0x30, 0xce, 0x8c, 0x08, 0xd4, 0xf0, 0xdb, 0x95, 0x74, 0xdb, 0x8e, 0x98, 0x7d, 0x91, 0x5f, 0x2b, 0x11, 0x8d, 0xcc } },
		.scenario_name = "levels\\test\\sidewinder\\sidewinder",
		.hp2_path = "maps/sidewinder.hp2",
		.map_path = "maps/sidewinder.map",
		.bsp_catalog = &s_bsps[79], .bsp_count = 1u
	},
	{
		.identity = { "ui", 33582080u, 31939584u, 1642244u, { 0x85, 0x56, 0xb6, 0x47, 0xb8, 0x27, 0x42, 0xd0, 0x72, 0x82, 0xfe, 0x4e, 0x6d, 0xb0, 0xcf, 0x84, 0x7b, 0x54, 0x2c, 0x04, 0x64, 0x84, 0xe9, 0x1e, 0x71, 0xec, 0x31, 0xfe, 0xa5, 0xf5, 0xfd, 0x7e } },
		.scenario_name = "levels\\ui\\ui",
		.hp2_path = "maps/ui.hp2",
		.map_path = "maps/ui.map",
		.bsp_catalog = &s_bsps[80], .bsp_count = 1u
	},
	{
		.identity = { "wizard", 40681984u, 33617408u, 7064204u, { 0x97, 0x85, 0x39, 0xff, 0x70, 0x08, 0x59, 0x98, 0x48, 0x58, 0x70, 0xa1, 0x5d, 0x4e, 0xc8, 0x1d, 0x38, 0x11, 0x44, 0x2a, 0xc4, 0x8f, 0x92, 0x65, 0xdb, 0x66, 0x8a, 0x39, 0x6f, 0x6f, 0xf1, 0xeb } },
		.scenario_name = "levels\\test\\wizard\\wizard",
		.hp2_path = "maps/wizard.hp2",
		.map_path = "maps/wizard.map",
		.bsp_catalog = &s_bsps[81], .bsp_count = 1u
	},
};

static int path_equal(const char *left, const char *right)
{
	while (*left && *right) {
		char a = *left++;
		char b = *right++;
		if (a == '/') a = '\\';
		if (b == '/') b = '\\';
		if (a != b) return 0;
	}
	return *left == '\0' && *right == '\0';
}

size_t hcu_map_catalog_count(void)
{
	return sizeof(s_maps) / sizeof(s_maps[0]);
}

const hcu_map_catalog_entry *hcu_map_catalog_at(size_t index)
{
	return index < hcu_map_catalog_count() ? &s_maps[index] : NULL;
}

const hcu_map_catalog_entry *hcu_map_catalog_find(const char *map_name)
{
	size_t i;
	if (!map_name || !map_name[0]) return NULL;
	for (i = 0; i < hcu_map_catalog_count(); i++) {
		const hcu_map_catalog_entry *entry = &s_maps[i];
		if (strcmp(map_name, entry->identity.map_name) == 0 ||
			path_equal(map_name, entry->scenario_name))
			return entry;
	}
	return NULL;
}

int hcu_map_catalog_validate_hmap(const hcu_map_catalog_entry *entry,
	const void *bytes, size_t size, hmap_identity *identity_out)
{
	hmap_identity identity;
	if (!entry || !hmap_open(&identity, bytes, size, entry->identity.map_name) ||
		identity.file_length != entry->identity.file_length ||
		identity.tag_data_offset != entry->identity.tag_data_offset ||
		identity.tag_data_size != entry->identity.tag_data_size ||
		memcmp(identity.source_sha256, entry->identity.source_sha256,
			sizeof(identity.source_sha256)) != 0)
		return 0;
	if (identity_out) *identity_out = identity;
	return 1;
}

int hcu_map_catalog_validate_bsp_catalog(
	const hcu_map_catalog_entry *entry, const void *bytes, size_t size)
{
	cbsp_catalog catalog;
	uint32_t i;
	if (!entry || !entry->bsp_catalog || entry->bsp_count == 0 ||
		!cbsp_catalog_open(&catalog, bytes, size, entry->identity.file_length) ||
		catalog.count != entry->bsp_count)
		return 0;
	for (i = 0; i < entry->bsp_count; i++) {
		const hcu_map_bsp_entry *expected = &entry->bsp_catalog[i];
		cbsp_catalog_entry actual;
		if (!cbsp_catalog_find(&catalog, expected->file_offset,
			expected->file_size, &actual) ||
			memcmp(actual.section_tag, expected->section_tag, 5) != 0)
			return 0;
	}
	return 1;
}
