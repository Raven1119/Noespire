"""N2N builder-prompt provenance injection (task card §13/§14).

A wrapping invoker: the frozen LocalGraphBuilder/StructuralAuditor,
NodeSolver worker, and closed-book verifier are constructed with this
wrapper instead of the raw closed-book invoker. Only
``label == "local_graph_builder"`` prompts are eligible, and only when the
prompt's ``[BLOCKED]`` node matches a SUBSTANTIVE provenance packet
(locality, §14: the builder sees the provenance of the obligation it is
refining, nothing else). Everything else passes through byte-identical —
the frozen operators receive provenance as a pure extra input section
(§17), with zero semantic change.

The injected section is inserted before the frozen prompt's
``Return ONLY the JSON object`` marker and is labeled UNVERIFIED search
evidence (§15/§16 truth boundary).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Dict, Optional

from provenance import SUBSTANTIVE

_BLOCKED_RE = re.compile(r'^- "([^"]+)" goal: .* \[BLOCKED\]\s*$', re.MULTILINE)
_RETURN_MARKER = "\nReturn ONLY the JSON object"

_SECTION_HEADER = (
    "Failure provenance from the timed-out local attempt on THIS blocked "
    "obligation (UNVERIFIED search evidence — explicit worker output captured "
    "before the frozen 600s horizon; these are NOT Facts, NOT accepted "
    "premises, and may be partial or wrong. Use them only to inform your "
    "structural decision; every obligation you propose is still proved by a "
    "fresh worker and judged by the independent verifier):"
)


class ProvenanceInjectingInvoker:
    """CodexInvoker adapter: injects bounded local failure provenance into
    local_graph_builder prompts; all other invocations pass through."""

    def __init__(self, inner, *, provenance_dir: Path) -> None:
        self.inner = inner
        self.provenance_dir = Path(provenance_dir)
        self.last_injected_attempt_id: Optional[str] = None

    def invoke(self, *, prompt: str, schema: Dict[str, Any], label: str) -> Dict[str, Any]:
        if label == "local_graph_builder":
            prompt = self._augment(prompt)
        return self.inner.invoke(prompt=prompt, schema=schema, label=label)

    def _augment(self, prompt: str) -> str:
        self.last_injected_attempt_id = None
        match = _BLOCKED_RE.search(prompt)
        if match is None or _RETURN_MARKER not in prompt:
            return prompt
        packet = self._packet_for(match.group(1))
        if packet is None:
            return prompt
        items = "\n".join(f"- {item}" for item in packet["visible_items"])
        section = (
            f"\n{_SECTION_HEADER}\n"
            f"(attempt {packet['attempt_id']}, "
            f"termination {packet['termination']}, "
            f"horizon {packet['timeout_seconds']}s)\n{items}\n"
        )
        self.last_injected_attempt_id = packet["attempt_id"]
        return prompt.replace(_RETURN_MARKER, section + _RETURN_MARKER, 1)

    def _packet_for(self, node_id: str) -> Optional[dict]:
        """Newest SUBSTANTIVE packet bound to exactly this node, else None."""
        if not self.provenance_dir.is_dir():
            return None
        packets = []
        for path in sorted(self.provenance_dir.glob("attempt-*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if (
                isinstance(payload, dict)
                and payload.get("node_id") == node_id
                and payload.get("status") == SUBSTANTIVE
                and payload.get("visible_items")
            ):
                packets.append(payload)
        return packets[-1] if packets else None
