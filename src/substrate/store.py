"""Scoped views over DANUS memory, never truth stores."""
from pathlib import Path
from danus.core import GlobalMemory, LocalMemory
from danus.core.schema import GLOBAL_KINDS


def lane(root, study_id):
    if not isinstance(study_id, str) or not study_id or any(c not in
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in study_id):
        raise ValueError("invalid Study lane")
    return Path(root) / "workers" / study_id


def append_once(memory, channel, source_key, record):
    """Import/transition dedup derived from memory itself, no parallel ref registry."""
    for item in memory.read(channel):
        if item.get("record", {}).get("source_key") == source_key:
            return item
    return memory.append(channel, {"source_key": source_key, **record})


def research_view(root, study_id, query, limit=4):
    """Disposable research view; invalid notes cannot veto legitimate actions."""
    local, shared = LocalMemory(lane(root, study_id)), GlobalMemory(root)
    try:
        own = local.read("notes")[-limit:]
        related = shared.search(query, limit_per_kind=limit)
        return {"authority": "UNVERIFIED_RESEARCH", "local": own, "shared": related}
    except (ValueError, TypeError, KeyError):
        return {"authority": "UNVERIFIED_RESEARCH", "diagnostic": "view unavailable"}
