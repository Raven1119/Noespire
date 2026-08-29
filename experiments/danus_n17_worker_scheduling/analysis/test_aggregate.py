from __future__ import annotations

import unittest

from experiments.danus_n17_worker_scheduling.analysis import aggregate


class AggregateEvidenceTests(unittest.TestCase):
    def test_frozen_eight_run_totals(self) -> None:
        evidence = aggregate.build_evidence()

        self.assertEqual(evidence["B"]["valid_runs"], 4)
        self.assertEqual(evidence["B"]["solved"], 4)
        self.assertEqual(evidence["B"]["workers_launched"], 4)
        self.assertEqual(evidence["B"]["verified_fact_count"], 5)
        self.assertEqual(evidence["B"]["outside_closure_count"], 1)
        self.assertEqual(evidence["B"]["total_tokens"], 443101)
        self.assertAlmostEqual(evidence["B"]["total_wall_clock_seconds"], 1554.057335)

        self.assertEqual(evidence["C"]["valid_runs"], 4)
        self.assertEqual(evidence["C"]["solved"], 4)
        self.assertEqual(evidence["C"]["workers_launched"], 4)
        self.assertEqual(evidence["C"]["verified_fact_count"], 4)
        self.assertEqual(evidence["C"]["outside_closure_count"], 0)
        self.assertEqual(evidence["C"]["total_tokens"], 364443)
        self.assertAlmostEqual(evidence["C"]["total_wall_clock_seconds"], 1203.444109)
        self.assertEqual(evidence["C"]["first_success_indices"], [1, 1, 1, 1])
        self.assertEqual(evidence["C"]["unused_worker_budget"], 24)

    def test_gate_selects_demand_driven_not_sequential_escalation(self) -> None:
        evidence = aggregate.build_evidence()

        self.assertEqual(aggregate.verdict(evidence), "DEMAND_DRIVEN_EXECUTION_SUPPORTED")


if __name__ == "__main__":
    unittest.main()
