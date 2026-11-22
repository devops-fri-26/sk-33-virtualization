#!/bin/bash

set -euo pipefail
. "$(dirname "$0")/common.sh"

# Database password and SECRET_KEY (signs session cookies and email links). Generated once, on this VM: never in the
# repository or the user data, and running the setup again keeps them (otherwise everyone would be logged out).
# umask 077: the file is readable only by root (600) from the moment it's created.
if [ ! -f /etc/varsis/secrets.env ]; then
    log "generate secrets"
    umask 077
    printf 'DB_PASSWORD=%s\nSECRET_KEY=%s\n' "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" \
        > /etc/varsis/secrets.env
fi
