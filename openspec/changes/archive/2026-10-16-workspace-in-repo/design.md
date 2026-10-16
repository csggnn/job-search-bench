# Design

## Context

- `load_config` in `bench/config.py` expands `[workspace] root` with `expanduser`. A relative root resolves against the current directory.
- `BENCH_ROOT` in `bench/config.py` is the folder of the running code. `uv run` in a git worktree uses that worktree's `.venv` and code, so `BENCH_ROOT` is the worktree root.
- `DATA_ROOT` in `bench/config.py` is `BENCH_ROOT / "data"`, gitignored. `config.comparisons` is `DATA_ROOT / "comparisons"`. `RESULTS_CSV` in `bench/score.py` is `DATA_ROOT / "results.csv"`. The README suggests making `data/` a separate git repository to keep a history of results.
- Worktrees made by `/start-task` live in `.trees/` inside the main checkout. The main checkout root is a parent folder of every worktree.
- `prepare` creates `<workspace>/<comparison>/` with `X/`, `Y/`, `mapping.json` and `judge-config/`. Each arm folder holds `repo/` (the target clone, its own git repository), `plugin/`, `claude-config/` and `env.sh`. `meta.json` records the comparison's workspace folder as an absolute path in `workspace`.
- `run.py` and `score.py` build arm paths from `config.workspace`.
- An arm runs `claude` with `cwd` at its clone and `CLAUDE_CONFIG_DIR` at its config dir. The judge and the task triage run in an empty temporary directory.
- The bench repository holds `.claude/skills/` with the OpenSpec skills. It holds no `CLAUDE.md`.
- Probe results with Claude Code, run while planning this change with a copy of an arm's config dir as `CLAUDE_CONFIG_DIR`. A session started in a folder that is its own git repository, below a folder with a `CLAUDE.md` and `.claude/skills/`:
  - loads the parent folder's `CLAUDE.md`;
  - does not load the parent folder's skills;
  - does not load the parent folder's `CLAUDE.md` when the config dir's `settings.json` lists that file's absolute path in `claudeMdExcludes`;
  - loads the config dir's `CLAUDE.md`, the user config snapshot, in both cases.
- Without a git repository between the folders, the parent folder's skills also load.
- No folder above `~/bench-runs` holds a `CLAUDE.md` or `CLAUDE.local.md`. The home folder holds `.claude/CLAUDE.md`, the user's global file. The user config snapshot copies the same file into every arm's config dir.

## Goals / Non-Goals

**Goals:**

- Arm inputs stay identical to those of existing comparisons, so their results remain comparable.
- Isolation from the bench repository holds for any content later added to it.
- Isolation is checked by an automated test and by one end-to-end probe.
- Unit tests stay offline and need no Claude Code login.

**Non-Goals:**

- Moving or rewriting existing comparisons under `~/bench-runs`.
- Protecting `runs/` or `data/` from `git clean -x`.
- Making `data/` a git repository.

## Decisions

### `runs/` and `data/` at the main checkout root

`bench/config.py` defines `MAIN_ROOT`: the parent of `git rev-parse --path-format=absolute --git-common-dir`, run in `BENCH_ROOT`. The common git dir is the main checkout's `.git` in the main checkout and in every worktree. When `BENCH_ROOT` is not in a git repository, `MAIN_ROOT` is `BENCH_ROOT`.

- `DATA_ROOT` becomes `MAIN_ROOT / "data"`. `config.comparisons` and `RESULTS_CSV` follow it unchanged.
- `bench.toml` sets `[workspace] root = "runs"`. `load_config` joins the expanded root to `MAIN_ROOT`. Joining an absolute path returns that path, so absolute and `~` roots keep their meaning.
- `.gitignore` lists `/runs/` next to `data/`.

`runs/` and `data/` are siblings. `data/` holds the results history, which the user may version. `runs/` holds clones, config dirs with credentials, transcripts and logs.

- Rejected: resolving against `BENCH_ROOT`. Each worktree would get its own `runs/` and `data/`, removing a worktree would delete its comparisons, and the main checkout's `CLAUDE.md` would sit above a worktree's `runs/` outside the exclusion list.
- Rejected: `data/runs/`. One folder holds everything, but a versioned `data/` then needs its own `.gitignore` to keep clones, credentials and transcripts out of its history.
- Rejected: `~/.local/share/job-search-bench`. It follows the XDG convention, but issue #6 asks for a folder inside the repository.
- Rejected: a hidden `.runs/`. The folder holds the arm clones a user opens with `env.sh`. A visible name keeps it in plain listings.

### Exclude the bench repository's instruction files in each arm's settings

`_write_claude_config` adds `claudeMdExcludes` to the arm's `settings.json`. The list holds `CLAUDE.md`, `CLAUDE.local.md`, `.claude/CLAUDE.md` and the glob `.claude/rules/**` of every folder from the arm folder up to and including `MAIN_ROOT`, as absolute paths. The arm's clone sits below the arm folder, so its own files stay out of the list. Folders outside the bench repository stay out of the list, so the user's instructions load as before. A workspace outside the bench repository gives an empty list. The arm settings are user-level settings, so the list applies to headless and interactive runs.

- Rejected: relying on the bench repository holding no `CLAUDE.md`. Adding one later would silently change every arm's context.
- Rejected: excluding every folder up to the filesystem root. It would also exclude files outside the bench repository, such as `~/.claude/CLAUDE.md`.
- Rejected: a glob such as `<main checkout root>/**/CLAUDE.md`. It also matches the clone's own `CLAUDE.md`, which the target repository's workflow depends on.

Skills and project settings need no exclusion. The clone is its own git repository, and this boundary stops skill discovery and project settings. The end-to-end probe confirmed it with a real arm: a skill and a `SessionStart` hook at the main checkout root did not reach the arm. The same probe showed that `.claude/rules/` files cross the git boundary like `CLAUDE.md`, and that the `.claude/rules/**` glob in `claudeMdExcludes` stops them.

### Run and score read the workspace from `meta.json`

A helper returns `Path(meta["workspace"])` for a comparison. `run`, `score`, `_triage_tasks`, `_judge` and `_judge_input` build arm paths from it. `prepare` keeps using `config.workspace` to create the folder and records it.

- Rejected: always using `config.workspace`. Comparisons under `~/bench-runs` would no longer resolve.

## Risks / Trade-offs

- [`git clean -fdx` in the main checkout deletes `runs/` and `data/`.] → The README states that both hold uncommitted data and that `git clean -x` removes them.
- [Code on a feature branch writes into the `runs/` and `data/` that the main checkout and other worktrees share. A branch with a changed `results.csv` layout appends rows to the shared table.] → Comparison IDs hold the date and the feature, and `prepare` refuses an existing comparison folder, so a collision fails before any write. `meta.json` records `bench_commit`, which identifies the code that wrote each comparison.
- [`MAIN_ROOT` runs `git` when `bench/config.py` is imported.] → One subprocess call per command. Tests that build `Config` directly do not depend on it.
- [Folders above the bench repository, such as `~/Projects`, become ancestors of the arm clones. A `CLAUDE.md` added there would reach the arms.] → None of them holds one. The exclusion list stays limited to the bench repository so that the user's own instruction files keep loading.
- [Editors index the arm clones inside the repository folder.] → Out of scope. Editor search usually skips gitignored folders.
- [A future Claude Code version adds another ancestor instruction file name or changes skill discovery.] → The end-to-end probe detects it. `claude_code_version` in `meta.json` dates each comparison.

## Migration Plan

1. Merge the change. New comparisons go to `runs/` and `data/` in the main checkout.
2. Existing comparisons stay under `~/bench-runs`. Their `meta.json` already records that path, so `run` and `score` find them.
3. A worktree's `data/` written before this change moves to the main checkout's `data/` by hand.
4. Rollback: set `[workspace] root = "~/bench-runs"`.
