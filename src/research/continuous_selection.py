"""Bounded local evidence and non-authoritative research action framing."""
import json

from .continuous_attention import AttentionOverflow, bounded_packet
from .run_storage import read_json, write_json


ACTION_PROPERTIES = {
    "action_mode": {"type": "string", "enum": ["RESEARCH", "CLOSE"]},
    **{key: {"type": "string"} for key in (
        "local_object", "proposed_boundary", "remaining_gap", "expected_deliverable")},
    "evidence_refs": {"type": "array", "items": {"type": "string"}},
}

CLOSE_INSTRUCTIONS = """ Prioritize closing one mathematically self-contained local result
from the accumulated research. Do not broaden the investigation or search for a
new construction unless the current candidate is shown to be unusable. If the
intended result is too strong, shrink it to the strongest complete local
proposition that can actually be proved. A smaller complete Fact is preferable
to a larger incomplete claim. The proposed boundary is a task, not an assumption.
Return the existing FACT / SUPPORT / no-candidate format. SUPPORT requires a real
mathematical premise, never 'more computation', 'check the logs', or 'machine
output is correct'. If no result closes, record the specific remaining closing
gap in continuation and next_work. All research artifacts remain UNVERIFIED;
only actual accepted Facts may be predecessors. """


def action_metadata(selected):
    """Validate an action interface, not the mathematical maturity of its object.

    Pre-extension frozen decisions remain implicit RESEARCH. Partial new
    interfaces are invalid; no timeout/counter heuristic supplies missing fields.
    """
    if not set(ACTION_PROPERTIES).intersection(selected):
        return {}
    if (selected.get('action_mode') not in ('RESEARCH', 'CLOSE') or
            any(not isinstance(selected.get(k), str) for k in (
                'local_object', 'proposed_boundary', 'remaining_gap', 'expected_deliverable'))):
        raise ValueError('invalid local action interface')
    refs = selected.get('evidence_refs')
    if not isinstance(refs, list) or any(not isinstance(r, str) or not r.strip() for r in refs):
        raise ValueError('invalid action evidence_refs')
    if selected['action_mode'] == 'CLOSE':
        if not all(isinstance(selected.get(k), str) and selected[k].strip() for k in (
                'local_object', 'proposed_boundary', 'remaining_gap', 'expected_deliverable', 'reason')):
            raise ValueError('CLOSE requires object, boundary, gap, deliverable and reason')
        if not refs:
            raise ValueError('CLOSE requires explicit evidence references')
    return {key: selected[key] for key in ACTION_PROPERTIES}


INSTRUCTIONS = """You are the fresh local Research Selector. Choose concrete local work, not merely
'continue proving the Claim'. In reason state: the specific task; which displayed
results you will use or why not; what is new relative to them; and what resumable
work you expect to leave. Compare complete statements AND conditions: a larger
bound need not supersede a different construction or assumptions. Reasonable
nonuse, UNKNOWN relevance, new representations and deeper work are allowed.
Cards are navigation, notes are unverified. fact_interfaces show accepted source
statements with original scope, NOT automatic target premises. Request fact:<id>
in material_refs for ordinary exact-scope use; foreign BRIDGE_CANDIDATE inspection
retains conditions and requires a separately verified bridge before proof use.
Never infer correspondence or authority from lexical overlap or an ID. Request
exact Study/object/search/evidence refs when needed; known_fact_ids and
context_requests are leads, not proof. representation_ref gives transport views,
not truth of an open Claim. A forced_study_id must be served: choose HOW. CONNECT
may investigate exposed regions; COMPOSE requires a listed ready Support.
continuation_window selects zero-based unverified-note lines, never assumptions
or proofs. If you need the next complete Fact page before deciding, return
operation=INSPECT, material_refs=[fact_interfaces.next_ref], support_id='', and
continuation_window=null. This reads that forward page then asks for your action;
it is not a Worker service. Any prior inspection_request_unverified is reading
intent, not evidence or a substitute for old conditions. Do not repeat pages. Otherwise choose ADVANCE,
CONNECT or COMPOSE and explicitly select this visit's material_refs; nothing
inspected is automatically added to the Worker window. bridge_candidate_pages
remain optional foreign navigation. No obligation to use every visible result.
Choose action_mode from the current mathematical state, not a timeout count.
RESEARCH is legitimate when no stable object/proposition exists, definitions or
direction are changing, or the gap is unclear. A checkpoint alone is not grounds
for CLOSE. Choose CLOSE only when the displayed research establishes a definite
local object, an accurate boundary, most of the construction/derivation, and a
few specific remaining links. Explain local_object, proposed_boundary,
remaining_gap, expected_deliverable and evidence_refs using exact displayed refs.
For RESEARCH these may state what remains undecided. Do not infer completed work
from navigation summaries or unexpanded material. local_action_evidence contains
complete UNVERIFIED notes, not facts. Describe why closure is or is not warranted.
CLOSE is only a task within this service; it never changes the selected channel,
fairness or proof authority. It is allowed in any channel, including EXPLORE.
PACKET:
"""


def fact_page(network, cards, offset=0, *, token_budget, reserved=None):
    """Only references already on exposed cards; never search the global graph."""
    # Ordinary Claim-bound results only. Support/transport certificates remain
    # explicitly readable; do not indirectly preload representation views.
    bound = {f for ids in network.data['fact_bindings'].values() for f in ids}
    owners = {}
    for card in cards:
        for key in card.get('known_fact_ids', []):
            if key not in bound:
                continue
            owners.setdefault(key, []).append(card['study_id'])
    keys = list(owners)
    if type(offset) is not int or not 0 <= offset <= len(keys):
        raise ValueError('invalid local Fact page offset')
    page = {'items': [], 'unexpanded': [], 'next_ref': None}
    reserved = reserved or {}
    for i in range(offset, min(offset+16, len(keys))):
        try:
            source = network.inspect_fact(keys[i])
        except ValueError:
            continue  # Stale, revoked, unbound and foreign-problem IDs fail closed.
        item = {'ref': 'fact:'+keys[i], 'source_scope': source['scope'],
                'exact_statement': source['statement'], 'source_study_ids': owners[keys[i]],
                'authority': 'SOURCE_INTERFACE_ONLY'}
        following = f'fact-interfaces:{i+1}' if i+1 < len(keys) else None
        proposed = {**page, 'items': page['items']+[item], 'next_ref': following}
        try:
            bounded_packet({**reserved, 'fact_interfaces': proposed}, token_budget)
        except AttentionOverflow:
            # Defer intact interfaces to a fresh page; an individually oversized
            # statement gets a notice, never a truncated condition or summary.
            try:
                bounded_packet({'fact_interfaces': {'items':[item], 'unexpanded':[],
                                                    'next_ref':following}}, token_budget)
            except AttentionOverflow:
                proposed = {**page, 'unexpanded':page['unexpanded']+[
                    {'ref':item['ref'], 'reason':'complete_interface_exceeds_page_budget'}],
                    'next_ref':following}
                try:
                    bounded_packet({**reserved, 'fact_interfaces':proposed}, token_budget)
                except AttentionOverflow:
                    page['next_ref'] = f'fact-interfaces:{i}'
                    break
            else:
                page['next_ref'] = f'fact-interfaces:{i}'
                break
        page = proposed
    else:
        end = min(offset+16, len(keys))
        page['next_ref'] = f'fact-interfaces:{end}' if end < len(keys) else None
    bounded_packet({**reserved, 'fact_interfaces':page}, token_budget)
    return page


def add_fact_interfaces(network, exposure, *, token_budget):
    reserved = {k:exposure.get(k, []) for k in ('bridge_candidates','bridge_candidate_pages')}
    # Use the existing navigation allocation, not another context allowance.
    try:
        page = fact_page(network, exposure['cards'], token_budget=token_budget, reserved=reserved)
    except AttentionOverflow:
        # Existing foreign navigation occupies the allocation. An empty first
        # page is a pointer to a separate intact page, not dropped conditions.
        available = fact_page(network, exposure['cards'], token_budget=token_budget)
        page = {'items':[], 'unexpanded':[], 'next_ref':
                'fact-interfaces:0' if any(available.values()) else None}
    return {**exposure, 'fact_interfaces':page}


def add_action_evidence(exposure, studies, schema, *, token_budget, artifact_store=None, checkpoint_store=None):
    """Project intact notes for already exposed Studies, inside the same ceiling.

    Preserve card order and scope. An oversized record stays an explicit ref;
    neither conditions nor proofs are truncated to suggest readiness to CLOSE.
    """
    page = {'items': [], 'unexpanded': []}
    result = {**exposure, 'local_action_evidence': page}
    def fits(value):
        try:
            bounded_packet({'prompt': INSTRUCTIONS + json.dumps(value, ensure_ascii=False),
                            'schema': schema}, token_budget)
        except AttentionOverflow:
            return False
        return True
    def records():
        for card in exposure['cards']:
            study = studies[card['study_id']]
            if study.get('continuation'):
                yield {'ref': study.get('research_delivery_ref', card['ref']),
                    'study_id': study['study_id'], 'claim_id': study.get('claim_id'),
                    'scope': study['scope'], 'focus': study['focus'], 'verified': False,
                    'continuation': study['continuation'], 'next_work': study['next_work']}
            if artifact_store:
                checkpoint = checkpoint_store.latest(study) if checkpoint_store else None
                # Reuse the existing bounded, same-Study public-material page.
                # Completed public items are research even without a checkpoint.
                try:
                    public = artifact_store.handover(study, token_budget=max(1, token_budget // 4), checkpoint=checkpoint)
                except AttentionOverflow:
                    public = {'unexpanded': [{'ref': 'research-artifacts:0'}]}
                for notice in (public or {}).get('unexpanded', []):
                    yield {'ref': notice['ref'], 'study_id': study['study_id'], 'unexpanded': True}
                if (public or {}).get('next_ref'):
                    yield {'ref': public['next_ref'], 'study_id': study['study_id'], 'unexpanded': True}
                for item in (public or {}).get('public_messages', []):
                    yield {**item, 'ref': item['material_ref']}
    for item in records():
        ref = item['ref']
        proposed = {**page, 'items': page['items'] + [item]}
        if item.get('unexpanded') or not fits({**result, 'local_action_evidence': proposed}):
            proposed = {**page, 'unexpanded': page['unexpanded'] + [
                {'ref': ref, 'study_id': item['study_id'], 'reason': 'complete_notes_exceed_remaining_context'}]}
            if not fits({**result, 'local_action_evidence': proposed}):
                break  # Its original card remains navigation; never imply inspection.
        page = proposed
    return {**exposure, 'local_action_evidence': page}


def _displayed_refs(exposure):
    refs = {r['ref'] for r in exposure.get('local_action_evidence', {}).get('items', [])}
    refs.update(r['ref'] for r in exposure.get('fact_interfaces', {}).get('items', []))
    for card in exposure['cards']:
        refs.update([card['ref'], 'study:' + card['study_id']])
    return refs


def choose(run, network, exposure, schema):
    current, page_number = exposure, 0
    displayed = set()
    while True:
        displayed.update(_displayed_refs(current))
        role = 'selector' if page_number == 0 else f'selector-page-{page_number}'
        selected = run.invoker(role).invoke(prompt=INSTRUCTIONS+json.dumps(current,ensure_ascii=False),
                                           schema=schema,label='continuous_selector')
        metadata = action_metadata(selected)
        if not set(metadata.get('evidence_refs', [])).issubset(displayed):
            raise ValueError('action references unexposed evidence')
        if selected['operation'] != 'INSPECT':
            return selected
        ref = current['fact_interfaces']['next_ref']
        if (not ref or selected['material_refs'] != [ref] or selected['support_id'] or
                selected['continuation_window'] is not None or
                selected['study_id'] not in {c['study_id'] for c in exposure['cards']}):
            raise ValueError('INSPECT requires exactly the advertised forward Fact page')
        page_number += 1
        path = run.step_dir / f'selector-page-{page_number}-input.json'
        if not path.exists():
            page = fact_page(network, exposure['cards'], int(ref.split(':')[1]),
                             token_budget=run.state['settings']['selector_context_tokens']//4)
            write_json(path, {**exposure, 'bridge_candidates':[], 'bridge_candidate_pages':[],
                              'fact_interfaces':page,
                              'inspection_request_unverified': {
                                  'material_refs':selected['material_refs'], 'reason':selected['reason']}})
        current = read_json(path)
        run.event('selector_page_saved', page=page_number)
