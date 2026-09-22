"""Small execution interfaces. Optional strategy prose has no truth authority."""

def obj(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}

STR = {"type": "string"}
STRS = {"type": "array", "items": STR}
CLAIM = obj({"context": STR, "goal": STR})
CANDIDATE = obj({"kind": {"enum": ["FACT", "SUPPORT", "REFUTATION"]}, "context": STR,
                 "goal": STR, "proof": STR, "predecessors": STRS,
                 "requirements": {"type": "array", "items": CLAIM}})
WORKER_SCHEMA = obj({"candidate": {"anyOf": [CANDIDATE, {"type": "null"}]},
                     "continuation": STR, "next_work": STR,
                     "new_study": {"anyOf": [obj({"focus": STR, "context": STR,
                         "continues_study_id": STR}), {"type": "null"}]}})
BRIDGE = obj({"source_fact_id": STR, "target_auxiliary_statement": STR,
              "correspondence": STR})
SELECTOR_SCHEMA = obj({"study_id": STR,
    "operation": {"enum": ["RESEARCH", "CLOSE", "COMPOSE", "INSPECT", "REQUEST_BRIDGE"]},
    "task": STR, "fact_ids": STRS, "research_queries": STRS,
    "bridge": {"anyOf": [BRIDGE, {"type": "null"}]}, "notes": STR})
VERIFY_SCHEMA = obj({"verdict": {"enum": ["correct", "wrong", "inconclusive"]},
                     "reason": STR})
PROBE_SCHEMA = obj({"ancestor_claim_id": {"anyOf": [STR, {"type": "null"}]},
                    "mapping": STR, "reason": STR})
REPRESENTATION_SCHEMA = obj({"mode": {"enum": ["DIRECT", "CONDITIONAL", "DECLINE"]},
    "helper": {"anyOf": [CLAIM, {"type": "null"}]}, "proof": STR,
    "predecessors": STRS})

SELECTOR = """Select useful local research within the exposed Studies. Research judgments
are advisory, never mathematical truth. Decide the concrete task, what verified
results it uses, and what remains unknown. Existing research notes are unverified.
A method limitation can inform or change work; explain exceptions in notes. Continuing
a finite series is legitimate when addressing a specific remaining question.
RESEARCH may prove directly, derive a conditional Support, use a new Fact to connect an
OPEN Claim, continue a derivation, or change direction. CLOSE attempts a complete
bounded local result already supported by the research; do not force closure.
COMPOSE uses a ready Support; do not claim automatic discharge. INSPECT requests
full Fact interfaces or research memory before deciding. Cross-scope inspected Facts
may justify REQUEST_BRIDGE with an exact auxiliary statement and explicit definition/
variable correspondence. Inspection is not acceptance; preserve all source conditions.
Choose only exposed Study IDs (respect a pinned REVISIT Study). Request only existing
project Fact IDs; ordinary predecessors must have the exact current ambient scope.
No object ranking, required comparison prose, or assessment schema is needed.
"""
WORKER = """Do the supplied local research task. Try direct proof when appropriate;
otherwise research, form a precise conditional reduction, or report concrete unfinished
work. Do not treat research memory as accepted truth. Actual predecessors must be
initial accepted_facts or results explicitly delivered by premise_request or accepted
candidate_submit in this session, and only if used. A candidate proves exactly its complete local statement,
not necessarily the root. A Support proves the conjunction of explicit requirements
implies the conclusion; it does not prove the requirements. Child contexts must match
conclusion context exactly. Put definitions, variable domains and conditional assumptions
in self-contained goals; do not add ambient assumptions. Use no external theorem retrieval.
Persist useful intermediate research with local_append; shared findings/dead ends may
use gm_add. These are unverified notes, never Facts. Continue existing notes faithfully
without assuming their calculations or claims correct. A final candidate needs a complete
self-contained proof; otherwise return null and preserve the precise continuation.
A REFUTATION needs a complete proof of the negated Claim; suspicion or failure is not
a refutation. Keep ordinary continuation in this lane. new_study is only for a genuinely
independent research focus (target relevance may be unknown); set continues_study_id
to this Study for the same line of work. New Study notes have no truth authority.
"""
VERIFIER = """Independently verify exactly candidate.statement, with its complete ambient
assumptions and the actual accepted predecessor statements. A local lemma need not prove
the root. Declared predecessors must be collectively sufficient and actually used.
Research notes, runtime output, and author confidence are not proof authority. Return
correct only for a complete closed-book proof without critical errors or gaps; otherwise
wrong or inconclusive. Check quantifiers, domains, boundary cases, strictness and both
implication directions when equivalence is claimed. A representation transport must use
only renaming, finite-set relabelling, definition folding/unfolding, notation or trivial
boundaries; any unproved substantive lemma must remain an explicit condition. A scope
bridge must retain all source assumptions or prove they hold at its target interface.
This is an LLM judgment, not kernel verification.
"""
PROBE = """Inspect only this unary requirement and its recorded ancestor path. Identify
possible representation-level equivalence (rename, finite relabelling, definitions,
notation, trivial boundaries); similarity is not authority. Return null if none. Do not
prove the original problem, inspect unrelated branches, or collapse AND decompositions.
"""
REPRESENTATION = """Prove both directions of the proposed representation transport using
only rename/relabelling/definition/notation/trivial boundary arguments. If a substantive
missing local lemma is necessary, return CONDITIONAL with one self-contained helper and
prove the equivalence conditional on it. Never assume an unproved helper is true.
DECLINE is legitimate. Do not prove the original ancestor theorem.
"""

BRIDGE_WORKER = """Establish the explicit target auxiliary interface from source_interface.
The source is an accepted Fact with its original scope and complete statement; it is
authorized as a predecessor ONLY for this scope-bridge proof. It is not an ordinary
accepted Fact in the target scope. Preserve every source condition, prove applicability
under the target assumptions, or retain conditions explicitly in the target statement.
Use exactly the source Fact as predecessor. Do not prove or discharge the research
requirement, invent missing assumptions, or change the frozen auxiliary statement.
Return a complete FACT candidate for the auxiliary interface, or null with precise
unfinished work. Persist useful unfinished work through local_append. Research memory
has no mathematical authority. Do not retrieve external theorems.
"""

# Adapted only from DANUS worker verification/citation and verifier sequential-review
# instructions. No native allocation, decomposition, branch elimination or retry policy.
LOCAL_MATH_WORK = """
Local research workbench (closed book): use local_search for your own past derivations,
local_record for an exact record, and gm_search/gm_read for relevant shared awareness.
Search results are excerpts; recover the needed text before relying on its details.
Use fact_search and fact_inspect to locate existing results; proof_read returns exact
character ranges with a stable digest, line positions, original scope and definitions.
Follow next_start when more proof is needed. Do not load the entire project.
To use a discovered accepted result, call premise_request and wait for its explicit
acceptance. Foreign scope still needs CRPN's existing bridge; record that need in
continuation rather than changing assumptions. Reading a proof does not turn its
internal assertions into independent Facts.
Organize a complete local proof into identifiable paragraphs or named claims. State
all variable domains, definitions and conditions; cite exact accepted evidence IDs
where used and check that the cited statement matches the step. Keep routine algebra
inside the proof; there is no requirement to submit each small step.
When a complete local candidate is ready, candidate_submit can return independent
verification during this session. Read its location/problem/repair feedback. A returned
accepted evidence ID can be used in further local reasoning immediately. Rejection or
unknown completion is not acceptance. An unchanged request reuses its recorded outcome;
a corrected proof is a different candidate. Continue within the supplied local task and
preserve unfinished work; no manual handover or new Selector is needed for these tools.
The final candidate may be null after tool submissions; do not describe an unconfirmed
submission as successful. Use text reasoning only, with no external retrieval, CAS,
code-based mathematical experiments, extra agents or computational proof checks.
"""
WORKER += LOCAL_MATH_WORK
VERIFIER += """
Read the candidate proof in its written order. In reason, identify each material error
or gap by named claim, paragraph or quoted short location, explain the issue and give
concrete repair feedback. Check exact cited interfaces and their applicability. You may
use proof_read only for the explicitly listed accepted predecessors; their own proof
text and definitions do not authorize unrelated assumptions. No memory, search, author
session or confidence is available. Use text reasoning only, without executing code,
CAS, external retrieval or additional agents. This adds feedback and material access,
not a different acceptance rule.
"""
