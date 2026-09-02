## Summary

Fixes AUT-2097: `build-hosted.yml` ships `autobrain-frontend` images whose OCI manifest declares `arm64` while the actual layer blobs are amd64. On the Oracle VM (152.69.188.133) the container fails with `exec /bin/sh: exec format error` and `hosted.autobrainservice.app` 502s.

Three coordinated changes:

1. **Per-arch cache scoping** (`docker/setup-buildx-action`): cache-from / cache-to now use `scope=build-hosted-${{ matrix.arch }}`. Previously both matrix entries shared one `type=gha` namespace and BuildKit reused amd64 diffs under an arm64 `--platform`. Per-arch scope forces arch-homogeneous reuse — cheapest fix; doesn't disable caching entirely.
2. **Per-image manifest assertion** inside the build loop: every `:hosted-${ARCH}` is `imagetools inspect`-ed immediately after push. Surfaces "I built nothing for this arch" before the manifest job tries to assemble.
3. **End-to-end arch smoke step** ("Verify pushed image architecture"): after all four services push for a given arch, `docker buildx run --platform linux/${ARCH} ... uname -m` on the native runner (which IS that arch) and assert it matches. A wrong answer fails the job with `::error::AUT-2097 arch mismatch` — Catches cache contamination and any QEMU silent fallback before the broken image leaves the matrix job.
4. **Manifest-job child-manifest existence check**: refuse to assemble `:hosted` if `:hosted-amd64` or `:hosted-arm64` is missing. Prevents `imagetools create` from promoting one arch to both slots when the other arch never pushed a real manifest.

## Acceptance criteria

- [ ] A fresh `build-hosted.yml` run on `gh-runner-autobrain-arm64` produces `:hosted-arm64` where `uname -m` returns `aarch64`.
- [ ] `docker run --rm .../autobrain-frontend:hosted-arm64 /bin/sh -c "true"` exits 0 on the Oracle VM.
- [ ] `docker buildx imagetools inspect autobrain-frontend:hosted` lists two distinct per-arch manifests with different layer diffs.
- [ ] After fix, hosted compose is repinned to the new SHA tag and `https://hosted.autobrainservice.app/health` returns 200.

## Linked

- AUT-2097 (this issue)
- AUT-2077 (Hosted Frontend Offline — the user-facing incident)
- AUT-2081 (Deployment Lead heartbeat)
- AUT-2100 (parallel 0.3.88 stopgap — restoration)

## Files Changed

- `.github/workflows/build-hosted.yml`

## Testing

- YAML lints clean (PyYAML).
- Will verify on first post-merge run: arm64 job exits 0, `uname -m` reports `aarch64`, `:hosted` manifest list contains both arches with distinct layer diffs (compare with `docker buildx imagetools inspect`).

## Risk

Lowest-risk fix path per AUT-2097 recommendation #1 + #2. Cache scope change is backward-compatible (a fresh scope just misses once and reuses on subsequent runs). The arch-smoke step adds ~30 s to each matrix job.