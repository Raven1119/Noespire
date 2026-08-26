from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.fact import Fact
from research.graph import FactGraph


class SupportingClosureTests(unittest.TestCase):
    def test_supporting_closure_contains_target_and_all_ancestors_only(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            a = self._add(graph, "A")
            b = self._add(graph, "B")
            c = self._add(graph, "C", a.fact_id, b.fact_id)
            d = self._add(graph, "D", c.fact_id)
            self._add(graph, "unrelated")

            closure = graph.supporting_closure(d.fact_id)

            self.assertEqual({fact.fact_id for fact in closure}, {a.fact_id, b.fact_id, c.fact_id, d.fact_id})

    @staticmethod
    def _add(graph: FactGraph, statement: str, *predecessors: str) -> Fact:
        fact = Fact.create(
            problem_id="closure",
            author="worker",
            statement=statement,
            proof=f"Proof of {statement}.",
            predecessors=predecessors,
        )
        graph.add_fact(fact)
        return fact


if __name__ == "__main__":
    unittest.main()
