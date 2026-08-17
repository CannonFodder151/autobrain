# Graph Report - autobrain  (2026-08-17)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 4441 nodes · 9568 edges · 244 communities (215 shown, 29 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 831 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e70a2704`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Base
- seed.py
- User
- AuthState
- tasks.py
- issues.py
- social.py
- package:flutter/material.dart
- _post
- get_accessible_vehicle
- package:provider/provider.dart
- test_iap.py
- obd_trip_recorder.dart
- test_social.py
- State
- test_social_regression.py
- config.py
- social_compose.dart
- add_fuel_screen.dart
- bikesguide.py
- iap.py
- community_garage_share_test.dart
- community_garage/models.dart
- home_screen.dart
- social_api.dart
- FuelLog
- service_form_screen.dart
- core/auth_state.dart
- market_data.py
- test_issues_blog.py
- auth_state.dart
- services/billing.py
- v1/auth.py
- test_billing.py
- _user
- SocialServerConfig
- analytics.dart
- server_settings.dart
- add_mod_screen.dart
- services/auth.py
- car_kit_trip_monitor.dart
- v1/billing.py
- test_services_extraction.py
- add_vehicle_screen.dart
- v1/diagnostics.py
- issues_blog_screen.dart
- dart:async
- obd_trip_monitor.dart
- dongle_provisioning_test.dart
- service.dart
- license_screen.dart
- String?
- dongle_wifi_screen.dart
- edit_vehicle_screen.dart
- mods.py
- test_config_prod_guard.py
- issue_detail_screen.dart
- rego.py
- trip.dart
- social_post_detail.dart
- test_api.py
- v1/obd.py
- settings_screen.dart
- api_client.dart
- config.dart
- login_screen.dart
- dongle_wifi_screen_test.dart
- notify.py
- backup.py
- test_workers.py
- car_integration_screen.dart
- valuation.dart
- dongle_settings.dart
- notifications_screen.dart
- car_kit_trip_monitor_test.dart
- logbook_screen.dart
- edit_build_screen.dart
- test_aut207_token_lifecycle.py
- bool get
- ocr_utils.py
- vehicle.dart
- service_list_screen.dart
- valuation_screen.dart
- test_fallbacks.py
- email.py
- test_issues_federation.py
- dongle_ble_io.dart
- package:flutter_test/flutter_test.dart
- export.py
- fuel_screen.dart
- models.py
- test_trip_gps.py
- service_prediction_screen.dart
- share_vehicle_screen.dart
- ai/app/main.py
- create_device
- router_client.py
- test_pt1_xff_bypass.py
- test_ws_auth.py
- car_kit_service.dart
- add_part_screen.dart
- geoloc_io_test.dart
- diagnose_fallback
- social_image.py
- test_device_api.py
- app.dart
- StatelessWidget
- schemas/logbook.py
- FakeClient
- _FakeRedis
- fuel.dart
- social_card.dart
- theme.dart
- trip_datetime.dart
- run
- test_aut206_security_hardening.py
- backfill_entity_embedding
- test_aut302_rate_limit.py
- speed_source_io.dart
- diagnostic.dart
- tests/test_auth.py
- check_verify_rate_limit
- test_assets_backup.py
- test_search_sql_injection.py
- test_logbook_club_reg.py
- test_share_access.py
- dongle_provisioning.dart
- enhance
- semantic_search
- offline_cache.dart
- share_scope_picker.dart
- manifest.json
- social/rate_limit.py
- share_scope_picker_test.dart
- download_io.dart
- receipt.dart
- timeline.dart
- trip_route.dart
- test-ci-fixes.sh
- estimate_condition
- _odometer_fallback
- db_env
- test_admin_delete_build_purges_related_rows
- trip_route_map.dart
- premium_gate.dart
- mod_impact_fallback
- env.py
- authenticate_ws
- timedelta
- test_pdf_dos_regression.py
- asyncio
- dongle_ble.dart
- market-data/test_auth.py
- predict_service_fallback
- test_gateway_security.py
- u1v2w3x4y5z6_add_issue_blog_tables.py
- v1w2x3y4z5a6_add_comment_flags_social_ban.py
- dump_backup
- test_restore_roundtrip_keeps_shares
- _externalize_url
- device_keys.py
- ConnectionManager
- obd_keepalive.dart
- obd_keepalive_stub.dart
- test_rate_limit.py
- a1b2c3d4e5f7_add_social_issue_photos.py
- a6b5c4d3e2f1_add_social_photo_comment.py
- a6b5c4d3e2f2_add_issue_federation_columns.py
- n4p5q6r7s8t9_add_social_tables.py
- p6q7r8s9t0u1_add_social_event_cursor.py
- w5x6y7z8a9b0_add_build_flags.py
- schemas/receipt.py
- _FlakySession
- test_deps_transitive_cves.py
- a1b2c3d4e5f6_add_devices.py
- q1r2s3t4u5v6_add_social_photo_position.py
- x1y2z3a4b5c6_add_remote_tombstones.py
- download_assets
- test_deps_pypdf_pin.py
- test_register_reuses_stored_server_key
- test_alembic_heads.py
- speed_source.dart
- import_profile
- _reject_oversized_content_length
- CarKitTripMonitor
- core/models.dart
- prune-images.sh
- require_premium
- conftest.py
- _db_setup
- test_create_with_photos_attaches_and_serializes
- test_create_rejects_unknown_or_foreign_photos
- download_io.dart
- geoloc.dart
- reset_password_io.dart
- auto-bump.sh
- backup.sh
- bump-version.sh
- check-release.sh
- deploy.sh
- init-minio.sh
- publish-images.sh
- setup-server.sh
- sync-mobile.sh
- DateTime
- Exception
- FuelLog?
- Modification?
- ServiceRecord
- SocialBuild
- SocialIssuePost
- Vehicle

## God Nodes (most connected - your core abstractions)
1. `User` - 273 edges
2. `AuthState` - 237 edges
3. `Vehicle` - 92 edges
4. `get_accessible_vehicle()` - 84 edges
5. `_post()` - 79 edges
6. `Base` - 76 edges
7. `_get()` - 66 edges
8. `create_access_token()` - 64 edges
9. `SocialServerConfig` - 43 edges
10. `hash_password()` - 42 edges

## Surprising Connections (you probably didn't know these)
- `health()` --references--> `_get()`  [EXTRACTED]
  market-data/main.py → backend/app/social/federation.py
- `list_modules()` --references--> `_get()`  [EXTRACTED]
  ai/app/main.py → backend/app/social/federation.py
- `test_login_schema_handles_mfa_setup_flag()` --uses--> `LoginResult`  [INFERRED]
  backend/tests/test_api.py → backend/app/schemas/auth.py
- `search()` --references--> `_post()`  [EXTRACTED]
  market-data/main.py → backend/app/social/federation.py
- `infer()` --references--> `_post()`  [EXTRACTED]
  ai/app/main.py → backend/app/social/federation.py

## Import Cycles
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/device.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/fuel.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/logbook.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/market_listing.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/refresh_token.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/share.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/user.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/valuation.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/diagnostic.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/mod.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/notification.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/obd.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/part.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/receipt.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/service.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/vehicle.py -> backend/app/db/session.py`
- 3-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/social/models.py -> backend/app/db/session.py`
- 4-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/vehicle.py -> backend/app/models/fuel.py -> backend/app/db/session.py`
- 4-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/vehicle.py -> backend/app/models/diagnostic.py -> backend/app/db/session.py`
- 4-file cycle: `backend/app/db/session.py -> backend/app/models/__init__.py -> backend/app/models/vehicle.py -> backend/app/models/mod.py -> backend/app/db/session.py`

## Communities (244 total, 29 thin omitted)

### Community 0 - "Base"
Cohesion: 0.04
Nodes (74): get_current_user(), get_device_from_key(), AsyncSession, Shared FastAPI dependencies., Free accounts cannot use rego lookup (exports are available on all plans)., Unattended device auth via X-Device-API-Key (dongle WiFi upload, AUT-918). The…, Demo accounts are read-only: reject any mutating request., require_admin() (+66 more)

### Community 1 - "seed.py"
Cohesion: 0.05
Nodes (73): _auto_resolve(), Mark a diagnostic resolved when its linked service is completed., create_service(), delete_service(), export(), get_service(), list_services(), predict() (+65 more)

### Community 2 - "User"
Cohesion: 0.07
Nodes (79): accept_share(), deny_share(), _get_share(), _invite_out(), list_invites(), AsyncSession, delete, Vehicle share invite endpoints: accept/deny invitations, remove access. (+71 more)

### Community 3 - "AuthState"
Cohesion: 0.04
Nodes (77): add_mod_screen.dart, add_vehicle_screen.dart, edit_vehicle_screen.dart, build, CommunityGarageScreen, _body, build, _body (+69 more)

### Community 4 - "tasks.py"
Cohesion: 0.05
Nodes (68): apply_receipt_to_service(), delete_receipt(), _ext(), list_receipts(), AsyncSession, delete, Receipt, UploadFile (+60 more)

### Community 5 - "issues.py"
Cohesion: 0.07
Nodes (69): add_comment(), apply_issue_event(), _comment_count(), _comment_photo_url(), CommentIn, create_issue(), _decode_cursor(), delete_issue() (+61 more)

### Community 6 - "social.py"
Cohesion: 0.08
Nodes (65): delete_build_admin(), Admin deletes a build post outright (moderation hub, AUT-883): cascades…, add_comment(), _apply_event(), _comment_count(), CommentIn, create_post(), create_share_link() (+57 more)

### Community 7 - "package:flutter/material.dart"
Cohesion: 0.04
Nodes (59): edit_build_screen.dart, IssueStatus, build, _builds, createState, _delete, _edit, _error (+51 more)

### Community 8 - "_post"
Cohesion: 0.06
Nodes (58): backup_user(), _best_effort_delete_media(), delete_build_comment_admin(), delete_comment_admin(), delete_issue_admin(), delete_user(), download_backup(), flagged_issues() (+50 more)

### Community 9 - "get_accessible_vehicle"
Cohesion: 0.07
Nodes (58): _current_fy(), delete_entry(), export_logbook(), _fy_bounds(), get_entry(), list_entries(), logbook_stats(), AsyncSession (+50 more)

### Community 10 - "package:provider/provider.dart"
Cohesion: 0.04
Nodes (52): add_diagnostic_screen.dart, add_part_screen.dart, ../core/models.dart, _FakeApi, _addToService, build, createState, _delete (+44 more)

### Community 11 - "test_iap.py"
Cohesion: 0.09
Nodes (40): _google_expiry_ms(), handle_apple_webhook(), Verify a store transaction server-side and grant the entitlement. Raises…, App Store Server Notifications v2 (JWS-signed). Matches the account by…, verify_and_grant(), anyio_run(), apple_cfg(), clean_iap_config() (+32 more)

### Community 12 - "obd_trip_recorder.dart"
Cohesion: 0.04
Nodes (54): ActiveTrip? get, _active, activeKey, ActiveTrip, bind, CarConnectionState, distanceKm, endedAt (+46 more)

### Community 13 - "test_social.py"
Cohesion: 0.13
Nodes (52): create_access_token(), _client(), _enable_feature(), _new_user(), _new_vehicle(), AsyncClient, asyncio, Vehicle (+44 more)

### Community 14 - "State"
Cohesion: 0.07
Nodes (35): MyBuildsScreen, _MyBuildsScreenState, ShareLinkView, _ShareLinkViewState, build, _busy, _confirm, createState (+27 more)

### Community 15 - "test_social_regression.py"
Cohesion: 0.07
Nodes (48): UploadFile, upload(), presigned_url(), Short-lived presigned GET URL (externalized for the public endpoint)., compress_to_webp(), MediaError, photo_key(), Social media handling: webp-compress on upload, MinIO storage, signed URLs. No… (+40 more)

### Community 16 - "config.py"
Cohesion: 0.07
Nodes (40): Application configuration. All settings are read from environment variables…, hash_password(), Security helpers: password hashing and JWT tokens., Database bootstrap. Runs Alembic migrations when available; falls back to…, _seed_admin(), _seed_demo(), Delete the demo user + all demo data, then re-seed. Used when the seed changes…, Ensure the admin account from ADMIN_EMAIL/ADMIN_INITIAL_PASSWORD exists. (+32 more)

### Community 17 - "social_compose.dart"
Cohesion: 0.04
Nodes (45): dart:typed_data, _body, build, createState, dispose, initState, IssueComposeScreen, _IssueComposeScreenState (+37 more)

### Community 18 - "add_fuel_screen.dart"
Cohesion: 0.04
Nodes (49): ../core/api_client.dart, AddFuelScreen, _AddFuelScreenState, build, _busy, _calcTotalAvailable, createState, _date (+41 more)

### Community 19 - "bikesguide.py"
Cohesion: 0.07
Nodes (37): limit, _browser_search(), _empty(), _gated(), _parked(), BikeGuide scraper: pull live used-motorcycle listings for a search query.…, True when the page is the FingerprintJS redirect challenge, not search markup., Run the Playwright worker in a subprocess (fresh process = reliable timeouts). (+29 more)

### Community 20 - "iap.py"
Cohesion: 0.07
Nodes (43): _apple_bearer(), _apple_subscription(), _apple_transaction(), _b64decode(), _chain_verified(), _decode_signed_transaction(), _expires_at_from_ms(), _google_access_token() (+35 more)

### Community 21 - "community_garage_share_test.dart"
Cohesion: 0.06
Nodes (37): TokenStore, main, _api, _build, _copiedText, _FakeAuthState, main, _mockClipboard (+29 more)

### Community 22 - "community_garage/models.dart"
Cohesion: 0.05
Nodes (41): authorDisplayName, body, caption, commentCount, comments, copyWith, createdAt, diff (+33 more)

### Community 23 - "home_screen.dart"
Cohesion: 0.05
Nodes (40): ../admin/admin_screen.dart, ../analytics/analytics_screen.dart, ../../community_garage/community_garage_screen.dart, ../diagnostics/diagnostics_screen.dart, _androidUrl, color, createState, _Feature (+32 more)

### Community 24 - "social_api.dart"
Cohesion: 0.05
Nodes (40): addComment, addIssueComment, adminDeleteBuildComment, adminDeleteBuildPost, adminDeleteComment, adminDeletePost, _api, comments (+32 more)

### Community 25 - "FuelLog"
Cohesion: 0.07
Nodes (49): analytics(), _insights(), _predicted_services(), AsyncSession, Analytics routes: spend, TCO, cost per km, forecasts, insights., add_fuel(), delete_fuel(), export_fuel_year() (+41 more)

### Community 26 - "service_form_screen.dart"
Cohesion: 0.05
Nodes (39): _addCustomItem, build, _busy, _CommonItem, _commonItems, createState, _customItems, _date (+31 more)

### Community 27 - "core/auth_state.dart"
Cohesion: 0.06
Nodes (36): app.dart, core/auth_state.dart, core/config.dart, ../diagnostics/add_diagnostic_screen.dart, load, main, build, _busy (+28 more)

### Community 28 - "market_data.py"
Cohesion: 0.11
Nodes (37): MarketListingCache, _aggregate(), _build(), clear_market_cache(), _dig(), _fallback(), _fetch_provider(), _first() (+29 more)

### Community 29 - "test_issues_blog.py"
Cohesion: 0.11
Nodes (38): _new_comment(), _new_issue(), asyncio, Regression tests for the Community Garage Issues Blog (AUT-627, AUT-643).…, AUT-736: a reply can carry one photo. The photo must belong to the uploader and…, AUT-736 F1 regression: with foreign keys enforced (as on Postgres), deleting a…, Owner edits their own post -> 200 with the refreshed payload (regression for…, Issues are premium-gated: global search must never surface them to a free… (+30 more)

### Community 30 - "auth_state.dart"
Cohesion: 0.05
Nodes (37): api_client.dart, config.dart, _anonymous, api, _client, completeMfaSetup, confirmPasswordReset, _darkMode (+29 more)

### Community 31 - "services/billing.py"
Cohesion: 0.10
Nodes (32): pricing(), Public price catalogue + early-adopter sale info (no auth)., _apply_subscription(), cancel_subscription(), construct_event(), create_portal_session(), _discounted(), get_client() (+24 more)

### Community 32 - "v1/auth.py"
Cohesion: 0.11
Nodes (35): auth_config(), confirm_password_reset(), _decode_token(), logout(), mfa_setup(), mfa_setup_session(), Any, patch (+27 more)

### Community 33 - "test_billing.py"
Cohesion: 0.11
Nodes (35): apply_free(), apply_plan(), create_checkout_session(), Find-or-create the Stripe customer and open a Checkout subscription., _checkout(), fake_stripe(), _FakeStripe, asyncio (+27 more)

### Community 34 - "_user"
Cohesion: 0.14
Nodes (37): me(), apply_iap(), clear_iap(), has_paid_subscription(), iap_status(), license_status(), plan_for_iap_product(), plan_for_user() (+29 more)

### Community 35 - "SocialServerConfig"
Cohesion: 0.09
Nodes (32): get_settings(), _canonical(), generate_keypair(), get_server_status(), _headers(), _hub_url(), pull_events(), pull_inbox() (+24 more)

### Community 36 - "analytics.dart"
Cohesion: 0.06
Nodes (33): CostForecast, double fuel, service,, double fuelTotal, serviceTotal, modTotal,, Analytics, basis, confidence, CostForecast, costPerKm (+25 more)

### Community 37 - "server_settings.dart"
Cohesion: 0.06
Nodes (33): build, _busy, createState, _error, _guard, initState, _items, _load (+25 more)

### Community 38 - "add_mod_screen.dart"
Cohesion: 0.06
Nodes (33): AddDiagnosticScreen, _AddDiagnosticScreenState, build, _busy, createState, dispose, initialCodes, initState (+25 more)

### Community 39 - "services/auth.py"
Cohesion: 0.12
Nodes (33): admin_create_user(), login(), mfa_complete_setup(), mfa_disable(), mfa_enable(), mfa_verify(), _prune_revoked_refresh(), AsyncSession (+25 more)

### Community 40 - "car_kit_trip_monitor.dart"
Cohesion: 0.06
Nodes (33): CarKitLinkState get, CarKitLinkState, _closeTrip, commitSeconds, commitSpeedKmh, _commitTrip, dispose, _disposed (+25 more)

### Community 41 - "v1/billing.py"
Cohesion: 0.10
Nodes (34): cancel_subscription(), create_checkout(), customer_portal(), iap_catalog(), iap_verify(), iap_webhook_apple(), iap_webhook_google(), AsyncSession (+26 more)

### Community 42 - "test_services_extraction.py"
Cohesion: 0.11
Nodes (29): bootstrap(), init_db(), Create tables (dev only; prod uses Alembic)., client_ip(), Request, asyncio, _setup(), test_bulk_clear_removes_all_codes() (+21 more)

### Community 43 - "add_vehicle_screen.dart"
Cohesion: 0.06
Nodes (32): AddVehicleScreen, _AddVehicleScreenState, _atLimit, _bodyType, build, _busy, _clubReg, _colour (+24 more)

### Community 44 - "v1/diagnostics.py"
Cohesion: 0.12
Nodes (29): add_to_service(), delete_diagnostic(), diagnose(), list_diagnostics(), AsyncSession, delete, AI diagnostics routes., Mark a diagnostic as resolved once the issue is fixed. (+21 more)

### Community 45 - "issues_blog_screen.dart"
Cohesion: 0.06
Nodes (31): createState, _debounce, _disabled, dispose, _error, _filterBar, _filterChip, initState (+23 more)

### Community 46 - "dart:async"
Cohesion: 0.08
Nodes (25): car_kit_connection_stub.dart, car_kit_trip_monitor.dart, dart:async, dart:html, getCurrentPosition, clearUrlToken, CarKitConnectionSource, create (+17 more)

### Community 47 - "obd_trip_monitor.dart"
Cohesion: 0.07
Nodes (30): ../../core/token_store.dart, arm, armed, _buildRecorder, _defaultApiFactory, _disposed, _instance, _keepAliveOn (+22 more)

### Community 48 - "dongle_provisioning_test.dart"
Cohesion: 0.07
Nodes (26): dart:convert, main, bodies, _FakeApi, main, post, requests, response (+18 more)

### Community 49 - "service.dart"
Cohesion: 0.07
Nodes (29): double get, completedDate, confidence, cost, fromJson, id, isScheduled, items (+21 more)

### Community 50 - "license_screen.dart"
Cohesion: 0.07
Nodes (29): build, _busy, _checkout, createState, _currency, dispose, _error, _fallbackPlans (+21 more)

### Community 51 - "String?"
Cohesion: 0.09
Nodes (22): code, description, fromJson, isResolved, models, ObdCode, source, build (+14 more)

### Community 52 - "dongle_wifi_screen.dart"
Cohesion: 0.07
Nodes (28): _apiUrlForSelfHosted, build, _busy, _config, _createDevice, createState, _devices, dispose (+20 more)

### Community 53 - "edit_vehicle_screen.dart"
Cohesion: 0.07
Nodes (28): _bodyType, build, _busy, _clubReg, _colour, createState, dispose, EditVehicleScreen (+20 more)

### Community 54 - "mods.py"
Cohesion: 0.15
Nodes (24): Demo and free accounts cannot call AI features., require_ai(), create_mod(), delete_mod(), export_build_sheet(), get_impact(), list_mods(), AsyncSession (+16 more)

### Community 55 - "test_config_prod_guard.py"
Cohesion: 0.12
Nodes (24): Settings, _clean_env(), _make(), fixture, MonkeyPatch, AUT-188: DB/MinIO credentials must be required (fail closed), never defaulted., test_missing_creds_fail_closed(), test_partial_creds_fail_closed() (+16 more)

### Community 56 - "issue_detail_screen.dart"
Cohesion: 0.07
Nodes (27): _addComment, build, _commentController, _commenting, _commentTile, _content, createState, _delete (+19 more)

### Community 57 - "rego.py"
Cohesion: 0.11
Nodes (19): _dig(), _first(), lookup_rego(), _map_provider(), _normalise_plate(), Rego (Australian registration plate) lookup — state-aware. Primary path: an…, Fuzzy-match the plate letters against known make/model words., Depth-first search for a key (case-insensitive) in nested JSON. (+11 more)

### Community 58 - "trip.dart"
Cohesion: 0.07
Nodes (26): double lat,, double? startLat, startLng, endLat,, autoSourceLabel, distanceKm, endedAt, endLng, endLocation, endOdometerKm (+18 more)

### Community 59 - "social_post_detail.dart"
Cohesion: 0.08
Nodes (26): _addComment, _askReason, _build, _commentController, _comments, _content, createState, _disabled (+18 more)

### Community 60 - "test_api.py"
Cohesion: 0.11
Nodes (24): _verify_password(), verify_password(), AdminUserUpdate, UserAdminOut, UserCreate, NotificationPreferenceIn, NotificationPreferenceOut, BaseModel (+16 more)

### Community 61 - "v1/obd.py"
Cohesion: 0.18
Nodes (22): add_code(), clear_codes(), delete_code(), list_codes(), obd_settings(), AsyncSession, delete, patch (+14 more)

### Community 62 - "settings_screen.dart"
Cohesion: 0.08
Nodes (25): car_integration_screen.dart, dongle_wifi_screen.dart, _aiEnabled, _beginSetup, _busy, _chip, _code, _countChip (+17 more)

### Community 63 - "api_client.dart"
Cohesion: 0.08
Nodes (25): ApiException, _decode, delete, export, ext, _inflightRefresh, message, mimeForFile (+17 more)

### Community 64 - "config.dart"
Cohesion: 0.08
Nodes (24): apiBase, AppConfig, customBase, _defaultApiBase, _defaultWsBase, hostedApi, hostedWs, isMobile (+16 more)

### Community 65 - "login_screen.dart"
Cohesion: 0.08
Nodes (25): _afterAuth, _busy, _code, _codeNode, createState, _dataUriBytes, dispose, _email (+17 more)

### Community 66 - "dongle_wifi_screen_test.dart"
Cohesion: 0.09
Nodes (23): ApiClient get, ApiClient, _FakeApi, _api, devices, _FailingApi, _FakeApi, _FakeAuthState (+15 more)

### Community 67 - "notify.py"
Cohesion: 0.17
Nodes (18): NotificationDelivery, NotificationPreference, User notification preferences and delivery log., Per-user, per-vehicle notification settings., Tracks which notifications have been sent (dedupe per vehicle + kind)., _check_pref(), check_vehicle_notifications(), deliver_due_service() (+10 more)

### Community 68 - "backup.py"
Cohesion: 0.15
Nodes (24): _backup_order(), _coerce_values(), delete_user_complete(), _delete_user_data(), import_user(), _insert_profile_rows(), _jsonable(), AsyncSession (+16 more)

### Community 69 - "test_workers.py"
Cohesion: 0.10
Nodes (10): Daily full-DB snapshot stored to MinIO. Admin backup safety-net., scheduled_backup(), FakeBucket, FakeDB, FakeManager, FakeReceipt, FakeVehicle, Worker task regression tests (mocked DB/manager, no live services). (+2 more)

### Community 70 - "car_integration_screen.dart"
Cohesion: 0.08
Nodes (24): DateTime? lastTripAt,
  CarKitLinkState, _autoLogging, base, build, carIntegrationStatusLine, carKitLink, _carKitMonitor, createState (+16 more)

### Community 71 - "valuation.dart"
Cohesion: 0.08
Nodes (24): double estimatedValue, low,, double? medianPrice, lowPrice,, factors, fromJson, hasData, high, highPrice, listings (+16 more)

### Community 72 - "dongle_settings.dart"
Cohesion: 0.08
Nodes (23): FlutterSecureStorage, clear, _refreshKey, _roleKey, _secure, _tokenKey, write, _apiKey (+15 more)

### Community 73 - "notifications_screen.dart"
Cohesion: 0.08
Nodes (24): build, createState, _daysCtrl, _discord, dispose, _dueDays, _dueKm, _email (+16 more)

### Community 74 - "car_kit_trip_monitor_test.dart"
Cohesion: 0.08
Nodes (23): ObdTripRecorder, advance, _build, _Clock, _data, m, main, now (+15 more)

### Community 75 - "logbook_screen.dart"
Cohesion: 0.06
Nodes (37): ../../core/download.dart, ../../core/geoloc.dart, ../../core/trip_datetime.dart, ../../core/trip_route.dart, _backup, build, _busy, createState (+29 more)

### Community 76 - "edit_build_screen.dart"
Cohesion: 0.09
Nodes (23): build, bytes, _caption, createState, dispose, EditBuildScreen, _EditBuildScreenState, id (+15 more)

### Community 77 - "test_aut207_token_lifecycle.py"
Cohesion: 0.21
Nodes (22): create_password_reset_token(), create_refresh_token(), Short-lived token that authorises a password reset (30 min)., Long-lived refresh token with a random `jti` (for rotation/revocation). Carries…, A refresh-token jti that has been consumed/rotated and must not be reused., RevokedRefreshToken, _login(), _make_user() (+14 more)

### Community 78 - "bool get"
Cohesion: 0.09
Nodes (21): bool get, category, cost, fromJson, installDate, models, Modification, notes (+13 more)

### Community 79 - "ocr_utils.py"
Cohesion: 0.12
Nodes (16): _fuel_receipt_fallback(), _num(), Deterministic fuel-receipt OCR fallback., Deterministic rule-based engines (one module per domain). These run whenever…, extract_receipt_fallback(), Deterministic receipt OCR fallback., AI module: fuel receipt OCR. Input: PDF text (`content`) or base64 image…, run() (+8 more)

### Community 80 - "vehicle.dart"
Cohesion: 0.09
Nodes (21): bool isPrimary,, byId, clubReg, condition, displayName, dropdownLabel, fromJson, hashCode (+13 more)

### Community 81 - "service_list_screen.dart"
Cohesion: 0.10
Nodes (21): build, count, createState, _delete, _export, icon, initState, _load (+13 more)

### Community 82 - "valuation_screen.dart"
Cohesion: 0.09
Nodes (21): build, controller, createState, data, _estimate, factors, _loading, _loadMarket (+13 more)

### Community 83 - "test_fallbacks.py"
Cohesion: 0.17
Nodes (20): estimate_value_fallback(), _async_identity(), asyncio, Tests for rule-based fallback engines., test_condition_user_override_not_overwritten_by_resale(), test_module_deterministic_model_label(), test_module_router_disabled_uses_fallback(), test_resale_crown_victoria_holds_value() (+12 more)

### Community 84 - "email.py"
Cohesion: 0.20
Nodes (20): create_user(), create_user(), public_signup(), Create a Free-tier account with display name + email only. A setup link is…, create_invite_token(), Long-lived token authorising an invited user to set their password (7 days)., _branding(), _button() (+12 more)

### Community 85 - "test_issues_federation.py"
Cohesion: 0.13
Nodes (19): Community Garage social layer (AUT-294/332)., db_env(), issues_app(), asyncio, fixture, Issues Blog federation regression tests (AUT-756). Guards the cross-instance…, Local-only servers never touch the hub., Inbox items tagged type=issue become origin=remote blog posts. (+11 more)

### Community 86 - "dongle_ble_io.dart"
Cohesion: 0.10
Nodes (19): dongle_ble.dart, dongle_provisioning.dart, _ackMessage, BleImpl, _findDongle, _peripheralHint, provision, _provisionCharUuid (+11 more)

### Community 87 - "package:flutter_test/flutter_test.dart"
Cohesion: 0.10
Nodes (15): main, main, main, main, aug11, dt, main, main (+7 more)

### Community 88 - "export.py"
Cohesion: 0.14
Nodes (19): export_build_sheet_csv(), export_build_sheet_pdf(), export_fuel_csv(), export_logbook_csv(), export_service_history_csv(), export_service_history_pdf(), export_user_profile(), _items_text() (+11 more)

### Community 89 - "fuel_screen.dart"
Cohesion: 0.11
Nodes (18): add_fuel_screen.dart, build, createState, _delete, _efficiencySpots, _export, FuelScreen, _FuelScreenState (+10 more)

### Community 90 - "models.py"
Cohesion: 0.15
Nodes (13): A list-of-strings column: native postgres ARRAY in prod, JSON text elsewhere…, StringArray, Social + federation-hub models (AUT-294 rev 7, AUT-332)., Per-build opt-in share scope (req 11). Default minimal: photos + specs + mods., SocialShareScope, _allowed(), _build_notes(), build_snapshot() (+5 more)

### Community 91 - "test_trip_gps.py"
Cohesion: 0.16
Nodes (17): clean_samples(), parse_board_csv(), BaseModel, Deterministic GPS ingestion for logbook trip routes (AUT-395). The trip-logging…, Drop invalid `0,0` (no-fix) and out-of-range samples, deterministically. Keeps…, Parse a board CSV dump into GPS samples. Accepted schema: `epoch,...,lat,lon` —…, _Sample, _init_schema() (+9 more)

### Community 92 - "service_prediction_screen.dart"
Cohesion: 0.11
Nodes (18): ServicePrediction, build, createState, dispose, _error, label, _lastKm, _loading (+10 more)

### Community 93 - "share_vehicle_screen.dart"
Cohesion: 0.11
Nodes (18): _accepted, build, _busy, createState, dispose, _email, _error, initState (+10 more)

### Community 94 - "ai/app/main.py"
Cohesion: 0.16
Nodes (17): _auth_disabled(), enforce_gateway_rate_limit(), enforce_payload_size(), _gateway_key(), _global_limit(), infer(), InferenceRequest, list_modules() (+9 more)

### Community 95 - "create_device"
Cohesion: 0.16
Nodes (16): create_device(), AsyncSession, Create a dongle device and return its one-time API key. The plaintext key is…, Idempotent batch upload of completed trips from one dongle. The dongle…, upload_trips(), DeviceCreate, DeviceCreated, DeviceOut (+8 more)

### Community 96 - "router_client.py"
Cohesion: 0.18
Nodes (15): get_logger(), BoundLogger, Structured logging for the AI gateway., setup_logging(), health(), lifespan(), FastAPI, _clean_json() (+7 more)

### Community 97 - "test_pt1_xff_bypass.py"
Cohesion: 0.21
Nodes (15): _issue(), _new_comment(), _new_issue(), asyncio, AUT-670 PT1: Issues Blog security remediation regression tests. Covers the…, F1: rotating X-Forwarded-For must NOT reset the per-IP window. Before the fix…, F1: per-user create cap holds even after the per-IP window resets, and is per-…, F2: the comment's own author cannot pin it and force the post resolved unless… (+7 more)

### Community 98 - "test_ws_auth.py"
Cohesion: 0.19
Nodes (12): client(), _FakeUser, fixture, TestClient, Regression tests for AUT-203 S1: WebSocket channel takeover. The /ws/{user_id}…, DB-free stand-in for the async session used by authenticate_ws., _StubDB, test_ws_accepts_own_authed_channel() (+4 more)

### Community 99 - "car_kit_service.dart"
Cohesion: 0.12
Nodes (15): car_kit_connection.dart, CarKitTripMonitor? get, arm, CarKitTripMonitorService, enabledKey, _instance, _monitor, setEnabled (+7 more)

### Community 100 - "add_part_screen.dart"
Cohesion: 0.12
Nodes (16): FormState, AddPartScreen, _AddPartScreenState, build, _busy, _cost, createState, dispose (+8 more)

### Community 101 - "geoloc_io_test.dart"
Cohesion: 0.12
Nodes (15): checkPermission, failFix, _FakeGeo, geo, getCurrentPosition, isLocationServiceEnabled, main, permission (+7 more)

### Community 102 - "diagnose_fallback"
Cohesion: 0.19
Nodes (13): _cost_for(), _diag_item(), diagnose_fallback(), _parts_for(), _parts_with_numbers(), Deterministic diagnostics fallback (symptom + OBD rules)., _sev_rank(), AI module: diagnostics. Input: symptoms text, optional vehicle context and OBD… (+5 more)

### Community 103 - "social_image.py"
Cohesion: 0.18
Nodes (13): _ai_image(), _load_font(), AI module: social post image generation (LinkedIn + Facebook). Deterministic-…, Free Pollinations text-to-image. Returns PNG bytes or None on any failure., Deterministic branded card. Always succeeds, never touches the network., render_card(), run(), _wrap() (+5 more)

### Community 104 - "test_device_api.py"
Cohesion: 0.31
Nodes (14): _init_schema(), asyncio, fixture, AUT-918: dongle device keys + idempotent WiFi trip upload. Covers: device…, Security F1: prefix-colliding keys must still resolve to the right device.…, _setup(), test_create_device_returns_key_and_hashes_it(), test_dongle_upload_gps_samples_are_cleaned_deterministically() (+6 more)

### Community 105 - "app.dart"
Cohesion: 0.13
Nodes (14): community_garage/screens/share_link_view.dart, core/theme.dart, AutoBrainApp, build, initialFragment, licenseRequested, resetTokenFromUrl, shareTokenFromUrl (+6 more)

### Community 106 - "StatelessWidget"
Cohesion: 0.13
Nodes (15): _DisabledView, _ErrorView, _DisabledView, _ErrorView, DownloadAppDialog, _ErrorView, _FeatureGrid, _FeatureTile (+7 more)

### Community 107 - "schemas/logbook.py"
Cohesion: 0.22
Nodes (11): GpsSample, LogEntryCreate, LogEntryDetail, LogEntryOut, LogEntryUpdate, BaseModel, field_validator, Logbook (ATO trip) schemas. (+3 more)

### Community 108 - "FakeClient"
Cohesion: 0.14
Nodes (3): FakeClient, _Obj, _Resp

### Community 109 - "_FakeRedis"
Cohesion: 0.15
Nodes (3): _FakePipeline, _FakeRedis, Minimal in-memory Redis subset used by the login rate limiter (AUT-303).

### Community 110 - "fuel.dart"
Cohesion: 0.14
Nodes (13): double litres, pricePerLitre,, double? lPer100km,, costPerKm, fillDate, fromJson, FuelLog, id, isFullTank (+5 more)

### Community 111 - "social_card.dart"
Cohesion: 0.14
Nodes (13): build, count, icon, _IconStat, _initial, onDelete, onEdit, onShare (+5 more)

### Community 112 - "theme.dart"
Cohesion: 0.14
Nodes (13): accentBlue, AppTheme, _base, bgDark, cardDark, dark, grayText, light (+5 more)

### Community 113 - "trip_datetime.dart"
Cohesion: 0.14
Nodes (13): ampm, date, day, direct, h, m, minute, null (+5 more)

### Community 114 - "run"
Cohesion: 0.19
Nodes (11): _depreciation_multiplier(), _model_market_value(), Deterministic resale-value fallback (AU market anchors + RRP depreciation)., Return (market_anchor, floor_ratio) for a make/model. Falls back to a make-…, Look up a new-car RRP (AUD) for a make/model from the static table., rrp_for(), _f(), AI module: resale value estimation. Input: vehicle attributes, service history,… (+3 more)

### Community 115 - "test_aut206_security_hardening.py"
Cohesion: 0.29
Nodes (12): Request, Machine-to-machine admin access via X-Admin-API-Key header. Disabled unless…, require_admin_api_key(), asyncio, MonkeyPatch, Request, AUT-206: constant-time admin key compare + CORS origin allow-list., _req() (+4 more)

### Community 116 - "backfill_entity_embedding"
Cohesion: 0.15
Nodes (13): backfill_entity_embedding(), _embedding_literal(), AsyncSession, Serialize a float vector as a pgvector array literal (floats only)., Generate and store embedding for a single entity. Returns True on success., Extract fields needed for embedding from a model row., _row_to_dict(), _call_embedding_api() (+5 more)

### Community 117 - "test_aut302_rate_limit.py"
Cohesion: 0.31
Nodes (12): _app(), burst_client(), _client(), daily_client(), FastAPI, fixture, MonkeyPatch, TestClient (+4 more)

### Community 118 - "speed_source_io.dart"
Cohesion: 0.15
Nodes (11): getCurrentPosition, SpeedSource, create, distanceFilterMeters, _GeolocatorSpeedSource, interval, SpeedSourceImpl, _NoopSpeed (+3 more)

### Community 119 - "diagnostic.dart"
Cohesion: 0.15
Nodes (12): addedToService, Diagnostic, estimatedCost, fromJson, isResolved, linkedServiceId, models, severity (+4 more)

### Community 120 - "tests/test_auth.py"
Cohesion: 0.17
Nodes (5): _env(), fixture, parametrize, Regression tests for fail-closed gateway auth (AUT-199). Before:…, test_dev_optout_opens_gateway()

### Community 121 - "check_verify_rate_limit"
Cohesion: 0.50
Nodes (4): check_verify_rate_limit(), Raise HTTPException 429 when the user exceeds the verify window., test_check_verify_rate_limit_429(), test_check_verify_rate_limit_windows_are_per_user()

### Community 122 - "test_assets_backup.py"
Cohesion: 0.29
Nodes (10): export_assets(), MinIO object backup/restore (admin only). Exports every object in the…, Tar.gz every object in MINIO_BUCKET; returns the archive bytes., Return the member names if raw is a readable tar.gz; else raise ValueError., Wipe the bucket then upload every member of a validated archive., restore_assets(), validate_assets(), Self-check for MinIO assets backup/restore (no external services). Run: cd… (+2 more)

### Community 123 - "test_search_sql_injection.py"
Cohesion: 0.26
Nodes (11): Cosine-distance expression (`a <=> b`) with the vector bound as a parameter., _vector_similarity(), Validate router embedding output: a non-empty list of numbers only, whose…, _valid_embedding(), Regression tests for AUT-203 S3: embedding values are bound, never interpolated…, A correctly-sized embedding (matches EMBEDDING_DIMENSION)., test_valid_embedding_accepts_numbers_only(), test_valid_embedding_rejects_wrong_dimension() (+3 more)

### Community 124 - "test_logbook_club_reg.py"
Cohesion: 0.32
Nodes (11): _init_schema(), asyncio, fixture, AUT-177 / PR-1: digital logbook is disabled for club-registered vehicles.…, AUT-367 phone path: car_auto source + GPS odometer diff distance., _setup(), test_car_auto_source_with_gps_distance_round_trips(), test_club_reg_logbook_is_disabled() (+3 more)

### Community 125 - "test_share_access.py"
Cohesion: 0.39
Nodes (11): _accept(), _create_user(), asyncio, AUT-21: shared-vehicle access, list tagging, and owner-based feature gating.…, test_free_invitee_inherits_owners_rego_entitlement(), test_free_owner_blocks_invitee_ai_and_rego(), test_invite_accept_deny_and_remove_flow(), test_invitee_can_read_but_not_manage_shared_vehicle() (+3 more)

### Community 126 - "dongle_provisioning.dart"
Cohesion: 0.17
Nodes (11): appendProvisionToken, buildProvisioningPayload, d, _escape, k, null, p, s (+3 more)

### Community 127 - "enhance"
Cohesion: 0.27
Nodes (10): enhance(), _matches_type(), True when value's type is one of the allowed types (None handled explicitly)., Deterministic baseline, optionally enriched by 9Router. The rule engine runs…, asyncio, Tests for per-module router response schema validation (AUT-141)., test_enhance_drops_junk_and_typed_keys(), test_enhance_immutable_never_overridden() (+2 more)

### Community 128 - "semantic_search"
Cohesion: 0.20
Nodes (11): _accessible_vehicle_ids(), AsyncSession, Vehicle IDs the user owns or has an accepted share on., Hybrid search across diagnostics, services, modifications, receipts, and…, search(), Convert a model row to a search result dict., Search across entities using hybrid keyword + vector similarity. Scoped to…, semantic_search() (+3 more)

### Community 129 - "offline_cache.dart"
Cohesion: 0.18
Nodes (10): Database?, clear, _db, instance, OfflineCache, _open, put, package:path/path.dart (+2 more)

### Community 130 - "share_scope_picker.dart"
Cohesion: 0.18
Nodes (10): allowMods, allowNotes, allowOdometer, allowPhotos, allowSpecs, build, onChanged, scope (+2 more)

### Community 131 - "manifest.json"
Cohesion: 0.18
Nodes (10): background_color, description, display, icons, name, orientation, prefer_related_applications, short_name (+2 more)

### Community 132 - "social/rate_limit.py"
Cohesion: 0.22
Nodes (7): Social write routes: premium + not demo + not social-banned. Banned users are…, require_premium_write(), Per-client social route rate limiting (MB-1/MB-2, AUT-462). In-process sliding…, Dependency factory: enforce `limit` requests per 60s window per client IP., _SlidingWindow, social_rate_limit(), social_user_rate_limit()

### Community 133 - "share_scope_picker_test.dart"
Cohesion: 0.22
Nodes (9): CheckboxListTile, ShareScopeState, build, createState, _Host, _HostState, main, scope (+1 more)

### Community 134 - "download_io.dart"
Cohesion: 0.20
Nodes (9): dart:io, dir, downloadBytes, file, readLocalFile, shareXFiles, writeAsBytes, package:path_provider/path_provider.dart (+1 more)

### Community 135 - "receipt.dart"
Cohesion: 0.20
Nodes (9): double?, fromJson, id, models, ocrStatus, Receipt, total, vendor (+1 more)

### Community 136 - "timeline.dart"
Cohesion: 0.20
Nodes (9): amount, fromJson, models, occurredOn, odometerKm, TimelineEvent, title, int? (+1 more)

### Community 137 - "trip_route.dart"
Cohesion: 0.20
Nodes (9): _downsample, googleMapsMaxPathPoints, googleMapsRouteUrl, hasRoute, out, path, pts, validRoute (+1 more)

### Community 138 - "test-ci-fixes.sh"
Cohesion: 0.29
Nodes (9): extract(), fail(), gate(), GH_ERR, GH_FAILS, MAX_PUSH_FAILS, pass(), PATH (+1 more)

### Community 139 - "estimate_condition"
Cohesion: 0.22
Nodes (7): estimate_condition(), Deterministic vehicle-condition estimator. Condition is inferred from *data the…, AI module: vehicle-condition estimate. Input: vehicle context, diagnostics,…, run(), test_condition_bike_km_scale_differs(), test_condition_clean_well_serviced(), test_condition_open_critical_issue_poor()

### Community 140 - "_odometer_fallback"
Cohesion: 0.25
Nodes (7): _odometer_fallback(), Deterministic odometer-reading fallback (regex over OCR text)., Scan OCR text for a plausible odometer reading (6-7 digit number)., _clamp(), AI module: odometer reading from a dashboard photo. Input: base64 image…, run(), test_odometer_fallback()

### Community 141 - "db_env"
Cohesion: 0.22
Nodes (8): db_env(), env(), fixture, db_env(), env(), fixture, env(), fixture

### Community 142 - "test_admin_delete_build_purges_related_rows"
Cohesion: 0.33
Nodes (9): _new_build(), _new_comment(), asyncio, AUT-883: a build and each of its comments are flaggable once per user., AUT-883: build + comment flags surface in the review hub with target="build";…, AUT-883: admin build delete cascades comments, likes and flags., test_admin_delete_build_purges_related_rows(), test_build_flags_in_admin_review_and_delete() (+1 more)

### Community 143 - "trip_route_map.dart"
Cohesion: 0.22
Nodes (8): Color, build, color, _EndpointBadge, icon, route, TripRouteMap, package:flutter_map/flutter_map.dart

### Community 144 - "premium_gate.dart"
Cohesion: 0.22
Nodes (8): build, icon, label, LockedAction, lockedReason, PremiumGate, IconData, screens/settings/license_screen.dart

### Community 145 - "mod_impact_fallback"
Cohesion: 0.25
Nodes (6): mod_impact_fallback(), Deterministic modification-impact fallback., _mod_value_impact(), AI module: modification impact. Input: mod name, category, vehicle context,…, run(), test_mod_impact()

### Community 146 - "env.py"
Cohesion: 0.32
Nodes (5): do_run_migrations(), Alembic async environment. Overrides sqlalchemy.url from app settings., run_async_migrations(), run_migrations_online(), Connection

### Community 147 - "authenticate_ws"
Cohesion: 0.29
Nodes (8): authenticate_ws(), _extract_ws_token(), WebSocket, Pull a bearer token from the handshake: query param or Authorization header.…, Authenticate a WebSocket handshake. Returns the User, or None to reject. Fail…, AsyncSession, websocket, websocket_endpoint()

### Community 148 - "timedelta"
Cohesion: 0.39
Nodes (7): create_mfa_token(), Short-lived token granting a login in progress (MFA step only)., main(), upsert_coupon(), upsert_price(), upsert_promo(), timedelta

### Community 149 - "test_pdf_dos_regression.py"
Cohesion: 0.39
Nodes (7): _pdf_text(), Extract text from a PDF for downstream OCR/AI extraction., _build_pdf(), Regression guard for AUT-471: crafted-PDF DoS against the receipt worker.…, Hand-built 7-object PDF: page -> Type0 font (-> CID font -> optional…, test_large_to_unicode_stream_rejected_fast(), test_oversized_cid_width_range_rejected_fast()

### Community 150 - "asyncio"
Cohesion: 0.36
Nodes (8): asyncio, _seed(), test_my_posts_excludes_unpublished(), test_my_posts_returns_only_callers_builds(), test_update_caption_clears_to_null(), test_update_caption_non_owner_404(), test_update_caption_owner_ok(), test_update_missing_post_404()

### Community 151 - "dongle_ble.dart"
Cohesion: 0.25
Nodes (7): dongle_ble_stub.dart, DongleBle, DongleBleException, message, provision, supported, toString

### Community 152 - "market-data/test_auth.py"
Cohesion: 0.39
Nodes (6): Regression tests for /search constant-time auth + rate limiting (AUT-782). Run:…, _search(), test_auth_uses_constant_time_compare(), test_missing_key_rejected(), test_per_ip_limit(), test_per_key_limit()

### Community 153 - "predict_service_fallback"
Cohesion: 0.29
Nodes (5): predict_service_fallback(), Deterministic service-schedule fallback (manufacturer intervals)., AI module: service prediction. Input: make/model/year, current odometer, last…, run(), test_service_prediction_oil()

### Community 155 - "u1v2w3x4y5z6_add_issue_blog_tables.py"
Cohesion: 0.57
Nodes (5): _has_column(), _has_index(), _has_table(), _online(), upgrade()

### Community 156 - "v1w2x3y4z5a6_add_comment_flags_social_ban.py"
Cohesion: 0.71
Nodes (6): downgrade(), _has_column(), _has_index(), _has_table(), _online(), upgrade()

### Community 157 - "dump_backup"
Cohesion: 0.29
Nodes (7): download_backup(), Response, Full database snapshot (JSON) for machine-to-machine off-box retention., export_profile(), Response, Export the whole account (user + vehicles + all records) as JSON., dump_backup()

### Community 158 - "test_restore_roundtrip_keeps_shares"
Cohesion: 0.29
Nodes (7): UploadFile, Wipe MINIO_BUCKET and restore its objects from an uploaded tar.gz. DANGEROUS., Wipe and restore the whole database from an uploaded backup. DANGEROUS., restore_assets_endpoint(), restore_backup(), load_backup(), test_restore_roundtrip_keeps_shares()

### Community 159 - "_externalize_url"
Cohesion: 0.33
Nodes (6): _externalize_url(), Swap the internal MinIO host for the externally reachable public endpoint. The…, Self-check for MinIO object URLs — private bucket (AUT-321). Run: cd backend &&…, test_externalize_url_ignores_unrelated_host(), test_externalize_url_swaps_internal_host(), test_upload_object_returns_presigned_url()

### Community 160 - "device_keys.py"
Cohesion: 0.33
Nodes (6): generate_key(), hash_key(), Dongle device API keys — deterministic, no AI (AUT-918). Keys are opaque…, Return a fresh opaque device API key, e.g. `abdev_<64 hex chars>`., Constant-time comparison of the supplied key against a stored digest., verify_key()

### Community 162 - "obd_keepalive.dart"
Cohesion: 0.29
Nodes (6): ensureRunning, ObdKeepAlive, stop, supported, update, obd_keepalive_stub.dart

### Community 163 - "obd_keepalive_stub.dart"
Cohesion: 0.29
Nodes (6): ensureRunning, KeepAliveImpl, stop, supported, update, static const bool

### Community 164 - "test_rate_limit.py"
Cohesion: 0.33
Nodes (3): _env(), fixture, AUT-302: AI gateway rate limiting (defense in depth). Regression: N+1…

### Community 165 - "a1b2c3d4e5f7_add_social_issue_photos.py"
Cohesion: 0.73
Nodes (5): downgrade(), _has_column(), _has_index(), _online(), upgrade()

### Community 166 - "a6b5c4d3e2f1_add_social_photo_comment.py"
Cohesion: 0.80
Nodes (5): downgrade(), _has_column(), _has_index(), _online(), upgrade()

### Community 167 - "a6b5c4d3e2f2_add_issue_federation_columns.py"
Cohesion: 0.73
Nodes (5): downgrade(), _has_column(), _has_index(), _online(), upgrade()

### Community 168 - "n4p5q6r7s8t9_add_social_tables.py"
Cohesion: 0.60
Nodes (4): _has_index(), _has_table(), _online(), upgrade()

### Community 169 - "p6q7r8s9t0u1_add_social_event_cursor.py"
Cohesion: 0.60
Nodes (4): _has_column(), _is_nullable(), _online(), upgrade()

### Community 170 - "w5x6y7z8a9b0_add_build_flags.py"
Cohesion: 0.67
Nodes (5): downgrade(), _has_index(), _has_table(), _online(), upgrade()

### Community 171 - "schemas/receipt.py"
Cohesion: 0.47
Nodes (5): ApplyToServiceRequest, ExtractionResult, BaseModel, Receipt and OCR schemas., ReceiptOut

### Community 172 - "_FlakySession"
Cohesion: 0.33
Nodes (3): _FlakySession, AsyncSession, Delegates to a real session but fails the first execute with a transient…

### Community 173 - "test_deps_transitive_cves.py"
Cohesion: 0.47
Nodes (5): _pins(), Path, Regression guard for AUT-794: transitive CVE pins (starlette, ecdsa). The…, test_fastapi_and_starlette_above_cve_fixes(), test_pyjwt_replaces_python_jose_and_ecdsa()

### Community 174 - "a1b2c3d4e5f6_add_devices.py"
Cohesion: 0.90
Nodes (4): downgrade(), _has_table(), _online(), upgrade()

### Community 175 - "q1r2s3t4u5v6_add_social_photo_position.py"
Cohesion: 0.70
Nodes (4): downgrade(), _has_column(), _online(), upgrade()

### Community 176 - "x1y2z3a4b5c6_add_remote_tombstones.py"
Cohesion: 0.70
Nodes (4): downgrade(), _has_table(), _online(), upgrade()

### Community 177 - "download_assets"
Cohesion: 0.50
Nodes (5): download_assets(), _file_chunks(), Path, Tar.gz of every object in MINIO_BUCKET for off-box image retention., StreamingResponse

### Community 178 - "test_deps_pypdf_pin.py"
Cohesion: 0.50
Nodes (4): Path, _pypdf_pin(), Regression guard for AUT-301: pypdf pin must stay on the CVE-2026-71852/71870…, test_pypdf_pinned_above_cve_fix()

### Community 179 - "test_register_reuses_stored_server_key"
Cohesion: 0.50
Nodes (4): public_key_from_private(), Derive the public key hex from a stored private key (AUT-758)., AUT-758: the server keypair is generated once and persisted; re-registering…, test_register_reuses_stored_server_key()

### Community 180 - "test_alembic_heads.py"
Cohesion: 0.67
Nodes (3): _heads(), Alembic migration-graph regression guard (AUT-702). Asserts the migration chain…, test_alembic_single_head()

### Community 181 - "speed_source.dart"
Cohesion: 0.50
Nodes (3): create, SpeedSourceFactory, speed_source_stub.dart

### Community 204 - "import_profile"
Cohesion: 0.67
Nodes (3): import_profile(), UploadFile, Restore an exported profile onto the logged-in account. Wipes the current…

### Community 205 - "_reject_oversized_content_length"
Cohesion: 0.67
Nodes (3): Request, Return 413 on a declared Content-Length past the cap before any body read. Must…, _reject_oversized_content_length()

### Community 206 - "CarKitTripMonitor"
Cohesion: 0.67
Nodes (3): ChangeNotifier, CarKitTripMonitor, ObdTripMonitor

## Knowledge Gaps
- **1342 isolated node(s):** `createState`, `initState`, `_items`, `_loading`, `_severityColor` (+1337 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **29 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `User` to `Base`, `semantic_search`, `seed.py`, `social/rate_limit.py`, `issues.py`, `social.py`, `tasks.py`, `_post`, `get_accessible_vehicle`, `test_iap.py`, `test_social.py`, `test_social_regression.py`, `config.py`, `authenticate_ws`, `iap.py`, `FuelLog`, `dump_backup`, `test_issues_blog.py`, `services/billing.py`, `v1/auth.py`, `test_billing.py`, `_user`, `services/auth.py`, `v1/billing.py`, `test_services_extraction.py`, `v1/diagnostics.py`, `mods.py`, `test_api.py`, `v1/obd.py`, `notify.py`, `import_profile`, `test_aut207_token_lifecycle.py`, `require_premium`, `email.py`, `test_trip_gps.py`, `create_device`, `test_device_api.py`, `test_aut302_rate_limit.py`, `test_logbook_club_reg.py`, `test_share_access.py`?**
  _High betweenness centrality (0.088) - this node is a cross-community bridge._
- **Why does `AuthState` connect `AuthState` to `package:flutter/material.dart`, `package:provider/provider.dart`, `State`, `social_compose.dart`, `add_fuel_screen.dart`, `community_garage_share_test.dart`, `home_screen.dart`, `service_form_screen.dart`, `core/auth_state.dart`, `auth_state.dart`, `analytics.dart`, `server_settings.dart`, `add_mod_screen.dart`, `add_vehicle_screen.dart`, `issues_blog_screen.dart`, `license_screen.dart`, `String?`, `dongle_wifi_screen.dart`, `edit_vehicle_screen.dart`, `issue_detail_screen.dart`, `social_post_detail.dart`, `settings_screen.dart`, `login_screen.dart`, `dongle_wifi_screen_test.dart`, `notifications_screen.dart`, `logbook_screen.dart`, `edit_build_screen.dart`, `CarKitTripMonitor`, `service_list_screen.dart`, `valuation_screen.dart`, `fuel_screen.dart`, `service_prediction_screen.dart`, `share_vehicle_screen.dart`, `add_part_screen.dart`, `app.dart`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Why does `_post()` connect `_post` to `Base`, `seed.py`, `User`, `tasks.py`, `issues.py`, `social.py`, `get_accessible_vehicle`, `test_social_regression.py`, `bikesguide.py`, `FuelLog`, `test_restore_roundtrip_keeps_shares`, `v1/auth.py`, `SocialServerConfig`, `services/auth.py`, `v1/billing.py`, `v1/diagnostics.py`, `mods.py`, `v1/obd.py`, `import_profile`, `email.py`, `ai/app/main.py`, `create_device`?**
  _High betweenness centrality (0.013) - this node is a cross-community bridge._
- **Are the 219 inferred relationships involving `User` (e.g. with `authenticate_ws()` and `get_current_user()`) actually correct?**
  _`User` has 219 INFERRED edges - model-reasoned connections that need verification._
- **Are the 59 inferred relationships involving `Vehicle` (e.g. with `me()` and `upload_trips()`) actually correct?**
  _`Vehicle` has 59 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `get_accessible_vehicle()` (e.g. with `VehicleShare` and `User`) actually correct?**
  _`get_accessible_vehicle()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `createState`, `initState`, `_items` to the rest of the system?**
  _1342 weakly-connected nodes found - possible documentation gaps or missing edges._