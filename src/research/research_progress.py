"""Evidence-linked research judgments, never Fact truth or semantic subsumption.

The existing Selector writes these judgments in its confirmed selection. The
next local exposure derives a view from that journal and Study provenance; no
additional model, graph mutation, or globally accumulated transcript is needed.
"""
from copy import deepcopy

from .run_storage import read_json

AUTHORITY = 'UNVERIFIED_RESEARCH_JUDGMENT'
_TEXT = {'type': 'string'}


def _object(fields):
    return {'type': 'object', 'properties': fields, 'required': list(fields),
            'additionalProperties': False}


ASSESSMENT_SCHEMA = {'anyOf': [{'type': 'null'}, _object({
    **{k: _TEXT for k in ('series', 'established', 'latest_delta', 'next_question', 'why_this_action')},
    'fact_refs': {'type': 'array', 'items': _TEXT},
    'covered_work': {'type': 'array', 'items': _object({
        'fact_ref': _TEXT, 'covered_by': _TEXT, 'reason': _TEXT})},
    'method_limits': {'type': 'array', 'items': _object({
        'fact_ref': _TEXT, 'action_relation': _TEXT})},
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
Only use fact_refs actually displayed in full in this decision's pages. A prior
research_progress assessment is UNVERIFIED and may be stale; re-read its referenced
interfaces when relying on it. Null research_assessment is allowed for inspection
or when no evidenced research assessment is possible; explain uncertainty in reason.
The recorded assessment supplies task context, never accepted_facts or predecessors.
INSPECT is only a material request. Object comparison and final research-action
requirements apply when submitting ADVANCE/CONNECT/COMPOSE, not while reading.
"""


def validate_assessment(selected, displayed_facts):
    value = selected.get('research_assessment')
    if value is None:
        return
    fields = ASSESSMENT_SCHEMA['anyOf'][1]['properties']
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError('invalid research assessment interface')
    for key in ('series', 'established', 'latest_delta', 'next_question', 'why_this_action'):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError('research assessment needs explicit judgments or UNKNOWN')
    refs = value['fact_refs']
    if (not isinstance(refs, list) or any(not isinstance(r, str) for r in refs)
            or len(set(refs)) != len(refs) or not set(refs).issubset(displayed_facts)):
        raise ValueError('research assessment references an uninspected Fact interface')
    for key, expected in [('covered_work', {'fact_ref', 'covered_by', 'reason'}),
                          ('method_limits', {'fact_ref', 'action_relation'})]:
        if not isinstance(value[key], list):
            raise ValueError('research assessment relations must be lists')
        for row in value[key]:
            if (not isinstance(row, dict) or set(row) != expected or
                    any(not isinstance(v, str) or not v.strip() for v in row.values())):
                raise ValueError('invalid research assessment relation')
            used = [row['fact_ref']] + ([row['covered_by']] if key == 'covered_work' else [])
            if not set(used).issubset(refs):
                raise ValueError('research relation lacks inspected Fact references')
            if key == 'covered_work' and row['fact_ref'] == row['covered_by']:
                raise ValueError('research coverage cannot reference itself')


def assessment_material(selected):
    value = selected.get('research_assessment')
    return ({'research_assessment_unverified': {'authority': AUTHORITY, 'content': deepcopy(value)}}
            if value is not None else {})


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
        selected = read_json(path)['selected']
        value = selected.get('research_assessment')
        if selected.get('study_id') != card['study_id']:
            continue
        # A revoked/missing source invalidates this derived judgment, not truth.
        invalid = []
        for fact_ref in (value or {}).get('fact_refs', []):
            try:
                network.inspect_fact(fact_ref.removeprefix('fact:'))
            except ValueError:
                invalid.append(fact_ref)
        rows.append({'study_id': card['study_id'], 'source_ref': ref,
            'authority': AUTHORITY, 'assessment': value if not invalid else None,
            'prior_action': {k: selected[k] for k in ('reason', 'local_object', 'remaining_gap') if k in selected},
            'unavailable_sources': invalid})
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
