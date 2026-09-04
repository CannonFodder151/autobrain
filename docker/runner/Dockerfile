# AUT-2469: thin wrapper around ghcr.io/actions/actions-runner that swaps in
# our registration-token-refresh entrypoint. The official image is multi-arch
# (linux/amd64 + linux/arm64); on EP5 (Oracle VM aarch64) Docker pulls the
# arm64 variant — fixes the myoung34/github-runner restart loop that left
# ARM CI on Hosted dead (`ldd: ./bin/libcoreclr.so: No such file`).
#
# RUNNER_BASE_IMAGE defaults to the upstream multi-arch :latest. Pin it by
# @sha256 digest in production (AUT-1533) via the Portainer stack env.
ARG RUNNER_BASE_IMAGE=ghcr.io/actions/actions-runner:latest
FROM ${RUNNER_BASE_IMAGE}

USER root
COPY docker/runner/entrypoint.sh /usr/local/bin/runner-entrypoint.sh
RUN chmod +x /usr/local/bin/runner-entrypoint.sh

# The official image's CMD is `["/entrypoint.sh", "run"]` which boots
# Runner.Listener after a config.sh registration. Our entrypoint re-derives
# the registration token from $GITHUB_PAT_FILE before delegating.
ENTRYPOINT ["/usr/local/bin/runner-entrypoint.sh"]
CMD ["/entrypoint.sh", "run"]

# Re-drop to the upstream non-root user so we don't widen the security
# posture of the official image beyond what they ship.
USER runner
