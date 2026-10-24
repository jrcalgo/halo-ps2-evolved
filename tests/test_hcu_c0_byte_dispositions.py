import importlib.util
from pathlib import Path

P=Path(__file__).parents[1]/'tools/audit_hcu_c0_byte_dispositions.py'
s=importlib.util.spec_from_file_location('c0bytes',P); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)

def test_current_inventory_has_a_disposition_for_every_member():
    report=m.build(Path(__file__).parents[1])
    assert report['disposition_rows']==report['inventory_rows']
    assert report['unclassified_member_dispositions']==0
    assert report['issues']==[]
    assert report['unexplained_removals']==0
    assert 'tools/ctag_schema_walk.py' in report['source_pins']
    assert 'tests/test_step7_unmapped_bsp_range_retention.py' in report['source_pins']
    assert sum(r['disposition']=='retain_opaque_unchanged' for r in report['rows'])==54
    assert sum(r['disposition']=='preserve_root_bytes' for r in report['rows'])==12
