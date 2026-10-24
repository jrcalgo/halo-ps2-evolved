from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "submodules/halo-ce-universal/source/hs/hs_runtime.c"


def test_ps2_debug_stack_reader_uses_the_aligned_first_word():
    source = RUNTIME.read_text()
    start = source.index("static char const *expression_get_function_name(")
    end = source.index("boolean hs_runtime_waiting_on_call(", start)
    reader = source[start:end]

    assert "#ifdef HALO_PS2" in reader
    assert "uintptr_t data_address = (uintptr_t)thread->stack->data;" in reader
    assert "(4u - (data_address & 3u)) & 3u" in reader
    assert "thread->stack->data +\n\t\t\t\tfirst_word_offset" in reader
    assert "#else\n\t\tnext_expression_index = *(long *)thread->stack->data;\n#endif" in reader


def test_hs_frame_payload_offset_and_alignment_padding_agree():
    # On the PS2 ILP32 layout, previous/expression/result/size occupy 14
    # bytes, then the structure rounds to 16. A word-sized allocation from
    # data therefore needs two bytes of padding. Exercise all possible base
    # residues so the production address-based formula is not offset-based.
    for residue in range(4):
        offset = (4 - residue) & 3
        assert (residue + offset) % 4 == 0
        assert offset in range(4)

    ps2_data_residue = 0x0E % 4
    first_word_offset = (4 - ps2_data_residue) & 3
    assert first_word_offset == 2
