# Glossary

This file defines the terms the bench, its specs and its README use.

**Arm**: one side of a comparison, labelled X or Y. An arm is a folder under
`runs/<comparison>/` that holds a clone of the target repository at the snapshot tag
(`repo/`), where the agent implements the feature; a clone of the setup repository at the
arm's commit (`plugin/`), which supplies the plugin; the arm's own Claude Code config dir
(`claude-config/`); and `env.sh`, which prepares a shell for an interactive session in the
arm.
