#!/bin/bash
# Entry point of the CI deploy job, run on the server over SSH:
#   remote-deploy.sh <app_dir> <release_id>
# Picks the deploy method from DEPLOY_METHOD in <app_dir>/shared/.env:
#   docker  (default) - image built on the server, started with docker compose
#   systemd           - Python virtual environment on the host and a systemd service
set -euo pipefail

APP_DIR=${1:?usage: remote-deploy.sh <app_dir> <release_id>}
RELEASE_ID=${2:?usage: remote-deploy.sh <app_dir> <release_id>}
ENV_FILE="$APP_DIR/shared/.env"

[ -f "$ENV_FILE" ] || { echo "[deploy] $ENV_FILE not found, see README"; exit 1; }
METHOD=$(sed -n 's/^DEPLOY_METHOD=//p' "$ENV_FILE" | tail -n 1 | tr -d '"'"'"' \r')
METHOD=${METHOD:-docker}

case "$METHOD" in
    docker|systemd) ;;
    *) echo "[deploy] unknown DEPLOY_METHOD '$METHOD', use docker or systemd"; exit 1 ;;
esac

echo "[deploy] method: $METHOD"
exec bash "$(dirname "$0")/remote-deploy-$METHOD.sh" "$APP_DIR" "$RELEASE_ID"
