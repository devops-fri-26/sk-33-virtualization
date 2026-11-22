# Varsis with cloud-init

One Ubuntu 24.04 VM, set up entirely from [`user-data.yaml`](user-data.yaml) at first boot. No Docker: every
component comes from an apt repository and runs as a systemd service.

```
browser ──https──▶ Caddy :443 ──┬── /api/*  ──▶ uvicorn (FastAPI) 127.0.0.1:8000 ──▶ PostgreSQL 127.0.0.1:5432
                                └── /*      ──▶ /var/www/varsis (built Vue app)
```

| Component | Source | Notes |
|---|---|---|
| Caddy | Caddy's apt repo (cloudsmith) | HTTPS (Let's Encrypt or own CA), HSTS and security headers, body size limits, JSON access log |
| Backend | `/opt/varsis/backend`, Python 3.13 from the deadsnakes PPA, packages from `uv.lock` | `varsis-backend.service`, own `varsis` user, sandboxed (`ProtectSystem=strict`, writes only `/var/lib/varsis`) |
| PostgreSQL 16 | Ubuntu | Listens on localhost only; password generated at first boot |
| Frontend | Node 24 from NodeSource, `npm ci && npm run build` | Only the build output is served |
| ufw | Ubuntu | Open: 22, 80, 443 |

## Settings

Edit the `/etc/varsis/deploy.env` block at the top of `write_files` in `user-data.yaml`:

| Variable | Meaning |
|---|---|
| `DOMAIN` | Public host name. Its DNS points at the VM and ports 80/443 are reachable: Caddy gets a Let's Encrypt certificate. **Empty** (local VM): the VM's IP with a certificate from Caddy's local CA |
| `SITE` | Only for a VM reached through port forwarding: the address the browser opens, e.g. `localhost:8443`. Empty: `DOMAIN`, or the VM's IP |
| `REPO_URL`, `REPO_REF` | What to deploy |
| `ADMIN_EMAILS` | Comma-separated admin accounts |
| `SMTP_*` | Mail provider for sign-up and password mails. Empty: no mails are sent |
| `MAILPIT` | Testing only. `true`: installs [Mailpit](https://mailpit.axllent.org) on the VM and sends all mail there instead of `SMTP_*`. Inbox at `https://<site>/mailpit/`, user `mailpit`, password `MAILPIT_PASSWORD` in `/etc/varsis/secrets.env` |

`SECRET_KEY` and the database password are never in the repo: the VM generates them into
`/etc/varsis/secrets.env` (mode 600).

## Deploy on a server

On any cloud provider with Ubuntu 24.04 (Hetzner, DigitalOcean, AWS, …):

1. Copy `user-data.yaml` and fill in `DOMAIN`, `ADMIN_EMAILS` and `SMTP_*`; keep `MAILPIT=false`.
2. Create the server with Ubuntu 24.04 and paste the file into the **user data / cloud-init** field
   (at least 2 GB of memory: the frontend build needs it).
3. Point the domain's DNS A record at the server's IP. Caddy gets the certificate once DNS resolves.
4. Follow the setup over SSH: `tail -f /var/log/cloud-init-output.log` (ends with `[varsis-setup] done`).

## Run locally with Incus

An Incus VM boots the same Ubuntu cloud image and runs cloud-init the same way a cloud server does, so this
tests exactly what the server will run.

Install once (Arch: `sudo pacman -S incus edk2-ovmf`; Ubuntu: `sudo apt install incus`):

```bash
sudo systemctl enable --now incus.socket
sudo usermod -aG incus-admin $USER && newgrp incus-admin
incus admin init --minimal
# If the host runs ufw, let the VM bridge through (DHCP, internet access):
sudo ufw allow in on incusbr0 && sudo ufw route allow in on incusbr0 && sudo ufw route allow out on incusbr0
```

A dev copy of the settings with Mailpit on (no domain, no real SMTP):

```bash
cp deploy/cloud-init/user-data.yaml ~/varsis-dev.yaml
sed -i -e 's/^      MAILPIT=false/      MAILPIT=true/' \
       -e 's/^      ADMIN_EMAILS=/      ADMIN_EMAILS=you@example.com/' ~/varsis-dev.yaml
```

Launch it (`/cloud` images include cloud-init; 2 GB of memory is needed for the frontend build):

```bash
incus launch images:ubuntu/24.04/cloud varsis --vm \
  -c limits.cpu=2 -c limits.memory=2GiB -d root,size=15GiB \
  -c cloud-init.user-data="$(cat ~/varsis-dev.yaml)"
incus list varsis                # IPv4 address
```

Follow the setup while it runs (right after launch this can fail until the VM agent is up; run it again):

```bash
incus exec varsis -- tail -f /var/log/cloud-init-output.log   # ends with "[varsis-setup] done"
incus exec varsis -- cloud-init status --long
```

Open `https://<IPv4>` and accept the certificate warning (Caddy's own CA; with `DOMAIN` set it's a real one).
Start over with a fresh first boot: `incus delete -f varsis`, then launch again.


## Check it

```bash
incus shell varsis               # on a server: ssh
systemctl status varsis-backend caddy postgresql
curl -s http://127.0.0.1:8000/api/health
sudo journalctl -u varsis-backend -f          # backend log
sudo tail -f /var/log/caddy/varsis-access.log # requests
sudo ufw status
```

### Mails with Mailpit

With `MAILPIT=true`, open `https://<IPv4>/mailpit/` and log in as `mailpit` with the password from:

```bash
incus exec varsis -- grep MAILPIT_PASSWORD /etc/varsis/secrets.env
```

### First account without SMTP

Sign-up sends a verification mail. Without `SMTP_*` set, mark the account verified by hand (an address in
`ADMIN_EMAILS` is then admin and approved; others also need `is_approved`):

```bash
sudo -u postgres psql varsis -c "UPDATE users SET is_verified = true WHERE email = 'you@example.com'"
```

## Why the order works

cloud-init runs its modules in stages:

1. **init**: `write_files`, then `users-groups`. Files are written *before* the `varsis` user exists, so none of
   them is owned by it (otherwise `defer: true` would be needed). Ownership of the data folders is set later
   in the setup script.
2. **config**: `apt` (adds the deadsnakes PPA) and `runcmd`, which only *saves* the commands as a script.
3. **final**: `package-update-upgrade-install` installs `packages:`, then `scripts-user` *executes* the runcmd
   script. So `runcmd` already runs after all packages are installed.

`runcmd` clones the repository and runs the setup scripts from it, one per step, like the Vagrant version:
[`scripts/`](scripts) (`install-dependencies.sh`, `firewall.sh`, `secrets.sh`, `setup-mailpit.sh`,
`setup-postgresql.sh`, `setup-backend.sh`, `build-frontend.sh`, `start-caddy.sh`, `health-check.sh`), with the config
files they install in [`files/`](files). The first step adds the Caddy and NodeSource repos (keys pinned with
`signed-by`), so those two packages are installed there and not in `packages:`. Everything can run again: the
clone, the secrets and the database are skipped if they already exist.

The VM gets the scripts by cloning `REPO_URL` at `REPO_REF`, so that repository must be public, and a changed
script reaches new VMs only after it's pushed there.

## Update to a newer commit

```bash
sudo git -C /opt/varsis pull && sudo sh /var/lib/cloud/instance/scripts/runcmd
```
