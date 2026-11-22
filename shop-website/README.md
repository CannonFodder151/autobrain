# AutoBrain Shop Website (`autobrain-shop-website`)

Marketing site, customer portal (appointment booking), and workshop dashboard for the AutoBrain Shop. Built as a static site and deployed to **Azure Static Web Apps (SWA)**.

## Structure

```
shop-website/
├── public/                 # Static assets copied verbatim to dist
│   └── favicon.svg
├── src/                    # Vite build root
│   ├── index.html          # Marketing homepage
│   ├── customer/index.html # Customer portal (booking + service history)
│   ├── workshop/index.html # Workshop dashboard
│   ├── components/nav.js   # Shared nav component
│   ├── main.ts             # Marketing homepage entry
│   ├── customer/main.ts    # Portal entry
│   ├── workshop/main.ts    # Dashboard entry
│   └── styles/main.css     # Shared styles
├── staticwebapp.config.json # Azure SWA routing + security headers
├── vite.config.ts          # Multi-page entry config (marketing / customer / workshop)
├── tsconfig.json
├── package.json
└── .github/workflows/azure-swa-deploy.yml
```

## Pages

| Page | Path | Purpose |
|------|------|---------|
| Homepage | `/` | Hero, services grid, inline booking CTA, testimonials |
| Customer Portal | `/customer/` | Sign-in gate, book appointment, service history, my vehicles |
| Workshop Dashboard | `/workshop/` | Overview KPIs, appointments, work orders, customers |

## Local Development

```bash
cd shop-website
npm install       # or npm ci
npm run dev       # http://localhost:3000
npm run build     # output -> dist/
npm run preview   # serve production build locally
```

## Deployment

Push to `main` → GitHub Actions builds `dist/` and uploads it to Azure Static Web Apps via `Azure/static-web-apps-deploy@v1`.

Required secret: `AZURE_STATIC_WEB_APPS_API_TOKEN` (Azure SWA deployment token) configured in the repo settings.

Routing: all unknown paths fall back to `/index.html` (SPA-friendly); `/styles/*`, `/assets/*`, `/favicon.svg` are served directly.

## Notes

- The booking forms currently simulate submission (alert dialog). Wire them to the AutoBrain Shop booking API (`/api/v1/bookings`) once the backend endpoint is available.
- No build framework is used on the marketing side; pages are plain HTML/CSS/TS compiled by Vite for multi-page output.
- Security headers (CSP, X-Frame-Options, HSTS-adjacent) are applied via `staticwebapp.config.json`.
