#!/usr/bin/env bash
# provision-macos-runner.sh — registers a self-hosted macOS runner for autobrain-mobile
# with labels [self-hosted, macOS, X64] for iOS .ipa release workflow.
#
# Prerequisites (must be installed BEFORE running this):
#   - Xcode Command Line Tools: xcode-select --install
#   - Xcode (full) from Mac App Store or developer.apple.com
#   - Homebrew: /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
#   - Flutter SDK (stable): brew install --cask flutter
#   - CocoaPods: sudo gem install cocoapods
#   - GitHub CLI: brew install gh
#   - gh auth login (with admin:repo_hook, repo, workflow scopes)
#
# Usage:
#   REPO=CannonFodder151/autobrain-mobile RUNNER_NAME="Nathans-iMac-Pro" ./provision-macos-runner.sh
#   Or with explicit token: RUNNER_TOKEN=<token> REPO=... ./provision-macos-runner.sh
#
# The runner will be installed in ~/actions-runner and registered as a systemd-style
# launchd service (macOS equivalent) for auto-start on boot.

set -euo pipefail

: "${REPO:=CannonFodder151/autobrain-mobile}"
: "${RUNNER_NAME:=$(hostname -s)}"
: "${RUNNER_LABELS:=self-hosted,macOS,X64}"
: "${RUNNER_DIR:=${HOME}/actions-runner}"
: "${RUNNER_VERSION:=2.338.2}"  # match existing runner versions
: "${GITHUB_API:=https://api.github.com}"

log() { echo "[$(date -u +%FT%TZ)] $*"; }
die() { log "ERROR: $*"; exit 1; }

# Require gh CLI for token generation if RUNNER_TOKEN not provided
if [[ -z "${RUNNER_TOKEN:-}" ]]; then
  command -v gh >/dev/null || die "gh CLI not found. Install: brew install gh"
  log "Generating registration token for ${REPO}..."
  RUNNER_TOKEN=$(gh api -X POST "repos/${REPO}/actions/runners/registration-token" --jq '.token') || die "Failed to get registration token (check gh auth)"
  log "Token obtained (expires in ~1 hour)"
fi

# Verify prerequisites
log "Verifying prerequisites..."
for cmd in xcodebuild flutter pod ruby git curl tar; do
  command -v "$cmd" >/dev/null || die "Required command '$cmd' not found"
done

# Xcode version check
XCODE_VER=$(xcodebuild -version | head -1 | awk '{print $2}')
log "Xcode: ${XCODE_VER}"

# Flutter version check
FLUTTER_VER=$(flutter --version | head -1)
log "Flutter: ${FLUTTER_VER}"

# CocoaPods version check
POD_VER=$(pod --version)
log "CocoaPods: ${POD_VER}"

# Ruby version (for Fastlane if used)
RUBY_VER=$(ruby --version | awk '{print $2}')
log "Ruby: ${RUBY_VER}"

# Code signing identity check (for iOS distribution)
if security find-identity -v -p codesigning | grep -q "Apple Distribution"; then
  log "Apple Distribution certificate: PRESENT"
else
  log "WARNING: No 'Apple Distribution' identity found in keychain. iOS release signing will fail."
fi

# Create runner directory
log "Creating runner directory: ${RUNNER_DIR}"
mkdir -p "${RUNNER_DIR}"
cd "${RUNNER_DIR}"

# Download runner if not present
if [[ ! -f .runner ]]; then
  RUNNER_ARCH="x64"
  RUNNER_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-osx-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz"
  log "Downloading runner ${RUNNER_VERSION} for macOS ${RUNNER_ARCH}..."
  curl -fsSL "${RUNNER_URL}" | tar xz || die "Failed to download/extract runner"
else
  log "Runner already present, skipping download"
fi

# Configure runner (unattended, replace existing)
log "Configuring runner: ${RUNNER_NAME} with labels: ${RUNNER_LABELS}"
./config.sh \
  --url "https://github.com/${REPO}" \
  --token "${RUNNER_TOKEN}" \
  --name "${RUNNER_NAME}" \
  --labels "${RUNNER_LABELS}" \
  --unattended \
  --replace || die "Runner configuration failed"

# Install as launchd service (auto-start on boot)
log "Installing launchd service..."
sudo ./svc.sh install || die "svc.sh install failed (requires sudo)"

# Start the service
log "Starting runner service..."
sudo ./svc.sh start || die "svc.sh start failed"

# Verify runner is online
sleep 5
log "Verifying runner status..."
RUNNER_STATUS=$(gh api "repos/${REPO}/actions/runners" --jq ".runners[] | select(.name==\"${RUNNER_NAME}\") | {name, status, labels: [.labels[].name]}" 2>/dev/null || echo "{}")
log "Runner status: ${RUNNER_STATUS}"

if echo "${RUNNER_STATUS}" | grep -q '"status": "online"'; then
  log "SUCCESS: Runner ${RUNNER_NAME} is ONLINE with labels: ${RUNNER_LABELS}"
else
  log "WARNING: Runner may not be online yet. Check logs: ${RUNNER_DIR}/_diag/"
fi

log "Provisioning complete."
log "Runner directory: ${RUNNER_DIR}"
log "Service control: sudo ./svc.sh {start|stop|status|uninstall}"
log "Logs: ${RUNNER_DIR}/_diag/Runner_*.log"