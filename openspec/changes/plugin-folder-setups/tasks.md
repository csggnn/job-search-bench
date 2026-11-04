# Tasks

## 1. Setup arguments

- [x] 1.1 In `bench/prepare.py`, add a frozen `Setup(path, sha)` dataclass and rewrite `parse_setup` to parse `<path>@<sha>`: exactly one `@` with non-empty parts, no `:`, no absolute path, no `..` component, path normalized with `PurePosixPath`. Each refusal raises `ValueError` naming the argument and the form `<path>@<sha>`. Replace `test_parse_setup` in `tests/test_prepare.py` with cases for `plugins/a@abc`, `plugins/a/@abc`, `.@abc`, `plugins/a`, `@abc`, `plugins/a@`, `a@b@abc`, `plugins/a:b@abc`, `abc:label`, `/abs@abc` and `../x@abc`. Verify the tests pass.
- [x] 1.2 In `bench/cli.py`, set the `setups` metavar and help to `PATH@SHA`, map `ValueError` from `parse_setup` to `parser.error`, and remove the distinct-label check. Verify `uv run bench prepare bench/x plugins/a abc` exits with the `<path>@<sha>` message and creates no folder under `runs/` or `data/`.

## 2. Arm setup

- [x] 2.1 In `_clone_plugin` in `bench/prepare.py`, clone `[setup] repo` into `<arm>/setup`, keep the detached checkout and the prefix check, fail with a message naming the path and the SHA when `<arm>/setup/<path>` is not a directory, create `<arm>/plugin` as a relative symlink to it, print a warning to stderr naming the path and the full SHA when `<arm>/setup/<path>/.claude-plugin/plugin.json` is missing, and return the full SHA from `git rev-parse HEAD`. In `tests/test_prepare.py`, give the setup fixture repository a `plugins/a/` folder without a manifest and a `plugins/b/` folder with `.claude-plugin/plugin.json`. Assert that `<arm>/plugin` resolves to `<arm>/setup/plugins/a` for `plugins/a@<sha>` and to `<arm>/setup` for `.@<sha>`, and that stderr holds a warning naming `plugins/a` for `plugins/a@<sha>` and none for `plugins/b@<sha>`. Verify the tests pass.
- [x] 2.2 Rewrite `prepare` to take a list of two `Setup` values in arm order. Clone and check the setups of both arms before any target clone. On a failure, remove `<workspace>/<comparison>/` and re-raise. Tag a commit of the setup fixture repository. Add tests for a missing folder, a branch name, a tag name and an unknown SHA: each raises with the path or SHA in the message, and neither `<workspace>/<comparison>/` nor `<comparisons>/<comparison>/` exists afterwards. Add a test with the same setup in both arms. Verify the tests pass.
- [x] 2.3 Write `mapping.json` as arm to `{"path", "sha"}` and `meta.json` `setups` as a list of the same objects, both with full SHAs. Update the `mapping.json`, `meta.json` and `env.sh` assertions in `test_arms_are_isolated_and_pinned`, and keep the `--plugin-dir <arm>/plugin` assertion. Verify the tests pass.
- [x] 2.4 Update the `bench/prepare.py` module docstring to describe the setup clone and the plugin folder. In `bench/cli.py`, print each arm's path and full SHA after `prepare`. Verify `uv run python -m unittest tests.test_prepare` passes.

## 3. Scoring

- [x] 3.1 In `bench/score.py`, take `setup` and `setup_sha` of each arm from its `mapping.json` object in `_score_arm`, and print `arm X: <path>@<sha>` in `bench/cli.py`. Update `tests/test_score.py` fixtures and the `| setup |` summary assertion to paths. Verify `uv run python -m unittest tests.test_score tests.test_run` passes and `RESULTS_COLUMNS` is unchanged.

## 4. Documentation

- [x] 4.1 Update the README: the `prepare` steps and examples use `<path>@<sha>`, `.` is the repository root, no label, the `setup` column holds the path and `setup_sha` the full SHA, the isolation rule names the plugin folder and commit, and the arm folder holds `setup/` and `plugin/`. `prepare` warns when the folder holds no `.claude-plugin/plugin.json`. Remove the `origin/cc-hook` example. Verify `grep -n "LABEL\|<label>\|cc-hook" README.md bench/` returns nothing.

## 5. Verification

- [x] 5.1 Run `uv run python -m unittest discover -s tests -t .` and `uv run ruff check . && uv run ruff format --check .`. Verify both pass.
- [x] 5.2 End-to-end probe. Prepare a throwaway comparison with `plugins/sr-cc-review@<origin/main sha>` and `plugins/sr-v0@<origin/main sha>`. In arm X, source `env.sh` and run `claude -p` asking for the list of available skills, with `--output-format stream-json --verbose`. Verify the `init` message lists `sr-cc-review:design-review` and `sr-cc-review:cognitive-complexity`, and that the `SessionStart` hook of `sr-cc-review` runs and exits with 0. Verify `prepare` printed no manifest warning. If either fails through the symlink, apply the fallback in design.md, Risks, and repeat. Delete the throwaway comparison.
- [x] 5.3 Full run. In job-search-agent, tag the commit of `bench/csg-57-commute-city-level-fallback-r3` as `bench/csg-57-commute-city-level-fallback-r4` and push the tag. Run `bench prepare bench/csg-57-commute-city-level-fallback-r4 plugins/sr-v0@<origin/main sha> plugins/sr-cc-review@<origin/main sha>`, log in to both arms and the judge as printed, then run `bench run <comparison> --spec openspec/changes/csg-57-commute-city-level-fallback` and `bench score <comparison>`. Verify both arms exit with 0, `skills_used` of the `plugins/sr-cc-review` row lists at least one `sr-cc-review:` skill, and the two new `results.csv` rows hold `plugins/sr-v0` and `plugins/sr-cc-review` in `setup` with 40-character SHAs in `setup_sha`. Keep the comparison as a result.

## 6. Existing records

- [x] 6.1 Copy `data/` and both `runs/<comparison>/mapping.json` files to the scratchpad. With a script outside the repository, rewrite the two existing comparisons as in design.md, Migration Plan, step 2, using the full SHAs from `git -C ../simplicity-rules rev-parse fcbb2ac 49412cc`. Verify `results.csv` keeps four rows with `.` in `setup` and 40-character SHAs in `setup_sha`, and that both `meta.json` files and `mapping.json` files hold no label.
