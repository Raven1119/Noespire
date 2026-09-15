"""Literal, reconstructible local research views. No mathematical classification.

Numbered sections, a single unnumbered section, and explicit next_work are
independent spans. Unknown relations between sections stay unknown. A card is
not a Claim, a proof, or a promise that the recorded work can be closed.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re

from .continuous_attention import AttentionOverflow, bounded_packet

AUTHORITY = 'UNVERIFIED_RESEARCH'
FIELDS = ('object', 'boundary', 'established_components', 'remaining_gap', 'possible_deliverable')


def _hash(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def unknown():
    return {'value': 'UNKNOWN', 'source': None}


def _cell(record, field, start, end):
    text = record['scope'] if field == '@scope' else record['fields'][field]
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end-1].isspace():
        end -= 1
    return {'value': text[start:end], 'source': {
        'source_ref': record['source_ref'], 'source_message_id': record.get('source_message_id'),
        'artifact_id': record.get('artifact_id'), 'source_status': record['source_status'],
        'study_id': record['study_id'], 'scope': record['scope'],
        'source_span': {'field': field, 'start': start, 'end': end},
        'field_sha256': sha256(text.encode()).hexdigest()}}


def reconstruct(cell, records):
    """Check against the original decoded field, not a later summarization."""
    source = cell['source']
    if source is None:
        if cell['value'] != 'UNKNOWN':
            raise ValueError('invalid UNKNOWN provenance')
        return 'UNKNOWN'
    if 'parts' in source:
        value = '\n'.join(reconstruct(part, records) for part in source['parts'])
        if value != cell['value']:
            raise ValueError('combined research source provenance changed')
        return value
    for record in records:
        if (record['source_ref'] == source['source_ref'] and
                record['study_id'] == source['study_id'] and record['scope'] == source['scope'] and
                record.get('source_message_id') == source['source_message_id'] and
                record.get('artifact_id') == source['artifact_id']):
            span = source['source_span']; text = record['scope'] if span['field'] == '@scope' else record['fields'].get(span['field'], '')
            if (sha256(text.encode()).hexdigest() == source['field_sha256'] and
                    text[span['start']:span['end']] == cell['value']):
                return cell['value']
    raise ValueError('research object source provenance changed')


def _sections(text):
    starts = list(re.finditer(r'(?m)^\s*\d+[.)]\s+', text))
    if starts:
        return [(m.end(), starts[i+1].start() if i+1 < len(starts) else len(text))
                for i, m in enumerate(starts)]
    return [(0, len(text))] if text.strip() else []


def _sentences(text, start, end):
    # Only complete sentences/paragraphs; no character-prefix ellipsizing.
    fragment = text[start:end]
    cuts = [start] + [start+m.end() for m in re.finditer(r'(?<=[.!?])\s+(?=[A-Z])', fragment)] + [end]
    return [(a,b) for a,b in zip(cuts,cuts[1:]) if text[a:b].strip()]


def _label(record, field, start, end, names):
    text = record['scope'] if field == '@scope' else record['fields'][field]
    match = re.search(r'(?im)^\s*(?:'+names+r'):\s*(.+)(?:\n(?![A-Z_ ]+:).+)*', text[start:end])
    return _cell(record, field, start+match.start(1), start+match.end()) if match else unknown()


def _card(record, field, start, end):
    text = record['scope'] if field == '@scope' else record['fields'][field]
    spans = _sentences(text, start, end)
    obj = _label(record, field, start, end, 'object|goal')
    if obj['source'] is None:
        obj = _cell(record, field, *spans[0])
    boundary = _label(record, field, start, end, 'boundary|conditions|assumptions')
    gap = _label(record, field, start, end, 'remaining_gap|remaining gap|unresolved|obstruction')
    deliverable = _label(record, field, start, end, 'possible_deliverable|deliverable')
    established = []
    first = re.search(r'(?m)^\s*\d+[.)]\s+', text)
    prefix_start = 0
    prefix_end = first.start() if first and start >= first.end() else 0
    protocol = re.match(r'\A\s*(?:UNVERIFIED NOTES\.|Unverified notes:)\s*', text)
    if protocol:
        prefix_start = min(protocol.end(), prefix_end)
    qualification = text[prefix_start:prefix_end] + '\n' + text[start:end]
    conditions = ([boundary] if boundary['source'] else [])
    if record['scope']:
        conditions.insert(0, _cell(record, '@scope', 0, len(record['scope'])))
    tentative = r'\b(seems?|plausible|likely|should|might|may|must|would|need|unproved|unverified|if|not|no|none|never|neither|failed|conjectur\w*|hypothetic\w*|tentative\w*|open|unresolved|incomplete|unknown|assuming|unless)\b'
    for a,b in spans:
        sentence = text[a:b].strip()
        # A quoted condition is not normalized, completed, or interpreted.
        where = re.search(r'\bwhere\s', text[a:b])
        if where:
            conditions.append(_cell(record, field, a+where.start(), b))
        elif re.search(r'\b[A-Z][A-Za-z_0-9]*\s*(?:=|<=|>=|<|>)\s*\d', sentence):
            conditions.append(_cell(record, field, a,b))
        elif re.search(r'\b(?:If|Assume|Assuming|Provided|Unless)\b', sentence):
            conditions.append(_cell(record, field, a,b))
        if gap['source'] is None and re.match(
                r'(?:The )?(?:remaining|unresolved|missing) (?:gap|step|issue|link|obstruction)\b', sentence, re.I):
            gap = _cell(record, field, a,b)
        if deliverable['source'] is None and re.match(
                r'(?:Construct|Extract|Produce|Submit|Return|Give|Prove|Derive|Establish)\b', sentence) and re.search(
                r'\b(lemma|fact|reduction|construction|counterexample|certificate|identity|matrix|example)\b', sentence, re.I):
            deliverable = _cell(record, field, a,b)
        # Conservative explicit assertions only. Conditional/tentative language
        # is never promoted; remaining prose is available at the original ref.
        if (len(established) < 2 and len(sentence) <= 360 and
                not re.search(tentative, qualification, re.I) and
                re.match(r'(?:Direct evaluation gives\b|We (?:have )?(?:proved|derived|constructed|checked|computed)\b)', sentence)):
            established.append(_cell(record, field, a,b))
    if conditions:
        boundary = conditions[0] if len(conditions) == 1 else {
            'value':'\n'.join(c['value'] for c in conditions),'source':{'parts':conditions}}
    # A numbered object's shared preamble is kept verbatim, not silently lost
    # or interpreted as a new hypothesis. Strip only the exact protocol marker.
    if first and start >= first.end():
        if text[prefix_start:prefix_end].strip():
            prefix = _cell(record, field, prefix_start, prefix_end)
            obj = {'value':prefix['value']+'\n'+obj['value'], 'source':{'parts':[prefix,obj]}}
    return {'study_id':record['study_id'], 'scope':record['scope'], 'object':obj,
            'boundary':boundary, 'established_components':established, 'remaining_gap':gap,
            'possible_deliverable':deliverable, 'evidence_refs':[record['source_ref']],
            'authority':AUTHORITY, 'status':'ACTIVE', 'origins':[{
                'source_ref':record['source_ref'], 'source_span':{'field':field,'start':start,'end':end},
                'source_message_id':record.get('source_message_id'), 'artifact_id':record.get('artifact_id'),
                'source_status':record['source_status'], 'lineage':record['lineage']}],
            'source_identity':sha256(text[start:end].encode()).hexdigest(),
            'derivation':'literal-sections-v1'}


def _dedup_key(card):
    values={k:([v['value'] for v in card[k]] if k=='established_components' else card[k]['value']) for k in FIELDS}
    return [card['study_id'], card['scope'], card['source_identity'], values]


def derive_cards(records):
    cards = []
    for record in records:
        fields = record['fields']
        main = next((k for k in ('derivation','continuation','text','focus') if fields.get(k, '').strip()), None)
        if main is None:
            continue
        sections = _sections(fields[main])
        for field, spans in [(main, sections), ('next_work', _sections(fields.get('next_work','')))]:
            if field == main and field == 'next_work':
                continue
            for start,end in spans:
                card = _card(record, field, start,end)
                # A checkpoint's global gap can qualify a single object. It is
                # not distributed across independently numbered objects.
                if field == main and len(sections) == 1 and fields.get('obstruction'):
                    card['remaining_gap'] = _cell(record, 'obstruction', 0,len(fields['obstruction']))
                key = _dedup_key(card)
                lineage = set(record['lineage'])
                match = next((c for c in cards if
                    _dedup_key(c) == key and
                    lineage.intersection(r for o in c['origins'] for r in o['lineage'])), None)
                if match:
                    if card['origins'][0] not in match['origins']:
                        match['origins'] += card['origins']
                    match['evidence_refs'] = list(dict.fromkeys(match['evidence_refs']+card['evidence_refs']))
                    continue
                # Status, time, accepted results and timeout counters never
                # identify an object. Uncertain lineage stays a separate card.
                card['object_id'] = 'research-object:'+_hash([key, sorted(lineage)])[:24]
                cards.append(card)
    return cards


def lifecycle(card, network):
    """Only exact ordinary Claim-bound accepted results resolve a derived view.

    No result_at_visit/semantic matching, no mutation, and no timeout-based
    abandonment. Historical selector_input snapshots remain immutable.
    """
    # A title/headline is not an explicit complete Claim binding. Extra source
    # content/conditions keep the object ACTIVE rather than guessing resolution.
    obj = card['object']['value']
    if card['source_identity'] != sha256(obj.encode()).hexdigest():
        return deepcopy(card)
    from .proof_graph import ProofObligation
    proposed = ProofObligation.create(network.problem_id,card['scope'],card['object']['value'])
    for fact_id in network.data['fact_bindings'].get(proposed.obligation_id, []):
        try:
            fact = network.visible_fact(fact_id,card['scope'])
        except ValueError:
            continue
        if fact.statement == proposed.statement:
            return {**deepcopy(card),'status':'RESOLVED','resolution_fact_id':fact_id}
    return deepcopy(card)


def project(card):
    return {'object_id':card['object_id'], 'study_id':card['study_id'],
        **{k:([x['value'] for x in card[k]] if k=='established_components' else card[k]['value']) for k in FIELDS},
        'evidence_refs':card['evidence_refs']}


def object_page(cards, offset=0, *, token_budget, fits=None):
    if type(offset) is not int or not 0 <= offset <= len(cards):
        raise ValueError('invalid research object page offset')
    def check(page):
        if fits:
            return fits(page)
        try:
            bounded_packet({'research_object_cards':page},token_budget)
            return True
        except AttentionOverflow:
            return False
    page={'authority':AUTHORITY,'items':[],'unexpanded':[], 'next_ref':None, 'total':len(cards)}
    for i in range(offset,min(offset+16,len(cards))):
        following = f'research-objects:{i+1}' if i+1<len(cards) else None
        item = project(cards[i])
        proposed = {**page,'items':page['items']+[item],'next_ref':following}
        if not check(proposed):
            if page['items'] or page['unexpanded']:
                page['next_ref']=f'research-objects:{i}'; break
            notice={'object_id':cards[i]['object_id'],'study_id':cards[i]['study_id'],
                    'evidence_refs':cards[i]['evidence_refs'],'reason':'intact_object_exceeds_page_budget'}
            proposed={**page,'unexpanded':[notice],'next_ref':following}
            if not check(proposed):
                raise AttentionOverflow({'estimated_tokens':token_budget+1}, token_budget)
        page=proposed
    else:
        end=min(offset+16,len(cards))
        page['next_ref']=f'research-objects:{end}' if end<len(cards) else None
    if not check(page):
        raise AttentionOverflow({'estimated_tokens':token_budget+1}, token_budget)
    return page


def collect_records(exposure, studies, *, artifact_store=None, checkpoint_store=None):
    """Only exposed Studies' immutable local sources; no global graph scan."""
    records=[]
    historical=[]
    for card in exposure['cards']:
        study=studies[card['study_id']]
        checkpoints=[]
        if checkpoint_store:
            for path, _ in checkpoint_store._records(study['study_id']):
                original=checkpoint_store.read_material(study,path.relative_to(checkpoint_store.directory).as_posix())
                if original:
                    checkpoints.append(original)
        original_study=study
        if study.get('research_delivery_ref') and checkpoint_store:
            from .run_storage import read_json
            original_study=read_json(checkpoint_store.directory/card['ref'])
        records.append({'source_ref':card['ref'],'study_id':study['study_id'],'scope':study['scope'],
            'source_status':'RECORDED_STUDY','lineage':[r for r in (card['ref'], original_study.get('previous_revision')) if r],
            'fields':{k:original_study.get(k,'') for k in ('focus','continuation','next_work')}})
        for checkpoint in checkpoints:
            content=checkpoint['content']
            historical.append({'source_ref':checkpoint['ref'],'study_id':study['study_id'],'scope':study['scope'],
                'source_message_id':checkpoint.get('message_id'),'artifact_id':checkpoint['content_sha256'],
                'source_status':checkpoint['source_status'],'lineage':[checkpoint['call_id']],
                'fields':{k:content[k] for k in ('derivation','obstruction','next_work')}})
        # Follow only this registered Study's immutable revision chain, never
        # unrelated branches. Current revisions precede historical source pages.
        if checkpoint_store:
            from .continuous_materials import _original
            seen={card['ref']}; previous=original_study.get('previous_revision')
            while previous and previous not in seen:
                seen.add(previous)
                value=_original(checkpoint_store.directory,previous,{study['study_id']:card['ref']})
                if value is None:
                    break
                old=value['study']
                if old.get('claim_id') != study.get('claim_id'):
                    raise ValueError('research object historical Claim changed')
                historical.append({'source_ref':previous,'study_id':study['study_id'],'scope':study['scope'],
                    'source_status':'RECORDED_STUDY','lineage':[r for r in (previous, old.get('previous_revision')) if r],
                    'fields':{k:old.get(k,'') for k in ('focus','continuation','next_work')}})
                previous=old.get('previous_revision')
        if artifact_store:
            for original in artifact_store.records(study):
                if original['message_type'] != 'agent_message':
                    continue  # Program logs remain available at their original material refs.
                fields=public_fields(original['text'],study)
                if fields is None:
                    continue
                historical.append({'source_ref':original['material_ref'],'study_id':study['study_id'],
                    'scope':study['scope'],'source_status':original['source_status'],
                    'source_message_id':original['message_id'],'artifact_id':original['material_ref'].split(':')[1],
                    'lineage':[original['invocation_id']], 'fields':fields})
    return records+historical


def public_fields(text, study):
    """Known public envelopes only; do not scan arbitrary nested fields."""
    from .research_delivery import _decode, _valid, MARKER
    decoded=_decode(text)
    if decoded:
        content,_=decoded
        if not _valid(content,study):
            return None
        return {k:content[k] for k in ('derivation','obstruction','next_work')}
    if text.startswith(MARKER):
        return None
    try:
        envelope=json.loads(text)
    except ValueError:
        return None if text.lstrip().startswith(('{','[','```')) else {'text':text}
    if (isinstance(envelope,dict) and isinstance(envelope.get('continuation'),str)
            and isinstance(envelope.get('next_work'),str)):
        if envelope['continuation'].startswith(MARKER):
            return None
        return {k:envelope[k] for k in ('continuation','next_work')}
    return None
