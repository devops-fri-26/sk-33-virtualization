#!/bin/bash

set -euo pipefail

# The synced folder (/varsis-src) belongs to the vagrant user and is replaced on every `vagrant rsync`. The app gets
# its own copy, owned by root: the varsis user runs the backend but can't change its code (and the sandbox makes it
# read-only anyway). --delete removes files that were deleted in the repository; the excluded folders are built
# inside the VM and kept.
rsync -a --delete --exclude .venv --exclude node_modules --exclude dist /varsis-src/ /opt/varsis/
chown -R root:root /opt/varsis

# Exactly the package versions in uv.lock (--frozen fails instead of changing it), without the dev tools, with the
# Python 3.13 from apt (no downloaded Python). As root, like the rest of the code; the service only reads the venv.
cd /opt/varsis/backend
UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1 uv sync --frozen --no-dev --python python3.13
