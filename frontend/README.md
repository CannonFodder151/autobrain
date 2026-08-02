# AutoBrain Frontend (Flutter)

Offline-first mobile app for iOS and Android.

## Structure

```
lib/
  main.dart          entrypoint
  app.dart           MaterialApp + auth gate
  core/
    config.dart      --dart-define build configuration
    api_client.dart  HTTP client (REST + uploads + exports)
    auth_state.dart  auth token + session (provider)
    models.dart      typed API models
    offline_cache.dart  SQLite cache for offline mode
    theme.dart
  screens/
    auth/            login, register
    home/            dashboard
    vehicles/        list, add (with rego lookup), timeline
    services/        history, add, AI prediction, export
    fuel/            tracker, add, efficiency graph
    diagnostics/     AI diagnosis + add-to-service
    mods/            tracker, build sheet export
    receipts/        OCR scan + apply to service/inventory
    parts/           inventory, reorder suggestions
    valuation/       resale value estimator
    analytics/       spend, TCO, insights, forecast
  widgets/           shared widgets
test/                model unit tests
```

## Build

Flutter SDK is required. Regenerate platform boilerplate (Android/iOS/Web
folders beyond the config files committed here) with:

```bash
flutter create . --platforms=android,ios,web --org com.autobrain
flutter pub get
```

Configure API endpoints at build time:

```bash
flutter build web --dart-define=API_BASE_URL=http://your-host/api/v1 \
                  --dart-define=WS_BASE_URL=ws://your-host/ws
```

Mobile builds:

```bash
flutter build apk --release
flutter build ios --release   # requires macOS + Xcode
```

Web builds are also produced by the frontend Docker image (see
`docker/frontend/Dockerfile`).

## Offline mode

API responses are cached to SQLite (`offline_cache.dart`). Screens that
currently rely on live data degrade gracefully on failure; the cache layer is
the intended extension point for full offline queues.

## Tests

```bash
flutter test
```
