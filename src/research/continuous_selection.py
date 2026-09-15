"""Bounded local evidence and non-authoritative research action framing."""
import json

from .continuous_attention import AttentionOverflow, bounded_packet
from .run_storage import read_json, write_json
from .research_progress import INSTRUCTIONS as PROGRESS_INSTRUCTIONS, validate_assessment, progress_page


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


INSTRUCTIONS = PROGRESS_INSTRUCTIONS + """You are the fresh local Research Selector. Choose concrete local work, not merely
'continue proving the Claim'. In reason state: the specific task; which displayed
results you will use or why not; what is new relative to them; and what resumable
work you expect to leave. Compare complete statements AND conditions: a larger
bound need not supersede a different construction or assumptions. Reasonable
nonuse, UNKNOWN relevance, new representations and deeper work are allowed.
An accepted local result can change the task: consider using it to prove an
existing OPEN Claim, establish a conditional reduction with a precise remaining
requirement, or prove a local consequence. These are optional ordinary actions,
alongside continuing unfinished research or changing direction. Request the
actual Fact references needed; do not reprove an accepted interface merely to
connect it. A conditional reduction must remove a specific unproved step using
the supplied result, not just rename the OPEN Claim. Do not require a Support or
a new subproblem when a direct proof or further research is more appropriate.
Cards are navigation, notes are unverified. Organize the decision as follows:
1. Choose the Study.
2. Inspect the visible Research Objects belonging to that Study.
3. Identify the object you will actually work on, if any.
4. Record the main object alternatives you considered in considered_objects.
5. Only then choose RESEARCH or CLOSE for the selected object.
considered_objects is an observable decision record, not a requirement to rank
every visible card or read all pages. Include only objects in the selected Study.
SELECT means this visit's object: exactly one SELECT must match selected_object_id
when it is non-null. Record at least one DEFER/REJECT if you identify a real
alternative, with a reason specific to that object. With only the SELECT entry,
give a concrete no_alternative_reason. Otherwise no_alternative_reason is null.
A null selected_object_id permits general RESEARCH with an empty list or only
DEFER/REJECT entries, never SELECT. DEFER means not this visit, not low value,
immaturity, falsity or permanent parking. REJECT requires visible evidence that
the object is unsuitable for this action; UNKNOWN gap alone is not rejection.
An object mentioned only as a supporting method does not count as an alternative.
If it is also an independent actionable alternative, record its disposition.
These records do not change scheduling or truth. Other Studies may be background
in reason. Explain object comparisons there; UNKNOWN remains unknown, not a
readiness judgment. Object cards are UNVERIFIED_RESEARCH, not proof text or
accepted Facts. evidence_refs locate originals. fact_interfaces show statements with
original scope, NOT automatic target premises. Request fact:<id>
in material_refs for ordinary exact-scope use; foreign BRIDGE_CANDIDATE inspection
retains conditions and requires a separately verified bridge before proof use.
Never infer correspondence or authority from lexical overlap or an ID. Request
exact Study/object/search/evidence refs when needed; known_fact_ids and
context_requests are leads, not proof. representation_ref gives transport views,
not truth of an open Claim. A forced_study_id must be served: choose HOW. CONNECT
may investigate exposed regions; COMPOSE requires a listed ready Support.
continuation_window selects zero-based unverified-note lines, never assumptions
or proofs. To inspect before deciding, return operation=INSPECT with exactly one
material_ref: the currently advertised fact_interfaces.next_ref, research_progress.next_ref,
research_object_cards.next_ref, or an evidence_ref of a displayed object card in
the selected Study. Use support_id='' and continuation_window=null. This reads
that forward page or complete unverified source then asks for your action; it is
not a Worker service. Any prior inspection_request_unverified is reading
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


def fact_page(network, cards, offset=0, *, token_budget, reserved=None, recent_first=False):
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
    if recent_first:
        # Round-robin the most recently registered results of exposed Studies.
        # This is provenance order, not strength, coverage, or mathematical value.
        sequences = [list(reversed([k for k in c.get('known_fact_ids', []) if k in owners])) for c in cards]
        keys = list(dict.fromkeys(k for i in range(max(map(len, sequences), default=0))
                                 for seq in sequences for k in seq[i:i+1]))
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
        if recent_first:
            item['predecessor_refs'] = ['fact:'+key for key in
                network.visible_fact(keys[i], source['scope']).predecessors]
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
        page = fact_page(network, exposure['cards'], token_budget=token_budget, reserved=reserved,
                         recent_first=exposure.get('fact_order') == 'RECENT_PER_STUDY')
    except AttentionOverflow:
        # Existing foreign navigation occupies the allocation. An empty first
        # page is a pointer to a separate intact page, not dropped conditions.
        available = fact_page(network, exposure['cards'], token_budget=token_budget,
                              recent_first=exposure.get('fact_order') == 'RECENT_PER_STUDY')
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


def _fits(exposure, schema, token_budget):
    try:
        bounded_packet({'prompt': INSTRUCTIONS + json.dumps(exposure, ensure_ascii=False),
                        'schema': schema}, token_budget)
    except AttentionOverflow:
        return False
    return True


def add_object_cards(exposure, cards, schema, *, token_budget, offset=0):
    """Spend existing attention on intact object interfaces; originals stay local."""
    from .research_objects import object_page, AUTHORITY
    base = {**exposure, 'local_action_evidence': {'items': [], 'unexpanded': []}}
    def fits(page):
        return _fits({**base, 'research_object_cards': page}, schema, token_budget)
    try:
        page = object_page(cards, offset, token_budget=token_budget, fits=fits)
    except AttentionOverflow:
        page = {'authority': AUTHORITY, 'items': [], 'unexpanded': [],
                'next_ref': f'research-objects:{offset}' if offset < len(cards) else None,
                'total': len(cards)}
        if not _fits({**base, 'research_object_cards': page}, schema, token_budget):
            raise
    return {**base, 'research_object_cards': page}


def _object_rows(exposure, *, include_unexpanded=False):
    page = exposure.get('research_object_cards', {})
    return page.get('items', []) + (page.get('unexpanded', []) if include_unexpanded else [])


def object_metadata(selected, displayed):
    """Validate identity/scope only; this never decides whether an object can close."""
    if 'selected_object_id' not in selected:
        return {}  # Preserve pre-extension frozen action packets.
    key = selected['selected_object_id']
    if key is not None:
        if not isinstance(key, str) or not key or key not in displayed:
            raise ValueError('Selector chose an unexposed research object')
        if displayed[key] != selected['study_id']:
            raise ValueError('selected research object belongs to another Study')
    return {'selected_object_id': key}


def validate_object_comparison(selected, displayed):
    """Check observable accounting, never the mathematical merits of a reason."""
    if selected.get('operation') == 'INSPECT':
        return  # Reading has no selected research action or object disposition.
    if not {'selected_object_id', 'considered_objects', 'no_alternative_reason'} <= selected.keys():
        raise ValueError('incomplete object comparison contract')
    object_metadata(selected, displayed)
    entries = selected['considered_objects']
    if not isinstance(entries, list):
        raise ValueError('considered_objects must be a list')
    seen, chosen = set(), []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'object_id', 'disposition', 'reason'}:
            raise ValueError('invalid considered object entry')
        key = entry['object_id']
        if not isinstance(key, str) or key not in displayed:
            raise ValueError('considered object was not exposed')
        if displayed[key] != selected['study_id']:
            raise ValueError('considered object belongs to another Study')
        if key in seen:
            raise ValueError('duplicate considered object')
        seen.add(key)
        if entry['disposition'] not in ('SELECT', 'DEFER', 'REJECT'):
            raise ValueError('invalid object disposition')
        if not isinstance(entry['reason'], str) or not entry['reason'].strip():
            raise ValueError('considered object reason must be nonempty')
        if entry['disposition'] == 'SELECT':
            chosen.append(key)
    target = selected['selected_object_id']
    if chosen != ([] if target is None else [target]):
        raise ValueError('SELECT must uniquely match selected_object_id')
    reason = selected['no_alternative_reason']
    if target is not None and len(entries) == 1:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('single selected object requires no_alternative_reason')
    elif reason is not None:
        raise ValueError('no_alternative_reason is only for a single selected object')


def saved_object_metadata(run, selected, exposure):
    """Recheck the confirmed selection against its immutable displayed pages."""
    displayed = {r['object_id']: r['study_id'] for r in _object_rows(exposure)}
    facts = {r['ref'] for r in exposure.get('fact_interfaces', {}).get('items', [])}
    for path in run.step_dir.glob('selector-page-*-input.json'):
        page = read_json(path)
        displayed.update((r['object_id'], r['study_id']) for r in _object_rows(page))
        facts.update(r['ref'] for r in page.get('fact_interfaces', {}).get('items', []))
    metadata = object_metadata(selected, displayed)
    path = run.step_dir / 'selector_input.json'
    frozen = read_json(path) if path.exists() else {}
    # Legacy confirmed decisions are not rewritten into invented comparisons.
    # New frozen inputs require the record even if fields were later removed.
    if frozen.get('object_comparison_contract') == 1 or any(
            k in selected for k in ('considered_objects', 'no_alternative_reason')):
        validate_object_comparison(selected, displayed)
    validate_assessment(selected, facts)
    return metadata


def _displayed_refs(exposure):
    refs = {r['ref'] for r in exposure.get('local_action_evidence', {}).get('items', [])}
    refs.update(r['ref'] for r in exposure.get('fact_interfaces', {}).get('items', []))
    refs.update(r['source_ref'] for r in exposure.get('research_progress', {}).get('items', [])
                + exposure.get('research_progress', {}).get('unexpanded', []))
    refs.update(ref for row in _object_rows(exposure, include_unexpanded=True) for ref in row['evidence_refs'])
    for card in exposure['cards']:
        refs.update([card['ref'], 'study:' + card['study_id']])
        # These are displayed navigation sources, not accepted proof premises.
        refs.update(card.get('evidence_refs', []))
    return refs


def _inspection_base(exposure, current, selected):
    """Start a fresh bounded reading window, retaining forward navigation."""
    value = {**exposure, 'bridge_candidates': [], 'bridge_candidate_pages': [],
        'local_action_evidence': {'items': [], 'unexpanded': []},
        'fact_interfaces': {'items': [], 'unexpanded': [],
                            'next_ref': current.get('fact_interfaces', {}).get('next_ref')},
        'inspection_request_unverified': {
            'material_refs': selected['material_refs'], 'reason': selected['reason']}}
    if 'research_object_cards' in current:
        value['research_object_cards'] = {**current['research_object_cards'], 'items': [], 'unexpanded': []}
    if 'selected_object_id' in selected:
        value['inspection_request_unverified']['selected_object_id'] = selected['selected_object_id']
    # Keep one latest reading intent per exposed Study. This never pins a choice,
    # grants a Fact, or carries an unbounded page transcript into the next session.
    notes = {r['study_id']: dict(r) for r in current.get('inspection_intents_unverified', [])}
    notes[selected['study_id']] = {'study_id': selected['study_id'],
        'material_refs': selected['material_refs'], 'reason': selected['reason']}
    value['inspection_intents_unverified'] = list(notes.values())
    if 'research_progress' in current:
        value['research_progress'] = current['research_progress']
    return value


def _reading_budget(value, schema, limit):
    """Prior judgments yield space to the newly requested intact material page."""
    from copy import deepcopy
    value = deepcopy(value)
    reserve = 'x' * limit  # bytes for the existing quarter-window Fact page
    def fits():
        return _fits({**value, 'reserved_material_window': reserve}, schema, limit)
    if not fits() and value.get('research_progress', {}).get('items'):
        page = value['research_progress']
        page['unexpanded'] += [{'study_id': r['study_id'], 'source_ref': r['source_ref'],
            'reason': 'prior_judgment_deferred_for_requested_material'} for r in page['items']]
        page['items'] = []
    for note in value.get('inspection_intents_unverified', []):
        if fits():
            break
        note.pop('reason', None)
        note['unexpanded'] = 'Complete intention remains in confirmed Selector evidence.'
    return value


def choose(run, network, exposure, schema, *, object_index=None, progress_index=None):
    current, page_number = exposure, 0
    displayed, objects, source_owners, inspected, fact_interfaces = set(), {}, {}, set(), set()
    while True:
        displayed.update(_displayed_refs(current))
        fact_interfaces.update(r['ref'] for r in current.get('fact_interfaces', {}).get('items', []))
        objects.update((r['object_id'], r['study_id']) for r in _object_rows(current))
        for row in _object_rows(current, include_unexpanded=True):
            for ref in row['evidence_refs']:
                source_owners.setdefault(ref, set()).add(row['study_id'])
        for row in current.get('research_progress', {}).get('items', []) + current.get('research_progress', {}).get('unexpanded', []):
            source_owners.setdefault(row['source_ref'], set()).add(row['study_id'])
        role = 'selector' if page_number == 0 else f'selector-page-{page_number}'
        selected = run.invoker(role).invoke(prompt=INSTRUCTIONS+json.dumps(current,ensure_ascii=False),
                                           schema=schema,label='continuous_selector')
        # INSPECT retains material/evidence permissions, not final action rules.
        if not set(selected.get('evidence_refs', [])).issubset(displayed):
            raise ValueError('action references unexposed evidence')
        if selected['operation'] != 'INSPECT':
            action_metadata(selected)
            validate_object_comparison(selected, objects)
            validate_assessment(selected, fact_interfaces)
            return selected
        refs = selected['material_refs']
        if (not isinstance(refs, list) or len(refs) != 1 or not isinstance(refs[0], str)
                or refs[0] in inspected or selected['support_id']
                or selected['continuation_window'] is not None
                or selected['study_id'] not in {c['study_id'] for c in exposure['cards']}):
            raise ValueError('INSPECT requires one unused advertised forward page or displayed object source')
        ref = refs[0]
        fact_ref = current.get('fact_interfaces', {}).get('next_ref')
        object_ref = current.get('research_object_cards', {}).get('next_ref')
        progress_ref = current.get('research_progress', {}).get('next_ref')
        source_allowed = selected['study_id'] in source_owners.get(ref, set())
        if not ((fact_ref and ref == fact_ref) or (object_ref and ref == object_ref)
                or (progress_ref and ref == progress_ref) or source_allowed):
            raise ValueError('INSPECT requires an advertised forward page or same-Study displayed object source')
        if ref == object_ref and object_index is None:
            raise ValueError('research object page has no frozen source index')
        inspected.add(ref)
        page_number += 1
        path = run.step_dir / f'selector-page-{page_number}-input.json'
        if not path.exists():
            value = _inspection_base(exposure, current, selected)
            limit = run.state['settings']['selector_context_tokens']
            # Complete reading intentions are bounded too. Retain an honest notice
            # rather than a clipped mathematical explanation when they exceed it.
            for note in value['inspection_intents_unverified']:
                try:
                    bounded_packet(value['inspection_intents_unverified'], max(1, limit//4))
                except AttentionOverflow:
                    note.pop('reason', None)
                    note['unexpanded'] = 'Prior complete reading intent remains in confirmed Selector evidence.'
            value = _reading_budget(value, schema, limit)
            if ref == fact_ref:
                value['fact_interfaces'] = fact_page(network, exposure['cards'], int(ref.split(':')[1]),
                    token_budget=limit//4, recent_first=exposure.get('fact_order') == 'RECENT_PER_STUDY')
            elif ref == progress_ref:
                if progress_index is None:
                    raise ValueError('research progress page has no frozen source index')
                value['research_progress'] = {'items': [], 'unexpanded': [], 'next_ref': progress_ref}
                from .continuous_research import _progress_fits
                value['research_progress'] = progress_page(progress_index, int(ref.split(':')[1]),
                    lambda page: _fits({**value, 'research_progress': page}, schema, limit)
                        and _progress_fits(page, limit//4))
                if value['research_progress']['next_ref'] == ref:
                    raise AttentionOverflow({'estimated_tokens': limit+1}, limit)
            elif ref == object_ref:
                value = add_object_cards(value, object_index['cards'], schema,
                                         token_budget=limit, offset=int(ref.split(':')[1]))
                if not value['research_object_cards']['items'] and value['research_object_cards']['next_ref'] == ref:
                    raise AttentionOverflow({'estimated_tokens': limit+1}, limit)
            else:
                from .continuous_materials import load_materials
                study = read_json(run.directory / run.state['studies'][selected['study_id']])
                facts, materials, notices = load_materials(run.root, study, [ref], run.state['studies'], network)
                if facts:
                    raise ValueError('research object inspection cannot supply accepted Facts')
                value['local_action_evidence'] = {'items': materials, 'unexpanded': notices}
                if not _fits(value, schema, limit):
                    value['local_action_evidence'] = {'items': [], 'unexpanded': [
                        {'ref': ref, 'study_id': selected['study_id'],
                         'reason': 'complete_source_exceeds_selector_context'}]}
            if not _fits(value, schema, limit):
                bounded_packet({'prompt': INSTRUCTIONS+json.dumps(value,ensure_ascii=False), 'schema': schema}, limit)
            write_json(path, value)
        current = read_json(path)
        run.event('selector_page_saved', page=page_number)
