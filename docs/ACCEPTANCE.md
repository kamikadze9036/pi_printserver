# MVP acceptance verification

Verified on 2026-10-02 using the repository's Docker Compose configuration,
PostgreSQL 17, Chromium and the isolated TCP receiver in `docker-compose.e2e.yml`.
The application uses the same backend/frontend images as a normal deployment.
The extra service replaces only the printer endpoint during acceptance testing.

| SPEC acceptance criterion | Implemented behavior and evidence |
| --- | --- |
| Docker Compose starts after configuration | Both application images build; migrations and bootstrap run; database, backend and frontend health checks pass. README documents environment configuration and startup. |
| Users can log in | Argon2 passwords, server-side sessions, CSRF tokens, session revocation and role enforcement; API and browser tests cover login and denied viewer printing. |
| Admin can configure Zebra | Printer CRUD, address/port/DPI validation, connection test and audited test label; multiple destinations and DPI values are covered by API tests. |
| Products/templates can be created/imported | Functional editors with preview and duplication; API CRUD tests and browser catalog setup. Copy-only SQLite dry-run/execute maps source template relationships and product text/QR fields. |
| Select product and quantity 40 | Browser creates the catalog, searches/selects a product, previews it and sends a quantity of 40. |
| Valid ZPL sent over TCP/IP | A real socket receiver captures the complete single-label ZPL with `^PQ40,0,1,Y`; unit tests cover coordinates, all variables, UTF-8 QR byte payload, text escaping and deterministic output. |
| Attempts audited, failures visible | Durable immutable snapshots, status/error/hash, queued recovery and original-job reference; browser verifies visible connection failure, history and authorized reprint. Schema-invalid and permission-denied requests are rejected before creating a job. |
| Import preserves original | Tests import a synthetic standalone SQLite copy; before/after source SHA-256 matches. Import conflicts, repeat execution, mapping and validation are covered by backend tests. No live kiosk database is accessed. |
| Multiple printers supported | Printer catalog and selectors accept multiple printers; individual destination/DPI is snapshotted per job and tested. |

Final automated results:

- **45 backend tests passed** locally and against actual PostgreSQL in the isolated
  test Compose project. This includes migration/model agreement, audit triggers,
  concurrent idempotency, authorization, import and socket delivery.
- **8 Chromium acceptance scenarios passed**, including administration, 40-label
  delivery, reprint, viewer permissions, copy import, visible failure, settings,
  mobile layout and uncertain print/reprint retries after a lost HTTP response.
- Frontend TypeScript/Vite build and Ruff checks passed. Desktop/mobile screenshots
  were visually inspected; they are generated under `frontend/test-results`.
- Persistence was verified with `down` followed by `up -d --wait`, retaining the
  named volume. Counts and ordered row-content digests matched for users, products,
  templates, printers, settings, print jobs and import runs, including 16 jobs.
- Git whitespace checks passed. The reference `printserver_win` was read-only.

The test instance contains synthetic data and printer addresses targeting the
simulator. No physical Zebra printer was available in this workspace; physical
output, media alignment and installed font support still require a sample label
on the deployment's actual printer. A successful TCP send is reported as endpoint
delivery, never as confirmation of physical printing.

Reproduce the builds and test suites with the commands in [README](../README.md).
The supplied legacy fixture contains no production data or credentials.
