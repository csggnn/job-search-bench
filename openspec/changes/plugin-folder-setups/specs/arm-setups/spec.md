# Spec Delta

## Purpose

Defines how `bench prepare` selects the plugin each arm loads from the setup repository, which arguments it refuses, and how the comparison records each arm's setup.

## ADDED Requirements

### Requirement: Setup argument form

`bench prepare` SHALL take one setup argument per arm in the form `<path>@<sha>`. `<path>` SHALL be a folder of the `[setup] repo`, relative to the repository root. `.` SHALL select the repository root. `<sha>` SHALL be a full or abbreviated commit SHA. Both parts SHALL be required. The first argument SHALL be the setup of arm X and the second the setup of arm Y.

#### Scenario: Folder at a commit

- **WHEN** `bench prepare bench/feat plugins/a@7280529 plugins/b@7280529` runs
- **THEN** arm X loads the folder `plugins/a` and arm Y the folder `plugins/b` of the setup repository at commit `7280529`

#### Scenario: Repository root

- **WHEN** a setup argument is `.@fcbb2ac`
- **THEN** its arm loads the root of the setup repository at commit `fcbb2ac`

#### Scenario: Missing commit

- **WHEN** a setup argument is `plugins/a`
- **THEN** `bench prepare` exits with an error that names the form `<path>@<sha>`
- **AND** no comparison folder exists in the workspace or in the results folder

#### Scenario: Missing path

- **WHEN** a setup argument is `@7280529`
- **THEN** `bench prepare` exits with an error that names the form `<path>@<sha>`
- **AND** no comparison folder exists in the workspace or in the results folder

### Requirement: Reserved characters and path bounds

`bench prepare` SHALL refuse a setup argument that contains `:` or more than one `@`, or whose path is absolute or has a `..` component. The refusal SHALL happen before any folder is created.

#### Scenario: Path with a reserved character

- **WHEN** a setup argument is `plugins/a:b@7280529` or `plugins/a@b@7280529`
- **THEN** `bench prepare` exits with an error that names the argument
- **AND** no comparison folder exists in the workspace or in the results folder

#### Scenario: Path outside the repository

- **WHEN** a setup argument is `/home/user/plugin@7280529` or `../other@7280529`
- **THEN** `bench prepare` exits with an error that names the argument
- **AND** no comparison folder exists in the workspace or in the results folder

### Requirement: Setup resolves at preparation

Each setup SHALL name a commit reachable in the `[setup] repo` and a folder that exists at that commit. A branch or tag name SHALL NOT be accepted as `<sha>`. When a setup does not resolve, `bench prepare` SHALL exit with an error that names the path and the commit, and no comparison folder SHALL remain in the workspace or in the results folder.

#### Scenario: Folder missing at the commit

- **WHEN** a setup argument is `plugins/missing@7280529` and commit `7280529` has no folder `plugins/missing`
- **THEN** `bench prepare` exits with an error that names `plugins/missing` and `7280529`
- **AND** no comparison folder exists in the workspace or in the results folder

#### Scenario: Branch or tag name as commit

- **WHEN** a setup argument is `plugins/a@main` or `plugins/a@v1`
- **THEN** `bench prepare` exits with an error that names `main` or `v1`
- **AND** no comparison folder exists in the workspace or in the results folder

#### Scenario: Unknown commit

- **WHEN** a setup argument names a commit that the setup repository does not hold
- **THEN** `bench prepare` exits with an error that names the commit
- **AND** no comparison folder exists in the workspace or in the results folder

### Requirement: No assumption on the setup repository layout

`bench prepare` SHALL accept any folder of the setup repository that exists at the commit. It SHALL NOT require any file inside the folder, and SHALL NOT read any file of the setup repository outside the folder to select or validate the setup. When the folder holds no `.claude-plugin/plugin.json`, `bench prepare` SHALL print a warning to stderr that names the folder and the commit, and SHALL continue without asking for input.

#### Scenario: Folder without a plugin manifest

- **WHEN** a setup argument names a folder that holds no `.claude-plugin/plugin.json`
- **THEN** `bench prepare` prints a warning to stderr that names the folder and the commit
- **AND** creates the arm without asking for input, and the arm loads that folder

#### Scenario: Folder with a plugin manifest

- **WHEN** a setup argument names a folder that holds `.claude-plugin/plugin.json`
- **THEN** `bench prepare` prints no warning for that setup

### Requirement: Same setup in both arms

`bench prepare` SHALL accept two setup arguments that name the same folder at the same commit.

#### Scenario: Noise comparison

- **WHEN** `bench prepare bench/feat plugins/a@7280529 plugins/a@7280529` runs
- **THEN** both arms are created and each loads `plugins/a` at commit `7280529`

### Requirement: Setup folder loaded in each arm

An arm session SHALL load its setup folder as its only `--plugin-dir` plugin, in a `bench run` session and in an interactive session started with the arm's `env.sh`.

#### Scenario: Headless run

- **WHEN** `bench run` runs arm X of a comparison prepared with `plugins/a@7280529` for arm X
- **THEN** the arm session loads `plugins/a` of the setup repository at `7280529` and no other folder of it

#### Scenario: Interactive run

- **WHEN** the operator sources arm Y's `env.sh` and starts `claude`
- **THEN** the session loads arm Y's setup folder

### Requirement: Recorded setups

The comparison's `meta.json` SHALL record each setup's path and full 40-character commit SHA. After `bench score`, each `results.csv` row SHALL hold the arm's setup path in `setup` and the full commit SHA in `setup_sha`. The columns of `results.csv` SHALL stay unchanged.

#### Scenario: Abbreviated SHA given

- **WHEN** a comparison is prepared with `plugins/a@7280529`
- **THEN** `meta.json` records `plugins/a` with the full SHA of that commit

#### Scenario: Results rows

- **WHEN** `bench score` completes on a comparison prepared with `plugins/a@7280529 plugins/b@7280529`
- **THEN** the row of arm X holds `plugins/a` in `setup` and the full SHA in `setup_sha`
- **AND** the row of arm Y holds `plugins/b` in `setup` and the full SHA in `setup_sha`
