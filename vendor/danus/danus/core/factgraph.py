"""fact graph — project-shared, verified, content-addressed DAG.

One human/agent-readable markdown file per fact: YAML frontmatter (fact_id /
problem_id / author / predecessors / glossary_introduces) + a markdown body
(## statement / ## proof / optional ## intuition). Plus the project glossary, a
revocation log, and a ``_revoked/`` archive. See DATA_MODEL.md §3.

Pure data-structure I/O. *Whether* a claim deserves to be a fact is the
verifier's call (the gate lives in ``fact submit``, which calls ``add`` only on
accept). ``add`` keeps the project glossary up to date and exposes a glossary
coverage check so the graph stays readable.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from . import bm25
from . import glossary as _glossary
from ._util import append_jsonl, utc_now
from .schema import Fact, clean_external_refs, compute_fact_id
from .durable_io import atomic_text, atomic_json, read_json, locked

_PRED_RE = re.compile(r"^predecessors:\s*\[(.*)\]\s*$")
_GLOSS_LINE_RE = re.compile(r"^\s{2}([^:]+):\s*(.*)$")


def statement_of(text: str) -> str:
    """The fact's ``## statement`` body (up to the next ``##`` heading), as a
    one-line snippet — what a searcher needs to recognize a fact."""
    if "\nbody_format: length-framed-v1\n" in text.partition("\n---\n")[0]:
        return " ".join(parse_fact(text).statement.split())
    out: List[str] = []
    in_stmt = False
    for line in text.splitlines():
        if line.strip().startswith("## "):
            if in_stmt:
                break
            in_stmt = line.strip().lower() == "## statement"
            continue
        if in_stmt:
            out.append(line.strip())
    return " ".join(s for s in out if s).strip()


def serialize_fact(fact: Fact) -> str:
    """Readable markdown with explicit section lengths, preserving Fact identity.

    Mathematical text may contain any of the section headings. Length framing
    makes those headings content rather than accidental delimiters. Counts are
    Unicode code points after ordinary newline normalization, not UTF-8 bytes.
    Existing unframed markdown remains readable by parse_fact.
    """
    statement, proof, intuition = (value.replace("\r\n", "\n").replace("\r", "\n").strip()
                                  for value in (fact.statement, fact.proof, fact.intuition))
    lines = [
        "---",
        f"fact_id: {fact.fact_id}",
        f"problem_id: {fact.problem_id}",
        f"author: {fact.author}",
        f"predecessors: [{', '.join(fact.predecessors)}]",
    ]
    if fact.glossary_introduces:
        lines.append("glossary_introduces:")
        for k in sorted(fact.glossary_introduces):
            lines.append(f"  {k}: {fact.glossary_introduces[k]}")
    else:
        lines.append("glossary_introduces: {}")
    # external_refs: a JSON flow-array on one line (valid YAML, trivially parsed).
    # Always emitted (`[]` when empty), like glossary_introduces.
    lines.append("external_refs: " + json.dumps(fact.external_refs, ensure_ascii=False))
    lines += ["body_format: length-framed-v1",
              "body_lengths: " + json.dumps([len(statement), len(proof), len(intuition)]),
              "---", "", "## statement", statement, "", "## proof", proof]
    if intuition:
        lines += ["", "## intuition", intuition]
    lines.append("")
    return "\n".join(lines)


def parse_frontmatter(text: str) -> Dict[str, object]:
    """Extract ``predecessors`` (list), ``glossary_introduces`` (dict), and
    ``external_refs`` (list of dicts) from a fact's frontmatter. ``external_refs``
    defaults to ``[]`` for facts written before the field existed."""
    preds: List[str] = []
    gloss: Dict[str, str] = {}
    refs: List[Dict[str, object]] = []
    in_gloss = False
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if i > 0 and line.strip() == "---":
            break
        m = _PRED_RE.match(line.strip())
        if m:
            preds = [x.strip() for x in m.group(1).split(",") if x.strip()]
            in_gloss = False
            continue
        if line.strip().startswith("glossary_introduces:"):
            in_gloss = "{}" not in line
            continue
        if line.strip().startswith("external_refs:"):
            in_gloss = False
            payload = line.strip()[len("external_refs:"):].strip()
            try:
                refs = json.loads(payload) if payload else []
            except json.JSONDecodeError:
                refs = []
            continue
        if in_gloss:
            gm = _GLOSS_LINE_RE.match(line)
            if gm:
                gloss[gm.group(1).strip()] = gm.group(2).strip()
            else:
                in_gloss = False
    return {"predecessors": preds, "glossary_introduces": gloss, "external_refs": refs}


class FactGraph:
    """Rooted at the project directory; the only correctness source."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._assert_legacy_workspace()
        self.dir = Path(root) / "fact_graph"
        self.facts_dir = self.dir / "facts"
        self.revoked_dir = self.dir / "_revoked"
        self.glossary_path = self.dir / "glossary.json"
        self.revocation_log = self.dir / "revocation_log.jsonl"

    def _assert_legacy_workspace(self):
        state = self.root / 'crpn.json'
        if state.exists() and read_json(state).get('schema_version') == 'crpn-authority-2':
            raise ValueError('DANUS truth entry retired: use CRPN authority')

    def _path(self, fact_id: str) -> Path:
        self._assert_legacy_workspace()
        if not isinstance(fact_id, str) or not re.fullmatch(r"[0-9a-f]{16}", fact_id):
            raise ValueError("invalid Fact identifier")
        return self.facts_dir / f"{fact_id}.md"

    # ------------------------------------------------------------------ write
    def add(self, **kwargs):
        self._assert_legacy_workspace()
        with locked(self.dir / ".write.lock"):
            return self._add_locked(**kwargs)

    def _add_locked(
        self,
        *,
        problem_id: str,
        author: str,
        statement: str,
        proof: str,
        predecessors: Optional[List[str]] = None,
        glossary_introduces: Optional[Dict[str, str]] = None,
        intuition: str = "",
        external_refs: Optional[List[Dict[str, object]]] = None,
    ) -> str:
        """Write a verified fact; return its content-addressed fact_id.

        Refuses a revoked predecessor (cascade integrity). Idempotent: identical
        content -> identical id -> identical file. Merges the fact's introduced
        symbols into the project glossary. ``external_refs`` is structured
        bibliography for cited external results; it does NOT affect the fact_id
        (mutable metadata — see ``compute_fact_id``).
        """
        predecessors = sorted(set(p for p in (predecessors or []) if p))
        glossary_introduces = glossary_introduces or {}
        external_refs = clean_external_refs(external_refs)
        for pid in predecessors:
            if pid in self.revoked_ids():
                raise ValueError(f"predecessor_revoked: {pid}")
            for prior in self.supporting_closure(pid):
                if prior.problem_id != problem_id:
                    raise ValueError(f"cross_problem_predecessor: {pid}")
        fact_id = compute_fact_id(
            problem_id=problem_id,
            predecessors=predecessors,
            glossary_introduces=glossary_introduces,
            statement=statement,
            proof=proof,
        )
        if fact_id in self.revoked_ids():
            raise ValueError(f"fact_revoked: {fact_id}")
        fact = Fact(
            fact_id=fact_id, problem_id=problem_id, author=author,
            predecessors=predecessors, statement=statement, proof=proof,
            glossary_introduces=glossary_introduces, intuition=intuition,
            external_refs=external_refs,
        )
        self.facts_dir.mkdir(parents=True, exist_ok=True)
        if self._path(fact_id).exists():
            self.get(fact_id)  # Never overwrite accepted provenance.
            return fact_id
        rendered = serialize_fact(fact)
        checked = parse_fact(rendered, expected_id=fact_id)
        if checked.author != author or checked.problem_id != problem_id:
            raise ValueError("Fact metadata cannot be represented without changing provenance")
        # Validate before publication: an encoding failure must never leave an
        # active Fact that the authoritative reader cannot load.
        atomic_text(self._path(fact_id), rendered)
        self._merge_glossary(glossary_introduces)
        return fact_id

    def _merge_glossary(self, new: Dict[str, str]) -> None:
        if not new:
            return
        cur = self.glossary()
        cur.update({str(k): str(v) for k, v in new.items()})
        self.glossary_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(self.glossary_path, cur)

    # ------------------------------------------------------------------- read
    def exists(self, fact_id: str) -> bool:
        return self._path(fact_id).exists() and fact_id not in self.revoked_ids()

    def list(self) -> List[str]:
        if not self.facts_dir.exists():
            return []
        revoked = self.revoked_ids()
        return sorted(p.stem for p in self.facts_dir.glob("*.md") if p.stem not in revoked)

    def get_raw(self, fact_id: str) -> Optional[str]:
        """The fact's markdown (agents read markdown directly)."""
        p = self._path(fact_id)
        return p.read_text(encoding="utf-8") if self.exists(fact_id) else None

    def glossary(self) -> Dict[str, str]:
        """The accumulated project glossary (symbol -> definition)."""
        if self.glossary_path.exists():
            try:
                return json.loads(self.glossary_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def search(self, query: str, limit: int = 10) -> List[Dict[str, object]]:
        """BM25 over the fact bodies (statement + proof + intuition + glossary),
        the derived fact index rebuilt **on demand** from ``facts/*.md`` — no
        persisted board, so no double-write drift (DATA_MODEL.md §3). Returns the
        top matches as ``{fact_id, score, statement}`` for novelty checks ("does a
        fact like this already exist?") and citation lookup ("which verified facts
        bear on my subgoal?"). The fact graph stays the single source of truth;
        this is just a read view over it."""
        fids = self.list()
        if not fids:
            return []
        raws = [self.get_raw(fid) or "" for fid in fids]
        docs = [bm25.tokenize(r) for r in raws]
        scores = bm25.bm25_scores(query, docs)
        ranked: List[Dict[str, object]] = []
        for fid, raw, score in sorted(zip(fids, raws, scores), key=lambda t: -t[2]):
            if score <= 0:
                break
            ranked.append({"fact_id": fid, "score": score, "statement": statement_of(raw)})
            if len(ranked) >= limit:
                break
        return ranked

    def predecessors(self, fact_id: str) -> List[str]:
        raw = self.get_raw(fact_id) or ""
        return parse_frontmatter(raw)["predecessors"]  # type: ignore[return-value]

    def external_refs(self, fact_id: str) -> List[Dict[str, object]]:
        """The fact's structured external bibliography (``[]`` if none / absent)."""
        raw = self.get_raw(fact_id) or ""
        return parse_frontmatter(raw)["external_refs"]  # type: ignore[return-value]

    def set_external_refs(self, fact_id: str, external_refs: List[Dict[str, object]]) -> List[Dict[str, object]]:
        """Replace a fact's ``external_refs`` in place — the reference auditor's
        write path. Touches only this mutable frontmatter line; the body and the
        content-addressed ``fact_id`` are unchanged (refs are not hashed). Returns
        the normalized refs written. Raises if the fact does not exist."""
        p = self._path(fact_id)
        if not p.exists():
            raise ValueError(f"unknown fact_id: {fact_id}")
        refs = clean_external_refs(external_refs)
        new_line = "external_refs: " + json.dumps(refs, ensure_ascii=False)
        lines = p.read_text(encoding="utf-8").splitlines()
        # frontmatter is between the first '---' (line 0) and the next '---'
        close = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if close is None:
            raise ValueError(f"malformed fact file (no frontmatter close): {fact_id}")
        idx = next((i for i in range(1, close) if lines[i].startswith("external_refs:")), None)
        if idx is not None:
            lines[idx] = new_line
        else:
            lines.insert(close, new_line)  # facts written before the field existed
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return refs

    def descendants(self, fact_id: str) -> List[str]:
        """All facts that (transitively) depend on ``fact_id``."""
        out: List[str] = []
        seen = set()
        frontier = [fact_id]
        while frontier:
            cur = frontier.pop()
            for fid in self.list():
                if fid in seen:
                    continue
                if cur in self.predecessors(fid):
                    out.append(fid)
                    seen.add(fid)
                    frontier.append(fid)
        return out

    # --------------------------------------------------------- glossary check
    def undefined_symbols(
        self,
        *,
        statement: str,
        proof: str,
        intuition: str = "",
        predecessors: Optional[List[str]] = None,
        glossary_introduces: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """Symbols used in the body but defined nowhere available: (this fact's
        glossary) ∪ (each predecessor's glossary) ∪ (the project glossary) ∪ (the
        repo-wide global glossary of universal notation). Used by `fact submit` to
        keep the graph readable (advisory)."""
        defined = _glossary.global_terms()  # universal notation, all projects
        defined |= set(self.glossary())
        defined |= set(glossary_introduces or {})
        for pid in (predecessors or []):
            raw = self.get_raw(pid)
            if raw:
                defined |= set(parse_frontmatter(raw)["glossary_introduces"])  # type: ignore[arg-type]
        return _glossary.undefined_symbols(
            statement=statement, proof=proof, intuition=intuition, defined=defined
        )

    # --------------------------------------------------------------- revoke
    def revoked_ids(self):
        """Write-ahead revocation batches fail closed even halfway through moves."""
        self._assert_legacy_workspace()
        ids = {p.stem for p in self.revoked_dir.glob("*.md")}
        for path in (self.dir / "revocations").glob("*.json"):
            ids.update(read_json(path)["fact_ids"])
        return ids

    def get(self, fact_id):
        raw = self.get_raw(fact_id)
        if raw is None:
            raise ValueError(f"missing_or_revoked_fact: {fact_id}")
        return parse_fact(raw, expected_id=fact_id)

    def supporting_closure(self, fact_id):
        ordered, visiting, seen = [], set(), set()
        def visit(key):
            if key in visiting:
                raise ValueError("Fact dependency cycle")
            if key in seen:
                return
            visiting.add(key)
            fact = self.get(key)
            for parent in fact.predecessors:
                prior = self.get(parent)
                if prior.problem_id != fact.problem_id:
                    raise ValueError("cross_problem_predecessor")
                visit(parent)
            visiting.remove(key); seen.add(key); ordered.append(fact)
        visit(fact_id)
        return ordered

    def revoke(self, fact_id: str, reason: str) -> List[str]:
        with locked(self.dir / ".write.lock"):
            return self._revoke_locked(fact_id, reason)

    def _revoke_locked(self, fact_id: str, reason: str) -> List[str]:
        """Cascade revoke with a durable batch before any destructive move."""
        self._path(fact_id)
        receipt = self.dir / "revocations" / (fact_id + ".json")
        if receipt.exists():
            batch = read_json(receipt)
        else:
            if not self.exists(fact_id):
                raise ValueError(f"unknown fact_id: {fact_id}")
            batch = {"fact_ids": [fact_id] + self.descendants(fact_id),
                     "reason": reason, "timestamp_utc": utc_now()}
            atomic_json(receipt, batch)
        self.revoked_dir.mkdir(parents=True, exist_ok=True)
        for fid in batch["fact_ids"]:
            src, target = self._path(fid), self.revoked_dir / (fid + ".md")
            if src.exists():
                if target.exists() and target.read_bytes() != src.read_bytes():
                    raise ValueError("conflicting revoked evidence")
                if not target.exists():
                    shutil.move(str(src), str(target))
                else:
                    src.unlink()
            if not target.exists():
                raise ValueError("revoked evidence missing")
        return batch["fact_ids"]


def parse_fact(raw, expected_id=None):
    """Decode the upstream format and validate the content address on every read."""
    header, body = raw[4:].split("\n---", 1)
    fields = {}
    for line in header.splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            fields[key] = value.strip()
    metadata = parse_frontmatter(raw)
    if "body_format" in fields:
        if fields["body_format"] != "length-framed-v1":
            raise ValueError("unknown Fact body format")
        lengths = json.loads(fields.get("body_lengths", "null"))
        if (not isinstance(lengths, list) or len(lengths) != 3 or
                any(type(n) is not int or n < 0 for n in lengths)):
            raise ValueError("invalid Fact section lengths")
        sections, position = [], 0
        for heading, size in zip(("statement", "proof", "intuition"), lengths):
            if heading == "intuition" and size == 0:
                sections.append("")
                continue
            prefix = "\n\n## " + heading + "\n"
            if not body.startswith(prefix, position):
                raise ValueError("Fact section boundary mismatch")
            position += len(prefix)
            section = body[position:position + size]
            if len(section) != size:
                raise ValueError("truncated Fact section")
            sections.append(section)
            position += size
        if body[position:] != "\n":
            raise ValueError("unexpected Fact body suffix")
        statement, proof, intuition = sections
    else:
        # Original upstream files retain their exact bytes and content IDs.
        body = body.strip()
        if not body.startswith("## statement\n"):
            raise ValueError("malformed Fact statement")
        statement, proof = body[len("## statement\n"):].split("\n## proof\n", 1)
        intuition = ""
        if "\n## intuition\n" in proof:
            proof, intuition = proof.split("\n## intuition\n", 1)
    fact = Fact(fields["fact_id"], fields["problem_id"], fields["author"],
                metadata["predecessors"], statement.strip(), proof.strip(),
                metadata["glossary_introduces"], intuition.strip(), metadata["external_refs"])
    computed = compute_fact_id(problem_id=fact.problem_id, statement=fact.statement,
                               proof=fact.proof, predecessors=fact.predecessors,
                               glossary_introduces=fact.glossary_introduces)
    if fact.fact_id != computed or (expected_id and fact.fact_id != expected_id):
        raise ValueError("Fact content hash mismatch")
    return fact
