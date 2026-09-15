"""Bounded navigation and exact reads of registered local research originals.

Historical notes and invocation evidence remain unverified material. Only an
explicit accepted Fact reference can enter the accepted-predecessor window.
"""
from hashlib import sha256
from itertools import islice
from pathlib import Path
import re

from .graph import FactGraph
from .fact import _normalize
from .run_storage import read_json
from .continuous_attention import bounded_packet, AttentionOverflow


_STUDY = re.compile(r"studies/([A-Za-z0-9_-]+)/([0-9]{6,}(?:-verified)?|(?:timeout|capacity|materials)-[0-9]{8,})\.json\Z")
_VISIT = re.compile(r"visits/[0-9]{8,}/(?:packet|worker_result|verification|admission|feedback)\.json\Z")
_OBJECT = re.compile(r"obj-[A-Za-z0-9]+\Z")
_PAGE_SIZE = 16


def _local_file(directory, ref):
    path = directory / ref
    base = directory.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        return None
    if resolved != base / ref:
        # A symlink must not turn a whitelisted name into a global-state read.
        return None
    return path if path.is_file() else None


def _registered_study(directory, study_id, study_refs):
    ref = study_refs.get(study_id, "")
    match = _STUDY.fullmatch(ref)
    if match is None or match[1] != study_id:
        return None
    path = _local_file(directory, ref)
    if path is None:
        return None
    value = read_json(path)
    if value.get("study_id") != study_id or not isinstance(value.get("scope"), str):
        raise ValueError("registered Study identity or scope is invalid")
    return value


def _check_study(value, registered):
    if value.get("study_id") != registered["study_id"] or value.get("scope") != registered["scope"]:
        raise ValueError("historical Study identity or scope changed")


def _original(directory, ref, study_refs):
    """Allow only versioned registered Studies and a visit's local evidence."""
    match = _STUDY.fullmatch(ref)
    if match:
        registered = _registered_study(directory, match[1], study_refs)
        path = _local_file(directory, ref)
        if registered is None or path is None:
            return None
        value = read_json(path)
        _check_study(value, registered)
        return {"ref": ref, "verified": False, "study": value}
    if _VISIT.fullmatch(ref):
        path = _local_file(directory, ref)
        packet_path = _local_file(directory, ref.rsplit("/", 1)[0] + "/packet.json")
        if path is None or packet_path is None:
            return None
        owner = read_json(packet_path).get("study", {})
        registered = _registered_study(directory, owner.get("study_id"), study_refs)
        if registered is None:
            return None
        _check_study(owner, registered)
        return {"ref": ref, "verified": False, "study_id": owner["study_id"],
                "scope": owner["scope"], "evidence": read_json(path)}
    return None


def _page(items, offset, next_ref):
    selected = list(islice(items, offset, offset + _PAGE_SIZE + 1))
    return selected[:_PAGE_SIZE], next_ref if len(selected) > _PAGE_SIZE else None


def _studies(directory, study_refs):
    for key in sorted(study_refs):
        value = _registered_study(directory, key, study_refs)
        if value is not None:
            yield value


def _search(directory, study_refs, network, query):
    for value in _studies(directory, study_refs):
        if query in value["focus"]:
            yield {"ref": "study:" + value["study_id"], "navigation_only": True}
    graph = FactGraph(network.root)
    for path in sorted(graph.facts_dir.glob("*.md")):
        fact = graph.get_fact(path.stem)
        if query in fact.statement:
            yield {"ref": "fact:" + fact.fact_id, "navigation_only": True}


def _related(directory, study_refs, object_ref, network):
    seen_facts = set()
    for value in _studies(directory, study_refs):
        if object_ref in value.get("object_refs", []):
            yield {"kind": "Study", "id": value["study_id"], "ref": study_refs[value["study_id"]],
                   "scope_ref": sha256(value["scope"].encode("utf-8")).hexdigest(), "navigation_only": True}
            scope = _normalize(value["scope"])
            for fact_id in value.get("known_fact_ids", []):
                if fact_id in seen_facts:
                    continue
                try:
                    fact = network.visible_fact(fact_id, scope)
                except ValueError:
                    # A Study's remembered reference may have gone stale. It
                    # neither admits a Fact nor overrides its accepted scope.
                    continue
                seen_facts.add(fact.fact_id)
                yield {"kind": "Fact", "id": fact.fact_id, "ref": "fact:" + fact.fact_id,
                       "scope_ref": sha256(scope.encode("utf-8")).hexdigest(), "navigation_only": True}


def load_materials(root, study, refs, study_refs, network):
    """Read exact local references; search/object matches are paged navigation.

    ``root`` is the problem workspace. Raw paths must match the narrow Study,
    visit or same-Study checkpoint allowlist; no state, global graph, call journal
    or arbitrary file is addressable. Distinct scopes may be compared as labelled
    unverified notes.
    Accepted Fact reads retain the network's exact-scope and revocation guards.
    """
    directory = Path(root) / "continuous_run"
    facts, unverified, notices = {}, [], []
    for ref in refs:
        if not isinstance(ref, str):
            raise ValueError("local material references must be strings")
        if ref.startswith("research_deliveries/"):
            from .research_delivery import DeliveryStore
            value = DeliveryStore(directory, read_json(directory / "state.json")["run_id"]).read_material(study, ref)
            if value is not None:
                unverified.append(value)
            else:
                notices.append({"ref": ref, "error": "unknown same-Study research checkpoint"})
            continue
        if ref.startswith(("research-artifact:", "research-artifacts:")):
            from .research_artifacts import ArtifactStore
            value = ArtifactStore(directory, read_json(directory / "state.json")["run_id"]).read_material(study, ref)
            if value is not None:
                unverified.append(value)
            else:
                notices.append({"ref": ref, "error": "unknown same-Study research artifact"})
            continue
        representation = re.fullmatch(r"representations:(ob-[0-9a-f]{24})(?::([0-9]+))?",ref)
        if representation:
            key, offset = representation[1], int(representation[2] or 0)
            rows, next_ref = _page(iter(network.representation_views(key)),offset,
                                   f"representations:{key}:{offset+_PAGE_SIZE}")
            # These are views of OPEN propositions, not accepted premises. The
            # certified equivalence does not establish either proposition.
            unverified.append({"ref":ref,"verified":False,"representation_views":rows,
                               "next_ref":next_ref,"authority":"TRANSPORT_ONLY"})
            continue
        if ref.startswith("fact:"):
            fact = network.visible_fact(ref[5:], _normalize(study["scope"]))
            facts[fact.fact_id] = {"fact_id": fact.fact_id, "statement": fact.statement}
            continue
        if ref.startswith("study:"):
            value = _registered_study(directory, ref[6:], study_refs)
            if value is not None:
                unverified.append({"ref": ref, "verified": False, "study": value})
                continue
        original = _original(directory, ref, study_refs)
        if original is not None:
            unverified.append(original)
            continue
        search_page = re.fullmatch(r"search-page:([0-9]+):(.*)", ref, re.DOTALL)
        if ref.startswith("search:") or search_page:
            offset, query = (int(search_page[1]), search_page[2]) if search_page else (0, ref[7:])
            matches, next_ref = _page(_search(directory, study_refs, network, query), offset,
                                     f"search-page:{offset + _PAGE_SIZE}:{query}")
            notices.append({"query": query, "matches": matches, "navigation_only": True, "next_ref": next_ref})
            continue
        object_page = re.fullmatch(r"object-page:([0-9]+):(obj-[A-Za-z0-9]+)", ref)
        if ref.startswith("object:") or object_page:
            offset, key = (int(object_page[1]), object_page[2]) if object_page else (0, ref[7:])
            if _OBJECT.fullmatch(key):
                path = _local_file(directory, "objects/" + key + ".json")
                if path is not None:
                    object_ref = "object:" + key
                    if object_page is None:
                        unverified.append({"ref": ref, "verified": False, "definition": read_json(path)})
                    related, next_ref = _page(_related(directory, study_refs, object_ref, network), offset,
                                             f"object-page:{offset + _PAGE_SIZE}:{key}")
                    notices.append({"object_ref": object_ref, "related": related,
                                    "navigation_only": True, "next_ref": next_ref})
                    continue
        notices.append({"ref": ref, "error": "unknown local reference"})
    return facts, unverified, notices


# Exact callable notation only: bare single-letter variables and generic operators
# are too weak to justify unsolicited navigation. No aliases or semantic matching.
_CALLABLE = re.compile(r"(?<![\w])([A-Za-z\u0370-\u03ff][A-Za-z0-9\u0370-\u03ff]*(?:_(?:\{[A-Za-z0-9]+\}|[A-Za-z0-9]+))?)(?=\s*\()")
_GENERIC = {"max", "min", "sum", "prod", "log", "exp", "sin", "cos", "if", "for"}


def _notation(text):
    return {name for name in _CALLABLE.findall(text) if name not in _GENERIC
            and (len(name) > 1 or '\u0370' <= name <= '\u03ff')}


def _bridge_rows(root, study, study_refs, network):
    """Rebuild a lexical/reference index locally; emit only related interfaces."""
    scope, terms = _normalize(study['scope']), _notation(study['focus'])
    object_refs = set(study.get('object_refs', []))
    associated = {}
    for peer in _studies(Path(root) / 'continuous_run', study_refs):
        shared = object_refs.intersection(peer.get('object_refs', []))
        if shared:
            for fact_id in peer.get('known_fact_ids', []):
                associated.setdefault(fact_id, set()).update(shared)
    # Accepted bindings, not every file in FactGraph. No proofs are exposed.
    identities = {fact_id for ids in network.data['fact_bindings'].values() for fact_id in ids}
    identities.update(s['bridge_fact_id'] for s in network.data['supports'].values())
    for fact_id in sorted(identities):
        try:
            source = network.inspect_fact(fact_id)
        except ValueError:
            continue  # Revoked/unavailable material is not a lawful candidate.
        if source['scope'] == scope:
            continue
        shared = sorted(associated.get(fact_id, []))
        matches = sorted(terms.intersection(_notation(source['statement'])))
        if not shared and not matches:
            continue
        yield {'kind': 'BRIDGE_CANDIDATE', 'study_id': study['study_id'],
               'ref': 'fact:' + fact_id, 'source_fact_id': fact_id,
               'source_scope': source['scope'], 'exact_statement': source['statement'],
               'discovery_reason': {'shared_object_refs': shared, 'exact_notation': matches},
               'navigation_only': True, 'requires_bridge': True}


def bridge_candidate_page(root, study, study_refs, network, offset=0, *, token_budget=2000):
    if type(offset) is not int or offset < 0:
        raise ValueError('invalid bridge candidate page offset')
    items, next_ref = _page(_bridge_rows(root, study, study_refs, network), offset,
        f"bridge-candidates:{offset + _PAGE_SIZE}:{study['study_id']}")
    page = {'study_id': study['study_id'], 'navigation_only': True,
            'candidates': [], 'unexpanded': [], 'next_ref': next_ref}
    for index, item in enumerate(items):
        item = {**item, 'page_offset': offset + index}
        following = (f"bridge-candidates:{offset + index + 1}:{study['study_id']}"
                     if index + 1 < len(items) else next_ref)
        proposed = {**page, 'candidates': page['candidates'] + [item], 'next_ref': following}
        try:
            bounded_packet(proposed, token_budget)
        except AttentionOverflow:
            try:
                bounded_packet({**page, 'candidates': [item], 'unexpanded': [], 'next_ref': following}, token_budget)
            except AttentionOverflow as error:
                # This interface cannot fit even alone: do not hide all later
                # candidates behind it or replace its conditions with a summary.
                notice = {'ref': item['ref'], 'source_fact_id': item['source_fact_id'],
                    'navigation_only': True, 'requires_bridge': True,
                    'reason': 'complete_interface_exceeds_navigation_budget',
                    'estimated_tokens': error.measurement['estimated_tokens']}
                proposed = {**page, 'unexpanded': page['unexpanded'] + [notice], 'next_ref': following}
                try:
                    bounded_packet(proposed, token_budget)
                except AttentionOverflow:
                    page['next_ref'] = f"bridge-candidates:{offset + index}:{study['study_id']}"
                    break
            else:
                page['next_ref'] = f"bridge-candidates:{offset + index}:{study['study_id']}"
                break
        page = proposed
    bounded_packet(page, token_budget)
    return page


def expose_bridge_candidates(root, exposure, studies, study_refs, network, *, token_budget):
    """Attach bounded navigation without changing Study exposure or scheduling."""
    navigation = {'bridge_candidates': [], 'bridge_candidate_pages': []}
    for card in exposure['cards']:
        study = studies[card['study_id']]
        page = bridge_candidate_page(root, study, study_refs, network, token_budget=token_budget)
        if not page['candidates'] and not page['unexpanded']:
            continue
        pointer = {'study_id': study['study_id'], 'navigation_only': True,
                   'ref': f"bridge-candidates:0:{study['study_id']}"}
        if page['unexpanded']:
            pointer['unexpanded'] = page['unexpanded']
        pages = navigation['bridge_candidate_pages'] + [pointer]
        try:
            bounded_packet({**navigation, 'bridge_candidate_pages': pages}, token_budget)
        except AttentionOverflow:
            break
        navigation['bridge_candidate_pages'] = pages
        for index, candidate in enumerate(page['candidates']):
            next_ref = (f"bridge-candidates:{candidate['page_offset'] + 1}:{study['study_id']}"
                        if index + 1 < len(page['candidates']) else page['next_ref'])
            next_pages = pages[:-1] + ([{**pointer, 'ref': next_ref or pointer['ref']}]
                                      if next_ref or page['unexpanded'] else [])
            proposed = {'bridge_candidates': navigation['bridge_candidates'] + [candidate],
                        'bridge_candidate_pages': next_pages}
            try:
                bounded_packet(proposed, token_budget)
            except AttentionOverflow:
                break  # The full conditional interface remains reachable by page.
            navigation = proposed
    return {**exposure, **navigation}


def load_selector_materials(root, study, refs, study_refs, network, *, candidates=(), token_budget=2000):
    """Inspect exposed foreign interfaces, keeping the ordinary resolver intact.

    Cards authorize inspection only, never proof use. Revalidate the source on
    every read; stale or fabricated cards cannot grant acceptance or scope access.
    """
    normal, inspections, allowed = [], [], {c['ref']: c for c in candidates
        if c.get('kind') == 'BRIDGE_CANDIDATE' and c.get('study_id') == study['study_id']}
    pages = []
    for ref in dict.fromkeys(refs):
        page = re.fullmatch(r'bridge-candidates:([0-9]+):(study-[A-Za-z0-9_-]+)', ref) if isinstance(ref, str) else None
        if page:
            if page[2] != study['study_id']:
                raise ValueError('candidate page concerns another Study')
            value = bridge_candidate_page(root, study, study_refs, network, int(page[1]), token_budget=token_budget)
            pages.append(value)
            allowed.update((c['ref'], c) for c in value['candidates'])
        else:
            normal.append(ref)
    remaining = []
    for ref in normal:
        card = allowed.get(ref) if isinstance(ref, str) else None
        if card is None:
            remaining.append(ref)
            continue
        source = network.inspect_fact(card['source_fact_id'])
        if ref != 'fact:' + source['fact_id'] or source['scope'] != card['source_scope'] or source['statement'] != card['exact_statement']:
            raise ValueError('bridge candidate source interface changed')
        if source['scope'] == _normalize(study['scope']):
            remaining.append(ref)
            continue
        fact = FactGraph(Path(root)).get_fact(source['fact_id'])
        inspections.append({**card, 'kind': 'BRIDGE_CANDIDATE_INSPECTION',
            'accepted_in_target_scope': False,
            'provenance': {'problem_id': fact.problem_id, 'source_accepted': True,
                'predecessors': list(fact.predecessors),
                'claim_ids': sorted(k for k, ids in network.data['fact_bindings'].items() if fact.fact_id in ids)}})
    facts, notes, notices = load_materials(root, study, remaining, study_refs, network)
    bounded_packet(pages + inspections, token_budget)
    return facts, notes, notices + pages + inspections
