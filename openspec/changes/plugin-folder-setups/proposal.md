# Proposal

## Why

simplicity-rules keeps each plugin in its own folder on `main`, e.g. `plugins/sr-v0` and `plugins/sr-cc-review`. Its repository root is no longer a plugin. `bench prepare` selects a setup by commit only, and each arm loads the root of the setup repository at that commit. The bench cannot load or compare the plugins of the current setup repository.

A setup also takes a label typed by the operator. The label is the only name of a setup in the results. Keeping one setup under one label across comparisons depends on the operator.

## What Changes

- **BREAKING** Each arm's setup is a folder of the `[setup] repo` at a commit: `<path>@<sha>`. `.` selects the repository root, so a repository whose root is the plugin can be selected.
- **BREAKING** A setup has no label. The results name a setup by its folder.
- The setup argument specifies the commit by its SHA. A branch or tag name in its place fails, and so does an argument without a commit. A folder containing `@` or `:` fails. These forms stay free for later syntax, without changing the meaning of a valid argument.
- `bench prepare` fails before creating any arm when the folder does not exist at the commit, or when the path is absolute or leaves the repository.
- Both arms may name the same folder at the same commit.
- `meta.json` and `results.csv` record each arm's folder and full commit SHA.
- The bench assumes nothing about the layout of the setup repository beyond the folder given.
- `bench prepare` warns when the folder holds no Claude Code plugin manifest, and continues.
- The README describes the new argument form.

## Capabilities

### New Capabilities

- `arm-setups`: how each arm's plugin is selected, validated, loaded and recorded.

### Modified Capabilities

None.

## Impact

- `bench prepare` arguments, `bench/prepare.py`, `bench/cli.py`, `bench/score.py` and their tests.
- `meta.json`, `mapping.json` and `results.csv` contents.
- README.
- `bench.toml` is unchanged.
- GitHub issue #2 narrows to a repository per arm and an arm with no plugin. The plugin folder stays on the command line next to the commit.
