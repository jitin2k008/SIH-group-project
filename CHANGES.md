# Changes from your uploaded backend

| File | Changes |
|---|---|
| config.py (new) | Loads your existing .env explicitly; requires database URL and a non-placeholder secret; configures expiry. |
| auth.py | Validates JWT subject/type/expiry; returns 401 for malformed subjects; retains existing bcrypt passwords; adds reusable role dependencies. |
| database.py | Removes credential fallback; closes/rolls back request sessions; enables connection health checks. |
| models.py | Uses decimal money/weights and UTC dates; adds quote/history/coordinate fields, archival flag, indexes and constraints. Removes unused rating from ORM while preserving its legacy database column. |
| schemas.py | Uses Pydantic V2; rejects invalid/blank/nonfinite/null inputs; separates order/delivery statuses; enforces kg on new listings; removes unused schemas. |
| routers/auth_routes.py | Creates user and role profile in one transaction; catches unique conflicts; normalizes new vehicle numbers. |
| routers/product_routes.py | Archives listings; paginates lists; validates filters; supports PATCH plus old PUT; locks stock edits; adds stock-adjustment endpoint. |
| routers/order_routes.py | Requires a signed agreed quote; stores history and costs; reserves stock under a lock; avoids duplicate checkout from quote retries; handles cancellation and expiry. |
| routers/delivery_routes.py | Locks assignment/status/return rows; checks busy status and capacity; restores inventory once on confirmed return; preserves history; uses eager loading and pagination. |
| routers/map_routes.py | Adds authentication, length validation, and attribution. |
| services/map_service.py | Adds bounded cache, one-request-per-second geocoding throttle, timeouts and specific provider errors. |
| services/pricing.py (new) | Shares vehicle rates; uses decimal rounding; signs buyer-specific quotes and checks changed listings; caps delivery size. |
| services/common.py (new) | Shares safe database commits and record lookup helpers; logs errors without SQL parameter dumps. |
| services/orders.py (new) | Shares expiry and reservation-release rules. |
| expire_orders.py (new) | Scheduled cleanup of pending reservations; uses order/product locks. |
| main.py | Removes import-time table creation; registers specific error handlers; allows configured frontend origins. |
| migrations/ (new) | Initializes/adopts the original schema and upgrades without deleting records. |
| requirements*.txt | Adds requests, multipart, migrations and test dependencies. Compatibility ranges are supplied because installation was blocked here; record your resolved lock file after local tests. |
| tests/ (new) | Covers API workflows and an opt-in PostgreSQL assignment and return races. Full tests are supplied but not executed in the authoring environment. |

Comments now explain business decisions, especially stock reservations, confirmed returns and legacy records. Existing authorization and ownership checks are retained.

Important compatibility changes: checkout needs `quote_token`; decimals are returned as strings; old access tokens require re-login; products are archived; maps require login; lists are paginated. Read README.md before replacing the original files.
