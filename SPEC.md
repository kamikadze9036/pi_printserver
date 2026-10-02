# pi_printserver — Technical & Functional Specification

## Purpose
Central internal label-printing web application for team leaders, process engineers, technology and quality. It is separate from the production kiosk application `printserver_win`.

Target: Docker on internal Linux VM; browser clients; one or more Ethernet Zebra printers. Main workflow: select product, select printer, enter quantity (e.g. 40), reason/reference, print identical labels as one audited job.

## Architecture
Browser → React/Vite UI → FastAPI → PostgreSQL → ZPL renderer → RAW TCP → Zebra:9100.

No Windows spooler and no runtime dependency on `printserver_win`.

## Required functionality
- local users and roles (Admin, Process Engineer/Technician, Team Leader; optional Viewer)
- products with product_code, description, QR/text1-text4, template, active state and optional preferred printer
- data-driven label templates with dimensions and JSON elements
- text and QR elements for MVP
- variables: {product_code}, {qr_content}, {text_content}/{text1}, {text2}, {text3}, {text4}, {date}, {time}, {datetime_iso}, {operator}
- database-managed network printers: name, hostname/IP, TCP port, protocol, DPI, active, location and optional side/group
- batch printing as a first-class quantity; for identical Zebra labels prefer ZPL ^PQ
- print reason and optional note/reference
- immutable print-job audit history
- authorized reprint creates a new job referencing the original
- admin CRUD for products, templates, printers, users and settings
- import from an explicitly supplied copy of the existing printserver_win SQLite DB; dry-run first; never operate directly on its live DB
- multiple printers supported even if deployment starts with one

## Network printing
Open a TCP socket to configured printer host/port (default 9100), send complete ZPL bytes, close safely, and use explicit timeouts. A successful TCP send means data was delivered to the printer endpoint; it must not be described as proof that a physical label was produced.

## ZPL
Refactor the proven concepts from printserver_win/printer.py into an independent service:
- mm → dots using printer DPI
- text and QR rendering
- variable substitution
- sanitize ZPL control characters
- deterministic output
- quantity using ^PQ

## Print workflow
1. Login.
2. Search/select product.
3. Load assigned template.
4. Show product and label preview.
5. Select target printer.
6. Enter quantity (default 1).
7. Select reason and optionally enter note/reference.
8. Print.
9. Backend independently validates user permission, product, template, printer, quantity and variables.
10. Generate ZPL.
11. Send to Zebra.
12. Store audit record for success or failure.
13. Show clear result.

Prevent accidental double-submit in UI and support an idempotency/request token server-side.

## Audit fields
At minimum: timestamp, user snapshot, product snapshot, template snapshot, printer snapshot, requested quantity, reason, note/reference, job identifier, status (queued/sent/failed), error, optional ZPL hash, and original_job_id for reprints.

## Database
Production database: PostgreSQL with SQLAlchemy and Alembic. Suggested tables: users, products, templates, printers, settings, print_jobs, optional reason_codes. Startup must never destructively recreate a production schema.

## API outline
Auth: POST /api/auth/login, POST /api/auth/logout, GET /api/auth/me.
Products: GET/POST /api/products, GET/PUT /api/products/{id}, POST /api/products/{id}/duplicate.
Templates: GET/POST /api/templates, PUT /api/templates/{id}, duplicate and preview endpoints.
Printers: GET/POST /api/printers, PUT /api/printers/{id}, test-connection and test-print.
Printing: POST /api/print-jobs, GET /api/print-jobs, GET /api/print-jobs/{id}, POST /api/print-jobs/{id}/reprint.
Import: dry-run and execute endpoints for printserver_win SQLite import.

## UI
Login; operational Print/Home; History; Admin Products; Admin Templates; Admin Printers; Admin Users; Admin Settings. The primary Print page needs prominent product search, selected product details, preview, printer selector, quantity, reason, note and a large Print button.

## Deployment
Repository contains Docker Compose with db, backend and frontend services. PostgreSQL uses a persistent named volume. Secrets/configuration come from environment variables; printer addresses normally live in DB. Application must be reverse-proxy compatible.

## Safety/security
Secure password hashes; server-side authorization; validation; CSRF protection where applicable; secure cookies under HTTPS; no arbitrary network destination in normal print API; admin-only printer address changes; no committed production secrets. Printing failures must be logged and visibly reported.

## Tests
Cover variable resolution, mm-to-dots, ZPL, ^PQ, quantity validation, permissions, product/template validation, printer connection failure, audit creation on success/failure, reprint behavior and SQLite import mapping. Network printer service must be mockable.

## MVP acceptance
Docker Compose starts after documented configuration; user can log in; admin can configure Zebra; products/templates can be created/imported; user can select a product and quantity such as 40; valid ZPL is generated and sent over TCP/IP; every attempt is audited; failures are reported; printserver_win data can be imported from a copy without modifying the original; multiple printers are supported.

## Non-goals for MVP
Do not replace printserver_win production kiosk. No PLC/GPIO triggers, Windows USB printing, MES integration, production-order counting or public internet exposure.

## Implementation guidance
Treat printserver_win as reference behavior only. Inspect its schema and ZPL generator when implementing migration. Prefer clean modules over copying the monolithic Flask application. Use PostgreSQL migrations from day one. Keep printer operations server-side. Do not alter printserver_win.
