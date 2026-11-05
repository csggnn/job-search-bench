# job-search-bench

Benchmark for the AI-assisted code-generation rules, skills, hooks and agents defined in
[simplicity-rules](https://github.com/csggnn/simplicity-rules). It compares two versions of
that Claude Code setup by having each implement the same feature of
[job-search-agent](https://github.com/csggnn/job-search-agent) and scoring the resulting
code. Only the code-generation and simplification stage is measured.

Specification: [csggnn/job-search-agent#84](https://github.com/csggnn/job-search-agent/issues/84).

## How a comparison works

[GLOSSARY.md](GLOSSARY.md) defines the terms this README uses.

1. `prepare` creates two arms, X and Y. Each arm has a clone of job-search-agent at the
   snapshot tag, a clone of simplicity-rules at one setup's commit, and its own Claude
   config dir. The arm loads the setup's folder of that clone as its plugin. Both arms
   get the same settings and the same snapshot of the user's Claude config. Which setup
   is X and which is Y stays hidden until scoring.
2. `run` has each arm implement the feature headless, in random order. The judge model
   first lists the tasks a headless arm cannot perform, and both arms skip them. An arm
   may change the feature description where that simplifies the code and keeps the
   feature's purpose.
3. `score` measures each arm's diff, runs its unit tests, and has the judge model compare
   the two diffs without knowing which setup made which. It appends one row per arm to
   `data/results.csv` and writes a draft summary.

Arms are isolated from this repository. They load none of its instruction files, skills or
project settings.

## Layout

```
bench.toml                       # target repo, setup repo, user config snapshot, models
bench/                           # the `bench` command
  instruments/                   # arm settings and prompts shared by every comparison
data/                            # results, gitignored
  results.csv                    # one row per arm per comparison
  comparisons/<comparison>/      # metadata, Q&A log, task triage, metrics, judge
                                 # verdict, summary
runs/                            # workspace, gitignored
  <comparison>/                  # arms X and Y, judge config dir, X/Y mapping
    <arm>/
      repo/                      # clone of job-search-agent at the snapshot tag
      setup/                     # clone of simplicity-rules at the setup's commit
      plugin -> setup/<path>     # the setup's folder, loaded with --plugin-dir
      claude-config/             # the arm's Claude Code config dir
      env.sh                     # shell setup for an interactive session
```

`data/` and `runs/` are at the main checkout root. Every git worktree of this repository
uses them, so removing a worktree removes no comparison. `git clean -x` in the main
checkout deletes both folders.

## Usage

Requires [uv](https://docs.astral.sh/uv/), git, Claude Code, podman and podman-compose.
podman runs each arm's unit tests in the arm's own container.

```
uv sync
```

Run commands as `uv run bench <command>`, or activate `.venv` first.

### Prepare a comparison

1. Tag the job-search-agent commit that holds the feature description as
   `bench/<feature>` and push the tag. The description is a file or a directory, e.g. an
   OpenSpec change under `openspec/changes/`.
2. Run:
   ```
   bench prepare bench/<feature> <path>@<sha> <path>@<sha>
   ```
   Each argument is a setup: the folder `<path>` of the `[setup] repo` in `bench.toml` at
   the commit `<sha>`. `<path>` is relative to the repository root, and `.` is the root.
   `<sha>` is a pushed commit. A short SHA works. A branch name, a tag name or a
   local-only commit fails. A path with `@` or `:`, an absolute path and a path with a
   `..` component fail. Both arguments may name the same setup. Arm X gets the first
   setup and arm Y the second.

   `prepare` fails and leaves no comparison folder when a setup's folder does not exist
   at its commit. It prints a warning and continues when the folder holds no
   `.claude-plugin/plugin.json`. Example:
   ```
   sha=$(git -C ~/Projects/simplicity-rules rev-parse --short origin/main)
   bench prepare bench/<feature> plugins/sr-v0@$sha plugins/sr-cc-review@$sha
   ```
   `meta.json` records each setup's path and full SHA. In `results.csv`, `setup` holds the
   path and `setup_sha` the full SHA.
3. Log in once in each arm's config dir and in the judge's, as printed by `prepare`.

### Run the arms

```
bench run <comparison> --spec <path>
```

`<path>` is the feature description in the target repo. The prompt names no tool. The
target repo's instructions select the workflow, e.g. job-search-agent's `CLAUDE.md` selects
`/openspec-apply-change` for a path under `openspec/changes/`.

To run an arm interactively instead, `source runs/<comparison>/<arm>/env.sh && claude`. Do
not use `--continue` or `--resume`. An interactive run writes no transcript, so `score`
leaves `turns`, `cost_usd`, `model` and `skills_used` empty.

### Score

```
bench score <comparison>
```

Per arm, measured on the arm's diff against the snapshot tag:

| Metric | Source |
| -- | -- |
| `lines_changed`, `files_touched` | `git diff --numstat` |
| `cognitive_total`, `cognitive_worst` | complexipy on the changed Python files |
| `unit_tests_pass` | `tests/unit` in the arm's container |
| `turns`, `cost_usd`, `model`, `skills_used` | the arm's transcript |
| `nudges` | the arm's rows of `qa-log.md` |
| `judge_preferred` | the judge's verdict |

### Isolation rules

- Answer agent questions only from the frozen proposal, design and specs. The default
  answer is "not specified, use your judgment". Log every question and answer in
  `qa-log.md` and reuse answers word for word across arms.
- Run both arms before reading either output.
- The two setups differ only in the plugin folder and commit. A needed project change
  lands on the job-search-agent default branch before the snapshot tag.
- Comparisons are comparable only at the same `user_config_sha256` in `meta.json`.


## Development

Requires [uv](https://docs.astral.sh/uv/), which runs the bench, pre-commit and its hooks,
and [Node.js](https://nodejs.org/), which runs the pinned OpenSpec CLI. One-time setup:

```
uv sync
uvx pre-commit install
npm ci --ignore-scripts
```

Run all local checks:

```
uvx pre-commit run --all-files
uv run python -m unittest discover -s tests -t .
npx openspec validate --all --no-interactive
```

CI (`.github/workflows/ci.yml`) runs these checks on pushes to `main` and on pull requests.
The `check` job is required before merge. The hooks check whitespace, YAML, TOML and JSON,
lint and format Python with Ruff (`[tool.ruff]` in `pyproject.toml`), scan for secrets with
gitleaks and audit workflows with zizmor. CI also checks that the files under `.claude/` match
the output of `openspec update` at the version pinned in `package.json`.

- Dependabot updates GitHub Actions, pre-commit hooks, Python and npm packages weekly, after
  a 7-day cooldown. On an OpenSpec bump, `.github/workflows/openspec-regenerate.yml` commits
  the regenerated files, approves the CI runs of that commit and enables auto-merge.
- CodeRabbit reviews pull requests (`.coderabbit.yaml`).
- The `.claude/skills/openspec-*` files are generated by `openspec update`.

## License

MIT
