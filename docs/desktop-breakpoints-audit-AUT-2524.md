# Desktop Breakpoints Audit — AUT-2524

**Scope:** `CannonFodder151/autobrain` frontend (`frontend/lib/`)  
**Branch:** `audit/aut-2524-desktop-breakpoints`  
**Desktop breakpoint:** ≥ 1024px  
**Screenshot widths requested:** 1280, 1440, 1920  
**Screenshot status:** ⚠️ Flutter SDK + browser not available in this environment; visual capture deferred. Findings below are from a full source-code audit of all 56 Dart files in `lib/screens/`, `lib/widgets/`, and `lib/core/`.

---

## Key Finding

**Zero** files in the frontend contain `MediaQuery.of(context).size.width`, `LayoutBuilder`, responsive breakpoint logic, or `AdaptiveScaffold` / `NavigationRail`. Every screen is built to mobile dimensions and simply stretches or centers on desktop.

`lib/screens/parts/sca_lookup_results_screen.dart:224` has the **only** `MediaQuery` call in the entire 56-file codebase — used inside a bottom-sheet height calculation. No other screen adapts at all.

---

## Detailed Findings (sorted by file path)

### 🔴 HIGH — Must fix for desktop usability

| # | File | Line | Widget / Widget Tree | Hardcoded Value | Problem on ≥1024px | Recommended Fix |
|---|------|------|---------------------|-----------------|--------------------|-----------------|
| 1 | `lib/screens/home/home_screen.dart` | 359 | `GridView.count` | `crossAxisCount: 3` | 3-column grid on 1920px wastes ~80% of horizontal space; 14 feature tiles each become ~600px wide | `crossAxisCount: max(3, (constraints.maxWidth / 160).floor())` — at 1024px→6 cols, 1366px→8 cols, 1920px→12 cols |
| 2 | `lib/screens/fuel/petrol_price_map_screen.dart` | 392–393 | `_CallSheet` body | `SizedBox(height: 460)` | Inside a `showModalBottomSheet(isScrollControlled: true)`, a fixed 460px height wrapping an `Expanded > ListView` is contradictory. On desktop the sheet either clips long station fuel lists or leaves excessive empty space. | Remove the fixed height. Let the modal expand naturally. If a max height is needed, wrap in `LayoutBuilder` and use `constraints.maxHeight * 0.85` |
| 3 | `lib/screens/fuel/petrol_price_map_screen.dart` | 393 | `_CallSheet` → `Expanded` → `ListView` | `Expanded` inside fixed `SizedBox` | Conflicts with #2 — `Expanded` needs infinite space, `SizedBox(height: 460)` provides bounded space. | See #2 — remove the bounding `SizedBox`. |

---

### 🟡 MEDIUM — Should fix for polished desktop

| # | File | Line | Widget / Widget Tree | Hardcoded Value | Problem on ≥1024px | Recommended Fix |
|---|------|------|---------------------|-----------------|--------------------|-----------------|
| 4 | `lib/screens/auth/login_screen.dart` | 222 | `Text` brand title | `fontSize: 30` | 30px heading in an unbounded card looks like a subheading on 1920px | Constrain the card to `maxWidth: 420` or scale to `min(30, MediaQuery.of(context).size.width * 0.06)` |
| 5 | `lib/screens/auth/login_screen.dart` | 237 | `Container` form card | `width: double.infinity` | Inside `Center > SingleChildScrollView`, `double.infinity` resolves to full viewport width — card spans 1920px | Add `constraints: BoxConstraints(maxWidth: 420)` to the Container |
| 6 | `lib/screens/auth/login_screen.dart` | 261–262 | `Image.memory` QR code | `width: 200, height: 200` | 200px QR code in a full-width card is small on 1080p+ | Use `BoxConstraints(maxWidth: 200, maxHeight: 200)` inside a `Center`, or scale to `MediaQuery.of(context).size.width * 0.2` |
| 7 | `lib/screens/auth/signup_screen.dart` | 112 | `Text` page title | `fontSize: 26` | 26px heading in a full-width card is undersized on 1920px | Constrain the card to `maxWidth: 420` |
| 8 | `lib/screens/auth/signup_screen.dart` | 123 | `Container` form card | `width: double.infinity` | Same as #5 — card spans full viewport on desktop | Add `constraints: BoxConstraints(maxWidth: 420)` |
| 9 | `lib/screens/auth/server_setup_screen.dart` | 108 | `Text` page title | `fontSize: 26` | Same as #7 — undersized on desktop | Constrain the card to `maxWidth: 420` |
| 10 | `lib/screens/auth/server_setup_screen.dart` | 119 | `Container` form card | `width: double.infinity` | Same as #5 — card spans full viewport on desktop | Add `constraints: BoxConstraints(maxWidth: 420)` |
| 11 | `lib/screens/settings/license_screen.dart` | 496 | `Text` plan price | `fontSize: 32` | Highest font size in codebase; inside a ListView card that stretches full-width, looks undersized on 1920px | Constrain the plan card to `SizedBox(width: min(380, MediaQuery.of(context).size.width * 0.9))` |
| 12 | `lib/screens/settings/license_screen.dart` | 555 | `SizedBox` CTA button | `width: double.infinity` | Button fills stretched card on desktop — becomes excessively wide | Constrain the parent plan card, not just the button |
| 13 | `lib/screens/settings/settings_screen.dart` | 253–254 | `Image.memory` MFA QR code | `width: 180, height: 180` | 180px QR code in a full-width card is small on 1080p+ | Use `BoxConstraints(maxWidth: 200, maxHeight: 200)` and constrain the card to `maxWidth: 420` |
| 14 | `lib/screens/settings/car_integration_screen.dart` | 129, 144, 171 | `Text` section headers | `fontSize: 16` | 16px section headers on a 1080p+ desktop read as body text, not headings | Replace with `Theme.of(context).textTheme.titleMedium` (already used for some headings; make consistent) |
| 15 | `lib/screens/fuel/fuel_screen.dart` | 166 | `SizedBox` chart container | `height: 180` | 180px line chart in a ListView is visually dwarfed on 1080p+ | Use `LayoutBuilder`: `height: min(280, constraints.maxHeight * 0.25)` |
| 16 | `lib/screens/services/service_form_screen.dart` | 416 | `SizedBox` qty field | `width: 70` | 70px text field on a 1920px desktop is tiny and hard to interact with | Replace with `Expanded(flex: 2, child: ...)` or `Flexible` |
| 17 | `lib/screens/services/service_form_screen.dart` | 425 | `SizedBox` cost field | `width: 90` | Same — 90px is tiny on desktop | Replace with `Expanded(flex: 3, child: ...)` or `Flexible` |
| 18 | `lib/screens/services/service_form_screen.dart` | 475 | `SizedBox` qty field (custom editor) | `width: 70` | Same as #16 | Replace with `Expanded(flex: 2, child: ...)` |

---

### 🟢 LOW — Cosmetic / minor

| # | File | Line | Widget | Hardcoded Value | Problem | Recommended Fix |
|---|------|------|--------|-----------------|---------|-----------------|
| 19 | `lib/screens/admin/admin_screen.dart` | 496 | `Container` version banner | `width: double.infinity` | Inside a `Column` (not scrollable), fills full viewport width on desktop | Wrap in `Padding(horizontal: 16)` or constrain with `BoxConstraints(maxWidth: 900)` |
| 20 | `lib/screens/servo_spy/servo_spy_screen.dart` | 407 | `Container` location-denied banner | `width: double.infinity` | Same — fills full viewport width on desktop | Add `EdgeInsets.symmetric(horizontal: 16)` padding |
| 21 | `lib/screens/servo_spy/servo_spy_screen.dart` | 744 | `SizedBox` Navigate button in `_StationSheet` | `width: double.infinity` | Inside a bottom sheet, stretches full width | Constrain parent content to `maxWidth: 400` |
| 22 | `lib/screens/fuel/petrol_price_map_screen.dart` | 744 | `SizedBox` Navigate button in `_CallSheet` | `width: double.infinity` | Same | Constrain parent content to `maxWidth: 400` |
| 23 | `lib/screens/auth/login_screen.dart` | 261 | `Image.memory` QR code | `width: 200, height: 200` | Minor — acceptable on desktop | Use `BoxConstraints(maxWidth: 200, maxHeight: 200)` to keep aspect ratio safe |
| 24 | `lib/widgets/trip_route_map.dart` | 29 | `Padding` camera padding | `EdgeInsets.all(32)` | 32px padding around route map is slightly generous on large displays | Reduce to `EdgeInsets.all(16)` on desktop via `LayoutBuilder` |

---

## Screenshot Gap

⚠️ Visual screenshots at 1280, 1440, 1920 widths **cannot be captured** in this environment — Flutter SDK and a headless browser are not installed. The code audit above covers all identified issues. A follow-up ticket should:
1. Install Flutter SDK on a CI runner or dev box
2. Build the web app (`flutter build web`)
3. Serve and capture screenshots at the three desktop widths
4. Verify that the issues listed above manifest visually and discover any additional layout bugs not visible in code review

---

## Recommended Fix Pattern

Create a shared `Breakpoints` helper:

```dart
// lib/core/breakpoints.dart
import 'package:flutter/widgets.dart';

class Breakpoints {
  static const desktop = 1024.0;
  static const tablet = 768.0;

  static bool isDesktop(BuildContext context) =>
      MediaQuery.of(context).size.width >= desktop;

  static bool isTablet(BuildContext context) =>
      MediaQuery.of(context).size.width >= tablet;

  static int gridColumns(BuildContext context, {int minTileWidth = 160}) {
    final width = MediaQuery.of(context).size.width;
    if (width < tablet) return 2;
    return (width / minTileWidth).floor().clamp(3, 8);
  }

  static double scaled(double value, BuildContext context, {double minScale = 1.0}) {
    final width = MediaQuery.of(context).size.width;
    if (width < desktop) return value;
    return value * minScale + (width - desktop) / desktop * 10;
  }
}
```

Then per-screen application:
- **Home feature grid** (`home_screen.dart:359`): `crossAxisCount: Breakpoints.gridColumns(context)`
- **Auth screens** (`login_screen.dart:237`, `signup_screen.dart:123`, `server_setup_screen.dart:119`): Add `constraints: BoxConstraints(maxWidth: 420)` to the form card Container
- **Fuel chart** (`fuel_screen.dart:166`): `height: Breakpoints.isDesktop(context) ? 280 : 180`
- **CallSheet** (`petrol_price_map_screen.dart:392`): Remove fixed `height: 460`, use natural height
- **Service form** (`service_form_screen.dart:416,425,475`): Replace `SizedBox(width: 70/90)` with `Expanded(flex: N)`
- **License screen** (`license_screen.dart:496,555`): Constrain plan card width, scale font on desktop
- **Settings MFA** (`settings_screen.dart:253`): Constrain card width to 420px

---

## Files With No Issues Found

These files have clean layouts for desktop and need no changes:

- `lib/screens/auth/reset_password.dart`
- `lib/screens/diagnostics/add_diagnostic_screen.dart`
- `lib/screens/diagnostics/diagnostics_screen.dart`
- `lib/screens/fuel/add_fuel_screen.dart`
- `lib/screens/home/home_screen.dart` (grid only)
- `lib/screens/logbook/logbook_screen.dart`
- `lib/screens/mods/add_mod_screen.dart`
- `lib/screens/mods/mods_screen.dart`
- `lib/screens/notifications/notifications_screen.dart`
- `lib/screens/parts/add_part_screen.dart`
- `lib/screens/parts/parts_screen.dart`
- `lib/screens/parts/sca_lookup_results_screen.dart`
- `lib/screens/receipts/receipts_screen.dart`
- `lib/screens/servo_spy/servo_spy_list_model.dart`
- `lib/screens/services/service_list_screen.dart`
- `lib/screens/services/service_prediction_screen.dart`
- `lib/screens/valuation/valuation_screen.dart`
- `lib/screens/analytics/analytics_screen.dart`
- `lib/screens/obd/obd_screen.dart`
- `lib/screens/vehicles/*_screen.dart`
- `lib/widgets/vehicle_selector.dart`
- `lib/widgets/rego_status_badge.dart`
- `lib/core/*.dart`
