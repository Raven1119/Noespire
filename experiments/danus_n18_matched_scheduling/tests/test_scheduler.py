from __future__ import annotations

import unittest

from experiments.danus_n18_matched_scheduling.scheduler import run_schedule


class MatchedSchedulingTests(unittest.TestCase):
    def test_parallel_launches_all_seven_in_one_batch(self) -> None:
        batches: list[tuple[int, ...]] = []

        outcome = run_schedule("A", lambda batch: batches.append(batch) or True)

        self.assertEqual(batches, [tuple(range(1, 8))])
        self.assertEqual(outcome.workers_launched, 7)

    def test_single_launches_one_regardless_of_failure(self) -> None:
        batches: list[tuple[int, ...]] = []

        outcome = run_schedule("B", lambda batch: batches.append(batch) or False)

        self.assertEqual(batches, [(1,)])
        self.assertFalse(outcome.solved)

    def test_sequential_stops_after_pass(self) -> None:
        batches: list[tuple[int, ...]] = []

        outcome = run_schedule(
            "C", lambda batch: batches.append(batch) or batch == (3,)
        )

        self.assertEqual(batches, [(1,), (2,), (3,)])
        self.assertEqual(outcome.first_success_index, 3)
        self.assertTrue(outcome.stopped_after_success)

    def test_sequential_launches_next_after_failure(self) -> None:
        batches: list[tuple[int, ...]] = []

        run_schedule("C", lambda batch: batches.append(batch) or batch == (2,))

        self.assertEqual(batches[:2], [(1,), (2,)])

    def test_sequential_never_exceeds_seven(self) -> None:
        batches: list[tuple[int, ...]] = []

        outcome = run_schedule("C", lambda batch: batches.append(batch) or False)

        self.assertEqual(batches, [(i,) for i in range(1, 8)])
        self.assertEqual(outcome.workers_launched, 7)
        self.assertEqual(outcome.workers_saved, 0)


if __name__ == "__main__":
    unittest.main()
