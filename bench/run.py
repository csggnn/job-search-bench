"""Runs code generation headless in each arm of a prepared comparison.

Before the arms run, the judge model reads the feature description once and names the tasks
a headless arm cannot perform. Both arms get the same prompt, which excludes those tasks.
Each arm runs `claude -p` in its own clone and config dir, with its own version of the
setup plugin. The arms run one after the other, in random order. The stream-json
transcript and stderr go to the arm's workspace dir, outside the bench repo.
"""

import json
import os
import random
import re
import subprocess
import tempfile

from bench.config import BENCH_ROOT, Config
from bench.prepare import ARMS, arm_env, plugin_dir
from bench.spec import spec_text

TRIAGE_PROMPT = BENCH_ROOT / "bench" / "instruments" / "task-triage.md"
SKIP_RE = re.compile(r"^SKIP:\s*(.+?)\s*$", re.MULTILINE)

PROMPT = (
    "Implement the feature described in `{spec}`{skip}. "
    "The description is anchored, not fixed: change its spec or design where the change "
    "makes the code simpler and keeps the feature's purpose, and update the description "
    "files to match the code. "
    "Then commit all changes on the current branch."
)
SKIP = ", except tasks {tasks}: leave them undone and unchecked"


def prompt(spec: str, skip_tasks: list[str]) -> str:
    """The prompt of both arms."""
    skip = SKIP.format(tasks=", ".join(skip_tasks)) if skip_tasks else ""
    return PROMPT.format(spec=spec, skip=skip)


def parse_skip(text: str) -> list[str]:
    """Task IDs from the triage's last `SKIP:` line. `none` gives an empty list."""
    matches = SKIP_RE.findall(text)
    if not matches:
        raise ValueError("task triage gave no SKIP line")
    if matches[-1].lower() == "none":
        return []
    return [task.strip() for task in matches[-1].split(",")]


def _triage_tasks(config: Config, comparison_id: str, meta: dict, spec: str) -> list[str]:
    """Runs the task triage on the judge model and writes its reasoning to task-triage.md."""
    run_dir = config.workspace / comparison_id
    description = spec_text(run_dir / ARMS[0] / "repo", meta["snapshot_tag"], spec)
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(run_dir / "judge-config")}
    command = ["claude", "-p", "--model", config.judge_model, "--output-format", "text"]
    with tempfile.TemporaryDirectory() as empty:
        result = subprocess.run(
            command,
            input=f"{TRIAGE_PROMPT.read_text()}\n# Feature description\n\n{description}",
            cwd=empty,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
    triage_path = config.comparisons / comparison_id / "task-triage.md"
    triage_path.write_text(f"Model: {config.judge_model}\n\n{result.stdout}")
    return parse_skip(result.stdout)


def _run_arm(config: Config, comparison_id: str, arm: str, text: str) -> int:
    arm_dir = config.workspace / comparison_id / arm
    transcript = arm_dir / "transcript.jsonl"
    if transcript.exists():
        raise FileExistsError(transcript)
    env = {**os.environ, **arm_env(arm_dir)}
    repo = arm_dir / "repo"
    command = [
        "claude",
        "-p",
        text,
        "--model",
        config.arm_model,
        "--plugin-dir",
        str(plugin_dir(arm_dir)),
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    with transcript.open("w") as out, (arm_dir / "claude.log").open("w") as err:
        result = subprocess.run(
            command,
            cwd=repo,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            check=False,
        )
        # Containers the agent started belong to this arm's compose project.
        subprocess.run(
            ["podman-compose", "down"], cwd=repo, env=env, stdout=err, stderr=err, check=False
        )
    return result.returncode


def run(
    config: Config,
    comparison_id: str,
    spec: str,
    rng: random.Random | None = None,
) -> list[str]:
    """Runs both arms and records the order, the spec and the skipped tasks in meta.json.

    Returns the order.
    """
    meta_path = config.comparisons / comparison_id / "meta.json"
    meta = json.loads(meta_path.read_text())
    skip_tasks = _triage_tasks(config, comparison_id, meta, spec)
    print(f"skipped tasks: {', '.join(skip_tasks) or 'none'}")
    order = list(ARMS)
    (rng or random.SystemRandom()).shuffle(order)
    meta.update(spec=spec, skip_tasks=skip_tasks, arm_model=config.arm_model, run_order=order)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    for arm in order:
        returncode = _run_arm(config, comparison_id, arm, prompt(spec, skip_tasks))
        print(f"arm {arm}: claude exited with {returncode}")
    return order
