# job-search-bench

Evaluation of the Claude Code dev setup used on
[job-search-agent](https://github.com/csggnn/job-search-agent). Each setup change runs as a
candidate against the current champion on a real feature. Both arms start from the merged
design PR, and one of the two implementations ships. Only the code-generation and
simplification stage is measured.

Specification: Linear CSG-76 (GitHub issue
[csggnn/job-search-agent#84](https://github.com/csggnn/job-search-agent/issues/84)).

## Repositories

| Repo | Holds |
| -- | -- |
| [simplicity-rules](https://github.com/csggnn/simplicity-rules) | The setup under evaluation: a Claude Code plugin with skills, hooks and agents. `main` is the champion. Candidates are short-lived branches. |
| job-search-agent | The product and the project layer. It has no dependency on the setup. |
| job-search-bench (this repo) | `prepare` and `score` commands, pinned review-triage agent, judge prompt, `results.csv`, one folder per comparison, report generator. |

## Layout

```
bench.toml                       # target repo, setup repo, user config snapshot, workspace, models
bench/                           # the `bench` command
  instruments/                   # fixed inputs of every comparison, never part of a candidate
    arm-settings.json            # Claude settings of every arm
    judge.md                     # judge prompt
pyproject.toml, uv.lock          # pinned dependencies: complexipy measures the arms, ruff lints
                                 # this repo
results.csv                      # one row per arm per comparison
comparisons/<date>-<feature>/
  meta.json                      # snapshot tag, SHAs, Claude Code and complexipy versions
  qa-log.md                      # nudges: questions and answers
  summary.md                     # generated draft + notes and decision
  metrics/                       # per-arm scores and raw tool output
report/                          # generated charts and setup changelog
```

The workspace (`~/bench-runs` by default) is outside this repo. It holds, per comparison,
the arm clones, the per-arm plugin clones and Claude config dirs, and `mapping.json` (X/Y to
champion/candidate). `mapping.json` stays unread until scoring.

Raw session transcripts and logs are gitignored. Only counts and scrubbed summaries are
committed.

## Usage

Requires [uv](https://docs.astral.sh/uv/), git, Claude Code, rootless podman and
podman-compose. podman runs each arm's unit tests in the arm's own container.

```
uv sync
```

Run commands as `uv run bench <command>`, or activate `.venv` first.

### Prepare a comparison

1. Tag the design-PR merge commit in job-search-agent as `bench/<feature>` and push the tag.
2. Run:
   ```
   bench prepare bench/<feature> <champion-sha> <candidate-sha>
   ```
   For each arm X and Y, with the labels assigned at random, this:
   - clones the snapshot tag with `git clone --no-local` and removes the remote,
   - creates the default branch at the tag and checks out the work branch
     `work/<feature>`,
   - clones the setup plugin into `plugin/` and checks out the arm's SHA,
   - creates a Claude config dir with the user config snapshot and
     `bench/instruments/arm-settings.json`: auto memory off, edits accepted, and a fixed
     allowlist of commands,
   - writes `env.sh`, which sets `CLAUDE_CONFIG_DIR` and a per-arm
     `COMPOSE_PROJECT_NAME`, aliases `claude` to load the arm's plugin, and enters the
     clone.

   The user config snapshot is taken once and copied into both arms. It holds the paths in
   `[user_config]` of `bench.toml`, relative to `~/.claude`, and the listed keys of
   `~/.claude/settings.json`. Paths in those settings that point into `~/.claude`, such as
   hook commands, point into the arm's config dir. Auto memory, session history,
   credentials and installed plugins are not copied. `meta.json` records the snapshot's
   SHA-256 as `user_config_sha256`.

   It also creates the judge's config dir, and `comparisons/<date>-<feature>/` with
   `meta.json` and an empty `qa-log.md`.
3. Log in once in each arm's config dir and in the judge's, as printed by `prepare`. Each
   config dir starts empty.

### Run the arms

Headless:

```
bench run <comparison> --change <openspec-change>
```

Each arm runs `claude -p "/openspec-apply-change <change> ..." --plugin-dir <arm>/plugin`
on the model in `bench.toml`, in random order. The prompt asks the agent to commit its work. The
transcript and stderr go to the arm's workspace dir. Containers the agent started are
stopped after each arm.

Interactive: in each arm, `source <workspace>/<comparison>/<arm>/env.sh && claude`. Do
not use `--continue` or `--resume`.

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
| `nudges` | rows of `qa-log.md` for the arm |

The judge runs `bench/instruments/judge.md` on the judge model with the OpenSpec change and both diffs,
labelled X and Y, in an empty directory with its own config dir.

`score` writes `metrics/<arm>.json`, `metrics/complexipy-<arm>.txt`,
`metrics/unit-tests-<arm>.txt` and `metrics/judge.md`, appends one `results.csv` row per
arm, adds the X/Y mapping to `meta.json` and writes a draft `summary.md`.

### Isolation rules

- Answer agent questions only from the frozen proposal, design and specs. The default
  answer is "not specified, use your judgment". Log every question and answer in
  `qa-log.md` and reuse answers word for word across arms.
- Run both arms before reading either output. Alternate arm order across features.
- Candidates change only the setup plugin. A needed project change lands on
  job-search-agent `main` before the snapshot tag.
- Comparisons are comparable only at the same `user_config_sha256`.

## Decision rule

Adopt the candidate when the manual test passes, CodeRabbit findings are not worse, and
review effort or complexity is better. Differences smaller than the v0-vs-v0 baseline are
inconclusive, and the champion stays.

## results.csv columns

`comparison_id, date, feature, snapshot_tag, arm, role, setup_sha, model,
claude_code_version, lines_changed, files_touched, cognitive_total, cognitive_worst,
sonar_cognitive, triage_flagged_lines, coderabbit_actionable, nudges, turns, cost_usd,
manual_test_pass, judge_preferred, shipped, decision`

`role` is filled after scoring. `decision` is set on the candidate row.

## Status

Implemented: `bench prepare`, `bench run`, `bench score` with local metrics and the judge.

Not implemented: the review-triage agent, CodeRabbit and Sonar metrics, PR comments and the report
generator.

## Development

```
uv run python -m unittest discover -s tests -t .
uv run ruff check . && uv run ruff format --check .
```

CI runs the same checks on every pull request and on pushes to `main`.
