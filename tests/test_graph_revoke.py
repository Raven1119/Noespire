from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research.fact import Fact
from research.graph import FactGraph


class DescendantsTests(unittest.TestCase):
    def test_descendants_returns_transitive_dependents_of_linear_chain(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            a = _add(graph, "A")
            b = _add(graph, "B", a.fact_id)
            c = _add(graph, "C", b.fact_id)
            _add(graph, "unrelated")

            self.assertEqual(graph.descendants(a.fact_id), [b.fact_id, c.fact_id])
            self.assertEqual(graph.descendants(c.fact_id), [])

    def test_descendants_of_diamond_in_deterministic_order(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            a = _add(graph, "A")
            b = _add(graph, "B", a.fact_id)
            c = _add(graph, "C", a.fact_id)
            d = _add(graph, "D", b.fact_id, c.fact_id)

            expected = sorted([b.fact_id, c.fact_id]) + [d.fact_id]
            self.assertEqual(graph.descendants(a.fact_id), expected)
            self.assertEqual(graph.descendants(a.fact_id), graph.descendants(a.fact_id))

    def test_descendants_of_unknown_fact_raises(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            _add(graph, "A")

            with self.assertRaises(KeyError):
                graph.descendants("0" * 16)


class RevokeTests(unittest.TestCase):
    def test_revoke_cascades_to_transitive_dependents(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            a = _add(graph, "A")
            b = _add(graph, "B", a.fact_id)
            c = _add(graph, "C", b.fact_id)
            unrelated = _add(graph, "unrelated")

            revoked = graph.revoke(a.fact_id, "false premise")

            self.assertEqual(revoked, [a.fact_id, b.fact_id, c.fact_id])
            self.assertEqual([fact.fact_id for fact in graph.list_facts()], [unrelated.fact_id])

    def test_revoke_preserves_files_and_logs_each_revoked_fact(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            a = _add(graph, "A")
            b = _add(graph, "B", a.fact_id)

            graph.revoke(a.fact_id, "false premise")

            for fact_id in (a.fact_id, b.fact_id):
                self.assertTrue((Path(directory) / "_revoked" / f"{fact_id}.md").is_file())
            records = [
                json.loads(line)
                for line in (Path(directory) / "revocation_log.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([record["fact_id"] for record in records], [a.fact_id, b.fact_id])
            for record in records:
                self.assertEqual(record["reason"], "false premise")
                self.assertTrue(record["timestamp_utc"])
            self.assertIsNone(records[0]["revoked_as_dependent_of"])
            self.assertEqual(records[1]["revoked_as_dependent_of"], a.fact_id)

    def test_revoke_unknown_or_already_revoked_fact_raises(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            a = _add(graph, "A")

            with self.assertRaises(ValueError):
                graph.revoke("0" * 16, "no such fact")
            graph.revoke(a.fact_id, "false premise")
            with self.assertRaises(ValueError):
                graph.revoke(a.fact_id, "again")

    def test_revoked_predecessor_cannot_support_new_fact(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            a = _add(graph, "A")
            graph.revoke(a.fact_id, "false premise")

            orphan = Fact.create(
                problem_id="p",
                author="worker",
                statement="B",
                proof="A implies B.",
                predecessors=(a.fact_id,),
            )
            with self.assertRaisesRegex(ValueError, "predecessor_revoked"):
                graph.add_fact(orphan)
            self.assertFalse((Path(directory) / "facts" / f"{orphan.fact_id}.md").exists())

    def test_revoked_facts_are_absent_from_read_views(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            a = _add(graph, "A")
            b = _add(graph, "B", a.fact_id)
            c = _add(graph, "C")
            d = _add(graph, "D", c.fact_id)

            graph.revoke(a.fact_id, "false premise")

            with self.assertRaises(KeyError):
                graph.get_fact(a.fact_id)
            with self.assertRaises(KeyError):
                graph.get_fact("0" * 16)
            self.assertEqual(
                {fact.fact_id for fact in graph.list_facts()},
                {c.fact_id, d.fact_id},
            )
            with self.assertRaises(KeyError):
                graph.supporting_closure(b.fact_id)
            closure = graph.supporting_closure(d.fact_id)
            self.assertEqual({fact.fact_id for fact in closure}, {c.fact_id, d.fact_id})

    def test_descendants_excludes_revoked_facts(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            a = _add(graph, "A")
            b = _add(graph, "B", a.fact_id)
            c = _add(graph, "C", a.fact_id)

            graph.revoke(b.fact_id, "false lemma")

            self.assertEqual(graph.descendants(a.fact_id), [c.fact_id])


def _add(graph: FactGraph, statement: str, *predecessors: str) -> Fact:
    fact = Fact.create(
        problem_id="p",
        author="worker",
        statement=statement,
        proof=f"Proof of {statement}.",
        predecessors=predecessors,
    )
    graph.add_fact(fact)
    return fact


if __name__ == "__main__":
    unittest.main()
