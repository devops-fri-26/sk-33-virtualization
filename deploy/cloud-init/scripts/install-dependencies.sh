#!/bin/bash

set -euo pipefail
. "$(dirname "$0")/common.sh"
log "apt repos: Caddy, Node.js"

# Caddy and Node 24 (for Vite 8) aren't in Ubuntu's own repositories in the needed versions. Each repository's key is
# pinned to that repository only (signed-by) instead of being trusted for all of them. Everything else comes from
# packages: in user-data.yaml.
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" \
    > /etc/apt/sources.list.d/caddy-stable.list

curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | gpg --dearmor --yes -o /usr/share/keyrings/nodesource.gpg
echo "deb [signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_24.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list

# apt must not ask questions: there's no terminal
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q caddy nodejs
