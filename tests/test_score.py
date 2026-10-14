import json
import tempfile
import unittest
from pathlib import Path

from bench.score import (
    ArmMetrics,
    count_nudges,
    parse_complexipy,
    parse_transcript,
    parse_verdict,
    results_rows,
    summary_markdown,
)

META = {
    "comparison_id": "2026-10-15-feat",
    "feature": "feat",
    "snapshot_tag": "bench/feat",
    "claude_code_version": "2.1.300",
    "change": "add-feat",
    "run_order": ["Y", "X"],
}


def arm_metrics(arm: str, role: str) -> ArmMetrics:
    return ArmMetrics(
        arm=arm,
        role=role,
        setup_sha="abc",
        final_commit="def",
        uncommitted_changes=False,
        lines_changed=120,
        files_touched=4,
        cognitive_total=30,
        cognitive_worst=9,
        unit_tests_pass=True,
        nudges=0,
        turns=42,
        cost_usd=3.456,
        model="arm-model",
        run_error=False,
    )


class ParseTest(unittest.TestCase):
    def test_complexipy_plain_lines(self) -> None:
        output = "header line\njobsearch/scrape.py scrape_post 4\njobsearch/scrape.py _f 11\n"
        self.assertEqual(parse_complexipy(output), [4, 11])

    def test_transcript_init_and_result(self) -> None:
        lines = [
            {"type": "system", "subtype": "init", "model": "arm-model"},
            {"type": "assistant"},
            {"type": "result", "num_turns": 42, "total_cost_usd": 3.5, "is_error": False},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.jsonl"
            path.write_text("\n".join(json.dumps(line) for line in lines))
            summary = parse_transcript(path)
        self.assertEqual(
            summary, {"model": "arm-model", "turns": 42, "cost_usd": 3.5, "run_error": False}
        )

    def test_missing_transcript(self) -> None:
        self.assertIsNone(parse_transcript(Path("/nonexistent"))["turns"])

    def test_nudges_count_rows_of_one_arm(self) -> None:
        log = "| Arm | Question | Answer |\n| -- | -- | -- |\n| X | q1 | a1 |\n| Y | q2 | a2 |\n"
        self.assertEqual(count_nudges(log, "X"), 1)

    def test_verdict_is_the_last_preferred_line(self) -> None:
        self.assertEqual(parse_verdict("PREFERRED: X\nreasoning\nPREFERRED: Y\n"), "Y")
        self.assertIsNone(parse_verdict("no verdict"))


class OutputTest(unittest.TestCase):
    def test_results_rows_mark_the_preferred_arm(self) -> None:
        arms = [arm_metrics("X", "champion"), arm_metrics("Y", "candidate")]
        rows = results_rows(META, arms, "Y")
        self.assertEqual([row["judge_preferred"] for row in rows], ["no", "yes"])
        self.assertEqual(rows[0]["cost_usd"], 3.46)
        self.assertEqual(rows[1]["date"], "2026-10-15")

    def test_tie_and_missing_verdict(self) -> None:
        arms = [arm_metrics("X", "champion")]
        self.assertEqual(results_rows(META, arms, "TIE")[0]["judge_preferred"], "tie")
        self.assertEqual(results_rows(META, arms, None)[0]["judge_preferred"], "")

    def test_summary_lists_each_arm(self) -> None:
        arms = [arm_metrics("X", "champion"), arm_metrics("Y", "candidate")]
        text = summary_markdown(META, arms, "X")
        self.assertIn("| role | champion | candidate |", text)
        self.assertIn("Run order: Y, X.", text)


if __name__ == "__main__":
    unittest.main()
