from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.fact import Fact
from research.graph import FactGraph


class FactGraphTests(unittest.TestCase):
    def test_predecessors_survive_graph_reload(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            premise = Fact.create(
                problem_id="p",
                author="worker",
                statement="A",
                proof="Proof of A.",
            )
            conclusion = Fact.create(
                problem_id="p",
                author="worker",
                statement="C",
                proof="A implies C.",
                predecessors=(premise.fact_id,),
            )

            graph.add_fact(premise)
            graph.add_fact(conclusion)
            reloaded = FactGraph(Path(directory))

            self.assertEqual(reloaded.get_fact(conclusion.fact_id), conclusion)
            self.assertEqual(reloaded.predecessors(conclusion.fact_id), [premise])


if __name__ == "__main__":
    unittest.main()
