"""Creates two isolated arms for one comparison from a frozen snapshot tag.

Each arm gets a fresh clone of the snapshot with no remote, the default branch at the
snapshot and a work branch checked out, and a Claude Code config dir. The config dir holds
the pinned arm settings and a snapshot of the user-level files listed in bench.toml,
identical for both arms.

A setup is a folder of the setup repository at a commit, `<path>@<sha>`. Each arm holds a
clone of the setup repository at the setup's commit in `setup/`, and `plugin`, a relative
symlink to the setup's folder in that clone. `plugin` is the arm's --plugin-dir.

Arm X gets the first setup and arm Y the second. The mapping from arm to setup path and
full SHA is written to the workspace.
"""

import hashlib
import json
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from importlib.metadata import version
from pathlib import Path, PurePosixPath

from bench.config import BENCH_ROOT, MAIN_ROOT, Config

ARMS = ("X", "Y")
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


@dataclass(frozen=True)
class Setup:
    """A folder of the setup repository at a commit. `.` is the repository root."""

    path: str
    sha: str


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


def run_dir(meta: dict) -> Path:
    """The comparison's folder in the workspace it was prepared in, as recorded in meta.json."""
    return Path(meta["workspace"])


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


def claude_md_excludes(arm_dir: Path, main_root: Path) -> list[str]:
    """Instruction files of the folders from arm_dir up to main_root, which arms do not load.

    Claude Code loads CLAUDE.md and .claude/rules/ files from every folder above the
    session's folder. The list keeps files of the bench repository out of the arm's
    context. Empty when arm_dir is outside main_root.
    """
    if not arm_dir.is_relative_to(main_root):
        return []
    folders = [arm_dir, *arm_dir.parents[: len(arm_dir.relative_to(main_root).parts)]]
    return [
        str(folder / name)
        for folder in folders
        for name in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md", ".claude/rules/**")
    ]


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
    settings["claudeMdExcludes"] = claude_md_excludes(arm_dir, MAIN_ROOT)
    (claude_config / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")


def _clone_plugin(config: Config, setup: Setup, arm_dir: Path) -> str:
    """Clones the setup repository at the setup's commit and links the arm's plugin folder.

    Returns the full SHA of the checked-out commit.
    """
    clone = arm_dir / "setup"
    _git("clone", "--no-local", config.setup_repo, str(clone))
    try:
        _git("checkout", "--detach", setup.sha, cwd=clone)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"setup {setup.path}@{setup.sha}: commit {setup.sha} not found in the setup repository"
        ) from error
    actual = _git("rev-parse", "HEAD", cwd=clone)
    if not actual.startswith(setup.sha):
        raise RuntimeError(
            f"setup {setup.path}@{setup.sha}: {setup.sha} is not a commit SHA, it resolves to"
            f" {actual}"
        )
    folder = clone / setup.path
    if not folder.is_dir():
        raise RuntimeError(f"setup {setup.path}@{setup.sha}: no folder {setup.path} at {actual}")
    plugin_dir(arm_dir).symlink_to(Path(clone.name) / setup.path)
    if not (folder / ".claude-plugin" / "plugin.json").is_file():
        print(
            f"warning: setup {setup.path}@{actual} holds no .claude-plugin/plugin.json",
            file=sys.stderr,
        )
    return actual


def _prepare_arm(config: Config, tag: str, user_config: UserConfig, arm_dir: Path) -> None:
    repo = arm_dir / "repo"
    _git("clone", "--no-local", "--branch", tag, config.target_repo, str(repo))
    _git("remote", "remove", "origin", cwd=repo)
    _git("branch", config.default_branch, "HEAD", cwd=repo)
    _git("switch", "-c", WORK_BRANCH_PREFIX + tag.removeprefix(TAG_PREFIX), cwd=repo)

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


def parse_setup(text: str) -> Setup:
    """Parses `<path>@<sha>`.

    The argument holds exactly one `@` and no `:`. The path is relative and has no `..`
    component. `plugins/a/` and `plugins/a` parse to the same path.
    """
    parts = text.split("@")
    if ":" in text or len(parts) != 2 or not all(parts):
        raise ValueError(f"setup must be <path>@<sha>: {text}")
    path = PurePosixPath(parts[0])
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"setup path must be inside the setup repository, <path>@<sha>: {text}")
    return Setup(path=str(path), sha=parts[1])


def prepare(
    config: Config,
    tag: str,
    setups: list[Setup],
    today: date | None = None,
) -> str:
    """Creates both arms and the comparison folder. Returns the comparison id.

    setups holds one setup per arm, in arm order. The setups of both arms resolve before any
    other arm content is created. When one does not resolve, the comparison's workspace
    folder is removed and the error is re-raised.
    """
    if len(setups) != len(ARMS):
        raise ValueError(f"expected {len(ARMS)} setups: {setups}")
    if not tag.startswith(TAG_PREFIX):
        raise ValueError(f"snapshot tag must start with {TAG_PREFIX!r}: {tag}")
    feature = tag.removeprefix(TAG_PREFIX)
    comparison_id = f"{(today or date.today()).isoformat()}-{feature}"
    comparison_run_dir = config.workspace / comparison_id
    comparison_dir = config.comparisons / comparison_id
    for path in (comparison_run_dir, comparison_dir):
        if path.exists():
            raise FileExistsError(path)

    user_config = _snapshot_user_config(config)

    comparison_run_dir.mkdir(parents=True)
    resolved = []
    try:
        for arm, setup in zip(ARMS, setups, strict=True):
            (comparison_run_dir / arm).mkdir()
            sha = _clone_plugin(config, setup, comparison_run_dir / arm)
            resolved.append({"path": setup.path, "sha": sha})
    except Exception:
        shutil.rmtree(comparison_run_dir)
        raise
    mapping = dict(zip(ARMS, resolved, strict=True))

    for arm in ARMS:
        _prepare_arm(config, tag, user_config, comparison_run_dir / arm)
    (comparison_run_dir / "mapping.json").write_text(json.dumps(mapping, indent=2) + "\n")
    # The judge's own config dir, so no user-level guidance or plugin reaches it.
    judge_config = comparison_run_dir / "judge-config"
    judge_config.mkdir()
    (judge_config / "settings.json").write_text(json.dumps({"autoMemoryEnabled": False}) + "\n")

    (comparison_dir / "metrics").mkdir(parents=True)
    (comparison_dir / "qa-log.md").write_text(QA_LOG_TEMPLATE.format(comparison_id=comparison_id))
    meta = {
        "comparison_id": comparison_id,
        "feature": feature,
        "snapshot_tag": tag,
        "setups": resolved,
        "setup_repo": config.setup_repo,
        "bench_commit": _git("rev-parse", "HEAD", cwd=BENCH_ROOT),
        "user_config_sha256": user_config.sha256,
        "claude_code_version": _claude_code_version(),
        "complexipy_version": version("complexipy"),
        "workspace": str(comparison_run_dir),
    }
    (comparison_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return comparison_id
