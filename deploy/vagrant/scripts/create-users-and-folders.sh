#!/bin/bash

set -euo pipefail

# The app runs as its own system user: no login shell, no password. If the backend were compromised, the attacker
# would only have this user's rights.
if id varsis &>/dev/null; then
    echo "User varsis already exists"
else
    useradd --system --home-dir /var/lib/varsis --shell /usr/sbin/nologin varsis
fi

install -d -o varsis -g varsis /opt/varsis                        # code
install -d -o root -g varsis -m 750 /etc/varsis                   # settings and secrets (root writes, varsis reads)
install -d -o varsis -g varsis -m 750 /var/lib/varsis             # data, and the varsis user's home (uv/npm caches)
install -d -o varsis -g varsis -m 750 /var/lib/varsis/music /var/lib/varsis/covers
install -d -o root -g root -m 755 /var/www/varsis                 # built frontend, served by nginx
