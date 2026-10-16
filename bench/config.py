"""Loads bench.toml."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parent.parent
# Results of the operator's runs. Gitignored, so the repository holds no results.
DATA_ROOT = BENCH_ROOT / "data"


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
        workspace=Path(data["workspace"]["root"]).expanduser(),
        comparisons=DATA_ROOT / "comparisons",
        arm_model=data["models"]["arm"],
        judge_model=data["models"]["judge"],
    )
