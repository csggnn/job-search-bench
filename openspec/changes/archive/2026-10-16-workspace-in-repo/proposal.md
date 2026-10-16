# Proposal

## Why

`bench prepare` writes each comparison's arm clones, plugin clones, Claude config dirs, transcripts and logs to `~/bench-runs`, outside this repository. Project data then spreads into the home folder, apart from the repository that produces and reads it. GitHub issue #6.

Results live in a gitignored `data/` folder of the checkout that runs `bench`. A git worktree of this repository has its own `data/`. Removing the worktree deletes the comparisons and results prepared in it.

## What Changes

- The default workspace is a folder inside this repository. Git ignores it.
- The main checkout and every git worktree of this repository use the same workspace folder and the same results folder, whatever directory `bench` runs from. Removing a worktree removes no comparison data and no results.
- The workspace and the results are separate folders. The results folder can become its own git repository without holding arm clones, transcripts or logs.
- This repository's instruction files and skills do not reach an arm session. An arm session loads the same instructions as before: the target clone's, the plugin's and the user's `~/.claude` snapshot.
- A comparison prepared before this change stays runnable and scorable at the workspace location it was prepared with.
- The README describes both folders.

## Capabilities

### New Capabilities

- `local-data`: where the bench stores the files it creates per comparison and the results table, and how arms stay isolated from the folders around them.

### Modified Capabilities

None.

## Impact

- `bench.toml`, `.gitignore`, README.
- `bench prepare`, `bench run` and `bench score`.
- Existing comparisons under `~/bench-runs` stay in place.
