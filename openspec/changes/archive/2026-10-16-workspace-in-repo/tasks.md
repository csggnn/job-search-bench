# Tasks

## 1. Folder locations

- [x] 1.1 In `bench/config.py`, add a function that returns the main checkout root of a folder: the parent of `git rev-parse --path-format=absolute --git-common-dir`, or the folder itself outside a git repository. Define `MAIN_ROOT` from `BENCH_ROOT` with it, and set `DATA_ROOT` to `MAIN_ROOT / "data"`. Add `tests/test_config.py` with a temporary git repository and a worktree of it: the function returns the main checkout root from both, and returns the folder itself outside git. Verify the new tests pass.
- [x] 1.2 In `load_config`, join the expanded `[workspace] root` to `MAIN_ROOT`. Extend `tests/test_config.py` with a relative, an absolute and a `~` root, loaded while the current directory is a temporary folder. Verify the tests pass.
- [x] 1.3 Set `[workspace] root = "runs"` in `bench.toml` and add `/runs/` to `.gitignore`. Verify `git check-ignore -q runs/x` exits 0.

## 2. Arm isolation

- [x] 2.1 In `_write_claude_config` in `bench/prepare.py`, add `claudeMdExcludes` with `CLAUDE.md`, `CLAUDE.local.md`, `.claude/CLAUDE.md` and `.claude/rules/**` of every folder from the arm folder up to and including `MAIN_ROOT`, as absolute paths. Extend `tests/test_prepare.py`: with a workspace under the main checkout root, the list holds the main checkout root paths, no path above it and no path inside the arm's `repo/`; with a workspace outside the main checkout root, the list is empty. Verify the tests pass.

## 3. Recorded workspace

- [x] 3.1 Add a helper that returns a comparison's workspace folder from `meta.json`. Use it in `run`, `_triage_tasks` and `_run_arm` in `bench/run.py`, and in `score`, `_score_arm`, `_judge_input` and `_judge` in `bench/score.py`. Add `workspace` to the `meta.json` fixture in `tests/test_run.py`, pointing at a folder other than `config.workspace`. Verify the test passes and the arms run under the recorded folder.

## 4. Documentation

- [x] 4.1 Update the README: list `runs/` next to `data/` in Layout, replace the paragraph that places the workspace outside the repository, and state that both folders sit at the main checkout root, that every worktree uses them, and that `git clean -x` in the main checkout removes them. Update the module docstrings of `bench/run.py` and `bench/prepare.py` that place the workspace outside the repository. Verify `grep -rn "outside the bench repo\|outside this repo\|bench-runs" README.md bench/` returns only the migration note.

## 5. Verification

- [x] 5.1 Run `uv run python -m unittest discover -s tests -t .` and `uv run ruff check . && uv run ruff format --check .`. Verify both pass.
- [x] 5.2 End-to-end probe. From a worktree, prepare a throwaway comparison and verify its arms land in the main checkout's `runs/` and its comparison folder in the main checkout's `data/comparisons/`. At the main checkout root, write a `CLAUDE.md` with a sentinel word, a skill `.claude/skills/bench-probe/`, a rule file `.claude/rules/bench-probe.md` with a second sentinel word, and a `SessionStart` hook in `.claude/settings.json` that writes a marker file outside the clone. In arm X, source `env.sh` and run `claude -p` asking for any sentinel word, with `--output-format stream-json --verbose`. Also ask for a rule that only the user's `~/.claude/CLAUDE.md` states. Verify the reply holds neither sentinel and states that rule, the `init` message lists no `bench-probe` skill and lists the clone's own skills, the hook marker file does not exist, and `git status` in the bench repository lists no workspace or data file. If the rule file's sentinel appears, add `.claude/rules/` files of the excluded folders to `claudeMdExcludes` in task 2.1 and repeat the probe. Delete the probe files and the throwaway comparison.
