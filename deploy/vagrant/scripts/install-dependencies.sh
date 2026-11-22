#!/bin/bash

set -euo pipefail

# apt must not ask questions during provisioning
export DEBIAN_FRONTEND=noninteractive

# Python 3.13: the backend needs >= 3.13, Ubuntu 24.04 ships 3.12. The deadsnakes PPA has newer versions.
add-apt-repository -y -n ppa:deadsnakes/ppa

# Node.js 24 (the frontend build needs it; Ubuntu's own is too old). NodeSource's apt repository, with its key
# pinned to this repository only (signed-by) instead of trusting it for every repository.
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
  | gpg --dearmor --yes -o /usr/share/keyrings/nodesource.gpg
echo "deb [signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_24.x nodistro main" \
  > /etc/apt/sources.list.d/nodesource.list

# Packages:
# - nginx: web server (HTTPS, static frontend files, proxy to the backend and Mailpit)
# - ssl-cert: generates the self-signed "snakeoil" certificate nginx uses
# - postgresql: database
# - python3.13, python3.13-venv: runs the backend
# - pipx: installs uv, which installs the backend's exact package versions from uv.lock
# - nodejs: builds the frontend (not needed at runtime)
# - rsync: copies the synced code into place
# - ufw: firewall
apt-get update
apt-get install -y nginx ssl-cert postgresql python3.13 python3.13-venv pipx nodejs rsync ufw curl

# uv, installed with pipx for all users, at a pinned version (it reads this uv.lock); reinstalled only when another
# version is there.
UV_VERSION=0.13.6
if [ "$(uv --version 2>/dev/null | awk '{print $2}')" != "$UV_VERSION" ]; then
    PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx install --force "uv==$UV_VERSION"
fi
