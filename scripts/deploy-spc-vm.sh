#!/bin/sh
# Run from the dedicated pi_printserver checkout on spc-vm.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
test -f .env || { echo 'Configure .env before deployment' >&2; exit 1; }
test "$(git branch --show-current)" = main || { echo 'Expected main branch' >&2; exit 1; }
test -z "$(git status --porcelain)" || { echo 'Checkout contains local changes; review them before deploying' >&2; exit 1; }
umask 077
compose() { docker compose -p pi-printserver --env-file .env -f docker-compose.yml "$@" </dev/null; }
# Back up the existing production database before any new migration.
if [ -n "$(compose ps --status running -q db)" ]; then
  mkdir -p .backups
  backup=".backups/pi-printserver-$(date -u +%Y%m%dT%H%M%SZ).dump"
  compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup"
  test -s "$backup"
  printf 'Database backup: %s\n' "$backup"
fi
git pull --ff-only origin main
COMPOSE_PARALLEL_LIMIT=1 compose up --build -d --wait
compose ps
printf 'Deployed commit: '
git rev-parse HEAD
