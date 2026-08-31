from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from application.http import create_app

from application_fixtures import WorkspaceBuilder, run_attempt


class HttpApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))
        self.client = TestClient(create_app(self.builder.root))

    def test_list_problems_returns_contract_payload(self) -> None:
        solved_dir = self.builder.add_problem("p-solved", "Solved theorem.")
        run_attempt(solved_dir, "p-solved", "Solved theorem.", accepted=True)
        self.builder.add_problem("p-open", "Open theorem.")

        response = self.client.get("/api/problems")

        self.assertEqual(response.status_code, 200)
        problems = response.json()["problems"]
        self.assertEqual(
            {item["problem_id"] for item in problems}, {"p-solved", "p-open"}
        )
        by_id = {item["problem_id"]: item for item in problems}
        self.assertEqual(by_id["p-solved"]["status"], "SOLVED")
        self.assertEqual(by_id["p-solved"]["attempt_count"], 1)
        self.assertEqual(by_id["p-open"]["status"], "OPEN")
        self.assertEqual(by_id["p-open"]["display_status"], "OPEN")
        self.assertIsNone(by_id["p-open"]["last_activity"])

    def test_get_problem_returns_full_read_model(self) -> None:
        problem_dir = self.builder.add_problem("p-solved", "Solved theorem.")
        run_attempt(problem_dir, "p-solved", "Solved theorem.", accepted=True)

        response = self.client.get("/api/problems/p-solved")

        self.assertEqual(response.status_code, 200)
        model = response.json()
        self.assertEqual(model["problem_id"], "p-solved")
        self.assertEqual(model["statement"], "Solved theorem.")
        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(model["obligation"]["status"], "DISCHARGED")
        self.assertEqual(model["attempts"][0]["verdict"], "PASS")
        self.assertEqual(model["target_fact"]["statement"], "Solved theorem.")
        self.assertEqual(len(model["supporting_closure"]), 1)
        self.assertNotIn("live", model)

    def test_get_unknown_problem_returns_404(self) -> None:
        response = self.client.get("/api/problems/p-missing")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
