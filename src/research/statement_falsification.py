"""Source-grounded falsification receipts, not a mathematical parser or kernel."""
import ast
from fractions import Fraction
import math
import re


def obj(properties):
    return {"type": "object", "additionalProperties": False,
            "properties": properties, "required": list(properties)}


def array(items):
    return {"type": "array", "items": items}


def enum(*values):
    return {"type": "string", "enum": list(values)}


TEXT = {"type": "string", "minLength": 1}
IDS = array(TEXT)
ARITHMETIC = {"anyOf": [{"type": "null"}, obj({
    "left": TEXT, "relation": enum("<", "<=", "=", "!=", ">=", ">"), "right": TEXT})]}
SCHEMA = obj({
    "status": enum("NO_CONCRETE_CONTRADICTION", "CONCRETE_COUNTEREXAMPLE", "SANITY_INCONCLUSIVE"),
    "assumptions": array(obj({"id": TEXT, "source_id": TEXT, "quote": TEXT})),
    "clauses": array(obj({"id": TEXT, "source_ids": IDS, "quantifiers": TEXT,
                          "domain": TEXT, "assertion": TEXT, "assumption_ids": IDS})),
    "attacks": array(obj({
        "id": TEXT, "clause_ids": IDS, "surface_ids": IDS,
        "substitutions": array(obj({"symbol": TEXT, "value": TEXT})),
        "assumption_checks": array(obj({"assumption_id": TEXT, "instantiated": TEXT,
            "justification": TEXT, "status": enum("SATISFIED", "VIOLATED", "UNRESOLVED"),
            "arithmetic": ARITHMETIC})),
        "instantiated_conclusion": TEXT, "evaluation": TEXT,
        "arithmetic": ARITHMETIC,
        "status": enum("SURVIVED", "CONCRETE_COUNTEREXAMPLE", "UNRESOLVED")
    })),
    "reason": TEXT
})

# Lexical attention obligations only. They neither parse quantifiers nor decide
# whether a sum is normalized. Matching sums conservatively includes extra work.
_PATTERNS = {
    "STRICT_RELATION": r"(?<![<>=])<(?![=>])|(?<![<>=])>(?![=])|\\(?:lt|gt)\b|\bstrict(?:ly)?\b",
    "NORMALIZATION_OR_SUM": r"\bsum\b|sum_|[\u03a3\u2211]|\\sum|normali[sz]|probability",
    "PSD_OR_GRAM": r"\bPSD\b|\bGram\b|positive[ -]semidefinite",
    "SCALAR_DOMAIN": r"non[ -]?negative|\bpositive\b|non[ -]?zero|denominator",
    "QUANTIFIER": r"\b(?:all|any|every|each|exists?|there is|there are)\b|[\u2200\u2203]",
    "FINITE_FAMILY": r"\b(?:finite|singleton|family|families|indexed)\b",
}


def attack_map(packet):
    """Lossless source coordinates and mechanically required lexical surfaces."""
    sources = [("statement", packet["statement"]), ("ambient_scope", packet["ambient_scope"])]
    sources += [("fact:" + f["fact_id"], f["statement"]) for f in packet["accepted_predecessors"]]
    units, surfaces = [], []
    for source, text in sources:
        start = 0
        boundaries = [m.end() for m in re.finditer(r"(?<=[.;])\s+|\n+", text)] + [len(text)]
        for end in boundaries:
            if text[start:end].strip():
                unit = {"id": f"u{len(units)}", "source": source, "start": start,
                        "end": end, "text": text[start:end]}
                units.append(unit)
                if source in {"statement", "ambient_scope"}:
                    for kind, pattern in _PATTERNS.items():
                        matches = [{"start": start + m.start(), "end": start + m.end(), "text": m.group()}
                                   for m in re.finditer(pattern, unit["text"], re.I)]
                        if matches:
                            surfaces.append({"id": f"s{len(surfaces)}", "source_id": unit["id"],
                                             "kind": kind, "matches": matches})
            start = end
    return {"source_units": units, "required_surfaces": surfaces}


def _shape(value, schema):
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                _shape(value, option)
                return
            except ValueError:
                pass
        raise ValueError("invalid nullable field")
    kind = schema["type"]
    if kind == "null":
        if value is not None:
            raise ValueError("expected null")
    elif kind == "string":
        if not isinstance(value, str) or not value.strip() or ("enum" in schema and value not in schema["enum"]):
            raise ValueError("invalid text/status")
    elif kind == "array":
        if not isinstance(value, list):
            raise ValueError("expected array")
        for item in value:
            _shape(item, schema["items"])
    elif kind == "object":
        if not isinstance(value, dict) or set(value) != set(schema["properties"]):
            raise ValueError("invalid fields")
        for key, sub in schema["properties"].items():
            _shape(value[key], sub)


def _indexed(items):
    result = {item["id"]: item for item in items}
    if len(result) != len(items):
        raise ValueError("duplicate identity")
    return result


def _refs(values, allowed, *, nonempty=False):
    if len(values) != len(set(values)) or not set(values) <= set(allowed) or (nonempty and not values):
        raise ValueError("missing, duplicate or unknown reference")


def exact_comparison(record):
    """Tiny closed rational arithmetic; no eval, symbols, approximations or CAS.

    Confirms the submitted arithmetic only, not its derivation from the clause.
    Bounded grammar: integer, + - * /, integer power |e|<=12, exact sqrt.
    """
    if record is None:
        return None

    def number(text):
        if len(text) > 256:
            raise ValueError("arithmetic too large")
        tree = ast.parse(text, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 80:
            raise ValueError("arithmetic too complex")

        def walk(node, depth=0):
            if depth > 20:
                raise ValueError("arithmetic too deep")
            if isinstance(node, ast.Constant) and type(node.value) is int:
                result = Fraction(node.value)
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                result = walk(node.operand, depth+1) * (-1 if isinstance(node.op, ast.USub) else 1)
            elif isinstance(node, ast.BinOp):
                a, b = walk(node.left, depth+1), walk(node.right, depth+1)
                if isinstance(node.op, ast.Add): result = a+b
                elif isinstance(node.op, ast.Sub): result = a-b
                elif isinstance(node.op, ast.Mult): result = a*b
                elif isinstance(node.op, ast.Div): result = a/b
                elif isinstance(node.op, ast.Pow) and b.denominator == 1 and abs(b) <= 12: result = a**int(b)
                else: raise ValueError("unsupported arithmetic operator")
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sqrt"
                  and len(node.args) == 1 and not node.keywords):
                a = walk(node.args[0], depth+1)
                if a < 0: raise ValueError("negative square root")
                n, d = math.isqrt(a.numerator), math.isqrt(a.denominator)
                if n*n != a.numerator or d*d != a.denominator:
                    raise ValueError("not an exact rational square root")
                result = Fraction(n, d)
            else:
                raise ValueError("not closed exact arithmetic")
            if max(abs(result.numerator).bit_length(), result.denominator.bit_length()) > 2048:
                raise ValueError("arithmetic result too large")
            return result
        return walk(tree.body)

    try:
        left, right = number(record["left"]), number(record["right"])
        truth = {"<": left < right, "<=": left <= right, "=": left == right,
                 "!=": left != right, ">=": left >= right, ">": left > right}[record["relation"]]
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, KeyError) as error:
        raise ValueError("invalid closed arithmetic: " + str(error)) from error
    return {"left": str(left), "relation": record["relation"], "right": str(right), "holds": truth}


def validate(response, mapping):
    """Validate coverage/evidence integrity, not deep mathematical soundness.

    A valid concrete attack vetoes even when other clauses remain unresolved.
    Insufficient coverage never upgrades to NO_CONCRETE_CONTRADICTION.
    """
    diagnostics, arithmetic = [], []
    try:
        _shape(response, SCHEMA)
        units = _indexed(mapping["source_units"])
        surfaces = _indexed(mapping["required_surfaces"])
        assumptions = _indexed(response["assumptions"])
        clauses = _indexed(response["clauses"])
        attacks = _indexed(response["attacks"])
        covered_units, covered_surfaces, tested_clauses = set(), set(), set()
        for assumption in assumptions.values():
            if (assumption["source_id"] not in units or
                    assumption["quote"] not in units[assumption["source_id"]]["text"]):
                raise ValueError("assumption not grounded in exact source")
        for clause in clauses.values():
            _refs(clause["source_ids"], units, nonempty=True)
            _refs(clause["assumption_ids"], assumptions)
            positions = [list(units).index(u) for u in clause["source_ids"]]
            if positions != sorted(positions):
                raise ValueError("clause sources must retain original order")
            if not any(units[s]["source"] == "statement" for s in clause["source_ids"]):
                raise ValueError("clause must include candidate statement")
            original = "".join(units[u]["text"] for u in clause["source_ids"]
                               if units[u]["source"] == "statement").strip()
            if clause["assertion"] != original:
                raise ValueError("assertion must quote the complete selected statement units verbatim")
            covered_units.update(clause["source_ids"])
        concrete, unresolved = [], []
        for case in attacks.values():
            _refs(case["clause_ids"], clauses, nonempty=True)
            _refs(case["surface_ids"], surfaces)
            if not case["substitutions"]:
                raise ValueError("attack needs explicit substitution")
            names = [s["symbol"] for s in case["substitutions"]]
            if len(set(names)) != len(names):
                raise ValueError("duplicate substitution")
            case_sources = set().union(*(set(clauses[c]["source_ids"]) for c in case["clause_ids"]))
            if any(surfaces[s]["source_id"] not in case_sources for s in case["surface_ids"]):
                raise ValueError("surface not grounded in attacked clause")
            required = set().union(*(set(clauses[c]["assumption_ids"]) for c in case["clause_ids"]))
            checks = case["assumption_checks"]
            _refs([c["assumption_id"] for c in checks], assumptions)
            if not required <= {c["assumption_id"] for c in checks}:
                raise ValueError("attack omits clause assumptions")
            legal = True
            for check in checks:
                result = exact_comparison(check["arithmetic"])
                if result is not None:
                    arithmetic.append({"attack_id": case["id"], "assumption_id": check["assumption_id"], **result})
                if check["status"] != "SATISFIED" or result is not None and not result["holds"]:
                    legal = False
            result = exact_comparison(case["arithmetic"])
            if result is not None:
                arithmetic.append({"attack_id": case["id"], "assumption_id": None, **result})
            if case["status"] != "UNRESOLVED" and not legal:
                raise ValueError("resolved attack has unlawful/unresolved assumptions")
            if case["status"] == "CONCRETE_COUNTEREXAMPLE":
                if result is not None and result["holds"]:
                    raise ValueError("counterexample arithmetic does not contradict")
                concrete.append(case["id"])
            elif case["status"] == "SURVIVED" and result is not None and not result["holds"]:
                raise ValueError("surviving attack contains a false instantiated assertion")
            if case["status"] == "UNRESOLVED":
                unresolved.append(case["id"])
            else:
                covered_surfaces.update(case["surface_ids"])
                tested_clauses.update(case["clause_ids"])
        missing_units = {u for u in units if units[u]["source"] in {"statement", "ambient_scope"}} - covered_units
        missing_surfaces = set(surfaces) - covered_surfaces
        missing_clauses = set(clauses) - tested_clauses
        coverage = {"missing_source_ids": sorted(missing_units), "missing_surface_ids": sorted(missing_surfaces),
                    "untested_clause_ids": sorted(missing_clauses), "unresolved_attack_ids": unresolved,
                    "concrete_attack_ids": concrete}
        adequate = bool(clauses and attacks) and not (missing_units or missing_surfaces or missing_clauses or unresolved)
        if concrete:
            status = "CONCRETE_COUNTEREXAMPLE"  # Asymmetric veto, even on a conflicting global verdict.
        elif response["status"] == "NO_CONCRETE_CONTRADICTION" and adequate:
            status = "NO_CONCRETE_CONTRADICTION"
        else:
            status = "SANITY_INCONCLUSIVE"
            diagnostics.append("Unresolved, incomplete coverage or inconsistent global verdict; proof audit is blocked.")
        return {"status": status, "coverage": coverage, "adequate_coverage": adequate,
                "arithmetic_confirmations": arithmetic, "diagnostics": diagnostics}
    except ValueError as error:
        return {"status": "SANITY_INCONCLUSIVE", "coverage": None, "adequate_coverage": False,
                "arithmetic_confirmations": arithmetic, "diagnostics": [str(error)]}
