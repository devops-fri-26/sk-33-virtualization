#!/usr/bin/env bash
# Boot user-data.yaml in a local QEMU VM, set up for testing: no domain, Mailpit instead of a mail provider.
# Needs only qemu-system-x86_64, qemu-img, curl and python3; no root, no bridge (ports are forwarded):
#
#   https://localhost:8443            the app (accept the certificate warning: Caddy's own CA)
#   https://localhost:8443/mailpit/   sent mails, user "mailpit", password: see below
#   ssh -p 2222 ubuntu@localhost      your ~/.ssh/*.pub keys are authorized
#
# Usage: deploy/cloud-init/run-qemu.sh [--reset]
#   First run: downloads Ubuntu 24.04 and runs the whole setup (~5-10 min, log in the terminal).
#   Later runs boot the same VM again. --reset throws it away for a fresh first boot.
#   Stop the VM: Ctrl-A then X (or `sudo poweroff` inside).
#
# Settings (environment): ADMIN_EMAIL (default admin@example.com), REPO_REF (branch to deploy, default: as in
# user-data.yaml), HTTPS_PORT (8443), SSH_PORT (2222), SEED_PORT (8471), CPUS (2), MEMORY (2G),
# VM_DIR (~/.cache/varsis-qemu). Changing them needs --reset: they're applied at first boot.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
dir=${VM_DIR:-$HOME/.cache/varsis-qemu}
https_port=${HTTPS_PORT:-8443}
ssh_port=${SSH_PORT:-2222}
seed_port=${SEED_PORT:-8471}
img_url=https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img

for cmd in qemu-system-x86_64 qemu-img curl python3; do
  command -v "$cmd" >/dev/null || { echo "missing: $cmd" >&2; exit 1; }
done

mkdir -p "$dir/seed"
cd "$dir"
[ "${1:-}" = "--reset" ] && rm -f disk.qcow2

# 1. Ubuntu cloud image, once, checked against Ubuntu's published SHA256SUMS.
if [ ! -f base.img ]; then
  echo "Downloading Ubuntu 24.04 cloud image..."
  curl -fL -o base.img.part "$img_url"
  curl -fsSL "${img_url%/*}/SHA256SUMS" | grep ' \*\?noble-server-cloudimg-amd64.img$' \
    | awk '{print $1 "  base.img.part"}' | sha256sum -c --quiet -
  mv base.img.part base.img
fi

# 2. New VM: a thin disk on top of the image, and the cloud-init settings for this test setup.
if [ ! -f disk.qcow2 ]; then
  qemu-img create -q -f qcow2 -F qcow2 -b base.img disk.qcow2 15G
  edits=(-e "s|^      SITE=$|      SITE=localhost:$https_port|"
         -e "s|^      MAILPIT=false$|      MAILPIT=true|"
         -e "s|^      ADMIN_EMAILS=$|      ADMIN_EMAILS=${ADMIN_EMAIL:-admin@example.com}|")
  [ -n "${REPO_REF:-}" ] && edits+=(-e "s|^      REPO_REF=.*|      REPO_REF=$REPO_REF|")
  sed "${edits[@]}" "$here/user-data.yaml" > seed/user-data
  keys=$(cat "$HOME"/.ssh/*.pub 2>/dev/null || true)
  if [ -n "$keys" ]; then
    { echo "ssh_authorized_keys:"; sed 's/^/  - /' <<<"$keys"; } >> seed/user-data
  else
    echo "No ~/.ssh/*.pub key: you won't be able to log in (ssh-keygen, then --reset)." >&2
  fi
  # A new instance-id makes cloud-init treat this disk as a first boot.
  printf 'instance-id: varsis-%s\nlocal-hostname: varsis\n' "$(date +%s)" > seed/meta-data
fi

# 3. cloud-init's NoCloud source fetches the settings over HTTP. Inside the VM, the host's 127.0.0.1 is 10.0.2.2.
python3 -m http.server "$seed_port" --bind 127.0.0.1 --directory seed >/dev/null 2>&1 &
seed_pid=$!
trap 'kill $seed_pid 2>/dev/null' EXIT

accel=(-accel tcg)
if [ -w /dev/kvm ]; then
  accel=(-enable-kvm -cpu host)
else
  echo "No access to /dev/kvm: the VM runs without hardware acceleration and is very slow." >&2
fi

cat <<EOF
App:      https://localhost:$https_port   (ready when the log says "[varsis-setup] done")
Mailpit:  https://localhost:$https_port/mailpit/   user "mailpit", password:
          ssh -p $ssh_port ubuntu@localhost sudo grep MAILPIT_PASSWORD /etc/varsis/secrets.env
Stop:     Ctrl-A then X
EOF

qemu-system-x86_64 "${accel[@]}" -smp "${CPUS:-2}" -m "${MEMORY:-2G}" \
  -drive file=disk.qcow2,if=virtio \
  -smbios "type=1,serial=ds=nocloud;s=http://10.0.2.2:$seed_port/" \
  -netdev "user,id=net0,hostfwd=tcp:127.0.0.1:$https_port-:443,hostfwd=tcp:127.0.0.1:$ssh_port-:22" \
  -device virtio-net-pci,netdev=net0 \
  -nographic
