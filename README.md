# QuotationHist

QuotationHist is a portable quotation-history and procurement-pricing service. It imports Excel/CSV quotation files, stores catalog and material price history, supports preview-before-commit workflows, and exposes APIs for search, analytics, export, and cost estimation.

The project is written so Render is only one deployment target. Frontend, backend, database, and file storage are separated by environment variables and replaceable adapters.

## Architecture

- Frontend: static HTML/CSS/JS in `static/`, deployable as Render Static/Web Service or Docker/Nginx.
- Backend: FastAPI in `app/`.
- Database: configured by `DATABASE_URL`; local SQLite is supported for development/tests, PostgreSQL is the production target.
- File storage: configured by `STORAGE_BACKEND`; local storage is for development, S3-compatible storage covers Supabase Storage, Cloudflare R2, MinIO, and AWS S3.

Uploads are stored through the storage adapter. The database stores object keys, hashes, MIME types, sizes, and original filenames; production code should not depend on Render local disk.

## Local venv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000.

For quick local SQLite development, set:

```bash
DATABASE_URL=sqlite:///quotation_history.db
STORAGE_BACKEND=local
LOCAL_STORAGE_DIR=.data/uploads
```

## Docker local stack

```bash
docker compose up --build
```

This starts:

- Backend: http://localhost:8000
- Frontend/Nginx: http://localhost:8080
- PostgreSQL: localhost:5432
- MinIO S3-compatible storage: http://localhost:9001

Create the MinIO bucket named `quotationhist` before production-like upload testing.

## Render deployment

Use `render.yaml` as the starting point:

- Backend: Docker web service.
- Frontend: Docker/Nginx static web service. Set `BACKEND_URL` to the backend service URL; the default blueprint value assumes `https://quotationhist-backend.onrender.com`.
- Database: Render PostgreSQL or Supabase PostgreSQL, provided as `DATABASE_URL`.
- File storage: S3-compatible provider, provided through `S3_*` variables.

Required production environment variables:

- `DATABASE_URL`
- `JWT_SECRET`
- `CORS_ORIGINS`
- `STORAGE_BACKEND=s3`
- `S3_ENDPOINT_URL`
- `S3_BUCKET`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`

After the backend is live, include every production frontend origin in `CORS_ORIGINS`, for example:

```bash
CORS_ORIGINS=https://quotationhist-frontend.onrender.com,https://your-netlify-site.netlify.app
```

## Netlify deployment

`netlify.toml` publishes the static frontend from `static/` and proxies `/api/*` to:

```text
https://quotationhist-backend.onrender.com
```

If your Render backend URL differs, update the two redirect targets in `netlify.toml` before deploying to Netlify. The frontend JavaScript uses relative `/api` paths, so no rebuild-time API variable is needed.

## Auth

The app creates two default users when the database is initialized:

- Admin: `admin@example.com` / `Admin@123456`
- User: `user@example.com` / `User@123456`

Change these passwords before production use. Write actions use real login tokens; the old `X-User-Role` development shortcut is no longer accepted.

## Useful APIs

- `GET /health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/quotations/import`
- `GET /api/quotations`
- `GET /api/quotations/{id}`
- `DELETE /api/quotations/{id}`
- `GET /api/history/{catalog_no}`
- `GET /api/history/{catalog_no}/export.xlsx`
- `POST /api/import/preview`
- `POST /api/import/confirm`
- `POST /api/quotations/calculate-batch`
- `POST /api/pdf/import`
- `GET /api/analytics/dashboard`
- `POST /api/fx-rates`
- `GET /api/fx-rates`
- `GET /api/records/export.csv`

## Tests

```bash
python -m pytest -q
```

The current app still supports isolated temporary SQLite databases in tests. PostgreSQL deployment uses the same repository layer through `DATABASE_URL`.

## Current acceptance checklist

Use this checklist to verify the current MVP stage: local startup, import preview, confirmed storage, search, dashboard, quote calculation, and export.

1. Create and activate a local environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

2. Start the backend:

```bash
uvicorn app.main:app --reload
```

3. Open http://127.0.0.1:8000 and verify `GET /api/health` returns `status: ok`.
4. Run the automated tests from the activated virtual environment:

```bash
python -m pytest -q
```

5. Upload `data/samples/acceptance_procurement.csv` from the Import tab and confirm:
   - Chinese headers are mapped automatically.
   - Preview rows show normalized quantity, unit price, and match status.
   - Confirm import completes successfully for both inquiry and purchase flows.
   - Uploading the same file again shows the duplicate-file notice.

6. Validate user-facing flows:
   - Search for `乙醇` or `64-17-5` and open the material records.
   - Calculate a quote for `乙醇` with `500g`; the app should return an estimated cost.
   - Refresh the Dashboard tab and verify summary cards/tables update.
   - Refresh the Quotation History tab, search a catalog number from an imported quotation workbook, and export XLSX.
   - Use the Search tab CSV export to download all procurement records.

## Sample acceptance data

The CSV fixture at `data/samples/acceptance_procurement.csv` covers Chinese field mapping, CAS lookup, repeated materials, mixed units, suppliers, requesters, and dates. It is intended for manual acceptance testing of the generic procurement/import workflow.

## Next recommended features

- Add row-level review before import confirmation: select rows, edit normalized fields, and skip invalid rows before commit.
- Improve material details with a price trend chart, supplier comparison, and clear latest purchase/latest inquiry markers.
- Add multi-item quote-sheet generation with CSV/XLSX export.

## Migration

For old SQLite data:

```bash
SQLITE_PATH=quotation_history.db DATABASE_URL=postgresql://... python scripts/migrate_sqlite_to_postgres.py
```

Alembic is included for future versioned migrations. The current schema bootstrap lives in `app/db.py` for both SQLite and PostgreSQL.

## Deferred integrations

ISISlike and email-triggered imports are intentionally not wired to live systems yet. The architecture leaves them as future adapter integrations so the current codebase remains deployable without external credentials.
