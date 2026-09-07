# AutoBrain frontend — builds Flutter web, serves via nginx.
# Mobile (Android/iOS) artifacts are built with Flutter tooling outside this image.
# Build from repo root:  docker build -f docker/frontend/Dockerfile .

ARG FLUTTER_IMAGE=ghcr.io/cirruslabs/flutter:3.27.7

FROM ${FLUTTER_IMAGE} AS build

# Required on hosted builds (Azure/cloud): the runtime base URL must point at
# the public host, NOT localhost, or the app silently talks to the container.
# CI should pass --build-arg API_BASE_URL / WS_BASE_URL explicitly.
ARG API_BASE_URL=http://localhost:8000/api/v1
ARG WS_BASE_URL=ws://localhost:8000/ws
# AUT-2220: CARTO basemap API key. CARTO keys are designed to be public
# (embedded in tile URLs as ?key=...). CI must pass --build-arg CARTO_API_KEY
# explicitly. Empty value falls back to the key-less public basemap.
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

FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:45ce1e2e699234253d1def7baa96218a5d00b498d1ba0cbb1a17b6bdf73d1351
COPY --from=build /build/build/web /usr/share/nginx/html
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/frontend/security-headers.inc /etc/nginx/conf.d/security-headers.inc
EXPOSE 8080
USER nginx
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1:8080/ || exit 1
