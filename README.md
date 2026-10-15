# job-search-bench

Benchmark for the AI-assisted code-generation rules, skills, hooks and agents defined in
[simplicity-rules](https://github.com/csggnn/simplicity-rules). It compares two versions of
that Claude Code setup by having each implement the same feature of
[job-search-agent](https://github.com/csggnn/job-search-agent) and scoring the resulting
code.

Each version is a simplicity-rules commit with a label that names it, e.g. `main` or
`cc-hook`. Both arms start from the same job-search-agent commit, which holds the spec documents
of a real feature.
Only the code-generation and simplification stage is measured.

Specification: [csggnn/job-search-agent#84](https://github.com/csggnn/job-search-agent/issues/84).

## Layout

```
bench.toml                       # target repo, setup repo, user config snapshot, workspace, models
bench/                           # the `bench` command
  instruments/                   # fixed inputs of every comparison, never part of a setup
    arm-settings.json            # Claude settings of every arm
    judge.md                     # judge prompt
    task-triage.md               # prompt that finds tasks a headless arm cannot perform
pyproject.toml, uv.lock          # pinned dependencies: complexipy measures the arms, ruff lints
                                 # this repo
results.csv                      # one row per arm per comparison
comparisons/<date>-<feature>/
  meta.json                      # snapshot tag, SHAs, Claude Code and complexipy versions
  qa-log.md                      # nudges: questions and answers
  task-triage.md                 # tasks the arms skip, with reasons
  summary.md                     # generated draft + notes and decision
  metrics/                       # per-arm scores and raw tool output
```

The workspace (`~/bench-runs` by default) is outside this repo. It holds, per comparison,
the arm clones, the per-arm plugin clones and Claude config dirs, and `mapping.json` (X/Y to
setup label).

Session transcripts and logs are written to the workspace. `.gitignore` also excludes them
from this repo.

## Usage

Requires [uv](https://docs.astral.sh/uv/), git, Claude Code, podman and
podman-compose. podman runs each arm's unit tests in the arm's own container.

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
   bench prepare bench/<feature> <sha>:<label> <sha>:<label>
   ```
   The two labels differ. Arm X gets the first setup and arm Y the second. `meta.json`
   records them as `setups` (label to SHA). For each arm, this:
   - clones the snapshot tag with `git clone --no-local` and removes the remote,
   - creates the default branch at the tag and checks out the work branch
     `work/<feature>`,
   - clones the setup plugin into `plugin/` and checks out the arm's SHA,
   - creates a Claude config dir with the user config snapshot and
     `bench/instruments/arm-settings.json`: auto memory off, edits accepted, and a fixed
     allowlist of commands,
   - writes `env.sh`, which sets `CLAUDE_CONFIG_DIR` and a per-arm
     `COMPOSE_PROJECT_NAME`, defines a `claude` shell function that loads the arm's plugin,
     and enters the clone.

   The user config snapshot is taken once and copied into both arms. It holds the paths in
   `[user_config]` of `bench.toml`, relative to `source`, and the listed keys of
   `<source>/settings.json`. Paths in those settings that point into `source`, such as
   hook commands, point into the arm's config dir. `meta.json` records the snapshot's
   SHA-256 as `user_config_sha256`.

   It also creates the judge's config dir, and `comparisons/<date>-<feature>/` with
   `meta.json` and an empty `qa-log.md`.
3. Log in once in each arm's config dir and in the judge's, as printed by `prepare`. No
   config dir holds credentials.

### Run the arms

Headless:

```
bench run <comparison> --spec <path>
```

Each arm runs `claude -p "Implement the feature described in <path> ..." --plugin-dir
<arm>/plugin` on the model in `bench.toml`, in random order. The prompt names no tool. The
target repo's instructions and skills select the workflow, e.g. job-search-agent's
`CLAUDE.md` selects `/openspec-apply-change` for a path under `openspec/changes/`. The
prompt asks the agent to commit its work. The
transcript and stderr go to the arm's workspace dir. Containers the agent started are
stopped after each arm.

Before the arms run, the judge model reads the feature description with
`bench/instruments/task-triage.md` and names the tasks a headless arm cannot perform:
tasks that need personal data, paid API calls, human input or manual inspection. The prompt
tells both arms to leave those tasks undone and unchecked. `meta.json` records them as
`skip_tasks`, and `task-triage.md` in the comparison folder holds the reasoning.

Interactive: in each arm, `source <workspace>/<comparison>/<arm>/env.sh && claude`. Do
not use `--continue` or `--resume`. An interactive run writes no `transcript.jsonl`, so
`score` leaves `turns`, `cost_usd`, `model` and `skills_used` empty.

### Score

```
bench score <comparison>
```

Per arm, measured on the arm's `HEAD` against the snapshot tag:

| Metric | Source |
| -- | -- |
| `lines_changed`, `files_touched` | `git diff --numstat` |
| `cognitive_total`, `cognitive_worst` | complexipy, from the bench's locked environment, on the changed Python files, every function in them |
| `unit_tests_pass` | `tests/unit` in the arm's `job-search` container |
| `turns`, `cost_usd`, `model` | the transcript's `result` and `init` messages |
| `skills_used` | the transcript's Skill tool calls, in order of first use |
| `nudges` | rows of `qa-log.md` for the arm |

The judge runs `bench/instruments/judge.md` on the judge model with the feature description
and both diffs, labelled X and Y, in an empty directory with its own config dir.

`score` writes `metrics/<arm>.json`, `metrics/complexipy-<arm>.txt`,
`metrics/unit-tests-<arm>.txt` and `metrics/judge.md`, appends one `results.csv` row per
arm, adds the X/Y mapping to `meta.json` and writes a draft `summary.md`.

### Isolation rules

- Answer agent questions only from the frozen proposal, design and specs. The default
  answer is "not specified, use your judgment". Log every question and answer in
  `qa-log.md` and reuse answers word for word across arms.
- Run both arms before reading either output.
- The two setups differ only in the plugin commit. A needed project change lands on
  the job-search-agent default branch before the snapshot tag.
- Comparisons are comparable only at the same `user_config_sha256`.

## results.csv columns

`comparison_id, date, feature, snapshot_tag, arm, setup, setup_sha, model,
claude_code_version, lines_changed, files_touched, cognitive_total, cognitive_worst,
sonar_cognitive, triage_flagged_lines, coderabbit_actionable, nudges, skills_used, turns,
cost_usd, manual_test_pass, judge_preferred, shipped`

`setup` is the label given to `prepare`.

## Status

Implemented: `bench prepare`, `bench run`, `bench score` with local metrics and the judge.

Not implemented: the review-triage agent, CodeRabbit and Sonar metrics, and the report
generator.

## Development

```
uv run python -m unittest discover -s tests -t .
uv run ruff check . && uv run ruff format --check .
```

CI runs the same checks on every pull request and on pushes to `main`.
