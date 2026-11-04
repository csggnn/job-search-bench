import contextlib
import dataclasses
import io
import json
import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from bench.config import Config
from bench.prepare import Setup, claude_md_excludes, parse_setup, prepare

GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def commit(repo: Path, files: dict[str, str], message: str) -> str:
    for name, content in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(content)
        git("add", name, cwd=repo)
    git("commit", "-m", message, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo)


class PrepareTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict(os.environ, GIT_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

        # plugins/a holds no manifest, plugins/b holds one.
        setup = self.root / "setup"
        setup.mkdir()
        git("init", "-b", "main", cwd=setup)
        self.base = commit(
            setup,
            {"plugins/a/rules.md": "base", "plugins/b/.claude-plugin/plugin.json": "{}"},
            "base",
        )
        git("tag", "v1", cwd=setup)
        git("checkout", "-b", "hook", cwd=setup)
        self.hook = commit(setup, {"plugins/a/rules.md": "hook"}, "hook")
        git("checkout", "main", cwd=setup)
        self.setups = [Setup("plugins/a", self.base[:7]), Setup("plugins/b", self.hook)]

        target = self.root / "target"
        target.mkdir()
        git("init", "-b", "main", cwd=target)
        commit(target, {"README.md": "product"}, "product")
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

    def prepare_quietly(self, setups: list[Setup]) -> tuple[str, str]:
        """Runs prepare on 2026-10-13. Returns the comparison id and the captured stderr."""
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            comparison_id = prepare(self.config, "bench/feat", setups, today=date(2026, 10, 13))
        return comparison_id, stderr.getvalue()

    def test_arms_are_isolated_and_pinned(self) -> None:
        comparison_id, _ = self.prepare_quietly(self.setups)

        self.assertEqual(comparison_id, "2026-10-13-feat")
        run_dir = self.config.workspace / comparison_id
        expected = {
            "X": {"path": "plugins/a", "sha": self.base},
            "Y": {"path": "plugins/b", "sha": self.hook},
        }
        mapping = json.loads((run_dir / "mapping.json").read_text())
        self.assertEqual(mapping, expected)
        for arm, setup in mapping.items():
            repo = run_dir / arm / "repo"
            self.assertEqual(git("remote", cwd=repo), "")
            self.assertEqual(git("rev-parse", "HEAD", cwd=run_dir / arm / "setup"), setup["sha"])
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
            # The test workspace is outside the bench repository.
            self.assertEqual(settings["claudeMdExcludes"], [])
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
        self.assertEqual(len(meta["bench_commit"]), 40)
        self.assertTrue(meta["complexipy_version"])
        self.assertEqual(meta["setups"], [expected["X"], expected["Y"]])

    def test_plugin_links_to_the_setup_folder(self) -> None:
        comparison_id, stderr = self.prepare_quietly(self.setups)

        run_dir = self.config.workspace / comparison_id
        for arm, path in (("X", "plugins/a"), ("Y", "plugins/b")):
            plugin = run_dir / arm / "plugin"
            self.assertFalse(os.path.isabs(os.readlink(plugin)))
            self.assertEqual(plugin.resolve(), (run_dir / arm / "setup" / path).resolve())
        self.assertIn(f"plugins/a@{self.base}", stderr)
        self.assertNotIn("plugins/b", stderr)

    def test_repository_root(self) -> None:
        comparison_id, _ = self.prepare_quietly([Setup(".", self.base), Setup(".", self.hook)])

        run_dir = self.config.workspace / comparison_id
        for arm in ("X", "Y"):
            plugin = run_dir / arm / "plugin"
            self.assertEqual(plugin.resolve(), (run_dir / arm / "setup").resolve())

    def test_same_setup_in_both_arms(self) -> None:
        setup = Setup("plugins/b", self.base)
        comparison_id, stderr = self.prepare_quietly([setup, setup])

        run_dir = self.config.workspace / comparison_id
        mapping = json.loads((run_dir / "mapping.json").read_text())
        self.assertEqual(mapping["X"], mapping["Y"])
        self.assertEqual(stderr, "")

    def test_unresolved_setup_leaves_no_folder(self) -> None:
        cases = (
            (Setup("plugins/missing", self.base[:7]), ("plugins/missing", self.base[:7])),
            (Setup("plugins/a", "main"), ("main",)),
            (Setup("plugins/a", "v1"), ("v1",)),
            (Setup("plugins/a", "deadbeef"), ("deadbeef",)),
        )
        for setup, names in cases:
            with self.subTest(setup=setup):
                # Arm X resolves, so its clone exists when arm Y fails.
                with self.assertRaises(RuntimeError) as raised:
                    self.prepare_quietly([self.setups[0], setup])
                for name in names:
                    self.assertIn(name, str(raised.exception))
                self.assertFalse((self.config.workspace / "2026-10-13-feat").exists())
                self.assertFalse((self.config.comparisons / "2026-10-13-feat").exists())

    def test_missing_user_config_path_fails(self) -> None:
        config = dataclasses.replace(self.config, user_config_paths=("absent",))
        with self.assertRaises(FileNotFoundError):
            prepare(config, "bench/feat", self.setups)

    def test_requires_two_setups(self) -> None:
        with self.assertRaises(ValueError):
            prepare(self.config, "bench/feat", self.setups[:1])

    def test_parse_setup(self) -> None:
        self.assertEqual(parse_setup("plugins/a@abc"), Setup(path="plugins/a", sha="abc"))
        self.assertEqual(parse_setup("plugins/a/@abc"), Setup(path="plugins/a", sha="abc"))
        self.assertEqual(parse_setup(".@abc"), Setup(path=".", sha="abc"))

    def test_parse_setup_refuses(self) -> None:
        for text in (
            "plugins/a",
            "@abc",
            "plugins/a@",
            "a@b@abc",
            "plugins/a:b@abc",
            "abc:label",
            "/abs@abc",
            "../x@abc",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError) as raised:
                parse_setup(text)
            self.assertIn(text, str(raised.exception))
            self.assertIn("<path>@<sha>", str(raised.exception))

    def test_rejects_tag_without_prefix(self) -> None:
        with self.assertRaises(ValueError):
            prepare(self.config, "feat", self.setups)

    def test_refuses_existing_comparison(self) -> None:
        self.prepare_quietly(self.setups)
        with self.assertRaises(FileExistsError):
            self.prepare_quietly(self.setups)


if __name__ == "__main__":
    unittest.main()


class ClaudeMdExcludesTest(unittest.TestCase):
    def test_folders_from_the_arm_up_to_the_main_checkout(self) -> None:
        main = Path("/home/u/bench")
        excludes = claude_md_excludes(main / "runs" / "c1" / "X", main)

        self.assertIn("/home/u/bench/CLAUDE.md", excludes)
        self.assertIn("/home/u/bench/.claude/CLAUDE.md", excludes)
        self.assertIn("/home/u/bench/runs/c1/X/CLAUDE.local.md", excludes)
        self.assertIn("/home/u/bench/.claude/rules/**", excludes)
        self.assertEqual(len(excludes), 4 * 4)
        self.assertFalse(any(path.startswith("/home/u/bench/runs/c1/X/repo/") for path in excludes))
        self.assertFalse(any(not path.startswith("/home/u/bench/") for path in excludes))

    def test_arm_outside_the_main_checkout(self) -> None:
        self.assertEqual(
            claude_md_excludes(Path("/home/u/bench-runs/c1/X"), Path("/home/u/bench")), []
        )
