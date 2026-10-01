# AutoBrain frontend — builds Flutter web, serves via nginx.
# Mobile (Android/iOS) artifacts are built with Flutter tooling outside this image.
# Build from repo root:  docker build -f docker/frontend/Dockerfile .

ARG FLUTTER_IMAGE=ghcr.io/cirruslabs/flutter:3.38.2

FROM ${FLUTTER_IMAGE} AS build

# Required on hosted builds (Azure/cloud): the runtime base URL must point at
# the public host, NOT localhost, or the app silently talks to the container.
# CI should pass --build-arg API_BASE_URL / WS_BASE_URL explicitly.
ARG API_BASE_URL=http://localhost:8000/api/v1
ARG WS_BASE_URL=ws://localhost:8000/ws
# AUT-2220: CARTO basemap API key. CARTO keys are designed to be public
# (embedded in tile URLs as ?key=...). CI must pass --build-arg CARTO_API_KEY
# explicitly. An empty value is now a hard build failure (see the assertion
# below) instead of silently shipping the watermapped public basemap.
ARG CARTO_API_KEY=

# AUT-4690: fail fast, before the multi-minute `flutter build web`, when the key
# is unset/expired. Previously this only surfaced as a watermapped basemap in
# production, caught weeks later by a human QA curl (AUT-4533, AUT-4649).
RUN [ -n "${CARTO_API_KEY}" ] || { \
      echo "ERROR: CARTO_API_KEY is empty. The --build-arg / GitHub Actions secret CARTO_API_KEY is unset or expired; refusing to build a key-less CARTO basemap." >&2; \
      exit 1; \
    }

WORKDIR /build
# Copy the lockfile too so `pub get` resolves the exact pinned dependency set
# (hermetic builds, no surprise transitive upgrades on hosted builders).
COPY frontend/pubspec.yaml frontend/pubspec.lock ./
RUN flutter pub get
COPY frontend ./
RUN flutter build web \
    --dart-define=API_BASE_URL=${API_BASE_URL} \
    --dart-define=WS_BASE_URL=${WS_BASE_URL} \
    --dart-define=CARTO_API_KEY=${CARTO_API_KEY}

# AUT-4690: belt-and-braces. The key is inlined into main.dart.js at compile
# time, so assert the value actually reached the shipped bundle (catches a
# dropped --dart-define or a renamed const, which the fail-fast check above
# cannot see). Matches on the literal value, so any key format works.
RUN set -eu; \
    js=build/web/main.dart.js; \
    if ! grep -qF "${CARTO_API_KEY}" "$js"; then \
      echo "ERROR: CARTO_API_KEY value not found in $js — the key was not baked into the bundle." >&2; \
      exit 1; \
    fi; \
    grep -qF '?key=' "$js" || echo "WARN: '?key=' not found in $js; check the CARTO tile template in frontend/lib/screens/servo_spy." >&2

FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:ed04ec1ff34502c339ee5c3ae3f855442398edc1d05591e2b98981dcbbd20b1e
COPY --from=build /build/build/web /usr/share/nginx/html
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/frontend/security-headers.inc /etc/nginx/conf.d/security-headers.inc
EXPOSE 8080
USER nginx
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1:8080/ || exit 1
