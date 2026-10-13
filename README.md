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
| Setup repo | Generic layer: skills, `CLAUDE.generic.md`, `ruff-base.toml`, complexipy config, minimum tool versions. `main` is the champion. Candidates are short-lived branches. |
| job-search-agent | The product and the project layer. Consumes the setup as submodule `.setup/` pinned to a SHA. |
| job-search-bench (this repo) | `prepare` and `score` commands, pinned review-triage agent, judge prompt, `results.csv`, one folder per comparison, report generator. |

## Layout

```
bench.toml                       # target repo, setup submodule path, workspace root
bench/                           # the `bench` command
results.csv                      # one row per arm per comparison
comparisons/<date>-<feature>/
  meta.json                      # snapshot tag, champion and candidate SHAs, Claude Code version
  qa-log.md                      # nudges: questions and answers
  summary.md                     # generated draft + notes and decision
  metrics/                       # per-arm scores and raw tool output
report/                          # generated charts and setup changelog
```

The workspace (`~/bench-runs` by default) is outside this repo. It holds, per comparison,
the arm clones, the per-arm Claude config dirs and `mapping.json` (X/Y to
champion/candidate). `mapping.json` stays unread until scoring.

Raw session transcripts and logs are gitignored. Only counts and scrubbed summaries are
committed.

## Usage

Requires Python 3.11+ and git.

```
pip install -e .
```

### Prepare a comparison

1. Tag the design-PR merge commit in job-search-agent as `bench/<feature>` and push the tag.
2. Run:
   ```
   bench prepare bench/<feature> <champion-sha> <candidate-sha>
   ```
   For each arm X and Y, with the labels assigned at random, this:
   - clones the snapshot tag with `git clone --no-local` and removes the remote,
   - checks out the setup submodule at the arm's SHA,
   - creates an empty Claude config dir with auto memory disabled,
   - writes `env.sh`, which sets `CLAUDE_CONFIG_DIR` and enters the clone.

   It also creates `comparisons/<date>-<feature>/` with `meta.json` and an empty
   `qa-log.md`.
3. In each arm: `source <workspace>/<comparison>/<arm>/env.sh && claude`. Each config dir
   starts empty and requires its own login. Do not use `--continue` or `--resume`.

### Isolation rules

- Answer agent questions only from the frozen proposal, design and specs. The default
  answer is "not specified, use your judgment". Log every question and answer in
  `qa-log.md` and reuse answers word for word across arms.
- Run both arms before reading either output. Alternate arm order across features.
- Candidates change only the generic layer. A needed project change lands on
  job-search-agent `main` before the snapshot tag.

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

Implemented: `bench prepare`.

Not implemented: `bench score`, the review-triage agent, the judge prompt and the report
generator.

## Development

```
python3 -m unittest discover -s tests -t .
scripts/ruff.sh check . && scripts/ruff.sh format --check .
```
