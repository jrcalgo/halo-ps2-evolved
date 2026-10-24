"""Independent pose bytes must keep both custom-source and CE-owner identities."""
import copy
import hashlib
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from hcu_profile_presentation import build_presentation
from hcu_profile_validate import _check_pose, ProfileValidationError


def _fixture():
    payloads = build_presentation()
    binding = payloads['bindings'][0]
    blob = payloads['chunks'][binding['chunk_id']]
    digest = hashlib.sha256(blob).hexdigest()
    key = 'POSE:' + digest
    owner = dict(source_key='custom-source', source_datum=0x12345678,
                 group='weap', path=binding['tag_path'], output_datum=12)
    row = dict(key=key, kind='POSE', bytes=len(blob), sha256=digest,
               owners=[owner], runtime_admitted=False,
               engine_consumer=dict(path='src/stream/hcu_pose_asset.c',
                   function='hcu_pose_asset_sample', source_sha256=hashlib.sha256(
                       (ROOT / 'src/stream/hcu_pose_asset.c').read_bytes()).hexdigest()))
    provenance = payloads['provenance'][binding['asset_id']]
    catalog = dict(key=key, kind='POSE', asset_id=binding['asset_id'],
                   owner=owner, chunk_id=8, jmad=binding['jmad'],
                   bytes=len(blob), sha256=digest, runtime_admitted=False,
                   source_map=provenance['source_map'],
                   source_map_sha256=provenance['source_map_sha256'],
                   source_pose=provenance['source_header'],
                   source_pose_sha256=provenance['source_header_sha256'])
    bindings = [dict(chunk_key=key, kind='POSE', asset_id=binding['asset_id'],
                     owner=owner, jmad=binding['jmad'], runtime_admitted=False)]
    media = {'pose_catalog': [catalog]}
    manifest = {'source_occurrence_remaps': [dict(owner)]}
    # Canonical import selection can use another identical source. The
    # occurrence ledger proves the explicit selected root still maps here.
    actual = [dict(output_datum=12, group='weap', path=binding['tag_path'])]
    return [blob, row, bindings, media, manifest, actual, payloads, 8]


def test_pose_matches_independent_source_and_deduplicated_ce_occurrence():
    assert _check_pose(*_fixture()) == 'sword'


@pytest.mark.parametrize('mutation,match', [
    ('custom_source', 'provenance'), ('header', 'provenance'),
    ('owner', 'owner'), ('chunk', 'physical chunk'),
    ('consumer', 'consumer source'), ('admission', 'binding disagree'),
])
def test_pose_rejects_identity_or_consumer_mutation(mutation, match):
    args = copy.deepcopy(_fixture())
    if mutation == 'custom_source': args[3]['pose_catalog'][0]['source_map_sha256'] = '0' * 64
    elif mutation == 'header': args[3]['pose_catalog'][0]['source_pose_sha256'] = '0' * 64
    elif mutation == 'owner': args[4]['source_occurrence_remaps'][0]['output_datum'] = 13
    elif mutation == 'chunk': args[3]['pose_catalog'][0]['chunk_id'] = 9
    elif mutation == 'consumer': args[1]['engine_consumer']['source_sha256'] = '0' * 64
    elif mutation == 'admission': args[2][0]['runtime_admitted'] = True
    with pytest.raises(ProfileValidationError, match=match):
        _check_pose(*args)
