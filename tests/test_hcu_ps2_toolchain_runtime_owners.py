import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "build/hcu-parent-link-probe/hcu-gameplay-machine.map"
LEDGER = ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json"


def test_hcu_ee_runtime_symbols_are_provided_by_pinned_libraries():
	"""Keep live libgcc/libm/libc calls out of generated success stubs."""
	link_map = MAP.read_text()
	providers = {
		"__extendsfdf2": "libgcc.a(_sf_to_df.o)",
		"__fixdfsi": "libgcc.a(_df_to_si.o)",
		"__truncdfsf2": "libgcc.a(_df_to_sf.o)",
		"floor": "libm.a(libm_a-s_floor.o)",
		"fmod": "libm.a(libm_a-w_fmod.o)",
		"rint": "libm.a(libm_a-s_rint.o)",
		"sqrt": "libm.a(libm_a-w_sqrt.o)",
		"memcpy": "libc.a(libc_a-memcpy.o)",
	}
	for symbol, provider in providers.items():
		assert provider in link_map, (symbol, provider)
		assert re.search(rf"\b{re.escape(symbol)}$", link_map, re.M), symbol

	generated = ROOT / "build/hcu-ps2-closure/all/ps2_platform.c"
	generated_text = generated.read_text() if generated.exists() else ""
	ledger = json.loads(LEDGER.read_text())
	cseries_h = (ROOT / "submodules/halo-ce-universal/source/cseries/cseries.h").read_text()
	cseries_c = (ROOT / "submodules/halo-ce-universal/source/cseries/cseries.c").read_text()
	rint_c = (ROOT / "build/toolchain/sources/ps2toolchain_ee_newlib/newlib/libm/common/s_rint.c").read_text()
	assert "result = (long)__builtin_rint((double)value);" in cseries_h
	assert "(byte *)source+size<=(byte *)destination || (byte *)destination+size<=(byte *)source" in cseries_c
	assert "TWO52[sx]+x" in rint_c
	for symbol in providers:
		assert not re.search(rf"\b{re.escape(symbol)}\s*\(", generated_text), symbol
		row = ledger["symbols"][symbol]
		assert row["disposition"] == "implemented", symbol
		assert row["owner"] and row["reason"] and row["evidence"] and row["test"]
		assert "hcu-ps2-toolchain-eight-review.md" in row["evidence"]

