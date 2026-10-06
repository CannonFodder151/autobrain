#!/bin/bash
# CI guard: fail if a workflow references a repo/org-wide credential for a push
# to a protected branch, or if a job that pushes via secrets.*_PAT declares
# permissions: contents: write.
# Exits 0 on pass, 1 on fail with details on stderr.
# Wrapper for the Python implementation.

set -euo pipefail

exec python3 "$(dirname "$0")/check-ci-credential-scope.py" "$@"