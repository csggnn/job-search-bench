import json
import os
import random
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from bench.config import Config
from bench.prepare import prepare

# Local submodule URLs need the file protocol, which git blocks by default.
GIT_ENV = {
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "protocol.file.allow",
    "GIT_CONFIG_VALUE_0": "always",
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
        self.champion = commit(setup, "CLAUDE.generic.md", "champion")
        git("checkout", "-b", "candidate", cwd=setup)
        self.candidate = commit(setup, "CLAUDE.generic.md", "candidate")
        git("checkout", "main", cwd=setup)

        target = self.root / "target"
        target.mkdir()
        git("init", "-b", "main", cwd=target)
        commit(target, "README.md", "product")
        git("submodule", "add", str(setup), ".setup", cwd=target)
        git("commit", "-m", "add setup", cwd=target)
        git("tag", "bench/feat", cwd=target)

        self.config = Config(
            target_repo=str(target),
            setup_path=".setup",
            default_branch="main",
            workspace=self.root / "runs",
            comparisons=self.root / "comparisons",
            arm_model="arm-model",
            judge_model="judge-model",
        )

    def test_arms_are_isolated_and_pinned(self) -> None:
        comparison_id = prepare(
            self.config,
            "bench/feat",
            self.champion,
            self.candidate,
            today=date(2026, 10, 13),
            rng=random.Random(0),
        )

        self.assertEqual(comparison_id, "2026-10-13-feat")
        run_dir = self.config.workspace / comparison_id
        mapping = json.loads((run_dir / "mapping.json").read_text())
        self.assertEqual(sorted(mapping.values()), ["candidate", "champion"])
        expected = {"champion": self.champion, "candidate": self.candidate}
        for arm, role in mapping.items():
            repo = run_dir / arm / "repo"
            self.assertEqual(git("remote", cwd=repo), "")
            self.assertEqual(git("rev-parse", "HEAD", cwd=repo / ".setup"), expected[role])
            self.assertEqual(git("branch", "--show-current", cwd=repo), "work/feat")
            self.assertEqual(
                git("rev-parse", "main", cwd=repo), git("rev-parse", "bench/feat", cwd=repo)
            )
            settings = json.loads((run_dir / arm / "claude-config" / "settings.json").read_text())
            self.assertFalse(settings["autoMemoryEnabled"])
            env_sh = (run_dir / arm / "env.sh").read_text()
            self.assertIn(f"COMPOSE_PROJECT_NAME=bench-2026-10-13-feat-{arm.lower()}", env_sh)
        self.assertTrue((run_dir / "judge-config" / "settings.json").is_file())

        comparison_dir = self.config.comparisons / comparison_id
        self.assertTrue((comparison_dir / "qa-log.md").is_file())
        self.assertTrue((comparison_dir / "metrics").is_dir())

    def test_rejects_tag_without_prefix(self) -> None:
        with self.assertRaises(ValueError):
            prepare(self.config, "feat", self.champion, self.candidate)

    def test_refuses_existing_comparison(self) -> None:
        prepare(self.config, "bench/feat", self.champion, self.candidate, today=date(2026, 1, 1))
        with self.assertRaises(FileExistsError):
            prepare(
                self.config, "bench/feat", self.champion, self.candidate, today=date(2026, 1, 1)
            )


if __name__ == "__main__":
    unittest.main()
