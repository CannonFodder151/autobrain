# AutoBrain frontend — builds Flutter web, serves via nginx.
# Mobile (Android/iOS) artifacts are built with Flutter tooling outside this image.
# Build from repo root:  docker build -f docker/frontend/Dockerfile .

ARG FLUTTER_IMAGE=ghcr.io/cirruslabs/flutter:stable

FROM ${FLUTTER_IMAGE} AS build

ARG API_BASE_URL=http://localhost:8000/api/v1
ARG WS_BASE_URL=ws://localhost:8000/ws

WORKDIR /build
COPY frontend/pubspec.yaml ./
RUN flutter pub get
COPY frontend ./
RUN dart run build_runner build --delete-conflicting-outputs 2>/dev/null || true
RUN flutter build web \
    --dart-define=API_BASE_URL=${API_BASE_URL} \
    --dart-define=WS_BASE_URL=${WS_BASE_URL}

FROM nginx:1.27-alpine
COPY --from=build /build/build/web /usr/share/nginx/html
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD wget -qO- http://localhost/ || exit 1
