import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bench.config import Config
from bench.run import run


class RunTest(unittest.TestCase):
    def test_runs_each_arm_in_its_own_env_and_records_the_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = Config(
                target_repo="unused",
                default_branch="main",
                setup_repo="unused",
                user_config_source=root / "user-claude",
                user_config_paths=(),
                user_config_settings_keys=(),
                workspace=root / "runs",
                comparisons=root / "comparisons",
                arm_model="arm-model",
                judge_model="judge-model",
            )
            for arm in ("X", "Y"):
                (config.workspace / "c1" / arm / "repo").mkdir(parents=True)
            (config.comparisons / "c1").mkdir(parents=True)
            (config.comparisons / "c1" / "meta.json").write_text("{}")

            with mock.patch("bench.run.subprocess.run") as subprocess_run:
                subprocess_run.return_value.returncode = 0
                order = run(config, "c1", "add-feat", ["5.2", "5.3"], rng=random.Random(0))

            meta = json.loads((config.comparisons / "c1" / "meta.json").read_text())
            self.assertEqual(meta["run_order"], order)
            self.assertEqual(meta["change"], "add-feat")
            self.assertEqual(meta["skip_tasks"], ["5.2", "5.3"])
            claude_calls = [c for c in subprocess_run.call_args_list if c.args[0][0] == "claude"]
            self.assertEqual(len(claude_calls), 2)
            for call, arm in zip(claude_calls, order, strict=True):
                self.assertIn("/openspec-apply-change add-feat", call.args[0][2])
                self.assertIn("except tasks 5.2, 5.3: leave them undone", call.args[0][2])
                self.assertEqual(call.kwargs["cwd"], config.workspace / "c1" / arm / "repo")
                plugin = str(config.workspace / "c1" / arm / "plugin")
                args = call.args[0]
                self.assertEqual(args[args.index("--plugin-dir") + 1], plugin)
                self.assertEqual(
                    call.kwargs["env"]["CLAUDE_CONFIG_DIR"],
                    str(config.workspace / "c1" / arm / "claude-config"),
                )


if __name__ == "__main__":
    unittest.main()
