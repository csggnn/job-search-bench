import dataclasses
import json
import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from bench.config import Config
from bench.prepare import parse_setup, prepare

GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def commit(repo: Path, name: str, content: str) -> str:
    (repo / name).write_text(content)
    git("add", name, cwd=repo)
    git("commit", "-m", content, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo)


class PrepareTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict(os.environ, GIT_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

        setup = self.root / "setup"
        setup.mkdir()
        git("init", "-b", "main", cwd=setup)
        base = commit(setup, "rules.md", "base")
        git("checkout", "-b", "hook", cwd=setup)
        hook = commit(setup, "rules.md", "hook")
        self.setups = {"base": base, "hook": hook}
        git("checkout", "main", cwd=setup)

        target = self.root / "target"
        target.mkdir()
        git("init", "-b", "main", cwd=target)
        commit(target, "README.md", "product")
        git("tag", "bench/feat", cwd=target)

        self.user = self.root / "user-claude"
        (self.user / "hooks").mkdir(parents=True)
        (self.user / "CLAUDE.md").write_text("user rules")
        (self.user / "hooks" / "check.sh").write_text("#!/bin/sh\n")
        (self.user / "hooks" / "check.sh").chmod(0o755)
        (self.user / "history.jsonl").write_text("not copied")
        hook = {"type": "command", "command": f"bash {self.user}/hooks/check.sh"}
        user_settings = {"hooks": {"PreToolUse": [{"hooks": [hook]}]}, "model": "not copied"}
        (self.user / "settings.json").write_text(json.dumps(user_settings))

        self.config = Config(
            target_repo=str(target),
            default_branch="main",
            setup_repo=str(setup),
            user_config_source=self.user,
            user_config_paths=("CLAUDE.md", "hooks"),
            user_config_settings_keys=("hooks",),
            workspace=self.root / "runs",
            comparisons=self.root / "comparisons",
            arm_model="arm-model",
            judge_model="judge-model",
        )

    def test_arms_are_isolated_and_pinned(self) -> None:
        comparison_id = prepare(
            self.config,
            "bench/feat",
            self.setups,
            today=date(2026, 10, 13),
        )

        self.assertEqual(comparison_id, "2026-10-13-feat")
        run_dir = self.config.workspace / comparison_id
        mapping = json.loads((run_dir / "mapping.json").read_text())
        self.assertEqual(mapping, {"X": "base", "Y": "hook"})
        for arm, label in mapping.items():
            repo = run_dir / arm / "repo"
            self.assertEqual(git("remote", cwd=repo), "")
            self.assertEqual(
                git("rev-parse", "HEAD", cwd=run_dir / arm / "plugin"), self.setups[label]
            )
            self.assertEqual(git("branch", "--show-current", cwd=repo), "work/feat")
            self.assertEqual(
                git("rev-parse", "main", cwd=repo), git("rev-parse", "bench/feat", cwd=repo)
            )
            claude_config = run_dir / arm / "claude-config"
            self.assertEqual((claude_config / "CLAUDE.md").read_text(), "user rules")
            self.assertTrue(os.access(claude_config / "hooks" / "check.sh", os.X_OK))
            self.assertFalse((claude_config / "history.jsonl").exists())
            settings = json.loads((claude_config / "settings.json").read_text())
            self.assertFalse(settings["autoMemoryEnabled"])
            self.assertNotIn("model", settings)
            command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            self.assertEqual(command, f"bash {claude_config}/hooks/check.sh")
            env_sh = (run_dir / arm / "env.sh").read_text()
            self.assertIn(f"COMPOSE_PROJECT_NAME=bench-2026-10-13-feat-{arm.lower()}", env_sh)
            self.assertIn(f"--plugin-dir {run_dir / arm / 'plugin'}", env_sh)
        self.assertTrue((run_dir / "judge-config" / "settings.json").is_file())

        comparison_dir = self.config.comparisons / comparison_id
        self.assertTrue((comparison_dir / "qa-log.md").is_file())
        self.assertTrue((comparison_dir / "metrics").is_dir())
        meta = json.loads((comparison_dir / "meta.json").read_text())
        self.assertEqual(meta["setup_repo"], self.config.setup_repo)
        self.assertEqual(len(meta["user_config_sha256"]), 64)
        self.assertTrue(meta["complexipy_version"])
        self.assertEqual(meta["setups"], self.setups)

    def test_missing_user_config_path_fails(self) -> None:
        config = dataclasses.replace(self.config, user_config_paths=("absent",))
        with self.assertRaises(FileNotFoundError):
            prepare(config, "bench/feat", self.setups)

    def test_requires_two_setups(self) -> None:
        with self.assertRaises(ValueError):
            prepare(self.config, "bench/feat", {"base": self.setups["base"]})

    def test_parse_setup(self) -> None:
        self.assertEqual(parse_setup("715c15d:cc-hook"), ("cc-hook", "715c15d"))
        self.assertEqual(parse_setup("abc:candidate/x"), ("candidate/x", "abc"))
        for text in ("715c15d", "715c15d:", ":label"):
            with self.assertRaises(ValueError):
                parse_setup(text)

    def test_rejects_tag_without_prefix(self) -> None:
        with self.assertRaises(ValueError):
            prepare(self.config, "feat", self.setups)

    def test_refuses_existing_comparison(self) -> None:
        prepare(self.config, "bench/feat", self.setups, today=date(2026, 1, 1))
        with self.assertRaises(FileExistsError):
            prepare(self.config, "bench/feat", self.setups, today=date(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
