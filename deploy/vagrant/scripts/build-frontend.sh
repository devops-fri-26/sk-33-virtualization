#!/bin/bash

set -euo pipefail

# npm ci installs exactly what package-lock.json lists. The build output (dist/) is plain HTML/JS/CSS: nginx serves
# it, Node.js isn't needed after this. Built as root (the code is root's), so the served files are root's too.
cd /opt/varsis/frontend
npm ci --no-audit --no-fund
npm run build

rsync -a --delete dist/ /var/www/varsis/
