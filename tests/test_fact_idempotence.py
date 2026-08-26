from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.fact import Fact
from research.graph import FactGraph


class FactIdempotenceTests(unittest.TestCase):
    def test_same_content_from_another_author_is_idempotent(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            first = Fact.create(
                problem_id="p",
                author="worker-a",
                statement="A",
                proof="Proof of A.",
            )
            duplicate = Fact.create(
                problem_id="p",
                author="worker-b",
                statement=" A ",
                proof="Proof  of A.",
            )

            stored = graph.add_fact(first)
            deduplicated = graph.add_fact(duplicate)

            self.assertEqual(first.fact_id, duplicate.fact_id)
            self.assertEqual(deduplicated, stored)
            self.assertEqual(graph.list_facts(), [stored])


if __name__ == "__main__":
    unittest.main()
