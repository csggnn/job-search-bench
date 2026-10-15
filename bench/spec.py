"""The feature description of a comparison: a file or directory in the target repo."""

import subprocess
from pathlib import Path


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


def spec_text(repo: Path, tag: str, path: str) -> str:
    """Every file under path at tag, each under a `## <file>` heading."""
    files = _git(repo, "ls-tree", "-r", "--name-only", tag, "--", path).split()
    if not files:
        raise FileNotFoundError(f"{path} at {tag}")
    return "\n\n".join(f"## {name}\n\n{_git(repo, 'show', f'{tag}:{name}')}" for name in files)
