# Security headers for every frontend response (AUT-234/236).
# CSP is tuned for the Flutter web build: 'wasm-unsafe-eval' is required by
# the CanvasKit/skwasm renderer (wasm compilation is checked against
# script-src in Chrome), and 'self' covers the same-origin /api, /ws and /ai
# proxies plus wss. Include from nginx.conf; do NOT drop this file into
# conf.d as *.conf or nginx would load it as a top-level server block.
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "no-referrer" always;
