"""Creates two isolated arms for one comparison from a frozen snapshot tag.

Each arm gets a fresh clone of the snapshot with no remote, the default branch at the
snapshot and a work branch checked out, a clone of the setup plugin at the arm's SHA, and a
Claude Code config dir. The config dir holds the pinned arm settings and a snapshot of the
user-level files listed in bench.toml, identical for both arms.
Arms are labelled X and Y; the champion/candidate mapping is written to the
workspace and stays out of the comparison folder until scoring.
"""

import hashlib
import json
import random
import shutil
import stat
import subprocess
from dataclasses import dataclass
from datetime import date
from importlib.metadata import version
from pathlib import Path

from bench.config import BENCH_ROOT, Config

ARMS = ("X", "Y")
ROLES = ("champion", "candidate")
TAG_PREFIX = "bench/"
WORK_BRANCH_PREFIX = "work/"
# Auto memory off, permissions for headless runs. Pinned here, identical for both arms.
ARM_SETTINGS = BENCH_ROOT / "bench" / "instruments" / "arm-settings.json"


@dataclass(frozen=True)
class UserConfig:
    """User-level files and settings copied into every arm's config dir."""

    files: dict[str, tuple[bytes, int]]  # path relative to the source -> (content, mode)
    settings: dict
    sha256: str


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


def arm_env(arm_dir: Path) -> dict[str, str]:
    """Environment variables of one arm. arm_dir is <workspace>/<comparison>/<arm>."""
    compose_project = f"bench-{arm_dir.parent.name}-{arm_dir.name}".lower()
    return {
        "CLAUDE_CONFIG_DIR": str(arm_dir / "claude-config"),
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
        "COMPOSE_PROJECT_NAME": compose_project,
    }


def plugin_dir(arm_dir: Path) -> Path:
    """The setup plugin of one arm, loaded with --plugin-dir."""
    return arm_dir / "plugin"


def _snapshot_user_config(config: Config) -> UserConfig:
    source = config.user_config_source
    files: dict[str, tuple[bytes, int]] = {}
    for name in config.user_config_paths:
        path = source / name
        if not path.exists():
            raise FileNotFoundError(path)
        members = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
        for member in members:
            mode = stat.S_IMODE(member.stat().st_mode)
            files[str(member.relative_to(source))] = (member.read_bytes(), mode)

    settings_file = source / "settings.json"
    all_settings = json.loads(settings_file.read_text()) if settings_file.exists() else {}
    keys = config.user_config_settings_keys
    settings = {key: all_settings[key] for key in keys if key in all_settings}

    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode() + b"\0" + files[name][0] + b"\0")
    digest.update(json.dumps(settings, sort_keys=True).encode())
    return UserConfig(files=files, settings=settings, sha256=digest.hexdigest())


def _relocate(settings: dict, source: Path, target: Path) -> dict:
    """Points paths under the user config source, such as hook commands, at target."""
    prefixes = [f"{source}/"]
    if source.is_relative_to(Path.home()):
        relative = source.relative_to(Path.home())
        prefixes += [f"~/{relative}/", f"$HOME/{relative}/"]
    text = json.dumps(settings)
    for prefix in prefixes:
        text = text.replace(prefix, f"{target}/")
    return json.loads(text)


def _write_claude_config(config: Config, user_config: UserConfig, arm_dir: Path) -> None:
    claude_config = arm_dir / "claude-config"
    claude_config.mkdir()
    for name, (content, mode) in user_config.files.items():
        path = claude_config / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(mode)

    settings = json.loads(ARM_SETTINGS.read_text())
    relocated = _relocate(user_config.settings, config.user_config_source, claude_config)
    for key, value in relocated.items():
        settings.setdefault(key, value)
    (claude_config / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")


def _clone_plugin(config: Config, setup_sha: str, arm_dir: Path) -> None:
    plugin = plugin_dir(arm_dir)
    _git("clone", "--no-local", config.setup_repo, str(plugin))
    _git("checkout", "--detach", setup_sha, cwd=plugin)
    actual = _git("rev-parse", "HEAD", cwd=plugin)
    if not actual.startswith(setup_sha) and not setup_sha.startswith(actual):
        raise RuntimeError(f"{plugin} is at {actual}, expected {setup_sha}")


def _prepare_arm(
    config: Config, tag: str, setup_sha: str, user_config: UserConfig, arm_dir: Path
) -> None:
    repo = arm_dir / "repo"
    _git("clone", "--no-local", "--branch", tag, config.target_repo, str(repo))
    _git("remote", "remove", "origin", cwd=repo)
    _git("branch", config.default_branch, "HEAD", cwd=repo)
    _git("switch", "-c", WORK_BRANCH_PREFIX + tag.removeprefix(TAG_PREFIX), cwd=repo)

    _clone_plugin(config, setup_sha, arm_dir)
    _write_claude_config(config, user_config, arm_dir)
    exports = "".join(f"export {name}={value}\n" for name, value in arm_env(arm_dir).items())
    # bash expands aliases when it reads a line. A function applies to the `claude` in
    # `source env.sh && claude`. An existing `claude` alias would take precedence over the
    # function, so it is removed first.
    wrapper = (
        "unalias claude 2>/dev/null || true\n"
        f'function claude {{ command claude --plugin-dir {plugin_dir(arm_dir)} "$@"; }}\n'
    )
    (arm_dir / "env.sh").write_text(f"{exports}{wrapper}cd {repo}\n")


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
    user_config = _snapshot_user_config(config)

    run_dir.mkdir(parents=True)
    for arm, role in mapping.items():
        _prepare_arm(config, tag, setup_shas[role], user_config, run_dir / arm)
    (run_dir / "mapping.json").write_text(json.dumps(mapping, indent=2) + "\n")
    # The judge's own config dir, so no user-level guidance or plugin reaches it.
    judge_config = run_dir / "judge-config"
    judge_config.mkdir()
    (judge_config / "settings.json").write_text(json.dumps({"autoMemoryEnabled": False}) + "\n")

    (comparison_dir / "metrics").mkdir(parents=True)
    (comparison_dir / "qa-log.md").write_text(QA_LOG_TEMPLATE.format(comparison_id=comparison_id))
    meta = {
        "comparison_id": comparison_id,
        "feature": feature,
        "snapshot_tag": tag,
        "champion_sha": champion_sha,
        "candidate_sha": candidate_sha,
        "setup_repo": config.setup_repo,
        "user_config_sha256": user_config.sha256,
        "claude_code_version": _claude_code_version(),
        "complexipy_version": version("complexipy"),
        "workspace": str(run_dir),
    }
    (comparison_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return comparison_id
