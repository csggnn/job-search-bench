# local-data Specification

## Purpose

Defines where the bench stores the uncommitted files of each comparison and the results table, and how arm sessions stay isolated from the folders that contain them.

## Requirements

### Requirement: Workspace inside the repository

The workspace SHALL be a fixed folder inside the bench repository. Git SHALL ignore that folder and every file below it.

#### Scenario: Prepare a comparison

- **WHEN** `bench prepare` runs
- **THEN** the comparison's arm folders, `mapping.json` and judge config dir are created inside the bench repository
- **AND** `git status` in the bench repository lists none of them

#### Scenario: Run and score a comparison

- **WHEN** `bench run` and `bench score` complete on a comparison in the workspace
- **THEN** `git status` in the bench repository lists no transcript, log or arm file

### Requirement: One workspace and one results folder per repository

The workspace and the results folder, holding `results.csv` and the comparison folders, SHALL be fixed folders under the root of the bench repository's main checkout. Both SHALL be the same for the main checkout, for every git worktree of the bench repository, and for any current directory.

#### Scenario: Command run from a subfolder

- **WHEN** `bench prepare` runs from a subfolder of the main checkout
- **THEN** the comparison's arms and its comparison folder are created under the main checkout root, not under the subfolder

#### Scenario: Command run from a worktree

- **WHEN** `bench prepare`, `bench run` and `bench score` run in a git worktree of the bench repository
- **THEN** the arms, the comparison folder and the `results.csv` rows are written under the main checkout root, not under the worktree

#### Scenario: Worktree removed

- **WHEN** a comparison was prepared and scored from a worktree and the worktree is removed
- **THEN** the comparison's arm folders, transcripts, logs, comparison folder and `results.csv` rows still exist

### Requirement: Workspace and results in separate folders

The workspace and the results folder SHALL be sibling folders. Neither SHALL contain the other.

#### Scenario: Results folder as its own repository

- **WHEN** the user makes the results folder a git repository
- **THEN** `git status` in that repository lists no arm clone, transcript or log

### Requirement: Arm sessions ignore the bench repository

An arm session SHALL NOT load `CLAUDE.md`, `CLAUDE.local.md`, `.claude/CLAUDE.md` or `.claude/rules/` files from the main checkout root of the bench repository or from any folder between that root and the arm's clone. An arm session SHALL NOT load skills or settings of the bench repository. Every other instruction source SHALL load as before, including the arm's clone, the plugin and the user config snapshot.

#### Scenario: Bench repository holds a CLAUDE.md

- **WHEN** the main checkout root holds a `CLAUDE.md` and an arm session starts in its clone
- **THEN** the session context holds no content of that file

#### Scenario: Bench repository holds a rules file

- **WHEN** the main checkout root holds a file in `.claude/rules/` and an arm session starts in its clone
- **THEN** the session context holds no content of that file

#### Scenario: Bench repository holds a SessionStart hook

- **WHEN** the main checkout's `.claude/settings.json` defines a `SessionStart` hook and an arm session starts in its clone
- **THEN** the hook does not run

#### Scenario: Comparison prepared from a worktree

- **WHEN** a comparison is prepared from a worktree, the main checkout root holds a `CLAUDE.md`, and an arm session starts in its clone
- **THEN** the session context holds no content of that file

#### Scenario: Bench repository holds skills

- **WHEN** the bench repository holds skills in `.claude/skills/` and an arm session starts in its clone
- **THEN** the session's skill list holds none of them

#### Scenario: Target repository instructions

- **WHEN** the arm's clone holds a `CLAUDE.md`
- **THEN** the arm session loads it

#### Scenario: User instructions

- **WHEN** the user config snapshot holds the user's `CLAUDE.md`
- **THEN** the arm session loads its content

### Requirement: Comparisons use their recorded workspace

`bench run` and `bench score` SHALL locate a comparison's arms at the workspace path recorded in the comparison's `meta.json`, independent of the current workspace.

#### Scenario: Comparison prepared in another workspace

- **WHEN** a comparison's `meta.json` records a workspace under `~/bench-runs`
- **THEN** `bench score` on that comparison reads the arms under `~/bench-runs`
