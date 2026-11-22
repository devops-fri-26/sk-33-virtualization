#!/bin/bash

set -euo pipefail

# Mailpit isn't packaged in Ubuntu's apt repositories: a pinned release from GitHub, downloaded only if this version
# isn't installed yet.
MAILPIT_VERSION=v1.33.0
# SHA-256 of that release's mailpit-linux-amd64.tar.gz (GitHub shows it next to the file on the release page). A
# download that doesn't match (replaced or damaged) stops the provisioning before anything is installed. amd64 only:
# another architecture needs its own file and hash.
MAILPIT_SHA256=d0ec50080cbf3e7c1fa2cda2ee68125d7894175811084b1f8f47c6cfc6f487c8

# The version is the 2nd word of the first line of `mailpit version` (later lines may announce a newer release).
if [ "$(/usr/local/bin/mailpit version 2>/dev/null | awk 'NR==1{print $2}')" != "$MAILPIT_VERSION" ]; then
    tmp=$(mktemp)
    trap 'rm -f "$tmp"' EXIT
    curl -fsSL -o "$tmp" "https://github.com/axllent/mailpit/releases/download/$MAILPIT_VERSION/mailpit-linux-amd64.tar.gz"
    echo "$MAILPIT_SHA256  $tmp" | sha256sum -c -
    tar -xzf "$tmp" -C /usr/local/bin mailpit
fi
