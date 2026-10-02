# pi_printserver

Independent internal label-printing application: React/Vite → FastAPI →
PostgreSQL → ZPL → network Zebra printer (RAW TCP, normally port 9100).
It does not run or modify the `printserver_win` production kiosk.

## Start with Docker Compose

Requirements: Docker Engine/Desktop with Linux containers and Docker Compose v2
or newer. The deployment host must be able to reach each printer's configured
hostname/IP and TCP port. Supported Zebra resolutions: 203, 300 and 600 DPI.

1. Copy `.env.example` to `.env` (`cp .env.example .env`, or `Copy-Item
   .env.example .env` in PowerShell).
2. Replace `POSTGRES_PASSWORD`, `SECRET_KEY` and `ADMIN_PASSWORD`.
   Use a random `SECRET_KEY` of at least 32 characters and an administrator
   password of at least 12 characters. Placeholder secrets are rejected.
   For example, `openssl rand -hex 32` generates a suitable secret.
   Password symbols are supported: the backend constructs and escapes the
   database URL; there is no second database password to synchronize.
3. Run `docker compose up --build -d --wait`.
4. Open [http://localhost:8080](http://localhost:8080), or the host's address and
   `FRONTEND_PORT`. Log in with `ADMIN_USERNAME` and `ADMIN_PASSWORD` from `.env`.
5. In **Tiskárny**, create a Zebra with its hostname/IP, port, DPI and location.
   **Test spojení** checks TCP reachability. **Tisk 1 testovacího štítku** sends
   one audited 60 × 40 mm label; use matching media.
6. Create a template in **Šablony**, then create a product and assign it that
   template. Alternatively import an explicitly prepared SQLite copy as below.
7. In **Tisk štítků**, search/select the product, inspect its preview, select a
   printer, enter e.g. **40**, choose a reason and click **TISKNOUT**.

Only the frontend port is published. Nginx proxies `/api/` on the same origin;
database and backend ports remain internal. Health checks verify the database,
backend and frontend proxy. PostgreSQL data survives container recreation in the
`postgres_data` named volume. Startup applies Alembic migrations and initializes
an administrator/settings only when missing; it never recreates the schema.
Changing the bootstrap password in `.env` does **not** reset an existing account.

For the shared `spc-vm` deployment, see [server deployment and updates](docs/SPC_VM.md)
(dedicated project, pull-only key and port 8089).

Inspect service status with `docker compose ps` and errors with `docker compose
logs backend`. A failed login can be retried after the 15-minute rate-limit
window. Administrator password changes and account deactivation revoke sessions.

## Printing and history

A job contains a user, product, template and printer snapshot, requested quantity,
reason, note, reference, UTC timestamp, terminal status/error, ZPL and its SHA-256.
Printer test labels are also audited. Authenticated, schema-valid print requests
are audited even when catalog validation or rendering fails. Malformed requests
and denied permissions return HTTP 4xx before becoming print jobs.

Identical batches use **one** ZPL format with `^PQ40,0,1,Y`, rather than opening
40 connections. `sent` / **Odesláno** means the data was sent to the printer
endpoint; it does not confirm physical label output. Timeout or connection errors
are visible in the print result and **Historie**. No network operation is retried
automatically because the printer could already have received some/all bytes.

The client disables double submission and retains an uncertain print request's
token and full parameters in the tab's session storage, scoped to the logged-in
user. Retrying that request returns the original job without sending again.
The database uniquely binds each token to its user and request parameters; reusing
the token with different parameters returns 409. After a completed request, use
**Připravit novou úlohu** before starting another batch.

Jobs left `queued` by an interruption become `failed` with an uncertain-delivery
message after five minutes (checked at startup and every 30 seconds). They are
never resent. Check the printer before creating a deliberate reprint.

**Historie** supports product, status and date filters, pagination, snapshot/ZPL
inspection and authorized reprinting. Reprint creates a **new** job referring to
the original. It retains the original product/template data, uses the currently
selected configured printer and stamps the current date/time/operator. Product
and original template must still exist and be active. Print-job updates/deletes
are unavailable through the API, and PostgreSQL triggers prevent modification
except one `queued` → `sent`/`failed` transition.

## Roles and administration

| Role | Print/reprint | Catalog/history/preview | Product/template CRUD | Printers/users/settings/import |
| --- | --- | --- | --- | --- |
| `admin` | Yes | Yes | Yes | Yes |
| `engineer` (Process Engineer/Technician) | Yes | Yes | Yes | No |
| `team_leader` | Yes | Yes | No | No |
| `viewer` | No | Yes | No | No |

Products include description, QR content, text 1–4, active state, template,
optional preferred printer, side and the legacy right-side text highlight flag.
Products/templates can be duplicated. Records can be edited/deactivated/deleted;
assigned templates must first be unassigned or deactivated. Deleting catalog
records/users does not remove historic snapshots. The last active administrator
cannot be removed, demoted or deactivated.

The template editor supports text and QR elements, millimetre coordinates and
sizes, font size and variable contents, plus a live preview with configurable
sample data/DPI. Supported variables:

`{product_code}`, `{qr_content}`, `{text_content}` / `{text1}`, `{text2}`,
`{text3}`, `{text4}`, `{date}`, `{time}`, `{datetime_iso}`, `{operator}`.

Unknown variables and elements outside label dimensions are rejected for new
templates in **Text v blocích** mode. Imported templates use **Původní
printserver_win** mode: text remains a single line at the original coordinates
and font size, ignoring the old text box width/height exactly as the reference
ZPL generator did. This preserves older templates whose text boxes extend past
the media without resizing their contents. Text origins and QR bounds are still
validated. The template editor shows the selected mode; changing to block mode
requires fixing any out-of-bounds boxes first. Legacy `{datetime_iso}` keeps the
reference `YYYY-MM-DDTHH:MM:SS` format without an offset.

QR sizing
uses the actual payload's module count, including its quiet zone. Field data is
sanitized and UTF-8 hex encoded, so label contents cannot inject ZPL commands.
SVG preview displays actual QR data and element positions; browser text metrics
are approximate compared with Zebra font 0. Printer firmware/font support controls
the available Unicode glyphs. Check a sample label on the actual printer/media.

**Nastavení** manages default/maximum quantity and selectable print reasons.
Environment quantity/reason values initialize this table only on first startup;
later changes are made through administration. `TIMEZONE` controls rendered dates
(default `Europe/Prague`); audit timestamps are always UTC.

## Import from a printserver_win database copy

1. Prepare a **standalone SQLite backup** outside this application, e.g. with
   SQLite's backup function or `VACUUM INTO` as part of your existing backup
   procedure. Do not simply copy the `.db` file while writes/WAL are active:
   committed data can reside in `-wal`. The importer accepts one self-contained
   backup and never accepts a path to, or connects to, the kiosk's live database.
2. Open **Import katalogu**, choose the backup (`.db`, `.sqlite`, `.sqlite3`,
   max. 20 MiB) and confirm it is an explicitly supplied copy.
3. Run **Spustit dry-run**. Inspect the source SHA-256, new/existing templates,
   new/skipped products, conflicts and warnings. No catalog data changes yet.
4. Choose **Potvrdit a provést import** within one hour. Execute uses the exact
   validated upload and checks that the relevant target catalog has not changed.
   A conflict/change requires a new dry-run. The import is atomic and repeating
   execute does not duplicate records.

Templates and all product text/QR fields, source template relationships, side and
optional `highlight_right` are mapped. Missing template assignments are preserved
and reported; assign a template before printing those products. Existing products
are **skipped**, never overwritten. Existing template names are reused only when
their data match exactly; otherwise resolve the conflict and repeat dry-run.
Legacy accounts/passwords/PINs, Windows/TSPL printer settings, production orders
and kiosk print logs are excluded. Configure network printers and new users in
this application. See [reference mapping](docs/REFERENCE.md) for exact behavior.
The dry-run reports text boxes outside the media; legacy rendering retains their
original behavior and the printer clips at the actual label edge.

## HTTPS, reverse proxy and persistence

For HTTPS termination at your internal reverse proxy, route the entire host to
the frontend and set `COOKIE_SECURE=true` and `PUBLIC_ORIGIN` to the exact browser
origin, e.g. `https://labels.internal.example`. Restart with `docker compose up
-d`. For plain HTTP on the internal LAN, keep `COOKIE_SECURE=false`; a secure
cookie cannot be sent by browsers over HTTP. Use a dedicated host/root path.

Authentication uses Argon2 passwords and server-side expiring sessions. Cookies
are HttpOnly/SameSite Strict, and all authenticated mutating APIs also require the
session's `X-CSRF-Token`. Only administrators change printer destinations; print
requests take printer IDs, never arbitrary hosts or raw ZPL. Keep `.env` private
and back up the database volume. The application is intended for an internal LAN.

Before an application upgrade, take a PostgreSQL backup. Example on Linux:

```sh
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > pi-printserver.dump
docker compose up --build -d --wait
```

Use `docker compose down` to stop; avoid `down -v` on a real deployment because
it removes the persistent database. The test stacks below have separate names
and resources.

## Automated verification

See [MVP acceptance verification](docs/ACCEPTANCE.md) for the exercised criteria,
final results and the physical-printer verification boundary.

Fast backend unit/API tests (Python 3.12+):

```sh
python -m venv .venv
# activate .venv, then:
pip install -r backend/requirements.txt
python -m pytest -q --basetemp=.test-tmp
```

The same suite against actual PostgreSQL, including Alembic migrations,
constraints, immutable-audit triggers and concurrent idempotency:

```sh
docker compose -p pi-printserver-tests -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
docker compose -p pi-printserver-tests -f docker-compose.test.yml down
```

Frontend build:

```sh
cd frontend
npm ci
npm run build
```

Browser acceptance tests use a **separate** Compose project and a RAW TCP
simulator, never a real printer. Copy `.env.example` to `.tools/acceptance.env`,
set three strong secrets and `FRONTEND_PORT=18080`, then run from repository root:

```sh
docker compose -p pi-printserver-mvp-check --env-file .tools/acceptance.env -f docker-compose.yml -f docker-compose.e2e.yml up --build -d --wait
cd frontend
npm ci
npx playwright install chromium
npm run test:e2e
```

The checked-in `e2e/fixtures/legacy-copy.db` contains only synthetic test data;
its generator is `backend/tests/make_legacy_fixture.py`. Test credentials come
from the ignored `.tools/acceptance.env` (or `E2E_ENV_FILE` / `E2E_ADMIN_PASSWORD`).
Optional test overrides: `E2E_BASE_URL`, `E2E_SIMULATOR_URL`, `SIMULATOR_PORT`.
The suite covers administration, 40-label TCP delivery, history/reprint, viewer
permissions, copy import, visible failure, lost-response idempotency and mobile
layout. Screenshot/trace artifacts are written under `frontend/test-results`.
Stop the acceptance stack with the same Compose arguments followed by `down`.

No GPIO, PLC, Windows spooler, production-order counting or external-service
integration is required for this MVP. API source is organized into catalog,
authentication, printing, renderer and importer modules; schema changes belong
in new Alembic revisions.
