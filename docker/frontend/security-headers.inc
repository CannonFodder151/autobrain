# Security headers for every frontend response (AUT-234/236).
# CSP is tuned for the Flutter web build: 'wasm-unsafe-eval' is required by
# the CanvasKit/skwasm renderer (wasm compilation is checked against
# script-src in Chrome), and 'self' covers the same-origin /api, /ws and /ai
# proxies plus wss. https://www.gstatic.com is allowlisted (AUT-339) so the
# CanvasKit engine bundle (canvaskit.js + canvaskit.wasm) can load from
# Google's CDN; without it the app renders a blank page. https://fonts.gstatic.com
# is allowlisted (AUT-347) so CanvasKit can fetch the default Roboto/Noto fonts
# at startup; blocking it also blanks the first frame. Google Fonts CSS lives on
# fonts.googleapis.com, which is NOT used by the Flutter bundle and stays blocked.
# blob: is allowlisted in img-src + connect-src (AUT-756): image_picker_for_web
# previews and reads picked files through same-origin blob: URLs (an <img> for
# resizing + an XHR for readAsBytes); without blob: the web app silently fails
# to attach photos ("nothing happens after I select the file").
# Include from nginx.conf; do NOT drop this file into
# conf.d as *.conf or nginx would load it as a top-level server block.
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'wasm-unsafe-eval' https://www.gstatic.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://www.gstatic.com; font-src 'self' data: https://www.gstatic.com https://fonts.gstatic.com; connect-src 'self' blob: https://www.gstatic.com https://fonts.gstatic.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "no-referrer" always;
