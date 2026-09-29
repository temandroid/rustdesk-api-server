#!/bin/bash
# Docker deploy: builds the image on the server and runs deploy/docker-compose.yml.
# Called by remote-deploy.sh (DEPLOY_METHOD=docker):
#   remote-deploy-docker.sh <app_dir> <release_id>
# Layout of <app_dir>:
#   releases/<release_id>/  uploaded code
#   shared/.env             settings (SECRET_KEY, ALLOWED_HOSTS, ...)
#   shared/db/              SQLite database, mounted into the container
#   backups/                database backups made before each deploy
#   current_release         id of the running release
set -euo pipefail

APP_DIR=${1:?usage: remote-deploy-docker.sh <app_dir> <release_id>}
RELEASE_ID=${2:?usage: remote-deploy-docker.sh <app_dir> <release_id>}
RELEASE="$APP_DIR/releases/$RELEASE_ID"
ENV_FILE="$APP_DIR/shared/.env"
DB_DIR="$APP_DIR/shared/db"
BACKUPS="$APP_DIR/backups"
COMPOSE_FILE="$RELEASE/deploy/docker-compose.yml"
KEEP_RELEASES=${KEEP_RELEASES:-5}
KEEP_BACKUPS=${KEEP_BACKUPS:-10}

log() { echo "[deploy] $*"; }

[ -d "$RELEASE" ] || { log "release $RELEASE not found"; exit 1; }
[ -f "$ENV_FILE" ] || { log "$ENV_FILE not found, see README"; exit 1; }

HEALTHCHECK_URL=$(sed -n 's/^HEALTHCHECK_URL=//p' "$ENV_FILE" | tail -n 1)
HEALTHCHECK_URL=${HEALTHCHECK_URL:-http://127.0.0.1:21114/api/user_action}

# Used by docker-compose.yml; the container runs as the deploy user
APP_UID=$(id -u)
APP_GID=$(id -g)
export APP_DIR APP_UID APP_GID

compose() { IMAGE_TAG="$1" docker compose -f "$COMPOSE_FILE" "${@:2}"; }

PREVIOUS=$(cat "$APP_DIR/current_release" 2>/dev/null || true)

log "building image rustdesk-api:$RELEASE_ID"
docker build --quiet --tag "rustdesk-api:$RELEASE_ID" "$RELEASE"

mkdir -p "$DB_DIR" "$BACKUPS"
compose "$RELEASE_ID" run --rm --no-deps api python manage.py check

BACKUP=""
if [ -f "$DB_DIR/db.sqlite3" ]; then
    BACKUP="$BACKUPS/db-$(date +%Y%m%d-%H%M%S)-$RELEASE_ID.sqlite3"
    log "backing up database to $BACKUP"
    # SQLite online backup: consistent while the running server writes to the database
    docker run --rm --user "$APP_UID:$APP_GID" \
        -v "$DB_DIR:/db" -v "$BACKUPS:/backups" "rustdesk-api:$RELEASE_ID" \
        python -c "import sqlite3, sys; sqlite3.connect('/db/db.sqlite3').backup(sqlite3.connect(sys.argv[1]))" \
        "/backups/$(basename "$BACKUP")"
fi

rollback() {
    log "deploy failed, rolling back"
    if [ -n "$BACKUP" ]; then
        cp "$BACKUP" "$DB_DIR/db.sqlite3"
    fi
    if [ -n "$PREVIOUS" ]; then
        compose "$PREVIOUS" up -d || true
        echo "$PREVIOUS" > "$APP_DIR/current_release"
        log "rolled back to $PREVIOUS"
    else
        compose "$RELEASE_ID" down || true
    fi
}
trap rollback ERR

log "applying migrations"
compose "$RELEASE_ID" run --rm --no-deps api python manage.py migrate --noinput

log "starting $RELEASE_ID"
compose "$RELEASE_ID" up -d
echo "$RELEASE_ID" > "$APP_DIR/current_release"

log "checking $HEALTHCHECK_URL"
healthy=""
for _ in $(seq 1 30); do
    if curl -fs -o /dev/null "$HEALTHCHECK_URL"; then
        healthy=1
        break
    fi
    sleep 2
done
trap - ERR
if [ -z "$healthy" ]; then
    log "health check failed, container logs:"
    docker logs --tail 50 rustdesk-api || true
    rollback
    exit 1
fi

log "removing old releases, images and backups"
# Release ids are commit SHAs, so parsing ls is safe here
# shellcheck disable=SC2010,SC2012
{ ls -1t "$APP_DIR/releases" | grep -vx "$RELEASE_ID" || true; } | tail -n +"$KEEP_RELEASES" | while read -r old; do
    rm -rf "${APP_DIR:?}/releases/$old"
    docker image rm "rustdesk-api:$old" >/dev/null 2>&1 || true
done
# shellcheck disable=SC2012
{ ls -1t "$BACKUPS"/db-*.sqlite3 2>/dev/null || true; } | tail -n +"$((KEEP_BACKUPS + 1))" | xargs -r rm -f --

log "deployed $RELEASE_ID"
