import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.experiment import run_experiment


@unittest.skipUnless(
    os.environ.get("NOESPIRE_RUN_CODEX_SMOKE") == "1",
    "set NOESPIRE_RUN_CODEX_SMOKE=1 to invoke the real Codex CLI",
)
class CodexSmokeTests(unittest.TestCase):
    def test_real_worker_and_fresh_verifier_build_three_fact_closure(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "experiment"

            result = run_experiment(output_dir=output_dir, workdir=repository)

            self.assertEqual(len(result.facts), 3)
            self.assertEqual(
                {fact.fact_id for fact in result.closure},
                {fact.fact_id for fact in result.facts},
            )
            invocations = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((output_dir / "codex_runs").glob("*.json"))]
            self.assertEqual(len(invocations), 6)
            thread_ids = [invocation["thread_id"] for invocation in invocations]
            self.assertTrue(all(thread_ids))
            self.assertEqual(len(set(thread_ids)), 6)
            self.assertTrue((output_dir / "fact_graph" / "facts" / f"{result.final_fact.fact_id}.md").is_file())
            summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["result"], "PASS")


if __name__ == "__main__":
    unittest.main()
