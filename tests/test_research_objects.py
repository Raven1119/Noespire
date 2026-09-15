"""Derived object views preserve quoted research; they never adjudicate truth."""
from copy import deepcopy
import json

import pytest

from research.research_objects import derive_cards, reconstruct, object_page, project, lifecycle
from research.continuous_attention import bounded_packet


TEXT = ("1. There is an exact polynomial representation of the finite sum. "
        "Then the coefficient identity follows by collecting terms. "
        "The identity holds where a>0, b>=0, and j belongs to {1,...,r}.\n\n"
        "2. Construct a rational example at R=31. "
        "The remaining gap is the missing endpoint calculation.")


def source(**changes):
    return {"source_ref":"studies/study-a/000001.json", "study_id":"study-a", "scope":"a>0",
        "source_status":"RECORDED_STUDY", "source_message_id":None, "artifact_id":None,
        "lineage":["revision-1"], "fields":{"continuation":TEXT}, **changes}


def test_multiple_objects_literal_conditions_unknown_gap_and_reconstruction():
    s=source(); cards=derive_cards([s])
    assert len(cards)==2
    first, second=cards
    assert first['object']['value']=='There is an exact polynomial representation of the finite sum.'
    assert 'a>0, b>=0' in first['boundary']['value']
    assert first['remaining_gap']=={'value':'UNKNOWN','source':None}
    assert 'endpoint calculation' in second['remaining_gap']['value']
    assert all(c['authority']=='UNVERIFIED_RESEARCH' and c['status']=='ACTIVE' for c in cards)
    for card in cards:
        for name in ('object','boundary','remaining_gap','possible_deliverable'):
            cell=card[name]
            assert reconstruct(cell,[s])==cell['value']
        for cell in card['established_components']:
            assert reconstruct(cell,[s])==cell['value']


def test_timeout_and_later_fact_cannot_invent_gap_or_change_object_identity():
    original=derive_cards([source()])
    timed=derive_cards([source(source_status='TIMEOUT',later_fact='a later unrelated result')])
    assert [c['object_id'] for c in original]==[c['object_id'] for c in timed]
    assert [c['remaining_gap']['value'] for c in original]==[c['remaining_gap']['value'] for c in timed]
    assert original[0]['remaining_gap']['source'] is None


@pytest.mark.parametrize('hedge',['seems plausible','likely follows','should be enough','might follow'])
def test_tentative_research_is_not_established(hedge):
    s=source(fields={'continuation':f'1. Study the endpoint identity. Then it {hedge}.'})
    card=derive_cards([s])[0]
    assert card['established_components']==[]
    assert card['remaining_gap']['value']=='UNKNOWN'


def test_checkpoint_gap_is_not_attached_to_every_object():
    s=source(fields={'derivation':TEXT,'obstruction':'The first endpoint is still missing.'},
             source_ref='research_deliveries/study-a/checkpoint.json', source_message_id='m1')
    cards=derive_cards([s])
    assert cards[0]['remaining_gap']['value']=='UNKNOWN'
    assert 'missing endpoint' in cards[1]['remaining_gap']['value']


def test_conservative_duplicates_require_same_study_boundary_and_lineage():
    s=source(); clone={**s,'source_ref':'public-copy','source_message_id':'m1'}
    cards=derive_cards([s,clone])
    assert len(cards)==2 and len(cards[0]['origins'])==2
    assert len(derive_cards([s,{**clone,'lineage':['unrelated-call']}]))==4
    assert len(derive_cards([s,{**clone,'study_id':'study-other'}]))==4
    assert len(derive_cards([s,source(fields={'continuation':TEXT.replace('a>0, b>=0','a<0, b<=0')})]))==3
    assert derive_cards([s,clone])==derive_cards([s,clone])


def test_tampered_source_cannot_reconstruct():
    s=source(); cell=derive_cards([s])[0]['object']
    with pytest.raises(ValueError,match='provenance'):
        reconstruct(cell,[source(fields={'continuation':TEXT+' changed'})])


def test_all_cards_page_without_silent_loss_and_oversized_objects_have_notice():
    sources=[source(source_ref=f'source-{n}',lineage=[str(n)],fields={
        'continuation':f'1. Construct an example with index R={n}. The remaining gap is the endpoint.'}) for n in range(18)]
    cards=derive_cards(sources)
    cards+=derive_cards([source(source_ref='huge',lineage=['huge'],fields={'continuation':'1. '+('condition '*1200)+'.'})])
    seen=[]; notices=[]; offset=0
    while True:
        page=object_page(cards,offset,token_budget=450)
        bounded_packet({'research_object_cards':page},450)
        seen.extend(c['object_id'] for c in page['items']);notices.extend(c['object_id'] for c in page['unexpanded'])
        if not page['next_ref']:break
        after=int(page['next_ref'].split(':')[1]);assert after>offset;offset=after
    assert set(seen+notices)=={c['object_id'] for c in cards}
    assert len(seen)==18 and len(notices)==1
    assert 'source' not in project(cards[0])['object']


def test_exact_resolution_is_a_new_view_and_never_rewrites_history(tmp_path):
    from test_continuous_selection import fixture
    from test_bridge_discovery import accepted
    net,study,state,_=fixture(tmp_path)
    original=derive_cards([source(study_id=study['study_id'],scope='',fields={'focus':'A finite local identity.'})])[0]
    prior=deepcopy(original)
    assert lifecycle(original,net)['status']=='ACTIVE'
    fact=accepted(tmp_path,net,'A finite local identity.','')
    current=lifecycle(original,net)
    assert current['status']=='RESOLVED' and current['resolution_fact_id']==fact.fact_id
    assert original==prior and current['origins']==prior['origins']
    assert derive_cards([source(study_id=study['study_id'],scope='',fields={'focus':'A finite local identity.'})])[0]==prior
    assert net.truth(net.target_id)=='OPEN'


def test_same_title_with_unstated_different_content_is_not_merged():
    one=source(fields={'continuation':'1. Study the same named object. Define f(x)=x.'})
    two=source(fields={'continuation':'1. Study the same named object. Define f(x)=x*x.'})
    assert len(derive_cards([one,two]))==2


def test_every_explicit_condition_span_survives_not_just_the_first():
    text=('1. There is an exact change of representation. '
          'Then W=Z where Z is a real linear combination. '
          'The identity holds where c>0 and a+b=1. '
          'If x is negative, the statement is conditional on H.')
    s=source(fields={'continuation':text});c=derive_cards([s])[0]
    assert 'real linear combination' in c['boundary']['value']
    assert 'c>0 and a+b=1' in c['boundary']['value']
    assert 'conditional on H' in c['boundary']['value']
    assert reconstruct(c['boundary'],[s])==c['boundary']['value']
    assert not c['established_components']


def test_known_public_checkpoint_envelope_retains_original_fields():
    from research.research_objects import public_fields
    from research.research_delivery import MARKER
    study={'focus':'Research f.','scope':'Assume x>0.'}
    content={'goal':study['focus'],'context':study['scope'],'derivation':TEXT,
             'obstruction':'A global remaining question.','next_work':'Check the boundary.','materials_used':[]}
    raw=json.dumps({'continuation':MARKER+json.dumps(content),'next_work':content['next_work'],
                    'candidate':None,'new_study':None,'definitions':[],'context_requests':[]})
    fields=public_fields(raw,study)
    assert fields=={k:content[k] for k in ('derivation','obstruction','next_work')}
    assert public_fields(raw,{**study,'scope':'Wrong scope'}) is None
    assert public_fields(raw[:-8],study) is None
    assert public_fields(json.dumps({'unrelated':content}),study) is None


@pytest.mark.parametrize('assertion', [
    'Then the coefficient identity is still an open conjecture.',
    'We checked none of the required cases.',
    'We have not proved the estimate.',
    'Consequently the conjecture should follow.'
])
def test_explicit_noncompletion_never_becomes_established(assertion):
    c=derive_cards([source(fields={'continuation':'1. Study the coefficient identity. '+assertion})])[0]
    assert not c['established_components']


def test_numbered_objects_retain_shared_preamble_and_ambient_scope():
    text='Assume the denominator is nonzero. Define the symbol h as in the following formula.\n\n'+TEXT
    s=source(scope='Assume x is positive.',fields={'continuation':text})
    for c in derive_cards([s]):
        assert 'denominator is nonzero' in c['object']['value']
        assert 'Define the symbol h' in c['object']['value']
        assert 'Assume x is positive.' in c['boundary']['value']
        assert reconstruct(c['object'],[s])==c['object']['value']
        assert reconstruct(c['boundary'],[s])==c['boundary']['value']


def test_explicit_boundary_does_not_hide_additional_assumptions():
    s=source(scope='',fields={'continuation':'Object: A local identity.\nBoundary: N=4.\nAssume the entries are positive.'})
    c=derive_cards([s])[0]
    assert 'N=4' in c['boundary']['value'] and 'entries are positive' in c['boundary']['value']


def test_different_checkpoint_gaps_do_not_merge_under_same_invocation():
    base=source(fields={'derivation':'Fix the rational vector v=(1,2).','obstruction':'The first endpoint is missing.'})
    other={**base,'source_ref':'second-message','fields':{**base['fields'],'obstruction':'The second endpoint is missing.'}}
    cards=derive_cards([base,other])
    assert len(cards)==2 and len({c['object_id'] for c in cards})==2


def test_accepted_headline_does_not_resolve_a_card_with_extra_conditions(tmp_path):
    from test_continuous_selection import fixture
    from test_bridge_discovery import accepted
    net,study,state,_=fixture(tmp_path)
    accepted(tmp_path,net,'A finite local identity.','')
    c=derive_cards([source(scope='',fields={'continuation':'1. A finite local identity. Assume a new restriction.'})])[0]
    assert lifecycle(c,net)['status']=='ACTIVE'


@pytest.mark.parametrize("text", [
    "The following is a tentative calculation and remains unverified.\n1. Study the endpoint identity. We derived the coefficient identity.",
    "We derived the coefficient identity hypothetically.",
    "We derived a conjectural coefficient identity.",
])
def test_shared_or_inline_qualification_never_becomes_established(text):
    record=source(fields={'continuation':text})
    card=derive_cards([record])[0]
    assert card['established_components']==[]
    assert reconstruct(card['object'],[record])==card['object']['value']
