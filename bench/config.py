"""Loads bench.toml."""

import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path


def main_checkout_root(folder: Path) -> Path:
    """Root of the main checkout of the git repository holding folder, also from a worktree.

    Returns folder when it is not in a git repository.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=folder,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return folder
    return Path(result.stdout.strip()).parent


BENCH_ROOT = Path(__file__).resolve().parent.parent
# The main checkout and every worktree share the workspace and the results.
MAIN_ROOT = main_checkout_root(BENCH_ROOT)
# Results of the operator's runs. Gitignored, so the repository holds no results.
DATA_ROOT = MAIN_ROOT / "data"


@dataclass(frozen=True)
class Config:
    target_repo: str
    default_branch: str
    setup_repo: str
    user_config_source: Path
    user_config_paths: tuple[str, ...]
    user_config_settings_keys: tuple[str, ...]
    workspace: Path
    comparisons: Path
    arm_model: str
    judge_model: str


def load_config(path: Path = BENCH_ROOT / "bench.toml") -> Config:
    data = tomllib.loads(path.read_text())
    return Config(
        target_repo=data["target"]["repo"],
        default_branch=data["target"]["default_branch"],
        setup_repo=data["setup"]["repo"],
        user_config_source=Path(data["user_config"]["source"]).expanduser(),
        user_config_paths=tuple(data["user_config"]["paths"]),
        user_config_settings_keys=tuple(data["user_config"]["settings_keys"]),
        workspace=MAIN_ROOT / Path(data["workspace"]["root"]).expanduser(),
        comparisons=DATA_ROOT / "comparisons",
        arm_model=data["models"]["arm"],
        judge_model=data["models"]["judge"],
    )
