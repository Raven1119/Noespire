from __future__ import annotations

import unittest

from experiments.danus_n18_matched_scheduling.scheduler import run_schedule


class SchedulingContractTests(unittest.TestCase):
    def test_parallel_launches_exactly_seven(self) -> None:
        batches = []
        outcome = run_schedule("A", lambda batch: batches.append(batch) or True)
        self.assertEqual(batches, [tuple(range(1, 8))])
        self.assertEqual(outcome.workers_launched, 7)

    def test_single_launches_exactly_one(self) -> None:
        batches = []
        outcome = run_schedule("B", lambda batch: batches.append(batch) or False)
        self.assertEqual(batches, [(1,)])
        self.assertEqual(outcome.workers_launched, 1)

    def test_sequential_stops_after_pass(self) -> None:
        batches = []
        run_schedule("C", lambda batch: batches.append(batch) or batch == (3,))
        self.assertEqual(batches, [(1,), (2,), (3,)])

    def test_sequential_advances_after_fail(self) -> None:
        batches = []
        run_schedule("C", lambda batch: batches.append(batch) or batch == (2,))
        self.assertEqual(batches[:2], [(1,), (2,)])

    def test_sequential_maximum_is_seven(self) -> None:
        batches = []
        outcome = run_schedule("C", lambda batch: batches.append(batch) or False)
        self.assertEqual(batches, [(index,) for index in range(1, 8)])
        self.assertEqual(outcome.workers_launched, 7)


if __name__ == "__main__":
    unittest.main()
