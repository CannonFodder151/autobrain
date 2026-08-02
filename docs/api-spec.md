# API Specification

Base URL: `/api/v1`. Auth: `Authorization: Bearer <token>` (JWT).
Interactive spec: `http://<host>/docs` (OpenAPI).

## Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Register, returns token pair |
| POST | `/auth/login` | Login |
| POST | `/auth/refresh` | Refresh tokens |
| GET | `/auth/me` | Current user |

## Vehicles
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/vehicles` | List / create |
| GET/PATCH/DELETE | `/vehicles/{id}` | Detail / update / delete |
| POST | `/vehicles/rego-lookup` | Plate → VIN, make, model, year, engine |
| GET | `/vehicles/{id}/timeline` | Unified event timeline |

## Services (`/vehicles/{id}/services`)
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `` | List / create |
| GET/PATCH/DELETE | `/{service_id}` | Detail / update / delete |
| POST | `/predict` | AI next-service prediction |
| GET | `/export?fmt=csv|pdf` | Export history |

## Fuel (`/vehicles/{id}/fuel`)
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `` | List / add fill-up |
| DELETE | `/{fuel_id}` | Delete |
| GET | `/stats` | Totals, averages, series |

## Diagnostics (`/vehicles/{id}/diagnostics`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `` | Run AI diagnosis (symptoms + OBD codes) |
| GET | `` | List |
| POST | `/{diagnostic_id}/add-to-service` | Queue as a service |

## Mods (`/vehicles/{id}/mods`)
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `` | List / create |
| PATCH/DELETE | `/{mod_id}` | Update / delete |
| POST | `/impact` | AI performance/value impact |
| GET | `/export?fmt=csv|pdf` | Build sheet |

## Receipts (`/vehicles/{id}/receipts`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `` | Upload (multipart) → async OCR |
| GET | `` | List |
| POST | `/{receipt_id}/apply-to-service` | Add items to service + inventory |

## Parts (`/vehicles/{id}/parts`)
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `` | List / create |
| PATCH/DELETE | `/{part_id}` | Update / delete |
| POST | `/{part_id}/movement` | Stock in/out |
| GET | `/reorder-suggestions` | AI reorder list |

## Valuation (`/vehicles/{id}/valuation`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `` | Estimate resale value (stores snapshot) |
| GET | `/history` | Value snapshots |

## Analytics (`/vehicles/{id}/analytics`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `` | Spend, TCO, cost/km, forecast, insights |

## System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| WS | `/ws/{user_id}` | Live push (receipt.processed, etc.) |

## AI gateway (port 8001)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness + router status |
| GET | `/v1/modules` | List modules |
| POST | `/v1/{module}` | Infer (module ∈ diagnostics, service-prediction, ocr, resale, mod-impact) |
