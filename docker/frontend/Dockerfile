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

# AUT-4690: the CARTO key is inlined into main.dart.js at compile time, so an
# unset/expired repo secret produced a *green* build with a key-less basemap —
# the Servo Spy map silently fell back to the CARTO watermark tile and was only
# caught by a human QA curl weeks later (AUT-4533, AUT-4649). Assert the key is
# actually in the bundle. Matches on the literal value, so any key format works.
RUN set -eu; \
    js=build/web/main.dart.js; \
    if [ -z "${CARTO_API_KEY}" ]; then \
      echo "ERROR: CARTO_API_KEY is empty. The build-arg/GitHub secret CARTO_API_KEY is unset or expired; refusing to ship a key-less CARTO basemap." >&2; \
      exit 1; \
    fi; \
    if ! grep -qF "${CARTO_API_KEY}" "$js"; then \
      echo "ERROR: the CARTO_API_KEY value is not present in $js; the key was not baked into the bundle." >&2; \
      exit 1; \
    fi; \
    grep -qF '?key=' "$js" || echo "WARN: '?key=' not found in $js; check the CARTO tile template in frontend/lib/screens/servo_spy." >&2

FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:442753882674b49ae2c1de83ed67896131c0777f56df5005e356e62bc3f7e7ce
COPY --from=build /build/build/web /usr/share/nginx/html
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/frontend/security-headers.inc /etc/nginx/conf.d/security-headers.inc
EXPOSE 8080
USER nginx
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1:8080/ || exit 1
