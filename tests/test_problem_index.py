import json
import os
from pathlib import Path
import threading
from tempfile import TemporaryDirectory
import time
import unittest
from unittest import mock

import application.problem_index as problem_index_module
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


class ProblemIndexAddTests(unittest.TestCase):
    """Slice 2: ProblemIndex.add — the minimal write capability (spec §4/§6)."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.index = ProblemIndex(self.root)

    def test_add_creates_index_entry(self) -> None:
        created = self.index.add("Every even perfect number is triangular.")

        self.assertRegex(
            created.problem_id,
            r"^every-even-perfect-number-is-triangular-[0-9a-f]{6}$",
        )
        self.assertEqual(created.statement, "Every even perfect number is triangular.")
        self.assertIsNone(created.derived_from)
        self.assertFalse(created.archived)
        self.assertEqual(self.index.get(created.problem_id), created)

    def test_add_sets_a_real_local_timestamp_with_offset(self) -> None:
        from datetime import datetime

        created = self.index.add("Some theorem.")

        parsed = datetime.fromisoformat(created.created_at)
        self.assertIsNotNone(parsed.tzinfo)

    def test_add_creates_an_empty_workspace_directory(self) -> None:
        created = self.index.add("Some theorem.")

        problem_dir = self.root / created.problem_id
        self.assertTrue(problem_dir.is_dir())
        self.assertEqual(list(problem_dir.iterdir()), [])

    def test_add_rejects_empty_statement(self) -> None:
        with self.assertRaises(ValueError):
            self.index.add("")

    def test_add_rejects_whitespace_only_statement(self) -> None:
        with self.assertRaises(ValueError):
            self.index.add("  \n\t  ")

    def test_rejected_add_leaves_no_side_effects(self) -> None:
        write_index(self.root, [entry("p-existing", "Existing theorem.")])

        with self.assertRaises(ValueError):
            self.index.add("   ")

        self.assertEqual(
            [item.problem_id for item in self.index.list()], ["p-existing"]
        )
        self.assertEqual(
            json.loads((self.root / "index.json").read_text(encoding="utf-8"))["problems"],
            [entry("p-existing", "Existing theorem.")],
        )

    def test_add_normalizes_whitespace(self) -> None:
        created = self.index.add("  Every even\nperfect   number  is triangular. \n")

        self.assertEqual(created.statement, "Every even perfect number is triangular.")

    def test_add_generates_unique_ids_for_rapid_identical_statements(self) -> None:
        first = self.index.add("Same statement.")
        second = self.index.add("Same statement.")

        self.assertNotEqual(first.problem_id, second.problem_id)
        self.assertTrue((self.root / first.problem_id).is_dir())
        self.assertTrue((self.root / second.problem_id).is_dir())

    def test_add_preserves_existing_entries(self) -> None:
        write_index(self.root, [entry("p-existing", "Existing theorem.")])

        created = self.index.add("New theorem.")

        listed = {item.problem_id: item for item in self.index.list()}
        self.assertEqual(set(listed), {"p-existing", created.problem_id})
        self.assertEqual(listed["p-existing"].statement, "Existing theorem.")


class ProblemIndexAddConcurrencyTests(unittest.TestCase):
    """Regression: concurrent add() calls must not lose entries (stale-read
    read-modify-write race behind FastAPI's threadpool)."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_concurrent_adds_both_persist(self) -> None:
        # A sleep inside _write_json widens the race window deterministically:
        # without a lock, both threads read the same old index before either
        # write lands, and the later write clobbers the first entry.
        real_write = problem_index_module._write_json

        def slow_write(path, payload):
            time.sleep(0.05)
            real_write(path, payload)

        for iteration in range(10):
            with self.subTest(iteration=iteration):
                root = self.root / f"case-{iteration}"
                root.mkdir()
                index = ProblemIndex(root)
                barrier = threading.Barrier(2)
                results: dict = {}
                errors: list = []

                def do_add(name: str) -> None:
                    try:
                        barrier.wait()
                        results[name] = index.add(f"Theorem {name} of case {iteration}.")
                    except Exception as error:  # noqa: BLE001 - surfaced below
                        errors.append(error)

                threads = [
                    threading.Thread(target=do_add, args=("alpha",)),
                    threading.Thread(target=do_add, args=("beta",)),
                ]
                with mock.patch.object(problem_index_module, "_write_json", slow_write):
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join()

                self.assertEqual(errors, [])
                self.assertEqual(set(results), {"alpha", "beta"})
                listed = {item.problem_id for item in ProblemIndex(root).list()}
                self.assertEqual(
                    listed, {results["alpha"].problem_id, results["beta"].problem_id}
                )
                for created in results.values():
                    self.assertTrue((root / created.problem_id).is_dir())


class ProblemIndexAddRollbackTests(unittest.TestCase):
    """A failed index write must not leave an unindexed workspace dir behind."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_failed_index_write_removes_freshly_created_workspace_dir(self) -> None:
        write_index(self.root, [entry("p-existing", "Existing theorem.")])
        (self.root / "p-existing").mkdir()
        before = json.loads((self.root / "index.json").read_text(encoding="utf-8"))

        with mock.patch.object(
            problem_index_module, "_write_json", side_effect=OSError("disk full")
        ):
            with self.assertRaises(OSError):
                ProblemIndex(self.root).add("New theorem.")

        self.assertEqual(
            sorted(path.name for path in self.root.iterdir()),
            ["index.json", "p-existing"],
        )
        self.assertEqual(
            json.loads((self.root / "index.json").read_text(encoding="utf-8")), before
        )


class ProblemIndexForkTests(unittest.TestCase):
    """Slice 5: ProblemIndex.fork — revision is a new problem with lineage,
    never an edit (ADR-0001, spec §6)."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.index = ProblemIndex(self.root)

    def test_fork_creates_child_with_lineage(self) -> None:
        parent = self.index.add("Parent theorem.")

        child = self.index.fork(parent.problem_id, "Revised statement.")

        self.assertEqual(child.derived_from, parent.problem_id)
        self.assertFalse(child.archived)
        self.assertEqual(child.statement, "Revised statement.")
        self.assertNotEqual(child.problem_id, parent.problem_id)
        self.assertEqual(self.index.get(child.problem_id), child)

    def test_fork_leaves_parent_untouched(self) -> None:
        parent = self.index.add("Parent theorem.")

        self.index.fork(parent.problem_id, "Revised statement.")

        self.assertEqual(self.index.get(parent.problem_id), parent)
        self.assertEqual(list((self.root / parent.problem_id).iterdir()), [])

    def test_fork_creates_an_empty_child_workspace(self) -> None:
        parent = self.index.add("Parent theorem.")
        # Give the parent core content; none of it may leak into the child.
        attempts = self.root / parent.problem_id / "attempts"
        attempts.mkdir(parents=True)
        (attempts / "attempt-000001.json").write_text("{}", encoding="utf-8")

        child = self.index.fork(parent.problem_id, "Revised statement.")

        child_dir = self.root / child.problem_id
        self.assertTrue(child_dir.is_dir())
        self.assertEqual(list(child_dir.iterdir()), [])

    def test_fork_rejects_blank_statement(self) -> None:
        parent = self.index.add("Parent theorem.")

        with self.assertRaises(ValueError):
            self.index.fork(parent.problem_id, "  \n\t ")

        self.assertEqual(
            [item.problem_id for item in self.index.list()], [parent.problem_id]
        )

    def test_fork_unknown_parent_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            self.index.fork("p-missing", "Revised statement.")

        self.assertEqual(self.index.list(), [])

    def test_fork_of_archived_parent_is_allowed(self) -> None:
        parent = self.index.add("Parent theorem.")
        self.index.set_archived(parent.problem_id, True)

        child = self.index.fork(parent.problem_id, "Revised statement.")

        self.assertEqual(child.derived_from, parent.problem_id)
        self.assertFalse(child.archived)

    def test_fork_allows_identical_statement(self) -> None:
        """Fork is version identity, not a diff validator."""
        parent = self.index.add("Same statement.")

        child = self.index.fork(parent.problem_id, "Same statement.")

        self.assertEqual(child.statement, parent.statement)
        self.assertNotEqual(child.problem_id, parent.problem_id)


class ProblemIndexForkConcurrencyTests(unittest.TestCase):
    """Regression: concurrent forks (and fork/add mixes) must not lose
    entries — same stale-read clobber class as concurrent add()."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _slow_write(self):
        real_write = problem_index_module._write_json

        def slow_write(path, payload):
            time.sleep(0.05)
            real_write(path, payload)

        return mock.patch.object(problem_index_module, "_write_json", slow_write)

    def test_concurrent_forks_of_same_parent_both_persist(self) -> None:
        for iteration in range(10):
            with self.subTest(iteration=iteration):
                root = self.root / f"case-{iteration}"
                root.mkdir()
                index = ProblemIndex(root)
                parent = index.add(f"Parent theorem of case {iteration}.")
                barrier = threading.Barrier(2)
                results: dict = {}
                errors: list = []

                def do_fork(name: str) -> None:
                    try:
                        barrier.wait()
                        results[name] = index.fork(
                            parent.problem_id, f"Fork {name} of case {iteration}."
                        )
                    except Exception as error:  # noqa: BLE001 - surfaced below
                        errors.append(error)

                threads = [
                    threading.Thread(target=do_fork, args=("alpha",)),
                    threading.Thread(target=do_fork, args=("beta",)),
                ]
                with self._slow_write():
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join()

                self.assertEqual(errors, [])
                self.assertEqual(set(results), {"alpha", "beta"})
                listed = {item.problem_id for item in ProblemIndex(root).list()}
                self.assertEqual(
                    listed,
                    {
                        parent.problem_id,
                        results["alpha"].problem_id,
                        results["beta"].problem_id,
                    },
                )
                for child in results.values():
                    self.assertEqual(child.derived_from, parent.problem_id)
                    self.assertTrue((root / child.problem_id).is_dir())

    def test_concurrent_fork_and_add_lose_no_entries(self) -> None:
        for iteration in range(10):
            with self.subTest(iteration=iteration):
                root = self.root / f"mixed-{iteration}"
                root.mkdir()
                index = ProblemIndex(root)
                parent = index.add(f"Parent theorem of case {iteration}.")
                barrier = threading.Barrier(2)
                results: dict = {}
                errors: list = []

                def do_fork() -> None:
                    try:
                        barrier.wait()
                        results["fork"] = index.fork(
                            parent.problem_id, f"Fork of case {iteration}."
                        )
                    except Exception as error:  # noqa: BLE001
                        errors.append(error)

                def do_add() -> None:
                    try:
                        barrier.wait()
                        results["add"] = index.add(f"Fresh theorem of case {iteration}.")
                    except Exception as error:  # noqa: BLE001
                        errors.append(error)

                threads = [
                    threading.Thread(target=do_fork),
                    threading.Thread(target=do_add),
                ]
                with self._slow_write():
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join()

                self.assertEqual(errors, [])
                listed = {item.problem_id for item in ProblemIndex(root).list()}
                self.assertEqual(
                    listed,
                    {parent.problem_id, results["fork"].problem_id, results["add"].problem_id},
                )


class ProblemIndexForkRollbackTests(unittest.TestCase):
    """A failed index write on fork must not leave an unindexed dir behind."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_failed_index_write_removes_freshly_created_fork_dir(self) -> None:
        index = ProblemIndex(self.root)
        parent = index.add("Parent theorem.")
        before = json.loads((self.root / "index.json").read_text(encoding="utf-8"))

        with mock.patch.object(
            problem_index_module, "_write_json", side_effect=OSError("disk full")
        ):
            with self.assertRaises(OSError):
                index.fork(parent.problem_id, "Revised statement.")

        self.assertEqual(
            sorted(path.name for path in self.root.iterdir()),
            ["index.json", parent.problem_id],
        )
        self.assertEqual(
            json.loads((self.root / "index.json").read_text(encoding="utf-8")), before
        )


class ProblemIndexArchiveTests(unittest.TestCase):
    """Slice 5: ProblemIndex.set_archived — metadata-only, idempotent."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.index = ProblemIndex(self.root)

    def test_archive_marks_entry_and_persists(self) -> None:
        created = self.index.add("Some theorem.")

        archived = self.index.set_archived(created.problem_id, True)

        self.assertTrue(archived.archived)
        self.assertEqual(archived.problem_id, created.problem_id)
        self.assertTrue(self.index.get(created.problem_id).archived)
        self.assertTrue(
            ProblemIndex(self.root).get(created.problem_id).archived
        )

    def test_unarchive_clears_the_flag(self) -> None:
        created = self.index.add("Some theorem.")
        self.index.set_archived(created.problem_id, True)

        restored = self.index.set_archived(created.problem_id, False)

        self.assertFalse(restored.archived)
        self.assertFalse(self.index.get(created.problem_id).archived)

    def test_archive_is_idempotent_in_both_directions(self) -> None:
        created = self.index.add("Some theorem.")

        self.assertFalse(self.index.set_archived(created.problem_id, False).archived)
        self.assertTrue(self.index.set_archived(created.problem_id, True).archived)
        self.assertTrue(self.index.set_archived(created.problem_id, True).archived)

    def test_archive_unknown_problem_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            self.index.set_archived("p-missing", True)

    def test_archive_does_not_touch_core_files(self) -> None:
        created = self.index.add("Some theorem.")
        problem_dir = self.root / created.problem_id
        attempts = problem_dir / "attempts"
        attempts.mkdir()
        attempt_file = attempts / "attempt-000001.json"
        attempt_file.write_text('{"verdict": "PASS"}', encoding="utf-8")
        log = problem_dir / "_execution_log.jsonl"
        log.write_text('{"event": "attempt_started"}\n', encoding="utf-8")

        self.index.set_archived(created.problem_id, True)

        self.assertEqual(attempt_file.read_text(encoding="utf-8"), '{"verdict": "PASS"}')
        self.assertEqual(
            log.read_text(encoding="utf-8"), '{"event": "attempt_started"}\n'
        )

    def test_failed_archive_write_leaves_old_index_authoritative(self) -> None:
        created = self.index.add("Some theorem.")
        before = json.loads((self.root / "index.json").read_text(encoding="utf-8"))

        with mock.patch.object(
            problem_index_module, "_write_json", side_effect=OSError("disk full")
        ):
            with self.assertRaises(OSError):
                self.index.set_archived(created.problem_id, True)

        self.assertFalse(self.index.get(created.problem_id).archived)
        self.assertEqual(
            json.loads((self.root / "index.json").read_text(encoding="utf-8")), before
        )
        # No directory side effects to roll back — archive is metadata-only.
        self.assertEqual(
            sorted(path.name for path in self.root.iterdir()),
            ["index.json", created.problem_id],
        )


if __name__ == "__main__":
    unittest.main()
