#!/usr/bin/env bash
# Stage the Apple App Store Connect API key (.p8 file) from base64 env var.
# Requires: APPLE_KEY_BASE64, APPLE_KEY_PATH

set -euo pipefail

if [[ -z "${APPLE_KEY_BASE64:-}" ]]; then
  echo "ERROR: APPLE_KEY_BASE64 environment variable is required" >&2
  exit 1
fi

if [[ -z "${APPLE_KEY_PATH:-}" ]]; then
  echo "ERROR: APPLE_KEY_PATH environment variable is required" >&2
  exit 1
fi

# Create directory if it doesn't exist
mkdir -p "$(dirname "${APPLE_KEY_PATH}")"

# Decode base64 and write to file
echo "${APPLE_KEY_BASE64}" | base64 -d > "${APPLE_KEY_PATH}"

# Verify the file was created and has content
if [[ ! -s "${APPLE_KEY_PATH}" ]]; then
  echo "ERROR: Failed to write API key to ${APPLE_KEY_PATH}" >&2
  exit 1
fi

# Set restrictive permissions
chmod 600 "${APPLE_KEY_PATH}"

echo "Successfully staged Apple API key to ${APPLE_KEY_PATH}"
