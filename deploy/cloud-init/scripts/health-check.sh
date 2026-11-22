#!/bin/bash

set -euo pipefail
. "$(dirname "$0")/common.sh"

# The backend creates its database tables at startup: give it up to a minute. If it never answers, this fails, so
# cloud-init reports the deployment as failed instead of "done" with a broken app.
for i in $(seq 30); do
    if curl -fs http://127.0.0.1:8000/api/health >/dev/null; then
        log "done: https://$SITE"
        exit 0
    fi
    sleep 2
done
log "backend not healthy: journalctl -u varsis-backend"
exit 1
