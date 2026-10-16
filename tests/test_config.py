import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from bench.config import DATA_ROOT, MAIN_ROOT, RUNS_ROOT, load_config, main_checkout_root

GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}

BENCH_TOML = """
[target]
repo = "unused"
default_branch = "main"
[setup]
repo = "unused"
[user_config]
source = "~/.claude"
paths = []
settings_keys = []
[models]
arm = "arm-model"
judge = "judge-model"
"""


def git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, env={**os.environ, **GIT_ENV}
    )


class MainCheckoutRootTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()

    def test_same_root_from_main_checkout_and_worktree(self) -> None:
        main = self.root / "main"
        main.mkdir()
        git("init", "-q", cwd=main)
        git("commit", "-q", "--allow-empty", "-m", "init", cwd=main)
        git("worktree", "add", "-q", ".trees/feat", cwd=main)

        self.assertEqual(main_checkout_root(main), main)
        self.assertEqual(main_checkout_root(main / ".trees" / "feat"), main)

    def test_folder_outside_git(self) -> None:
        self.assertEqual(main_checkout_root(self.root), self.root)


class LoadConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        cwd = Path.cwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.root)

    def test_workspace_and_results_at_the_main_checkout(self) -> None:
        path = self.root / "bench.toml"
        path.write_text(BENCH_TOML)
        config = load_config(path)
        self.assertEqual(config.workspace, RUNS_ROOT)
        self.assertEqual(config.comparisons, DATA_ROOT / "comparisons")
        self.assertEqual(RUNS_ROOT.parent, MAIN_ROOT)
        self.assertEqual(DATA_ROOT.parent, MAIN_ROOT)
