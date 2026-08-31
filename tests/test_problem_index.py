import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from application.problem_index import ProblemIndex


def write_index(root: Path, entries: list) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.json").write_text(
        json.dumps({"problems": entries}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def entry(problem_id: str, statement: str, **overrides) -> dict:
    payload = {
        "problem_id": problem_id,
        "statement": statement,
        "derived_from": None,
        "archived": False,
        "created_at": "2026-08-31T10:15:00+08:00",
    }
    payload.update(overrides)
    return payload


class ProblemIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_lists_entries_from_index(self) -> None:
        write_index(self.root, [entry("p-one", "First theorem."), entry("p-two", "Second theorem.")])

        listed = ProblemIndex(self.root).list()

        self.assertEqual([item.problem_id for item in listed], ["p-one", "p-two"])
        self.assertEqual(listed[0].statement, "First theorem.")
        self.assertIsNone(listed[0].derived_from)
        self.assertFalse(listed[0].archived)
        self.assertEqual(listed[0].created_at, "2026-08-31T10:15:00+08:00")
    def test_get_returns_entry_by_problem_id(self) -> None:
        write_index(
            self.root,
            [entry("p-one", "First theorem."), entry("p-two", "Second theorem.", derived_from="p-one")],
        )

        found = ProblemIndex(self.root).get("p-two")

        self.assertEqual(found.problem_id, "p-two")
        self.assertEqual(found.derived_from, "p-one")

    def test_get_unknown_problem_id_raises_key_error(self) -> None:
        write_index(self.root, [entry("p-one", "First theorem.")])

        with self.assertRaises(KeyError):
            ProblemIndex(self.root).get("p-missing")

    def test_missing_index_file_lists_nothing(self) -> None:
        index = ProblemIndex(self.root)

        self.assertEqual(index.list(), [])
        with self.assertRaises(KeyError):
            index.get("p-one")

    def test_archived_entries_are_listed(self) -> None:
        write_index(self.root, [entry("p-old", "Old theorem.", archived=True)])

        listed = ProblemIndex(self.root).list()

        self.assertEqual(len(listed), 1)
        self.assertTrue(listed[0].archived)

    def _attempt_file(self, problem_id: str, name: str, mtime: float) -> None:
        attempts = self.root / problem_id / "attempts"
        attempts.mkdir(parents=True, exist_ok=True)
        path = attempts / name
        path.write_text("{}", encoding="utf-8")
        os.utime(path, (mtime, mtime))

    def test_list_orders_by_last_activity_descending(self) -> None:
        write_index(
            self.root,
            [
                entry("p-quiet", "No attempts yet."),
                entry("p-recent", "Touched later."),
                entry("p-earlier", "Touched earlier."),
            ],
        )
        self._attempt_file("p-earlier", "attempt-000001.json", 1_000_000.0)
        self._attempt_file("p-recent", "attempt-000001.json", 2_000_000.0)

        listed = ProblemIndex(self.root).list()

        self.assertEqual(
            [item.problem_id for item in listed],
            ["p-recent", "p-earlier", "p-quiet"],
        )

    def test_list_breaks_activity_ties_by_problem_id(self) -> None:
        write_index(
            self.root,
            [entry("p-b", "Theorem B."), entry("p-a", "Theorem A.")],
        )
        self._attempt_file("p-a", "attempt-000001.json", 1_000_000.0)
        self._attempt_file("p-b", "attempt-000001.json", 1_000_000.0)

        listed = ProblemIndex(self.root).list()

        self.assertEqual([item.problem_id for item in listed], ["p-a", "p-b"])

    def test_execution_log_mtime_counts_as_activity(self) -> None:
        write_index(
            self.root,
            [entry("p-a", "Theorem A."), entry("p-b", "Theorem B.")],
        )
        self._attempt_file("p-a", "attempt-000001.json", 1_000_000.0)
        log = self.root / "p-b" / "_execution_log.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("", encoding="utf-8")
        os.utime(log, (3_000_000.0, 3_000_000.0))

        listed = ProblemIndex(self.root).list()

        self.assertEqual([item.problem_id for item in listed], ["p-b", "p-a"])


if __name__ == "__main__":
    unittest.main()
