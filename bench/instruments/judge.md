You compare two implementations, X and Y, of the same change to a Python project. Both
started from the same commit and implement the same feature description, given below.

Judge which implementation a maintainer would rather merge and maintain. Consider, in this
order:

1. Correctness against the spec: every requirement and scenario is met.
2. Simplicity: the code is easy to read and change. Fewer concepts, shallow nesting, no
   unneeded abstraction, no duplicated logic.
3. Tests: they cover the spec's scenarios and are easy to read.
4. Fit: the code follows the conventions of the surrounding codebase.

Ignore differences in documentation wording unless a statement is wrong.

Write your reasoning first, citing files and functions. End with exactly one line:

PREFERRED: X

or `PREFERRED: Y`, or `PREFERRED: TIE` when neither is better.
