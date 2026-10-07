# Sabi-Stock

Initial foundation for a multi-business inventory management application, including owner/manager authentication and business membership scoping.

## Project layout

- `frontend/` — static HTML, CSS, and vanilla JavaScript landing, registration, and login pages
- `backend/` — FastAPI application and PostgreSQL connection layer

## Run the backend locally

1. Create and activate a virtual environment from `backend/`.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `backend/.env.example` to `backend/.env`, set `DATABASE_URL` to a PostgreSQL connection string, and set `JWT_SECRET_KEY` to a random secret of at least 32 characters (generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`).
4. Start the API from `backend/` with `uvicorn app.main:app --reload`.

Apply `backend/app/db/schema.sql` to the Neon database before using the API (for example, `psql "$DATABASE_URL" -f backend/app/db/schema.sql`). The schema is intentionally not applied automatically at startup.

The readiness endpoint is available at `http://127.0.0.1:8000/api/health`. It checks the PostgreSQL connection and returns `503` if the database is not configured or unavailable.

## Authentication API

- `POST /api/auth/register/owner` — create an owner account and business.
- `POST /api/auth/login` — validate credentials and return a bearer token.
- `POST /api/auth/invitations` — owner-only; create a manager invitation that expires after 24 hours. The plaintext code is returned once.
- `POST /api/auth/register/manager` — create a manager account using an invitation code.
- `GET /api/auth/me` — return the authenticated user and their business context.
- `POST /api/products` — create a product for the authenticated user's business.
- `GET /api/products` — list products, optionally filtered by `search` and `category`.
- `GET /api/products/{product_id}` — read one product from the authenticated user's business.
- `PUT /api/products/{product_id}` — update a product in the authenticated user's business.
- `DELETE /api/products/{product_id}` — delete a product in the authenticated user's business.
- `POST /api/sales` — record a sale and atomically reduce the product stock.
- `GET /api/sales` — list the authenticated business's sales (`limit` and `offset` supported).
- `GET /api/sales/{sale_id}` — read one sale from the authenticated business.
- `DELETE /api/sales/{sale_id}` — void a sale and atomically return its quantity to product stock.
- `GET /api/dashboard` — return business-scoped product/stock totals, today's database-date sales and profit, low-stock products, and the top 5 products ranked by quantity sold.

Send authenticated requests with `Authorization: Bearer <access_token>`. Access tokens expire after `JWT_EXPIRE_MINUTES` (60 by default). User membership is rechecked against PostgreSQL for authenticated requests, so removed membership immediately loses access. Future business-owned tables should include a non-null `business_id` foreign key and all queries should scope through the authenticated user's `business_id`.

## Frontend authentication

The static frontend pages are `frontend/index.html`, `frontend/register.html`, and `frontend/login.html`. Owner registration and login submit directly to the FastAPI API. Set `apiBaseUrl` in `frontend/js/config.js` to the deployed API origin before deployment; the committed value points at the deployed Render API (`https://sabi-stock-1.onrender.com`). The returned token is held in `sessionStorage` for this course project, so it is cleared when the browser tab session ends. `frontend/dashboard.html`, `frontend/products.html`, and `frontend/sales.html` are protected pages with shared Dashboard / Products / Sales navigation, account context, and logout. Products provides creation, listing, editing, deletion, search, and category filtering. Sales selects from live product stock, records sales, and shows sales history. Voiding a sale restores its stock inside the same database transaction; products with sales cannot be deleted until those sales are voided. The dashboard refreshes live aggregate metrics from the authenticated dashboard endpoint and uses Chart.js via CDN for best sellers. Authenticated pages include loading, empty, and API error/success feedback states and adapt their navigation and content for smaller screens.

Run the backend unit tests from `backend/` with `python -m unittest discover -s tests -v`.

For an existing database, apply migrations in order: `backend/app/db/migrations/002_products.sql`, then `backend/app/db/migrations/003_sales.sql`. For a new database, the current `backend/app/db/schema.sql` includes the products and sales tables. Products with sales cannot be deleted; void sales first if the product needs to be removed.

## Deploy

- **Render:** create a Blueprint service from `render.yaml`. Set `DATABASE_URL` to the Neon connection string, `FRONTEND_ORIGINS` to the deployed frontend origin, and `JWT_SECRET_KEY` to a random secret of at least 32 characters in the Render environment.
- **Vercel:** import the repository and set the project Root Directory to `frontend`. The frontend is static and requires no build step, so the committed `frontend/js/config.js` is used as-is. If you instead build from the repository root, `vercel.json` runs `scripts/build_frontend_config.js`, which rewrites `frontend/js/config.js` from the `API_BASE_URL` environment variable when it is set (and leaves the committed value alone when it is not).

For local frontend development, serve `frontend/` with any static file server and set `apiBaseUrl` in `frontend/js/config.js` to `http://127.0.0.1:8000`.
