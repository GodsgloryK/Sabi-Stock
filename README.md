# Sabi-Stock

Multi-business inventory and sales management application with owner/stock-manager authentication, product catalogue, inventory tracking, sales recording, low-stock alerts, team invitations, and CSV export.

## Project layout

- `frontend/` — static HTML, CSS, and vanilla JavaScript pages (landing, auth, dashboard, products, sales, team)
- `backend/` — FastAPI application and PostgreSQL connection layer

## Run the backend locally

1. Create and activate a virtual environment from `backend/`.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `backend/.env.example` to `backend/.env`, set `DATABASE_URL` to a PostgreSQL connection string, and set `JWT_SECRET_KEY` to a random secret of at least 32 characters (generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`).
4. Start the API from `backend/` with `uvicorn app.main:app --reload`.

Apply `backend/app/db/schema.sql` to the Neon database before using the API (for example, `psql "$DATABASE_URL" -f backend/app/db/schema.sql`). The schema is intentionally not applied automatically at startup.

The readiness endpoint is available at `http://127.0.0.1:8000/api/health`. It checks the PostgreSQL connection and returns `503` if the database is not configured or unavailable.

## API

### Authentication & team

- `POST /api/auth/register/owner` — create an owner account and business.
- `POST /api/auth/login` — validate credentials and return a bearer token. Rate-limited to 5 failed attempts per email/IP every 15 minutes (`429` on excess).
- `POST /api/auth/invitations` — owner-only; create a stock manager invitation that expires after 24 hours. The plaintext code is returned once.
- `POST /api/auth/register/manager` — create a stock manager account using an invitation code.
- `GET /api/auth/me` — return the authenticated user and their business context.
- `GET /api/auth/members` — owner-only; list team members with roles.
- `DELETE /api/auth/members/{user_id}` — owner-only; remove a stock manager. Owners cannot be removed or remove themselves.
- `GET /api/auth/invitations/list` — owner-only; list recent invitations with computed status (pending/used/expired).
- `DELETE /api/auth/invitations/{invitation_id}` — owner-only; revoke a pending invitation.

### Products

- `POST /api/products` — create a product for the authenticated user's business.
- `GET /api/products` — list products, optionally filtered by `search` and `category`.
- `GET /api/products/{product_id}` — read one product from the authenticated user's business.
- `PUT /api/products/{product_id}` — update a product in the authenticated user's business.
- `DELETE /api/products/{product_id}` — delete a product (blocked with `409` if sales exist).

### Sales

- `POST /api/sales` — record a sale and atomically reduce the product stock.
- `GET /api/sales` — list sales; supports `limit`, `offset`, `date_from`, `date_to`, and `product_id` filters. Returns `X-Total-Count` for pagination.
- `GET /api/sales/summary` — aggregated revenue, profit, units, and sale count for the same filters.
- `GET /api/sales/{sale_id}` — read one sale from the authenticated business.
- `DELETE /api/sales/{sale_id}` — void a sale and atomically return its quantity to product stock.

### Dashboard

- `GET /api/dashboard` — business-scoped product/stock totals, today's sales and profit (computed in the business's timezone), low-stock products (using the business's configurable threshold), and the top 5 products by quantity sold.
- `GET /api/dashboard/trends?days=30` — daily revenue/profit/units buckets for the last N days (1–90).

### Reports

- `GET /api/reports/export/sales.csv` — CSV export of sales; supports `date_from`, `date_to`, and `product_id` filters.
- `GET /api/reports/export/products.csv` — CSV export of the product catalogue.

Send authenticated requests with `Authorization: Bearer <access_token>`. Access tokens expire after `JWT_EXPIRE_MINUTES` (60 by default). User membership is rechecked against PostgreSQL for authenticated requests, so removed membership immediately loses access. All business-owned tables include a non-null `business_id` and all queries scope through the authenticated user's `business_id`.

## Frontend

Protected pages share Dashboard / Products / Sales / Team navigation (Team is owner-only), account context, and logout:

- `frontend/dashboard.html` — KPI cards, best-sellers bar chart, 30-day revenue/profit trend line chart, low-stock panel, auto-refresh every 60 seconds.
- `frontend/products.html` — product CRUD, live search, category filter, low-stock/out-of-stock badges, CSV export.
- `frontend/sales.html` — record sales from live stock, date-range and product filters, summary cards, paginated history with load-more, void & restock, CSV export.
- `frontend/team.html` — owner-only; list members, invite stock managers with single-use codes, revoke invitations, remove members.

`frontend/join.html` lets a stock manager create an account with an invitation code. The returned token is held in `sessionStorage`, so it is cleared when the browser tab session ends.

## Migrations

For a new database, apply `backend/app/db/schema.sql` (includes all tables). For existing databases, apply migrations in order:

1. `001_auth.sql` — users, businesses, memberships, invitations
2. `002_products.sql` — products
3. `003_sales.sql` — sales
4. `004_business_settings.sql` — `low_stock_threshold` and `timezone` columns on businesses

Products with sales cannot be deleted; void sales first if the product needs to be removed.

## Tests

Run the backend unit tests from `backend/` with `python -m unittest discover -s tests -v`. CI runs these on every push and pull request via `.github/workflows/ci.yml`.

## Deploy

- **Render:** create a Blueprint service from `render.yaml`. Set `DATABASE_URL` to the Neon connection string, `FRONTEND_ORIGINS` to the deployed frontend origin, and `JWT_SECRET_KEY` to a random secret of at least 32 characters in the Render environment.
- **Vercel:** import the repository and leave the project Root Directory empty (the repository root). `vercel.json` runs `scripts/build_frontend_config.js`, which rewrites `frontend/js/config.js` from the `API_BASE_URL` environment variable when it is set (and leaves the committed value alone when it is not), then serves the static site from `frontend/`. Do not set the Root Directory to `frontend`: the build script and `vercel.json` paths are resolved from the repository root, and a `frontend` Root Directory makes the build fail with `Cannot find module .../frontend/scripts/build_frontend_config.js`.

For local frontend development, serve `frontend/` with any static file server and set `apiBaseUrl` in `frontend/js/config.js` to `http://127.0.0.1:8000`.
