# FarmDirect replacement backend

This package replaces all 12 uploaded source files and adds shared helpers, PostgreSQL migrations, reservation expiry, and tests. The folder structure matches the `routers.*` and `services.*` imports in your original project.

**Keep your existing `.env`. Back up your code and database before migration. Test against a copy of your database first.** No migration has been run against your database by this package's author.

## 1. Put files in the correct locations

Extract this ZIP. Use the contents of the `farmdirect` folder as your backend folder, or copy its contents over your existing backend using the paths below. Add the new folders too; replacing only the original 12 files is insufficient.

| Uploaded file | Replacement location |
|---|---|
| auth.py | auth.py |
| database.py | database.py |
| main.py | main.py |
| models.py | models.py |
| schemas.py | schemas.py |
| requirements.txt | requirements.txt |
| auth_routes.py | routers/auth_routes.py |
| product_routes.py | routers/product_routes.py |
| order_routes.py | routers/order_routes.py |
| delivery_routes.py | routers/delivery_routes.py |
| map_routes.py | routers/map_routes.py |
| map_service.py | services/map_service.py |

Also copy `config.py`, the other `services/` files, `migrations/`, `alembic.ini`, `expire_orders.py`, and the tests. Empty `__init__.py` files are intentional.

Copy your real `.env` beside `main.py` if using the new folder. `.env.example` is only a reference; it does not contain your credentials.

## 2. Environment settings

Your existing `DATABASE_URL` and `SECRET_KEY` names still work. Missing/blank values now stop startup. The secret must be at least 32 bytes and must not equal the old placeholder. If you need a new secret, generate one locally:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste it into `.env`; do not share it. Existing password hashes remain valid. Users need to sign in again because access tokens now carry an explicit token type.

Optional settings:

| Setting | Default / purpose |
|---|---|
| RESERVATION_HOURS | 24; how long a new pending order reserves stock |
| ACCESS_TOKEN_EXPIRE_MINUTES | 1440 |
| CORS_ORIGINS | Comma-separated frontend origins; unset means no cross-origin browser access |
| MAP_USER_AGENT | Set your project name and a real contact URL/email for public geocoding |
| NOMINATIM_URL | Change geocoding provider URL without changing source |
| OSRM_URL | Change routing provider URL without changing source |

## 3. Install, migrate, run (Windows PowerShell)

Run these commands inside the folder containing `main.py`. Stop the old API before migration.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Use Python 3.10 or newer. For normal serving, omit `--reload`. Use one worker while using the public Nominatim endpoint: the cache and throttle are process-local.

Open http://127.0.0.1:8000/docs for Swagger. Log in using email as the `username` form field. Tests use a separate in-memory SQLite database and mocked maps; they do not modify your `.env` or application database.

Dependencies use compatibility ranges because a full installation could not be verified in the authoring environment. `passlib` and `bcrypt` are pinned together for compatibility with existing hashes. After successfully installing and running tests in your own environment, record the resolved set:

```powershell
.\.venv\Scripts\python.exe -m pip freeze > requirements-lock.txt
```

## 4. Migration behavior: read before running

`alembic upgrade head` supports an empty PostgreSQL database or the exact legacy table/column layout shown in your uploaded `models.py`. You do not need to use `alembic stamp`.

- `0001_legacy` creates the original tables on an empty database, or verifies their column layout on an existing database.
- `0002_integrity` adds the new fields, converts money/weights to fixed decimal precision, and converts the original naive ISO timestamps to UTC timestamps.
- Money rounds to two decimal places; weights round to three. Check whether this changes any existing unusually precise values before migration.
- Invalid legacy values (negative prices, invalid statuses, invalid dates, out-of-range numbers) make migration fail and roll back. Resolve them explicitly in a database copy before retrying; the migration does not delete problematic records.
- Existing records and password hashes are preserved. The unused legacy `farmers.rating` column remains in an existing database to avoid destroying data; new application code does not use it.
- Legacy names, units and pickup addresses are copied from the currently available records. They are best-known values, **not proof of the original historical listing**. Missing old quotes, unit prices and coordinates are not invented.
- Existing pending orders get 24 hours from migration. They have no agreed quote, so farmers must reject them (or buyers cancel them) and buyers place new quoted orders. Rejecting/cancelling returns reserved stock.
- Existing accepted deliveries keep their original delivery cost, including any historical zero cost. Migration cannot reconstruct a price the parties never agreed to. Resolve old inaccurate prices operationally before using these records for payment.
- Old non-kg listings are preserved but cannot receive new delivery orders until the farmer converts their quantity and price to kg. Unit changes are blocked while orders are active.
- Automatic downgrade is deliberately disabled because it would discard new quote/history fields. To revert, restore both your database backup and the old backend together.

If your actual database has additional columns or migrations beyond the uploaded code, have the migration adapted to that schema rather than deleting columns or bypassing the checks.

## 5. Frontend changes you must make

### Checkout now requires a quote token

1. Log in as a buyer.
2. Call `GET /deliveries/estimate?product_id=1&quantity=10&destination=Noida` with the bearer token.
3. Display product cost, transport cost, estimated total, and the resolved pickup/destination information. Confirm the addresses with the buyer.
4. Submit the returned `quote_token` when placing the order:

```json
{
  "product_id": 1,
  "quantity": "10.000",
  "delivery_location": "Noida",
  "quote_token": "PASTE_THE_RETURNED_QUOTE_TOKEN"
}
```

POST this to `/orders/`. Quotes are signed, bound to the buyer, and expire after 15 minutes. A changed name, price, pickup address, quantity, or destination requires a new estimate. Stock is checked and reserved at order creation, not at estimate time. Retrying the same still-valid quote returns the same order without reserving stock twice; it does not create a new order after cancellation. Request a fresh estimate for another order.

Vehicle rates remain prototype estimates, not a payment or invoicing integration. Delivery size is capped at 20,000 kg per order. An actual transporter is checked for availability and capacity during assignment.

### Other API differences

| Change | Frontend action |
|---|---|
| Decimal values serialize as strings, e.g. `"20.00"` | Accept numeric strings in responses; format prices for display. Do monetary arithmetic on the server. |
| `total_price` still means product subtotal | Show `grand_total` as the payable estimate including delivery; old rows may have null quote fields. |
| `PATCH /products/{id}` is the preferred partial-update endpoint | Old `PUT` URL remains as a deprecated compatibility alias. |
| New `POST /products/{id}/stock-adjustment` body: `{"delta":"25.000"}` | Use to add/remove available stock while orders are active. Quantity replacement with active orders returns 409. |
| Product DELETE archives listings | Archived products disappear from browsing; order and delivery history remains. |
| List endpoints default to 50 records | Use `offset` and `limit` (maximum 100). Responses remain arrays. |
| `POST /orders/{id}/cancel` | Allow buyers to cancel pending orders only. |
| `/maps/distance` now requires authentication | Include bearer token. |
| Invalid data returns 422; state conflicts return 409; map outages return 503 | Display the returned `detail` message. |
| Registration now returns 201 | Treat 201 as success. |
| Registration requires nonblank fields and passwords of 8–72 UTF-8 bytes | Validate the form and display API errors. Existing shorter passwords can still log in. |
| Unknown request fields are rejected | Send only documented schema fields. |

For farmers, `farm_location` is optional at registration and represents the farm address. `location` remains the person's contact address. Products can override the pickup address.

## 6. Schedule reservation expiry

Run this command every minute through Windows Task Scheduler or cron:

```powershell
.\.venv\Scripts\python.exe expire_orders.py
```

In Task Scheduler use the absolute path to `.venv\Scripts\python.exe` as the program, `expire_orders.py` as the argument, and your backend folder as **Start in**. The task releases expired pending reservations exactly once. Farmer acceptance also rejects and releases an expired reservation, but browsing does not run cleanup. Without the scheduled task, untouched expired orders will continue holding stock until processed.

## 7. Test coverage and limits

Performed during authoring:

- Syntax parsing of all Python files.
- 13 targeted Pydantic checks for product/order/status validation, normalization, and omission behavior.
- Static review of the route, transaction, migration, and import structure.

**Not executed here:** dependency installation, full API tests, PostgreSQL migrations/concurrency, real map provider requests. Dependency installation was blocked by the execution environment's network approval. Do not treat this as a deployment-tested build.

Included API tests cover registration rollback, invalid tokens, ownership, invalid updates, saved quotes, stock deduction, checkout retries, cancellation, expiry, driver availability/capacity, delivery transitions, repeated returns, and preserved history.

For the opt-in PostgreSQL assignment/return lock test, point `TEST_DATABASE_URL` at a dedicated disposable test database and run `pytest tests/test_postgres.py`. It creates and drops a uniquely named schema in that test database. Never use your real application database for this setting. SQLite tests cannot prove PostgreSQL locking behavior.

The prototype still needs deployment-level rate limiting for login/map routes and a shared cache/throttle or managed map service before scaling beyond one worker. No payment processing, SMS/email verification, partial/damaged returns, or truck-specific route restrictions are added by this package.

## Reference documentation

- [Pydantic V2 migration](https://docs.pydantic.dev/latest/migration/)
- [SQLAlchemy relationship loading](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html)
- [Alembic migrations](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Public Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/)

Display OpenStreetMap attribution wherever the frontend displays its map/geocoding results. Public mapping services are suitable for a small prototype; availability is not guaranteed.
