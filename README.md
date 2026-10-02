# pi_printserver

Central internal label-printing service for office/support use.

This project is intentionally separate from `printserver_win`, which remains the production-kiosk print server. `pi_printserver` is designed for batch reprinting/relabeling from browsers on the internal LAN and prints directly to network-connected Zebra printers over RAW TCP (normally port 9100).

## Target architecture

Browser → React UI → FastAPI API → PostgreSQL → ZPL renderer → Zebra printer over Ethernet

## Main requirements

- product database and label templates
- local users/roles initially; ready for later OIDC/Authentik
- configurable network printers
- ZPL generation
- batch printing (for example 40 identical labels in one job)
- print reason/reference
- full print audit/history
- Docker Compose deployment
- no runtime dependency on `printserver_win`

## Quick start

1. Copy `.env.example` to `.env`.
2. Set a strong `SECRET_KEY` and database password.
3. Run `docker compose up --build -d`.
4. Open the configured web port.

## Status

Initial project scaffold. The existing `printserver_win` repository is the behavioral reference for products, templates, variables and proven ZPL concepts, but this application is independently deployable.
