"""Runs code generation headless in each arm of a prepared comparison.

Each arm runs `claude -p` with the same prompt, in its own clone and config dir, with its
own version of the setup plugin. The arms run one after the other, in random order. The
stream-json transcript and stderr go to the arm's workspace dir, outside the bench repo.
"""

import json
import os
import random
import subprocess

from bench.config import Config
from bench.prepare import ARMS, arm_env, plugin_dir

PROMPT = (
    "/openspec-apply-change {change}\n\n"
    "Complete every task of the change{skip}. Then commit all changes on the current branch."
)
# Tasks that need resources an arm lacks, such as personal data or paid API calls.
SKIP = ", except tasks {tasks}: leave them undone and unchecked"


def prompt(change: str, skip_tasks: list[str]) -> str:
    """The prompt of both arms."""
    skip = SKIP.format(tasks=", ".join(skip_tasks)) if skip_tasks else ""
    return PROMPT.format(change=change, skip=skip)


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
    change: str,
    skip_tasks: list[str] | None = None,
    rng: random.Random | None = None,
) -> list[str]:
    """Runs both arms and records the order, the change and the skipped tasks in meta.json.

    Returns the order.
    """
    skip_tasks = skip_tasks or []
    meta_path = config.comparisons / comparison_id / "meta.json"
    meta = json.loads(meta_path.read_text())
    order = list(ARMS)
    (rng or random.SystemRandom()).shuffle(order)
    meta.update(change=change, skip_tasks=skip_tasks, arm_model=config.arm_model, run_order=order)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    for arm in order:
        returncode = _run_arm(config, comparison_id, arm, prompt(change, skip_tasks))
        print(f"arm {arm}: claude exited with {returncode}")
    return order
