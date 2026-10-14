#!/usr/bin/env bash
# Run complexipy, a cognitive complexity checker for Python, from a local container image.
# The bench owns this copy, so the measuring tool does not change with the setup under test.
# Arguments pass through to complexipy. Run from anywhere inside the repository it measures:
#
#   scripts/complexipy.sh <files> --plain
#
# The image is built on first use from a base image pinned by digest, with complexipy pinned
# by version. The repository is mounted at its host path, so absolute host paths and paths
# relative to the current directory resolve inside the container. The container has no
# network access and runs as the calling user.
set -euo pipefail

version=8.0.1
base=docker.io/library/python:3.12-slim@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe
image=localhost/simplicity-rules-complexipy:$version
repo=$(git rev-parse --show-toplevel)

if ! podman image exists "$image"; then
    podman build -q -t "$image" -f - . >&2 <<CONTAINERFILE
FROM $base
RUN pip install --no-cache-dir --quiet --root-user-action=ignore --disable-pip-version-check complexipy==$version
ENTRYPOINT ["complexipy"]
CONTAINERFILE
fi

exec podman run --rm -i --network none --userns=keep-id --security-opt label=disable \
    -v "$repo:$repo" -w "$PWD" "$image" "$@"
