#!/bin/bash

set -euo pipefail

# systemd starts both at boot and restarts them if they crash. The unit files are in ../files.
install -m 644 /vagrant/files/varsis-backend.service /vagrant/files/mailpit.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now mailpit varsis-backend
# restart: pick up new code and settings when provisioning again
systemctl restart mailpit varsis-backend

# Wait until the backend answers (it creates the database tables at startup)
for i in $(seq 30); do
    curl -fs http://127.0.0.1:8000/api/health >/dev/null && break
    sleep 2
done
curl -fs http://127.0.0.1:8000/api/health >/dev/null || { echo "Backend not healthy: journalctl -u varsis-backend"; exit 1; }
echo "Backend is up"
