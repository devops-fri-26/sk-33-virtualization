#!/bin/bash

set -euo pipefail
. "$(dirname "$0")/common.sh"
log "caddy ($SITE)"

install -d -o caddy -g caddy /var/log/caddy

# Mailpit's inbox behind a password (bcrypt hash), and the matcher that keeps X-Frame-Options DENY off it (Mailpit
# shows mails in a frame of its own). Without Mailpit: an empty file, and DENY on every path.
if [ "${MAILPIT:-false}" = "true" ]; then
    cat > /etc/caddy/mailpit.caddy <<CADDY
handle /mailpit* {
	basic_auth {
		mailpit $(caddy hash-password --plaintext "$MAILPIT_PASSWORD")
	}
	header X-Frame-Options SAMEORIGIN
	reverse_proxy 127.0.0.1:8025
}
CADDY
    FRAMED="not path /mailpit*"
else
    : > /etc/caddy/mailpit.caddy
    FRAMED="path *"
fi

# Fill in the template. TLS empty = Let's Encrypt for DOMAIN; "tls internal" = Caddy's own CA (local VM).
sed -e "s|__SITE__|$SITE_HOST|" -e "s|__TLS__|$TLS|" -e "s|__FRAMED__|$FRAMED|" \
    "$FILES/Caddyfile.tmpl" > /etc/caddy/Caddyfile

# Check it before loading, so a broken config stops the setup instead of Caddy. As the caddy user: validate opens
# the log file, and as root it would create it owned by root (the caddy service couldn't write it).
runuser -u caddy -- caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl reload-or-restart caddy
