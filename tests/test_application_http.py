from pathlib import Path
import threading
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


class CreateProblemHttpTests(unittest.TestCase):
    """Slice 2: POST /api/problems (spec §6)."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.root.mkdir(parents=True, exist_ok=True)
        self.client = TestClient(create_app(self.root))

    def test_post_creates_problem_and_returns_201_contract(self) -> None:
        response = self.client.post(
            "/api/problems",
            json={"statement": "Every even perfect number is triangular."},
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(
            set(payload), {"problem_id", "statement", "status", "derived_from", "archived"}
        )
        self.assertEqual(payload["statement"], "Every even perfect number is triangular.")
        self.assertEqual(payload["status"], "OPEN")
        self.assertIsNone(payload["derived_from"])
        self.assertFalse(payload["archived"])
        self.assertTrue((self.root / payload["problem_id"]).is_dir())

    def test_created_problem_appears_in_list_and_read_model(self) -> None:
        problem_id = self.client.post(
            "/api/problems", json={"statement": "A new theorem."}
        ).json()["problem_id"]

        listed = self.client.get("/api/problems").json()["problems"]
        by_id = {item["problem_id"]: item for item in listed}
        self.assertEqual(by_id[problem_id]["status"], "OPEN")
        self.assertEqual(by_id[problem_id]["attempt_count"], 0)
        self.assertIsNone(by_id[problem_id]["last_activity"])

        model = self.client.get(f"/api/problems/{problem_id}").json()
        self.assertEqual(model["status"], "OPEN")
        self.assertIsNone(model["obligation"])
        self.assertEqual(model["attempts"], [])

    def test_post_blank_statement_returns_400_without_side_effects(self) -> None:
        response = self.client.post("/api/problems", json={"statement": "  \n\t "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/problems").json()["problems"], [])
        self.assertFalse((self.root / "index.json").exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_concurrent_posts_both_persist(self) -> None:
        """Regression: two concurrent POSTs must not lose an index entry."""
        for iteration in range(5):
            with self.subTest(iteration=iteration):
                barrier = threading.Barrier(2)
                responses: list = []

                def do_post(statement: str) -> None:
                    barrier.wait()
                    responses.append(
                        self.client.post("/api/problems", json={"statement": statement})
                    )

                threads = [
                    threading.Thread(target=do_post, args=(f"Concurrent theorem {iteration} A.",)),
                    threading.Thread(target=do_post, args=(f"Concurrent theorem {iteration} B.",)),
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

                self.assertEqual([r.status_code for r in responses], [201, 201])
                created_ids = {r.json()["problem_id"] for r in responses}
                self.assertEqual(len(created_ids), 2)
                listed_ids = {
                    item["problem_id"]
                    for item in self.client.get("/api/problems").json()["problems"]
                }
                self.assertTrue(created_ids <= listed_ids)
                for problem_id in created_ids:
                    self.assertTrue((self.root / problem_id).is_dir())


if __name__ == "__main__":
    unittest.main()
