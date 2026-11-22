#!/bin/bash

set -euo pipefail

# Site config from ../files; Ubuntu's default "Welcome to nginx" site is switched off.
install -m 644 /vagrant/files/nginx-varsis.conf /etc/nginx/sites-available/varsis
ln -sf /etc/nginx/sites-available/varsis /etc/nginx/sites-enabled/varsis
rm -f /etc/nginx/sites-enabled/default

# The certificate is Ubuntu's self-signed "snakeoil" certificate, created by the ssl-cert package. A real one
# (Let's Encrypt) needs a public domain, which a development VM doesn't have.
nginx -t
systemctl reload-or-restart nginx

# Firewall: only SSH (vagrant ssh) and HTTPS from outside. The backend (8000), PostgreSQL (5432) and Mailpit
# (1025, 8025) listen on 127.0.0.1 only anyway.
ufw allow 22/tcp
ufw allow 443/tcp
ufw --force enable
