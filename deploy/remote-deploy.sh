#!/bin/bash
# Activates an uploaded release on the server. Run by the CI deploy job over SSH:
#   remote-deploy.sh <app_dir> <release_id>
# Layout of <app_dir>:
#   releases/<release_id>/  uploaded code
#   current -> releases/... the active release (the service runs from here)
#   venv/                   Python virtual environment
#   shared/.env             settings (SECRET_KEY, DB_PATH, ...), also used by the service
#   backups/                database backups made before each deploy
set -euo pipefail

APP_DIR=${1:?usage: remote-deploy.sh <app_dir> <release_id>}
RELEASE_ID=${2:?usage: remote-deploy.sh <app_dir> <release_id>}
RELEASE="$APP_DIR/releases/$RELEASE_ID"
ENV_FILE="$APP_DIR/shared/.env"
VENV="$APP_DIR/venv"
BACKUPS="$APP_DIR/backups"
KEEP_RELEASES=${KEEP_RELEASES:-5}
KEEP_BACKUPS=${KEEP_BACKUPS:-10}

log() { echo "[deploy] $*"; }

[ -d "$RELEASE" ] || { log "release $RELEASE not found"; exit 1; }
[ -f "$ENV_FILE" ] || { log "$ENV_FILE not found, see README"; exit 1; }

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
SERVICE_NAME=${SERVICE_NAME:-rustdesk-api}
HEALTHCHECK_URL=${HEALTHCHECK_URL:-http://127.0.0.1:21114/api/user_action}
DB_PATH=${DB_PATH:-$APP_DIR/shared/db/db.sqlite3}
export DB_PATH

PREVIOUS=$(readlink -f "$APP_DIR/current" 2>/dev/null || true)

log "installing dependencies"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --disable-pip-version-check -r "$RELEASE/requirements.txt"

cd "$RELEASE"
"$VENV/bin/python" manage.py check

BACKUP=""
mkdir -p "$(dirname "$DB_PATH")" "$BACKUPS"
if [ -f "$DB_PATH" ]; then
    BACKUP="$BACKUPS/db-$(date +%Y%m%d-%H%M%S)-$RELEASE_ID.sqlite3"
    log "backing up database to $BACKUP"
    # sqlite3 .backup is consistent while the service is writing; fall back to a copy
    if command -v sqlite3 >/dev/null; then
        sqlite3 "$DB_PATH" ".backup '$BACKUP'"
    else
        cp "$DB_PATH" "$BACKUP"
    fi
fi

rollback() {
    log "deploy failed, rolling back"
    if [ -n "$BACKUP" ]; then
        cp "$BACKUP" "$DB_PATH"
    fi
    if [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
        ln -sfn "$PREVIOUS" "$APP_DIR/current.tmp"
        mv -T "$APP_DIR/current.tmp" "$APP_DIR/current"
        sudo -n systemctl restart "$SERVICE_NAME" || true
        log "rolled back to $PREVIOUS"
    fi
}
trap rollback ERR

log "applying migrations"
"$VENV/bin/python" manage.py migrate --noinput
"$VENV/bin/python" manage.py collectstatic --noinput --verbosity 0

log "switching to $RELEASE"
ln -sfn "$RELEASE" "$APP_DIR/current.tmp"
mv -T "$APP_DIR/current.tmp" "$APP_DIR/current"
sudo -n systemctl restart "$SERVICE_NAME"

log "checking $HEALTHCHECK_URL"
healthy=""
for _ in $(seq 1 15); do
    if curl -fs -o /dev/null "$HEALTHCHECK_URL"; then
        healthy=1
        break
    fi
    sleep 2
done
trap - ERR
if [ -z "$healthy" ]; then
    log "health check failed"
    rollback
    exit 1
fi

log "removing old releases and backups"
cd "$APP_DIR/releases"
current_name=$(basename "$(readlink -f "$APP_DIR/current")")
# Release names are commit SHAs, so parsing ls is safe here
# shellcheck disable=SC2010,SC2012
{ ls -1t | grep -vx "$current_name" || true; } | tail -n +"$KEEP_RELEASES" | xargs -r rm -rf --
# shellcheck disable=SC2012
{ ls -1t "$BACKUPS"/db-*.sqlite3 2>/dev/null || true; } | tail -n +"$((KEEP_BACKUPS + 1))" | xargs -r rm -f --

log "deployed $RELEASE_ID"
