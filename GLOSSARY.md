# Glossary

This file defines the terms the bench, its specs and its README use.

**Arm**: one side of a comparison, labelled X or Y. An arm is a folder under
`runs/<comparison>/` that holds a clone of the target repository at the snapshot tag
(`repo/`), where the agent implements the feature; a clone of the setup repository at the
arm's setup commit (`setup/`); `plugin`, a link to the setup's folder in that clone, which
the arm loads as its plugin; the arm's own Claude Code config dir (`claude-config/`); and
`env.sh`, which prepares a shell for an interactive session in the arm.

**Setup**: the plugin an arm loads, written `<path>@<sha>`: the folder `<path>` of the
setup repository at the commit `<sha>`. `.` is the repository root. The results name a setup
by its path.
