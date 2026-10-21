# Design

## Context

Before this change, the root folder of the setup repository was assumed to be a Claude Code plugin. A version of this plugin, at the arm's commit, was loaded in each arm. `prepare` wrote the arm-to-setup mapping, and only `score` read it. The flow before this change:

```
bench prepare <tag> <sha>:<label> <sha>:<label>
  |
  +--> runs/<comparison>/X/plugin/              clone of [setup] repo at the first <sha>
  +--> runs/<comparison>/X/env.sh               claude --plugin-dir X/plugin
  +--> runs/<comparison>/Y/plugin/              clone of [setup] repo at the second <sha>
  +--> runs/<comparison>/Y/env.sh               claude --plugin-dir Y/plugin
  +--> runs/<comparison>/mapping.json           X -> label, Y -> label
  +--> data/comparisons/<comparison>/meta.json  setups: label -> <sha> as typed

bench run    claude --plugin-dir X/plugin       (plugin_dir(arm), no mapping read)
             claude --plugin-dir Y/plugin

bench score  reads mapping.json and meta["setups"]
  +--> meta.json                                mapping copied in
  +--> data/results.csv                         setup = label, setup_sha = <sha> as typed
```

## Goals / Non-Goals

**Goals:**

- A later release can accept `<path>` without `@<sha>`, or a branch name after `@`, and every argument valid in this change keeps its meaning.
- `bench run` keeps needing no arm-to-setup mapping.
- Unit tests stay offline and need no Claude Code login.

**Non-Goals:**

- A readable plugin name derived from the plugin's manifest or folder name.
- Validating that the folder holds a loadable plugin.
- Setups from more than one repository, and an arm with no plugin.

## Decisions

### Argument parsing in `parse_setup`

**Before this change:** `bench/cli.py` took two `SHA:LABEL` arguments. `parse_setup` in `bench/prepare.py` split each into `(label, sha)`.

**Decision:** `parse_setup` returns a `Setup(path, sha)`. It splits the argument on `@` and requires exactly two non-empty parts. It refuses `:` anywhere in the argument, an absolute path and a `..` component. The path is normalized with `PurePosixPath`, so `plugins/a/` and `plugins/a` are the same setup and `.` stays `.`. Parsing runs in `bench/cli.py` before `prepare`, so a malformed argument creates no folder.

Refusing `:` and a second `@` keeps both characters free for later forms, such as a repository prefix for issue #2.

- Rejected: `<sha>:<label>:<path>`. The form `<sha>:<label>` used before this change would keep parsing, but with a new meaning once the label is gone.
- Rejected: a default path of `.` when `@` is missing. Two spellings of the root setup, and the missing-commit form would then be taken.

### Setup clone at `<arm>/setup`, plugin folder at `<arm>/plugin`

**Before this change:** `env.sh` and `bench run` passed `<arm>/plugin` as `--plugin-dir`, and `bench run` read no mapping (see Context).

**Decision:** `_clone_plugin` clones `[setup] repo` into `<arm>/setup` and checks out the SHA. It then checks that `<arm>/setup/<path>` is a directory and creates `<arm>/plugin` as a relative symlink to it. For `.` the symlink points at the clone. `plugin_dir` keeps returning `<arm>/plugin`, so `env.sh` and `_run_arm` keep their command lines.

```
runs/<comparison>/
  X/
    setup/                  clone of [setup] repo at the first <sha>
      plugins/sr-v0/
      plugins/sr-cc-review/
    plugin -> setup/<path>  symlink, passed as --plugin-dir
    repo/
    claude-config/
    env.sh
  Y/                        same layout, second <path>@<sha>
```

- Rejected: `_run_arm` reading the path from `mapping.json`. `bench run` would read the mapping before scoring.
- Rejected: a per-arm file holding the path, read by `_run_arm` and written into `env.sh`. Two places build the plugin path instead of one.
- Rejected: copying only the folder into `<arm>/plugin`. The copy holds no git repository, so the SHA check has nothing to read, and a plugin that refers to files of its repository outside its folder would lose them.

### Warning for a folder without a manifest

**Decision:** After the directory check, `_clone_plugin` tests for `<arm>/setup/<path>/.claude-plugin/plugin.json`. When it is missing, `prepare` prints a warning to stderr with the path and the full SHA, and continues. The warning is not recorded in `meta.json`. `skills_used` in `results.csv` shows after a run whether the plugin acted.

- Rejected: refusing a folder without a manifest. Claude Code loads a plugin folder without one.
- Rejected: requiring a manifest or a component folder such as `skills/` or `hooks/`. The list of component folders is Claude Code's and changes with it.
- Rejected: `claude plugin validate`. It passes a folder with a `marketplace.json`, such as the simplicity-rules root, and unit tests would need the `claude` binary.
- Rejected: a confirmation prompt. `prepare` would block in scripts and tests.

### Setups resolve before any other arm content

**Before this change:** `prepare` created the arms before the results folder. A failure in an arm left `<workspace>/<comparison>/` behind, and a second `prepare` of the same comparison then failed with `FileExistsError`.

**Decision:** `prepare` clones and checks the setups of both arms first. If either fails, it removes `<workspace>/<comparison>/` and re-raises with the path and the SHA in the message. The target clones, config dirs and the results folder are created after both setups resolve.

- Rejected: checking the folder with `git ls-remote` or the GitHub API before cloning. `ls-remote` lists refs, not trees, and an API ties the bench to one host.

### Full SHA from the clone

**Before this change:** `_clone_plugin` checked out the given SHA detached and refused a checkout whose `HEAD` did not start with it. A branch or tag name checked out and then failed this test.

**Decision:** After the checkout, `git rev-parse HEAD` in `<arm>/setup` gives the full SHA. `prepare` records it. The prefix check stays.

### Recorded setups

**Before this change:** only `score` read the mapping (see Context), and the `bench/score.py` docstring stated it.

**Decision:** `mapping.json` maps each arm to `{"path": ..., "sha": ...}` with the full SHA. `meta.json` holds `setups` as a list of the same objects in argument order, with no label. `score` takes `setup` and `setup_sha` of each arm from `mapping.json` and copies the mapping into `meta.json`. `results.csv` keeps its columns.

```
bench prepare  --> mapping.json   X: {path, sha}, Y: {path, sha}
               --> meta.json      setups: [{path, sha}, {path, sha}]
bench run          (reads no mapping)
bench score    <-- mapping.json
               --> meta.json      mapping copied in
               --> results.csv    setup = path, setup_sha = full sha
```

`meta.json` holds the same information as before this change: the setups in argument order, and arm X is the first. The mapping stays the only file that pairs arms with setups explicitly, which keeps blind arm assignment (issue #9) a change to `prepare` alone.

- Rejected: a new `setup_path` column. `setup` is the name of the setup in the results, and the path is that name. A new column would misalign the existing `results.csv`.

### `cli.py` output

**Decision:** `bench score` prints `arm X: <path>@<sha>` per arm. `bench prepare` prints each arm's path and full SHA next to its `env.sh` line.

## Risks / Trade-offs

- [Claude Code resolves a `--plugin-dir` symlink differently from a folder, e.g. in `${CLAUDE_PLUGIN_ROOT}` or skill discovery.] → The end-to-end probe loads a folder plugin with a skill and a hook through the symlink. If it fails, `_clone_plugin` writes the resolved absolute path into `env.sh` and the arm folder holds it in `plugin-path`, read by `_run_arm`.
- [The results show a path, e.g. `plugins/sr-cc-review`. Before this change, they showed a short label.] → Accepted. A plugin name is a non-goal of this change.
- [A folder rename in the setup repository gives the same plugin two `setup` values across comparisons.] → Accepted. Grouping across renames is an analysis step.
- [Removing `<workspace>/<comparison>/` on a failed setup deletes a folder `prepare` just created.] → `prepare` already refuses an existing comparison folder before creating it, so the removed folder holds only this run's clones.

## Migration Plan

Before this change, `results.csv` held four rows of two comparisons. Their `meta.json` and `mapping.json` files used labels and abbreviated SHAs (`fcbb2ac`, `49412cc`).

1. Merge the change.
2. Rewrite the local records of the two existing comparisons once, with a script kept out of the repository:
   - `results.csv`: `setup` becomes `.`, `setup_sha` becomes the full SHA of `fcbb2ac` or `49412cc`.
   - `meta.json`: `setups` becomes a list of `{"path": ".", "sha": <full>}` in arm order, `mapping` maps each arm to its object.
   - `runs/<comparison>/mapping.json`: same form as `mapping` in `meta.json`.
   - `summary.md` keeps its text.
3. The existing arm folders keep `<arm>/plugin` as a clone. They are not run again.
4. Rollback: revert the merge and restore `data/` and the two `mapping.json` files from a copy taken before step 2.
