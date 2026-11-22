#!/bin/bash

set -euo pipefail
. "$(dirname "$0")/common.sh"
log "frontend"

# npm ci installs exactly what package-lock.json lists. The build output (dist/) is plain HTML/JS/CSS that Caddy
# serves: Node.js is only a build tool here.
cd /opt/varsis/frontend
npm ci --no-audit --no-fund
npm run build

rm -rf /var/www/varsis
install -d /var/www
cp -r dist /var/www/varsis
