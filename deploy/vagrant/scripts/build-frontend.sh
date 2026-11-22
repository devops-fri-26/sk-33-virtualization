#!/bin/bash

set -euo pipefail

# npm ci installs exactly what package-lock.json lists. The build output (dist/) is plain HTML/JS/CSS: nginx serves
# it, Node.js isn't needed after this.
cd /opt/varsis/frontend
sudo -u varsis npm ci --no-audit --no-fund
sudo -u varsis npm run build

rsync -a --delete dist/ /var/www/varsis/
