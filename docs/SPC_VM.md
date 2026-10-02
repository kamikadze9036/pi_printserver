# spc-vm deployment

Target: SSH alias `spc-vm`, `172.24.0.191`, user `martinkupilik`.
Dedicated checkout: `/home/martinkupilik/apps/pi_printserver`.
Compose project: `pi-printserver`; frontend port: **8089**.
Application URL: [http://172.24.0.191:8089](http://172.24.0.191:8089).
Only the frontend port is published; the other applications and their proxies
on this shared VM are not modified.

The repository-specific ED25519 key is generated on this server:

- Private key: `~/.ssh/pi_printserver_deploy_ed25519` (mode 600).
- Public key: `~/.ssh/pi_printserver_deploy_ed25519.pub`.
- GitHub repository: `kamikadze9036/pi_printserver` → Settings → Deploy keys.
  **Allow write access must remain unchecked**. Read-only access is enforced by
  GitHub, not by the SSH key's comment. No private key belongs in the repository.

The checkout's `core.sshCommand` selects this key with `IdentitiesOnly=yes`,
`BatchMode=yes` and `StrictHostKeyChecking=yes`, using the server's existing
verified GitHub host keys. Its origin push URL is disabled as an additional
guard; deployments only fetch/pull.

First deployment uses a private `.env` (mode 600) with independently generated
database, application and initial administrator secrets. `ADMIN_USERNAME=admin`,
`FRONTEND_PORT=8089`, `COOKIE_SECURE=false` and
`PUBLIC_ORIGIN=http://172.24.0.191:8089`. Existing secrets must never be regenerated
on update. Change the initial administrator password in the application's Users
page; editing `.env` does not reset an existing account.

Updates after changes are committed to `main`:

```sh
ssh spc-vm
cd ~/apps/pi_printserver
sh scripts/deploy-spc-vm.sh
```

The script rejects local checkout changes, saves a PostgreSQL custom-format backup
in the private `.backups/` directory if the database is running, pulls with
`--ff-only`, builds and waits for all service health checks. Migrations are applied
by the backend entrypoint. Backups remain on the VM; include them in the site's
normal off-host backup process.

Useful commands from this checkout:

```sh
docker compose -p pi-printserver --env-file .env -f docker-compose.yml ps
docker compose -p pi-printserver --env-file .env -f docker-compose.yml logs --tail=100 backend
curl --fail http://127.0.0.1:8089/api/health
```

The initial deployment contains no synthetic acceptance data or simulator. Create
network printer records and users in the application; import products/templates
only from an explicitly prepared SQLite backup. No physical printer is contacted
until an authorized user requests a test or print job.

For future HTTPS termination, configure the chosen reverse proxy first, then set
`PUBLIC_ORIGIN` to its exact HTTPS origin and `COOKIE_SECURE=true`; restart this
Compose project. The initial deployment uses the dedicated HTTP LAN port above.
