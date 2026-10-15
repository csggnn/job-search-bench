You read the task list of an OpenSpec change to a Python project. An agent will implement
the change headless, and no human answers its questions.

The agent works in a git clone of the project. It can edit files, run git, run the unit
tests and linters, start the project's containers and run local scripts on files that the
repository holds. Files the repository ignores, such as personal data, are absent.

A task is not performable when it needs any of:

- files the repository does not hold, such as personal data or a populated database,
- a call to a paid external API,
- input from a human, such as a URL, an account or a choice,
- a manual inspection, such as looking at a page in a browser.

List the tasks that are not performable, with one reason each. End with exactly one line:

SKIP: 5.2, 5.3

with the task IDs as they appear in the list, or `SKIP: none`.
