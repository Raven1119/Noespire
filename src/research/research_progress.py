"""Evidence-linked research judgments, never Fact truth or semantic subsumption.

The existing Selector writes these judgments in its confirmed selection. The
next local exposure derives a view from that journal and Study provenance; no
additional model, graph mutation, or globally accumulated transcript is needed.
"""
from copy import deepcopy
from hashlib import sha256
import json

from .run_storage import read_json, write_json
from .continuous_attention import bounded_packet, AttentionOverflow

AUTHORITY = 'UNVERIFIED_RESEARCH_JUDGMENT'
_TEXT = {'type': 'string'}


def _object(fields):
    return {'type': 'object', 'properties': fields, 'required': list(fields),
            'additionalProperties': False}


ASSESSMENT_SCHEMA = {'anyOf': [{'type': 'null'}, _object({
    **{k: _TEXT for k in ('series', 'established', 'latest_delta', 'next_question', 'why_this_action')},
    'judgments': {'type': 'array', 'items': _object({
        'work_refs': {'type': 'array', 'items': _TEXT,
            'description': 'Displayed object/material refs being evaluated, not proof authority.'},
        'evidence_fact_refs': {'type': 'array', 'items': _TEXT,
            'description': 'Exact fact:<id> interfaces inspected in full; no prose.'},
        'explanation': {**_TEXT, 'description': 'Advisory prose, never an identifier.'}})},
})]}

INSTRUCTIONS = """Research progress is a change in what remains worth investigating,
not a count of new Facts. In research_assessment organize the selected line of
work: strongest established interfaces with their conditions, latest delta,
covered earlier work (only if the same mathematical content is covered), method
limitations, the unresolved question, and why this action addresses it. Group a
continuing construction as one series rather than treating each endpoint as an
independent advance. Distinguish incremental coverage, different constructions,
method limitations and new structural/proof interfaces in ordinary language.
Do not infer coverage from a larger number or from predecessor links. Different
conditions or construction value can justify retaining both results. Coverage is
your revisable research judgment, not Fact deletion or proof authority.
If extending the same construction/argument again, explain the open research
question (for example a failure law or structural test), not merely ease of
producing a Fact. Finite exploration and CLOSE remain legitimate.
For relevant verified method limitations, state whether this action remains
inside that restricted family or which structure/assumption it changes; remaining
inside can be justified, and UNKNOWN is allowed. Inspect complete Fact interfaces
before judging applicability; do not reason from IDs or truncated conditions.
On later pages, absence of a Study's cards is not evidence against its work.
Reconsider recorded inspection_intents_unverified before the final action; explain
continuing, changing or deferring relevant intentions. These never pin a Study.
Separate subjects (work_refs: displayed objects/materials), evidence_fact_refs
(exact fact:<id> interfaces read in full), and explanation (advisory prose).
Subjects need not be Facts. Empty evidence records uncertainty, not an established
limitation. Malformed optional judgments are retained raw with diagnostics and
dropped from task context; they cannot veto an otherwise legal action.
Only cite Fact interfaces actually displayed in full in this decision's pages. A prior
research_progress assessment is UNVERIFIED and may be stale; re-read its referenced
interfaces when relying on it. Null research_assessment is allowed for inspection
or when no evidenced research assessment is possible; explain uncertainty in reason.
The recorded assessment supplies task context, never accepted_facts or predecessors.
INSPECT is only a material request. Object comparison and final research-action
requirements apply when submitting ADVANCE/CONNECT/COMPOSE, not while reading.
"""


def validate_assessment(selected, displayed_facts, displayed_work=()):
    """Internal shape/reference check; callers must use the fail-soft projection."""
    value = selected.get('research_assessment')
    if value is None:
        return
    fields = ASSESSMENT_SCHEMA['anyOf'][1]['properties']
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError('invalid research assessment interface')
    for key in ('series', 'established', 'latest_delta', 'next_question', 'why_this_action'):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError('research assessment needs explicit judgments or UNKNOWN')
    if not isinstance(value['judgments'], list):
        raise ValueError('research judgments must be a list')
    for row in value['judgments']:
        if not isinstance(row, dict) or set(row) != {'work_refs', 'evidence_fact_refs', 'explanation'}:
            raise ValueError('invalid research judgment interface')
        if not isinstance(row['explanation'], str) or not row['explanation'].strip():
            raise ValueError('research judgment explanation must be text')
        for field, available in [('work_refs', displayed_work), ('evidence_fact_refs', displayed_facts)]:
            refs = row[field]
            if (not isinstance(refs, list) or any(not isinstance(r, str) or not r.strip() for r in refs)
                    or len(set(refs)) != len(refs) or not set(refs).issubset(available)):
                raise ValueError('invalid or unexposed research judgment ' + field)


def displayed_context(step_dir, exposure):
    from .continuous_selection import _displayed_refs, _object_rows
    pages = [exposure] + [read_json(p) for p in sorted(step_dir.glob('selector-page-*-input.json'))]
    facts, work = {}, set()
    for page in pages:
        work.update(_displayed_refs({'cards': [], **page}))
        work.update(r['object_id'] for r in _object_rows(page))
        facts.update((r['ref'], r) for r in page.get('fact_interfaces', {}).get('items', []))
    return facts, work


def project_assessment(selected, fact_interfaces, work_refs, network, *, token_budget=2000):
    """Discard invalid advisory content; never soften material/action authority."""
    result = {'authority': AUTHORITY, 'status': 'ABSENT', 'content': None,
              'diagnostics': [], 'unavailable_sources': []}
    if selected.get('research_assessment') is None:
        return result
    try:
        validate_assessment(selected, fact_interfaces, work_refs)
    except (ValueError, TypeError, KeyError) as error:
        return {**result, 'status': 'DROPPED', 'diagnostics': [str(error)]}
    value = selected['research_assessment']
    try:
        bounded_packet(value, token_budget)
    except AttentionOverflow:
        return {**result, 'status': 'DROPPED', 'diagnostics': ['Complete advisory exceeds its material allocation; raw evidence retained.']}
    refs = {r for row in value['judgments'] for r in row['evidence_fact_refs']}
    for ref in sorted(refs):
        try:
            actual = network.inspect_fact(ref.removeprefix('fact:'))
        except ValueError:
            result['unavailable_sources'].append(ref)
            continue
        shown = fact_interfaces[ref]
        if actual['statement'] != shown['exact_statement'] or actual['scope'] != shown['source_scope']:
            result['unavailable_sources'].append(ref)
    if result['unavailable_sources']:
        return {**result, 'status': 'DROPPED', 'diagnostics': ['Evidence interface is no longer available as inspected.']}
    return {**result, 'status': 'USABLE', 'content': deepcopy(value)}


def record_assessment(step_dir, selected, exposure, network, *, token_budget=2000):
    """Separate immutable diagnostic receipt; raw selection remains untouched."""
    facts, work = displayed_context(step_dir, exposure)
    result = project_assessment(selected, facts, work, network, token_budget=token_budget)
    source_hash = sha256(json.dumps(selected, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    path = step_dir / 'research_assessment.json'
    if path.exists():
        if read_json(path)['source_selection_sha256'] != source_hash:
            raise ValueError('confirmed selection changed after advisory projection')
    elif result['status'] != 'ABSENT':
        write_json(path, {'source_selection_sha256': source_hash, 'contract_version': 2, **result})
    # Recompute current availability on recovery rather than trust a stale receipt.
    return result


def assessment_material(projection):
    return ({'research_assessment_unverified': {'authority': AUTHORITY, 'content': projection['content']}}
            if projection['status'] == 'USABLE' else {})


def fit_worker_advisory(run, packet):
    """An optional judgment cannot displace ordinary evidence or a checkpoint."""
    if 'research_assessment_unverified' not in packet:
        return packet
    from .continuous_research import worker_prompt, _WORKER_SCHEMA
    try:
        bounded_packet({'prompt': worker_prompt(packet), 'schema': _WORKER_SCHEMA},
                       run.state['settings']['worker_context_tokens'])
    except AttentionOverflow:
        packet = dict(packet)
        packet.pop('research_assessment_unverified')
        path = run.step_dir / 'research_assessment_capacity.json'
        if not path.exists():
            write_json(path, {'authority': AUTHORITY, 'status': 'DROPPED',
                'diagnostics': ['Advisory omitted at full Worker material capacity; raw selection retained.']})
    return packet


def history_rows(directory, exposure, schedule, network):
    """Only the last serviced decision of each already exposed Study."""
    rows = []
    for card in exposure['cards']:
        visit = schedule.get('last_served', {}).get(card['study_id'])
        if visit is None:
            continue
        ref = f'visits/{visit:08d}/selection.json'
        path = directory / ref
        if not path.exists():
            continue
        plan = read_json(path)
        selected = plan['selected']
        if selected.get('study_id') != card['study_id']:
            continue
        facts, work = displayed_context(path.parent, plan.get('exposure', {'cards': []}))
        result = project_assessment(selected, facts, work, network)
        rows.append({'study_id': card['study_id'], 'source_ref': ref,
            'authority': AUTHORITY, 'assessment': result['content'],
            'prior_action': {k: selected[k] for k in ('reason', 'local_object', 'remaining_gap') if k in selected},
            'assessment_status': result['status'], 'diagnostics': result['diagnostics'],
            'unavailable_sources': result['unavailable_sources']})
    return rows


def progress_page(rows, offset, fits):
    if type(offset) is not int or not 0 <= offset <= len(rows):
        raise ValueError('invalid research progress offset')
    page = {'authority': AUTHORITY, 'items': [], 'unexpanded': [], 'next_ref': None}
    for i in range(offset, min(offset + 16, len(rows))):
        following = f'research-progress:{i+1}' if i+1 < len(rows) else None
        candidate = {**page, 'items': page['items'] + [rows[i]], 'next_ref': following}
        if not fits(candidate):
            if page['items'] or page['unexpanded']:
                page['next_ref'] = f'research-progress:{i}'
                break
            candidate = {**page, 'unexpanded': [{'study_id': rows[i]['study_id'],
                'source_ref': rows[i]['source_ref'], 'reason': 'complete_assessment_exceeds_window'}],
                'next_ref': following}
            if not fits(candidate):
                return {**page, 'next_ref': f'research-progress:{i}'}
        page = candidate
    else:
        end = min(offset + 16, len(rows))
        page['next_ref'] = f'research-progress:{end}' if end < len(rows) else None
    return page
