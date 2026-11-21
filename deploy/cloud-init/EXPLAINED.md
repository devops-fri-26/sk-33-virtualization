# user-data.yaml, step by step

A walk through [`user-data.yaml`](user-data.yaml) in the order things happen on the VM. Line numbers refer to
that file.

## 0. The big picture

When a VM boots for the first time, **cloud-init** reads the "user data" the hypervisor or cloud handed it
(Incus: `-c cloud-init.user-data=...`; a cloud provider: the "user data" field). A file that starts with `#cloud-config` is YAML. Each top-level key
(`packages`, `users`, `write_files`, `runcmd`…) is handled by one cloud-init **module**.

The modules don't run in the order they appear in the file. They run in a fixed order, split into boot stages
(the list is in `/etc/cloud/cloud.cfg` on the VM):

| Stage | Modules used here | What happens |
|---|---|---|
| **init** (network is up) | `write_files`, `users_groups` | Files are written, then users are created |
| **config** | `apt_configure`, `runcmd` | The deadsnakes PPA is added; runcmd is *saved* as a shell script, not run |
| **final** (end of boot) | `package_update_upgrade_install`, `scripts_user`, `final_message` | `apt update` + install `packages:`, then the saved runcmd script runs |

Two consequences shape the file:

- **`write_files` runs before `users`.** A file can't be `owner: varsis:varsis`, because that user doesn't exist
  yet (cloud-init would fail). The fix is either `defer: true` (write it in the final stage) or, as done here,
  owning nothing by `varsis` in `write_files` and setting ownership later in the script.
- **`runcmd` runs after `packages`.** Postgres, git and Python are already installed when the script starts.

The design: **cloud-config declares what's static** (packages, a user, config files) and **one bash script does
everything that needs logic** (if/else, generated secrets, building). runcmd only calls that script.

---

## 1. Header and comments (lines 1–12)

```yaml
#cloud-config
```

This first line is required. Without it cloud-init doesn't treat the file as cloud-config. The comments below it
summarize the stage order from section 0.

## 2. Package settings (lines 14–15)

```yaml
package_update: true
package_upgrade: false
```

- `package_update: true` runs `apt-get update` before installing anything, so the package lists are current.
- `package_upgrade: false` skips `apt-get upgrade` of the whole system. That saves minutes on first boot. Ubuntu
  cloud images have **unattended-upgrades** enabled, which installs security updates in the background anyway.

## 3. Extra apt source: deadsnakes (lines 17–20)

```yaml
apt:
  sources:
    deadsnakes:
      source: ppa:deadsnakes/ppa
```

The backend's `pyproject.toml` requires Python ≥ 3.13, and Ubuntu 24.04 only has 3.12. The deadsnakes PPA
(Personal Package Archive on Launchpad) packages newer Pythons for Ubuntu. cloud-init adds it in the config stage
and fetches its signing key from the Ubuntu keyserver, so it's ready before `packages:` is installed.

Why not let `uv` download Python? See the end of this document.

## 4. Packages (lines 22–30)

| Package | Why |
|---|---|
| `git` | Clone the app's repository |
| `curl` | Download the Caddy/NodeSource signing keys; health check |
| `gpg` | Convert those keys to the binary format apt wants (`--dearmor`) |
| `ufw` | Firewall frontend for iptables/nftables |
| `postgresql` | Database server (version 16 on 24.04). The package creates the `postgres` user and starts the service |
| `python3.13`, `python3.13-venv` | Runtime for the backend (from deadsnakes) |
| `pipx` | Installs Python CLI tools in isolated venvs. Used to install `uv` |

Caddy and Node.js aren't here because their apt repositories are added later by the script (section 9.1).

## 5. Users (lines 32–38)

```yaml
users:
  - default
  - name: varsis
    system: true
    shell: /usr/sbin/nologin
    homedir: /var/lib/varsis
    no_create_home: true
```

- `default` keeps the image's normal user (`ubuntu`), which is the SSH login on cloud servers. Without this
  line the list would *replace* it.
- `varsis` is the account the backend runs as:
  - `system: true` gives a UID below 1000, with no password and no aging. It's a service account, not a person.
  - `shell: /usr/sbin/nologin`: nobody can log in as it.
  - `homedir` is the data folder; `no_create_home` because the script creates that folder itself with the right
    permissions.

**Why a separate user:** if someone found a bug in the backend, they'd get the rights of `varsis`. That's only
its own data folder, not root.

## 6. write_files, part 1: settings (lines 42–61)

```yaml
- path: /etc/varsis/deploy.env
  permissions: "0600"
```

The **only place you edit before launching**. It's a list of `NAME=value` lines that bash reads later
(`. /etc/varsis/deploy.env`). Mode `0600` means only root can read it, because it may contain the SMTP password.

| Variable | Effect |
|---|---|
| `DOMAIN` | Empty: local VM, HTTPS on the VM's IP with a self-signed certificate. Set: a real Let's Encrypt certificate for that name |
| `REPO_URL`, `REPO_REF` | Which git repository and branch to deploy |
| `ADMIN_EMAILS` | Accounts the backend makes admin (and approves) at startup |
| `DEFAULT_QUOTA_GB` | Upload space per new user |
| `SMTP_*` | Mail server for verification and password-reset mails |

## 7. write_files, part 2: Caddy template (lines 64–106)

Saved as `/etc/varsis/Caddyfile.tmpl`, **not** directly as `/etc/caddy/Caddyfile`. Two reasons:

1. Caddy isn't installed yet when `write_files` runs. If `/etc/caddy/Caddyfile` already existed when the package
   was installed, dpkg would see a conflict with the package's own config file.
2. It contains two placeholders, `__SITE__` and `__TLS__`, that depend on `DOMAIN`. The script fills them in
   (section 9.8).

Line by line:

| Lines | Directive | What it does |
|---|---|---|
| 66 | `__SITE__ { … }` | Site address: a domain or an IP. Caddy enables HTTPS automatically for it and redirects `http://` to `https://` |
| 67 | `__TLS__` | Becomes `tls internal` (certificate from Caddy's own local CA) or nothing (default: Let's Encrypt via the ACME protocol) |
| 68 | `encode zstd gzip` | Compress responses (JS/CSS/JSON) if the browser supports it |
| 70–76 | `header { … }` | Security headers on every response: **HSTS** (the browser only uses https for this host for a year), **nosniff** (don't guess file types: an uploaded "song" must never run as HTML/JS), **X-Frame-Options DENY** (no embedding in other sites, against clickjacking), **Referrer-Policy same-origin** (tokens in email links don't leak to other sites), `-Server` removes the header that names the server software |
| 79–86 | `request_body … max_size` | `@upload` and `@small` are *named matchers*. Uploads may be up to 2 GB; every other request at most 1 MB, because the backend reads JSON bodies into memory and a huge body could exhaust it |
| 88–94 | `handle /api/*` + `reverse_proxy` | Everything under `/api/` goes to the backend on `127.0.0.1:8000` |
| 91 | `header_up X-Real-IP {remote_host}` | The backend's login rate limit counts attempts per IP and reads it from `X-Real-IP` (`backend/app/ratelimit.py`). Caddy *overwrites* the header with the real client address, so a client can't fake it |
| 92 | `flush_interval -1` | Pass response data on immediately instead of buffering. Needed for streaming audio |
| 96–100 | `handle` + `try_files` + `file_server` | Everything else is a static file from `/var/www/varsis`. `try_files {path} /index.html` serves `index.html` for paths that aren't files (e.g. `/album/12`), so the Vue router can handle them (single-page app) |
| 102–105 | `log` | Access log as JSON in `/var/log/caddy/varsis-access.log`. Caddy rotates it itself (by default at 100 MB) |

`handle` blocks are mutually exclusive and checked most specific first, so `/api/...` never falls through to the
file server.

**Why Caddy and not nginx:** Caddy gets and renews TLS certificates by itself; with nginx you'd need certbot plus
a renewal timer. It replaces both the old `frontend/nginx.conf` and the Caddy container from the Docker setup.

## 8. write_files, part 3: systemd service (lines 109–139)

`/etc/systemd/system/varsis-backend.service` tells systemd how to run the backend. It's written now but started
by the script, after the code and config exist.

**`[Unit]`**

- `After=network-online.target postgresql.service`: start only after the network and the database.
- `Requires=postgresql.service`: if Postgres is stopped, the backend is stopped too.

**`[Service]`**

- `User=varsis`, `Group=varsis`: drop root.
- `WorkingDirectory=/opt/varsis/backend`: so `app.main` is found as a Python module.
- `EnvironmentFile=/etc/varsis/backend.env`: settings as environment variables. The backend reads them with
  pydantic-settings (`backend/app/config.py`). systemd reads this file as root, so it can stay `0600`.
- `ExecStart=… uvicorn app.main:app --host 127.0.0.1 --port 8000`: the ASGI server from the project's venv. It
  only listens on localhost, so the backend is reachable only through Caddy.
- `Restart=on-failure`, `RestartSec=3`: restart after a crash.

**Sandboxing** (systemd features, no extra software). If the process were compromised:

| Setting | Effect |
|---|---|
| `NoNewPrivileges` | Can't gain privileges, e.g. via setuid programs like `sudo` |
| `ProtectSystem=strict` | The whole filesystem is read-only… |
| `ReadWritePaths=/var/lib/varsis` | …except the data folder |
| `ProtectHome` | `/home`, `/root` are invisible |
| `PrivateTmp` | Its own empty `/tmp`, not shared with other services |
| `PrivateDevices` | No access to `/dev` hardware devices |
| `ProtectKernelTunables/Modules`, `ProtectControlGroups` | Can't change kernel settings, load modules or edit cgroups |
| `RestrictSUIDSGID` | Can't create setuid/setgid files |

`systemd-analyze security varsis-backend` on the VM scores these settings.

**`[Install]`** `WantedBy=multi-user.target`: `systemctl enable` makes it start on every normal boot.

## 9. write_files, part 4: the setup script (lines 142–256)

`/usr/local/sbin/varsis-setup`, mode `0755` (executable). `sbin` because it's an admin tool meant for root.

### Preamble (lines 145–148)

```bash
set -euo pipefail
```

Bash "strict mode":

- `-e`: stop at the first command that fails.
- `-u`: using an unset variable is an error (catches typos).
- `-o pipefail`: a pipeline fails if *any* part fails, not only the last. Without it, a failed `curl` piped into
  `gpg` would go unnoticed.

```bash
set -a; . /etc/varsis/deploy.env; set +a
```

`.` (source) reads the settings file as bash. `set -a` auto-exports every variable it defines, `set +a` turns
that off again. `log()` prefixes messages with `[varsis-setup]` so they're easy to find in
`/var/log/cloud-init-output.log`.

### 9.1 Third-party apt repositories (lines 150–161)

For both Caddy and NodeSource:

1. `curl` downloads the repository's public signing key.
2. `gpg --dearmor` converts it from text (ASCII-armored) to binary and saves it in `/usr/share/keyrings/`.
3. A `deb [signed-by=<that key>] <url> <suite> main` line goes into `/etc/apt/sources.list.d/`.

`signed-by` means apt trusts this key **only for this one repository**. The old `apt-key add` way trusted every
key for every repository, so a compromised third-party key could sign fake Ubuntu packages.

Then `apt-get update` (read the new repos) and `apt-get install caddy nodejs`. `DEBIAN_FRONTEND=noninteractive`
stops dpkg from asking questions, since there's no terminal. The Caddy package also installs and starts
`caddy.service` and creates a `caddy` user. NodeSource's `node_24.x` is used because Vite 8 needs Node ≥ 20.19
and Ubuntu 24.04 ships Node 18.

### 9.2 Firewall (lines 163–168)

- `ufw allow OpenSSH`: port 22. Allowed **before** enabling, otherwise you'd lock yourself out of SSH.
- `ufw allow 80/tcp`: plain HTTP. Needed for Let's Encrypt's HTTP challenge and the http→https redirect.
- `ufw allow 443`: TCP for HTTPS, and UDP for HTTP/3 (QUIC), which Caddy also offers.
- `ufw --force enable`: turn it on without the "are you sure?" prompt. The default policy denies everything else
  incoming, so Postgres (5432) and the backend (8000) aren't reachable from outside even if they listened there.

### 9.3 Get the code (lines 170–174)

`git clone --depth 1` fetches only the latest commit (faster, smaller). The `if` skips it when it's already
there, so the script can run again.

### 9.4 Secrets (lines 176–184)

On the first run, two random values are generated with `openssl rand -hex 32` (32 random bytes = 64 hex
characters):

- `DB_PASSWORD`: for the `varsis` Postgres role.
- `SECRET_KEY`: signs login cookies and email links. Anyone who knows it can log in as any user; the backend
  refuses to start if it's shorter than 32 characters.

`umask 077` makes the new file readable only by root (mode 600) from the moment it's created; `umask 022` resets
that. Because of the `if`, secrets are created **once**: a second run must not change the DB password or log
everyone out. They're never in the repo or in user data, so publishing `user-data.yaml` leaks nothing.

### 9.5 Database (lines 186–196)

```bash
sudo -u postgres psql -v ON_ERROR_STOP=1 -q <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'varsis') THEN
    CREATE ROLE varsis LOGIN PASSWORD '$DB_PASSWORD';
  END IF;
END \$\$;
SQL
```

- `sudo -u postgres`: on Ubuntu, the Postgres superuser `postgres` logs in via **peer authentication**: the OS
  user name must match the database user name. No password is needed.
- `<<SQL … SQL` is a *here-document*: the lines between are psql's input. It's unquoted, so bash replaces
  `$DB_PASSWORD` with the value. `\$\$` is escaped so bash leaves it alone and Postgres gets `$$`, its quote
  marker for the `DO` block's code.
- `DO … IF NOT EXISTS`: Postgres has no `CREATE ROLE IF NOT EXISTS`, so a small PL/pgSQL block checks first. That
  keeps it re-runnable.
- `ON_ERROR_STOP=1`: psql exits with an error code on SQL errors, so `set -e` stops the script.
- Next line: `createdb -O varsis varsis` creates the database `varsis` owned by role `varsis`, unless the
  `SELECT` finds it already exists (`grep -q 1` succeeds → `||` skips `createdb`).

Postgres on Ubuntu listens only on `localhost` by default, and the backend connects to `127.0.0.1` with the
password (`scram-sha-256`).

The **tables** aren't created here: the backend creates them itself at startup (`Base.metadata.create_all` in
`backend/app/main.py`).

### 9.6 Backend (lines 198–232)

```bash
command -v uv >/dev/null || PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx install uv
```

Install **uv** (a fast Python package manager) unless it's already there. Setting `PIPX_HOME`/`PIPX_BIN_DIR`
makes it a system-wide install (`/usr/local/bin/uv`) instead of in root's home.

```bash
UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1 uv sync --frozen --no-dev --python python3.13
```

Creates `/opt/varsis/backend/.venv` and installs the backend's dependencies:

- `--frozen`: exactly the versions in `uv.lock`, no re-resolving. Same packages as in development; the build is
  reproducible.
- `--no-dev`: skip dev tools (ruff).
- `--python python3.13` + `UV_PYTHON_DOWNLOADS=never`: use the deadsnakes Python; fail instead of silently
  downloading another one.
- `UV_COMPILE_BYTECODE=1`: compile `.pyc` files now. The service can't write them later (`ProtectSystem=strict`),
  and startup is faster.

```bash
if [ -z "$DOMAIN" ]; then SITE=$(hostname -I | awk '{print $1}'); TLS="tls internal"; else SITE=$DOMAIN; TLS=""; fi
```

Picks the site address. `hostname -I` lists the VM's IPs; the first is the one `incus list` shows.

```bash
install -d -o varsis -g varsis -m 0750 /var/lib/varsis /var/lib/varsis/music /var/lib/varsis/covers
```

`install -d` creates folders and sets owner and mode in one step. Mode 0750 means other users on the VM can't
read the music.

Then `backend.env` is written with a here-document (again `umask 077` → mode 600). It builds `DATABASE_URL`
(`postgresql+asyncpg://` = SQLAlchemy with the async `asyncpg` driver) and `APP_URL` (used in email links; the
`https` also makes the login cookie `Secure`). If `SMTP_HOST` is empty, `${SMTP_HOST:-localhost}` puts in
`localhost`, where no mail server listens, so sending fails and is only logged.

Finally:

- `systemctl daemon-reload`: systemd reads the new unit file.
- `enable --now`: start on boot, and start now.
- `restart`: on a re-run, pick up a changed env file or new code.

### 9.7 Frontend (lines 234–241)

- `npm ci`: install exactly what `package-lock.json` says (the npm equivalent of `uv sync --frozen`).
  `--no-audit --no-fund` skips network calls that only print messages.
- `npm run build`: Vite compiles the Vue app into plain HTML/JS/CSS in `dist/`.
- The old copy is removed and `dist` is copied to `/var/www/varsis`, where Caddy serves it.

Node is only a **build tool**. Nothing Node-based runs afterwards.

### 9.8 Caddy (lines 243–248)

- `sed` replaces `__SITE__` and `__TLS__` in the template and writes the real `/etc/caddy/Caddyfile`.
- `caddy validate` checks the syntax first. If it's wrong, the script stops (`set -e`) instead of breaking the
  running Caddy.
- `reload-or-restart`: Caddy loads the new config without dropping connections. When it first sees the site
  address it gets the certificate: from Let's Encrypt (with a domain) or from its local CA (with an IP).

### 9.9 Health check (lines 250–256)

The backend is polled up to 30 times, 2 seconds apart, on `/api/health`. `curl -f` fails on HTTP errors. If it
never answers, the script exits with an error, so `cloud-init status` reports the deployment as **failed**
instead of "done" with a broken app. On success it prints the URL.

## 10. runcmd and final_message (lines 258–261)

```yaml
runcmd:
  - [/usr/local/sbin/varsis-setup]
```

The list form (`[...]`) runs the program directly, without a shell in between. All the logic lives in the
script, which is easier to read, test (`bash -n`) and run again by hand than many YAML lines.

`final_message` is printed to the console and log when cloud-init finishes; `$UPTIME` is the seconds since
boot, a handy measure of deployment speed.

---

## Timeline of a first boot

1. **init:** `/etc/varsis/{deploy.env,Caddyfile.tmpl}`, the systemd unit and the setup script are written; users
   `ubuntu` and `varsis` are created.
2. **config:** the deadsnakes PPA is added; runcmd is saved as a script.
3. **final:** `apt update`; git, curl, gpg, ufw, postgresql, python3.13, pipx are installed (Postgres starts).
4. **final, runcmd → varsis-setup:**
   1. Caddy and NodeSource repos → install `caddy`, `nodejs`
   2. firewall on
   3. clone the code
   4. generate secrets
   5. create DB role and database
   6. install backend deps, write `backend.env`, start the backend (it creates the tables)
   7. build the frontend
   8. configure Caddy (certificate)
   9. health check
5. `final_message` with the total time.

## Where things end up on the VM

| Path | Contents |
|---|---|
| `/etc/varsis/deploy.env` | Your settings (600) |
| `/etc/varsis/secrets.env` | Generated DB password and SECRET_KEY (600) |
| `/etc/varsis/backend.env` | Everything the backend gets as environment (600) |
| `/opt/varsis/` | The git checkout; `backend/.venv` is the Python environment |
| `/var/www/varsis/` | Built frontend |
| `/var/lib/varsis/{music,covers}` | Uploaded data (owner `varsis`, 750) |
| `/var/lib/postgresql/16/main` | Database files |
| `/etc/caddy/Caddyfile`, `/var/lib/caddy/` | Caddy config; certificates |
| `/var/log/cloud-init-output.log` | Output of the whole setup |
| `/var/log/caddy/varsis-access.log` | HTTP access log |
| `journalctl -u varsis-backend` | Backend log |

## Likely defense questions

- **Why doesn't uv download Python itself?** It could, but the assignment asks for package managers, and apt's
  Python gets security updates. uv would also put it in `/root/.local/share/uv`, which the `varsis` service user
  can't reach (`ProtectHome=true`).
- **What happens if the script runs twice?** Clone, secrets, DB role and DB are skipped if they exist; packages,
  build and configs are redone. So it doubles as the update command.
- **What if user data changes after the first boot?** cloud-init runs the per-instance modules only once per
  instance ID; a new VM is needed (or `cloud-init clean && reboot`).
- **How is the backend protected from the internet?** It listens on 127.0.0.1, ufw blocks everything but
  22/80/443, and it runs as an unprivileged sandboxed user.
- **Where does the certificate come from?** With `DOMAIN`, Let's Encrypt via the ACME HTTP-01 / TLS-ALPN-01
  challenge on ports 80/443, renewed by Caddy before expiry. Without it, from Caddy's local CA (not trusted by
  browsers, so you get a warning).
