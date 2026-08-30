## Summary

Security hardening for 4 findings from AUT-1186:

| ID | Finding | Fix |
|----|---------|-----|
| F1 | Default API/WS URLs used plaintext HTTP | config.dart defaults to https/wss; AndroidManifest adds usesCleartextTraffic=false |
| F2 | Release APK signed with debug keystore | build.gradle.kts: release signing config from local.properties/CI secrets; debug signing removed |
| F3 | android:allowBackup default true | AndroidManifest: allowBackup=false |
| F4 | Password reset token in URL query string | Token via URL fragment (#token=); email links updated |

## Files Changed
- backend/app/services/email.py
- frontend/lib/core/config.dart
- frontend/lib/app.dart
- frontend/lib/screens/auth/reset_password_web.dart
- frontend/android/app/build.gradle.kts
- frontend/android/app/src/main/AndroidManifest.xml
- frontend/android/local.properties

## Testing
- flutter analyze: clean
