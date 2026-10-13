"""Creates two isolated arms for one comparison from a frozen snapshot tag.

Each arm gets a fresh clone of the snapshot with no remote, the setup submodule
checked out at its SHA, and an empty Claude Code config dir with auto memory off.
Arms are labelled X and Y; the champion/candidate mapping is written to the
workspace and stays out of the comparison folder until scoring.
"""

import json
import random
import shutil
import subprocess
from datetime import date
from pathlib import Path

from bench.config import Config

ARMS = ("X", "Y")
ROLES = ("champion", "candidate")
TAG_PREFIX = "bench/"

QA_LOG_TEMPLATE = """# Q&A log: {comparison_id}

Answers come only from the frozen proposal, design and specs.
Default answer: "not specified, use your judgment".

| Arm | Agent question | Answer |
| -- | -- | -- |
"""


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _claude_code_version() -> str | None:
    if shutil.which("claude") is None:
        return None
    result = subprocess.run(["claude", "--version"], check=False, capture_output=True, text=True)
    return result.stdout.split()[0] if result.returncode == 0 else None


def _prepare_arm(config: Config, tag: str, setup_sha: str, arm_dir: Path) -> None:
    repo = arm_dir / "repo"
    claude_config = arm_dir / "claude-config"
    setup = repo / config.setup_path

    _git("clone", "--no-local", "--branch", tag, config.target_repo, str(repo))
    _git("submodule", "update", "--init", config.setup_path, cwd=repo)
    _git("checkout", "--detach", setup_sha, cwd=setup)
    actual = _git("rev-parse", "HEAD", cwd=setup)
    if not actual.startswith(setup_sha) and not setup_sha.startswith(actual):
        raise RuntimeError(f"{setup} is at {actual}, expected {setup_sha}")
    _git("remote", "remove", "origin", cwd=repo)

    claude_config.mkdir()
    (claude_config / "settings.json").write_text(
        json.dumps({"autoMemoryEnabled": False}, indent=2) + "\n"
    )
    (arm_dir / "env.sh").write_text(
        f"export CLAUDE_CONFIG_DIR={claude_config}\n"
        "export CLAUDE_CODE_DISABLE_AUTO_MEMORY=1\n"
        f"cd {repo}\n"
    )


def prepare(
    config: Config,
    tag: str,
    champion_sha: str,
    candidate_sha: str,
    today: date | None = None,
    rng: random.Random | None = None,
) -> str:
    """Creates both arms and the comparison folder. Returns the comparison id."""
    if not tag.startswith(TAG_PREFIX):
        raise ValueError(f"snapshot tag must start with {TAG_PREFIX!r}: {tag}")
    feature = tag.removeprefix(TAG_PREFIX)
    comparison_id = f"{(today or date.today()).isoformat()}-{feature}"
    run_dir = config.workspace / comparison_id
    comparison_dir = config.comparisons / comparison_id
    for path in (run_dir, comparison_dir):
        if path.exists():
            raise FileExistsError(path)

    roles = list(ROLES)
    (rng or random.SystemRandom()).shuffle(roles)
    mapping = dict(zip(ARMS, roles, strict=True))
    setup_shas = {"champion": champion_sha, "candidate": candidate_sha}

    run_dir.mkdir(parents=True)
    for arm, role in mapping.items():
        _prepare_arm(config, tag, setup_shas[role], run_dir / arm)
    (run_dir / "mapping.json").write_text(json.dumps(mapping, indent=2) + "\n")

    (comparison_dir / "metrics").mkdir(parents=True)
    (comparison_dir / "qa-log.md").write_text(QA_LOG_TEMPLATE.format(comparison_id=comparison_id))
    meta = {
        "comparison_id": comparison_id,
        "feature": feature,
        "snapshot_tag": tag,
        "champion_sha": champion_sha,
        "candidate_sha": candidate_sha,
        "claude_code_version": _claude_code_version(),
        "workspace": str(run_dir),
    }
    (comparison_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return comparison_id
