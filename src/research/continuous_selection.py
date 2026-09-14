"""Read-only, paged Fact interfaces for one local Selector opportunity."""
import json

from .continuous_attention import AttentionOverflow, bounded_packet
from .run_storage import read_json, write_json


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


def choose(run, network, exposure, schema):
    current, page_number = exposure, 0
    while True:
        role = 'selector' if page_number == 0 else f'selector-page-{page_number}'
        selected = run.invoker(role).invoke(prompt=INSTRUCTIONS+json.dumps(current,ensure_ascii=False),
                                           schema=schema,label='continuous_selector')
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
