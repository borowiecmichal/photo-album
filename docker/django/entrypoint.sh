#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

readonly cmd="$*"

# Here you can place any logic that you want to execute on `entrypoint`.

# Set Poetry cache directory to a writable location
export POETRY_CACHE_DIR=/tmp/poetry-cache
mkdir -p "$POETRY_CACHE_DIR"

echo "Service is up: $cmd"

# Evaluating passed command (do not touch):
# shellcheck disable=SC2086
exec $cmd
