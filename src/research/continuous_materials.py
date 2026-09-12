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


_STUDY = re.compile(r"studies/([A-Za-z0-9_-]+)/([0-9]{6,}(?:-verified)?|(?:timeout|capacity)-[0-9]{8,})\.json\Z")
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


def _related(directory, study_refs, object_ref):
    for value in _studies(directory, study_refs):
        if object_ref in value.get("object_refs", []):
            yield {"kind": "Study", "id": value["study_id"], "ref": study_refs[value["study_id"]],
                   "scope_ref": sha256(value["scope"].encode("utf-8")).hexdigest(), "navigation_only": True}


def load_materials(root, study, refs, study_refs, network):
    """Read exact local references; search/object matches are paged navigation.

    ``root`` is the problem workspace. Raw paths must match the narrow Study or
    visit allowlist; no state, global graph, call journal, or arbitrary file is
    addressable. Distinct scopes may be compared as labelled unverified notes.
    Accepted Fact reads retain the network's exact-scope and revocation guards.
    """
    directory = Path(root) / "continuous_run"
    facts, unverified, notices = {}, [], []
    for ref in refs:
        if not isinstance(ref, str):
            raise ValueError("local material references must be strings")
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
                    related, next_ref = _page(_related(directory, study_refs, object_ref), offset,
                                             f"object-page:{offset + _PAGE_SIZE}:{key}")
                    notices.append({"object_ref": object_ref, "related": related,
                                    "navigation_only": True, "next_ref": next_ref})
                    continue
        notices.append({"ref": ref, "error": "unknown local reference"})
    return facts, unverified, notices
