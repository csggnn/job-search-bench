"""Loads bench.toml."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    target_repo: str
    setup_path: str
    default_branch: str
    workspace: Path
    comparisons: Path
    arm_model: str
    judge_model: str


def load_config(path: Path = BENCH_ROOT / "bench.toml") -> Config:
    data = tomllib.loads(path.read_text())
    return Config(
        target_repo=data["target"]["repo"],
        setup_path=data["target"]["setup_path"],
        default_branch=data["target"]["default_branch"],
        workspace=Path(data["workspace"]["root"]).expanduser(),
        comparisons=BENCH_ROOT / "comparisons",
        arm_model=data["models"]["arm"],
        judge_model=data["models"]["judge"],
    )
