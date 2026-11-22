# Sourced (not run) by every step: settings, secrets, helpers.

# Settings from user-data.yaml, and the secrets once secrets.sh has created them. set -a exports every variable
# defined until set +a.
set -a
. /etc/varsis/deploy.env
if [ -f /etc/varsis/secrets.env ]; then
    . /etc/varsis/secrets.env
fi
set +a

# Config files that come with these scripts (Caddyfile template, systemd units)
FILES="$(cd "$(dirname "${BASH_SOURCE[0]}")/../files" && pwd)"

log() { echo "[varsis-setup] $*"; }

# SITE: the address in the browser and in mail links. SITE_HOST: what Caddy serves and makes a certificate for.
# They differ only with port forwarding (localhost:8443 -> the VM's 443): Caddy matches the host name.
# TLS: empty = Let's Encrypt (public domain); "tls internal" = Caddy's own CA (local VM).
if [ -n "$DOMAIN" ]; then
    SITE=$DOMAIN
    TLS=""
else
    SITE=${SITE:-$(hostname -I | awk '{print $1}')}
    TLS="tls internal"
fi
SITE_HOST=${SITE%:*}
