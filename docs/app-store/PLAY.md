# AutoBrain Android — Google Play Submission Pack (AUT-160)

## App metadata
- **App name**: AutoBrain
- **Short description** (80 chars): Vehicle health & track readiness in one place.
- **Package name**: com.autobrainservice.app
- **Category**: Auto & Vehicles / Tools
- **Price**: Free
- **Content rating**: Everyone (IARC) — no user-generated content, no ads
- **Privacy policy URL**: https://paperclip2.nathanmartina.com/privacy (publish docs/app-store/PRIVACY.md)

## Full description (4000 chars max)
AutoBrain helps vehicle owners stay on top of their cars: health score, fuel price map and watchlist, service intervals and history, modifications log, ownership advisor, and track-day prep.

Features:
- Vehicle health score and readiness tracking
- Fuel price map and watchlist
- Service intervals and history
- Track mode with session live view, driver stats, prep checklist
- Ownership advisor and modifications log

All data stored locally on your device. No ads, no trackers.

## Screenshots (Google Play)
Phone (1080×1920 or 1440×2560, min 2, max 8):
1. Home / health score → docs/app-store/screenshots/1-home-health-score.png (placeholder)
2. Fuel price map → docs/app-store/screenshots/2-fuel-price-map.png (placeholder)
3. Track mode live session → docs/app-store/screenshots/3-track-mode-live.png (placeholder)
4. Service intervals → docs/app-store/screenshots/4-service-intervals.png (placeholder)
5. Ownership advisor → docs/app-store/screenshots/5-ownership-advisor.png (placeholder)

7" tablet (1024×600) and 10" tablet (1280×800): same 5 screens (optional).

Feature graphic: 1024×500 PNG (no alpha) → docs/app-store/feature-graphic-1024x500.png
App icon: 512×512 PNG (no alpha) → docs/app-store/app-icon-512.png

NOTE: screenshots are placeholders. Replace with real captures from the app before production (run app on emulator + capture). Icon + feature graphic are final.

## Promoted release flow
- Closed testing track `alpha` already has testers; pipeline uploads `.aab` there automatically (scripts/play-upload-closed-testing.sh).
- Promote `alpha` → production: run `scripts/play-promote-to-production.sh [versionCode]` in the autobrain-mobile repo. It adds the versionCode to the production track with status=completed and commits the edit (submitting for review/rollout).
- Never upload directly to production from CI; always promote an existing closed-testing release.

## Checklist
- [x] App icon 512×512 (no alpha)
- [x] Feature graphic 1024×500
- [ ] Screenshots captured for phone + tablet sizes (placeholders in place; replace with real captures)
- [x] Privacy policy published at https://paperclip2.nathanmartina.com/privacy (backend /privacy route serves docs/app-store/PRIVACY.md)
- [ ] Content rating questionnaire completed
- [ ] Store listing draft saved
- [x] Closed-testing → production promotion script ready (scripts/play-promote-to-production.sh)
