#!/bin/bash

set -euo pipefail

# Mailpit isn't packaged in Ubuntu's apt repositories: a pinned release from GitHub, downloaded only if this version
# isn't installed yet.
MAILPIT_VERSION=v1.33.0

if [ "$(/usr/local/bin/mailpit version 2>/dev/null | awk '{print $2}')" != "$MAILPIT_VERSION" ]; then
    curl -fsSL "https://github.com/axllent/mailpit/releases/download/$MAILPIT_VERSION/mailpit-linux-$(dpkg --print-architecture).tar.gz" \
        | tar -xz -C /usr/local/bin mailpit
fi
