"""Scores both arms of a comparison after their runs.

Per arm: diff size against the snapshot tag, cognitive complexity of the changed Python
files, unit test result, turns and cost from the transcript, and nudges from qa-log.md. A
judge compares both diffs on a different model than the arms. Writes metrics/, one
results.csv row per arm and a draft summary.md. The X/Y mapping is read only here.
"""

import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from bench.config import BENCH_ROOT, Config
from bench.prepare import ARMS, arm_env

RESULTS_CSV = BENCH_ROOT / "results.csv"
# complexipy is a dependency of the bench, installed next to the running interpreter.
COMPLEXIPY = Path(sys.executable).parent / "complexipy"
JUDGE_PROMPT = BENCH_ROOT / "bench" / "instruments" / "judge.md"
UNIT_TESTS = ["python3", "-m", "unittest", "discover", "-s", "tests/unit"]
PREFERRED_RE = re.compile(r"^PREFERRED:\s*(X|Y|TIE)\s*$", re.MULTILINE)


@dataclass
class ArmMetrics:
    arm: str
    role: str
    setup_sha: str
    final_commit: str
    uncommitted_changes: bool
    lines_changed: int
    files_touched: int
    cognitive_total: int
    cognitive_worst: int
    unit_tests_pass: bool
    nudges: int
    turns: int | None
    cost_usd: float | None
    model: str | None
    run_error: bool | None


def _run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, check=True, capture_output=True, text=True)
    return result.stdout


def _diff_size(repo: Path, tag: str) -> tuple[int, int]:
    lines = 0
    files = 0
    for row in _run(["git", "diff", "--numstat", tag, "HEAD"], repo).splitlines():
        added, deleted, _ = row.split("\t", 2)
        files += 1
        if added != "-":
            lines += int(added) + int(deleted)
    return lines, files


def parse_complexipy(output: str) -> list[int]:
    """Function scores from `complexipy --plain` lines: `<file> <function> <score>`."""
    scores = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2].isdigit():
            scores.append(int(fields[2]))
    return scores


def _complexity(repo: Path, tag: str, raw_path: Path) -> tuple[int, int]:
    changed = _run(
        ["git", "diff", "--name-only", "--diff-filter=d", tag, "HEAD", "--", "*.py"], repo
    ).split()
    if not changed:
        raw_path.write_text("")
        return 0, 0
    # Exit status 1 means a function exceeds complexipy's default limit; the output is valid.
    result = subprocess.run(
        [str(COMPLEXIPY), *changed, "--plain", "--sort", "desc", "--color", "no"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    raw_path.write_text(result.stdout)
    scores = parse_complexipy(result.stdout)
    return sum(scores), max(scores, default=0)


def _unit_tests_pass(repo: Path, env: dict[str, str], log_path: Path) -> bool:
    log = []
    for command in (
        ["podman-compose", "build", "job-search"],
        ["podman-compose", "run", "--rm", "-T", "job-search", *UNIT_TESTS],
        ["podman-compose", "down"],
    ):
        result = subprocess.run(
            command, cwd=repo, env=env, capture_output=True, text=True, check=False
        )
        log.append(result.stdout + result.stderr)
        if command[1] == "run":
            passed = result.returncode == 0
    log_path.write_text("\n".join(log))
    return passed


def parse_transcript(path: Path) -> dict:
    """Model, turns, cost and error flag from a `claude -p --output-format stream-json` file."""
    summary = {"model": None, "turns": None, "cost_usd": None, "run_error": None}
    if not path.exists():
        return summary
    for line in path.read_text().splitlines():
        message = json.loads(line)
        if message.get("type") == "system" and message.get("subtype") == "init":
            summary["model"] = message.get("model")
        elif message.get("type") == "result":
            summary["turns"] = message.get("num_turns")
            summary["cost_usd"] = message.get("total_cost_usd")
            summary["run_error"] = message.get("is_error")
    return summary


def count_nudges(qa_log: str, arm: str) -> int:
    """Rows of the qa-log.md table whose first cell is the arm label."""
    return sum(1 for line in qa_log.splitlines() if re.match(rf"^\|\s*{arm}\s*\|", line))


def _score_arm(config: Config, comparison_id: str, arm: str, meta: dict, role: str) -> ArmMetrics:
    arm_dir = config.workspace / comparison_id / arm
    repo = arm_dir / "repo"
    metrics_dir = config.comparisons / comparison_id / "metrics"
    tag = meta["snapshot_tag"]
    env = {**os.environ, **arm_env(arm_dir)}

    lines, files = _diff_size(repo, tag)
    total, worst = _complexity(repo, tag, metrics_dir / f"complexipy-{arm}.txt")
    qa_log = (config.comparisons / comparison_id / "qa-log.md").read_text()
    return ArmMetrics(
        arm=arm,
        role=role,
        setup_sha=meta[f"{role}_sha"],
        final_commit=_run(["git", "rev-parse", "HEAD"], repo).strip(),
        uncommitted_changes=bool(_run(["git", "status", "--porcelain"], repo).strip()),
        lines_changed=lines,
        files_touched=files,
        cognitive_total=total,
        cognitive_worst=worst,
        unit_tests_pass=_unit_tests_pass(repo, env, metrics_dir / f"unit-tests-{arm}.txt"),
        nudges=count_nudges(qa_log, arm),
        **parse_transcript(arm_dir / "transcript.jsonl"),
    )


def _judge_input(config: Config, comparison_id: str, meta: dict) -> str:
    tag = meta["snapshot_tag"]
    change_dir = f"openspec/changes/{meta['change']}"
    first_repo = config.workspace / comparison_id / ARMS[0] / "repo"
    files = _run(["git", "ls-tree", "-r", "--name-only", tag, change_dir], first_repo).split()
    parts = [JUDGE_PROMPT.read_text(), "# OpenSpec change"]
    for name in files:
        parts.append(f"## {name}\n\n{_run(['git', 'show', f'{tag}:{name}'], first_repo)}")
    for arm in ARMS:
        repo = config.workspace / comparison_id / arm / "repo"
        diff = _run(["git", "diff", "--text", tag, "HEAD", "--", ".", ":!*.png"], repo)
        parts.append(f"# Implementation {arm}\n\n```diff\n{diff}```")
    return "\n\n".join(parts)


def parse_verdict(text: str) -> str | None:
    matches = PREFERRED_RE.findall(text)
    return matches[-1] if matches else None


def _judge(config: Config, comparison_id: str, meta: dict) -> str | None:
    """Runs the judge in an empty directory with its own config dir. Returns X, Y, TIE or None."""
    run_dir = config.workspace / comparison_id
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(run_dir / "judge-config")}
    command = ["claude", "-p", "--model", config.judge_model, "--output-format", "text"]
    with tempfile.TemporaryDirectory() as empty:
        result = subprocess.run(
            command,
            input=_judge_input(config, comparison_id, meta),
            cwd=empty,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
    judge_path = config.comparisons / comparison_id / "metrics" / "judge.md"
    judge_path.write_text(f"Model: {config.judge_model}\n\n{result.stdout}")
    return parse_verdict(result.stdout)


def results_rows(meta: dict, arms: list[ArmMetrics], verdict: str | None) -> list[dict]:
    rows = []
    for metrics in arms:
        if verdict == "TIE":
            preferred = "tie"
        elif verdict is None:
            preferred = ""
        else:
            preferred = "yes" if verdict == metrics.arm else "no"
        rows.append(
            {
                "comparison_id": meta["comparison_id"],
                "date": meta["comparison_id"][:10],
                "feature": meta["feature"],
                "snapshot_tag": meta["snapshot_tag"],
                "arm": metrics.arm,
                "role": metrics.role,
                "setup_sha": metrics.setup_sha,
                "model": metrics.model or "",
                "claude_code_version": meta.get("claude_code_version") or "",
                "lines_changed": metrics.lines_changed,
                "files_touched": metrics.files_touched,
                "cognitive_total": metrics.cognitive_total,
                "cognitive_worst": metrics.cognitive_worst,
                "nudges": metrics.nudges,
                "turns": "" if metrics.turns is None else metrics.turns,
                "cost_usd": "" if metrics.cost_usd is None else round(metrics.cost_usd, 2),
                "judge_preferred": preferred,
            }
        )
    return rows


def _append_results(rows: list[dict], comparison_id: str) -> None:
    with RESULTS_CSV.open(newline="") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames
        if any(row["comparison_id"] == comparison_id for row in reader):
            raise FileExistsError(f"{comparison_id} is already in {RESULTS_CSV}")
    with RESULTS_CSV.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, restval="")
        writer.writerows(rows)


SUMMARY_FIELDS = (
    "role",
    "setup_sha",
    "lines_changed",
    "files_touched",
    "cognitive_total",
    "cognitive_worst",
    "unit_tests_pass",
    "uncommitted_changes",
    "nudges",
    "turns",
    "cost_usd",
    "run_error",
)


def summary_markdown(meta: dict, arms: list[ArmMetrics], verdict: str | None) -> str:
    header = "| Metric | " + " | ".join(m.arm for m in arms) + " |"
    lines = [
        f"# {meta['comparison_id']}",
        "",
        f"Feature: {meta['feature']}. Snapshot: `{meta['snapshot_tag']}`. "
        f"Change: `{meta.get('change')}`. Run order: {', '.join(meta.get('run_order', []))}.",
        "",
        "## Metrics",
        "",
        header,
        "| -- " * (len(arms) + 1) + "|",
    ]
    for field in SUMMARY_FIELDS:
        values = [str(asdict(m)[field]) for m in arms]
        lines.append(f"| {field} | " + " | ".join(values) + " |")
    lines += [
        "",
        f"Judge ({meta.get('judge_model', '')}): preferred {verdict or 'no verdict'}. "
        "See metrics/judge.md.",
        "",
        "## Suggested decision",
        "",
        "Inconclusive until a v0-vs-v0 baseline gives the noise band for each metric.",
        "",
        "## Notes",
        "",
        "## Decision",
        "",
    ]
    return "\n".join(lines)


def score(config: Config, comparison_id: str) -> list[ArmMetrics]:
    comparison_dir = config.comparisons / comparison_id
    if (comparison_dir / "summary.md").exists():
        raise FileExistsError(comparison_dir / "summary.md")
    meta = json.loads((comparison_dir / "meta.json").read_text())
    mapping = json.loads((config.workspace / comparison_id / "mapping.json").read_text())

    arms = [_score_arm(config, comparison_id, arm, meta, mapping[arm]) for arm in ARMS]
    for metrics in arms:
        path = comparison_dir / "metrics" / f"{metrics.arm}.json"
        path.write_text(json.dumps(asdict(metrics), indent=2) + "\n")
    verdict = _judge(config, comparison_id, meta)
    meta.update(judge_model=config.judge_model, mapping=mapping)
    (comparison_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    _append_results(results_rows(meta, arms, verdict), comparison_id)
    (comparison_dir / "summary.md").write_text(summary_markdown(meta, arms, verdict))
    return arms
