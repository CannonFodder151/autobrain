# Screenshots

App Store Connect requires screenshots for every device class. The deliver
lane reads PNG files at runtime; source artwork lives in `sources/` and is
reframed at upload time.

```
screenshots/
├── sources/                 # Master artwork (PNG, 1242x2688 or larger)
│   ├── en-US-01-dashboard.png
│   ├── en-US-02-trips.png
│   └── ...
└── <locale>/<device>/       # Output delivered to App Store Connect
    ├── 6.5-inch Display/
    │   ├── 01_dashboard.png
    │   └── ...
    └── 12.9-inch iPad Pro/
        └── ...
```

The `screenshots` lane invokes `frame_screenshots` to scale `sources/` into
the per-device folders before upload. Empty `sources/` will fail the lane
because App Store Connect requires at least three valid images per device.
