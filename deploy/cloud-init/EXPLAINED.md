# user-data.yaml, step by step

A walk through [`user-data.yaml`](user-data.yaml) and the setup scripts it runs, in the order things happen on the
VM.

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

The design: **cloud-config declares what's static** (settings, packages, a user) and **bash scripts do everything
that needs logic** (if/else, generated secrets, building). The scripts are normal files in the repository
([`scripts/`](scripts)), one per step, like the Vagrant version. `runcmd` clones the repository and calls them in
order. The config files they install (Caddyfile template, systemd units) are in [`files/`](files).

cloud-init only receives `user-data.yaml`, nothing else from the repository. That's why the VM gets the scripts by
cloning the repository: it must be reachable without a login (public), and a changed script only reaches new VMs
after it's committed and pushed to `REPO_REF`.

---

## 1. Header and comments

```yaml
#cloud-config
```

This first line is required. Without it cloud-init doesn't treat the file as cloud-config. The comments below it
summarize the stage order from section 0.

## 2. Package settings

```yaml
package_update: true
package_upgrade: false
```

- `package_update: true` runs `apt-get update` before installing anything, so the package lists are current.
- `package_upgrade: false` skips `apt-get upgrade` of the whole system. That saves minutes on first boot.
  **unattended-upgrades** installs security updates in the background instead (set up in section 6).

## 3. Extra apt source: deadsnakes

```yaml
apt:
  sources:
    deadsnakes:
      source: ppa:deadsnakes/ppa
```

The backend's `pyproject.toml` requires Python ≥ 3.13, and Ubuntu 24.04 only has 3.12. The deadsnakes PPA
(Personal Package Archive on Launchpad) packages newer Pythons for Ubuntu. cloud-init adds it in the config stage
and fetches its signing key from the Ubuntu keyserver, so it's ready before `packages:` is installed.

deadsnakes is a **community** PPA, run by volunteers: unlike Ubuntu's own packages, Ubuntu's security team doesn't
stand behind it. It's the usual way to get a newer Python from apt on an LTS release, and it's updated when Python
releases fixes.

Why not let `uv` download Python? See the end of this document.

## 4. Packages

| Package | Why |
|---|---|
| `git` | Clone the app's repository |
| `curl` | Download the Caddy/NodeSource signing keys; health check |
| `gpg` | Convert those keys to the binary format apt wants (`--dearmor`) |
| `ufw` | Firewall frontend for iptables/nftables |
| `postgresql` | Database server (version 16 on 24.04). The package creates the `postgres` user and starts the service |
| `python3.13`, `python3.13-venv` | Runtime for the backend (from deadsnakes) |
| `pipx` | Installs Python CLI tools in isolated venvs. Used to install `uv` |
| `unattended-upgrades` | Installs updates automatically every day (section 6). Usually already in the image; listed so it's certain |

Caddy and Node.js aren't here because their apt repositories are added later by `install-dependencies.sh`
(section 9.2).

## 5. Users

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

## 6. write_files: settings

```yaml
- path: /etc/varsis/deploy.env
  permissions: "0600"
```

The **only place you edit before launching**. It's a list of `NAME=value` lines that bash reads later
(`. /etc/varsis/deploy.env`). Mode `0600` means only root can read it, because it may contain the SMTP password.

Because bash reads it, a value with spaces or special characters needs single quotes: `SMTP_PASS='abc$def'`
(unquoted, bash would replace `$def` with an empty variable, and a space would end the value). The values are
later written into `backend.env`, which systemd reads with its own rules: it keeps spaces and `$` but drops
backslashes, so quote characters and backslashes inside a value don't work. `ADMIN_EMAILS` is written without
spaces (`a@x.com,b@y.com`).

| Variable | Effect |
|---|---|
| `DOMAIN` | Empty: local VM, HTTPS on the VM's IP with a self-signed certificate. Set: a real Let's Encrypt certificate for that name |
| `SITE` | Only for a local VM reached through port forwarding: the address the browser opens (e.g. `localhost:8443`). Ignored when `DOMAIN` is set |
| `REPO_URL`, `REPO_REF` | Which git repository and branch to deploy. The setup scripts come from it too |
| `ADMIN_EMAILS` | Accounts the backend makes admin (and approves) at startup |
| `DEFAULT_QUOTA_GB` | Upload space per new user |
| `SMTP_*` | Mail server for verification and password-reset mails |
| `MAILPIT` | `true`: install Mailpit and send all mail there instead of `SMTP_*` (testing) |

The second file is apt configuration for **unattended-upgrades**, the service that installs updates every day:

```yaml
- path: /etc/apt/apt.conf.d/51varsis-upgrades
  content: |
    APT::Periodic::Update-Package-Lists "1";
    APT::Periodic::Unattended-Upgrade "1";
    Unattended-Upgrade::Origins-Pattern {
            "site=dl.cloudsmith.io";
            "site=ppa.launchpadcontent.net";
    };
```

- The two `APT::Periodic` lines turn on the daily `apt update` and the daily upgrade run. The package normally
  sets them in `20auto-upgrades`; files are read in name order, so `51…` wins even if an image turned them off.
- By default unattended-upgrades only installs Ubuntu's own **security** updates. `Origins-Pattern` adds two
  repositories by their host name (`site`): Caddy's (`dl.cloudsmith.io`; Caddy faces the internet) and the
  deadsnakes PPA (`ppa.launchpadcontent.net`; Python 3.13). Node.js isn't listed: it only builds the frontend once,
  nothing runs it.
- A Caddy update restarts Caddy (the package does that). A Python update is used by the backend after its next
  restart (e.g. a reboot).
- `/etc/caddy/Caddyfile` is also a file the Caddy package ships. If a Caddy release ever changes its own default
  version of it, unattended-upgrades holds that one update back instead of asking which version to keep (it logs
  this in `/var/log/unattended-upgrades/`).

Check on the VM: `sudo unattended-upgrade --dry-run --debug | grep "Allowed origins"` lists both hosts.

## 7. Caddy template ([`files/Caddyfile.tmpl`](files/Caddyfile.tmpl))

A template, not the final `/etc/caddy/Caddyfile`: it contains placeholders (`__SITE__`, `__TLS__`, `__FRAMED__`)
that depend on the settings. `start-caddy.sh` fills them in and writes the real file (section 9.9).

Line by line:

| Directive | What it does |
|---|---|
| `__SITE__ { … }` | Site address: a domain or an IP. Caddy enables HTTPS automatically for it and redirects `http://` to `https://` |
| `__TLS__` | Becomes `tls internal` (certificate from Caddy's own local CA) or nothing (default: Let's Encrypt via the ACME protocol) |
| `encode zstd gzip` | Compress responses (JS/CSS/JSON) if the browser supports it |
| `header { … }` | Security headers on every response: **HSTS** (the browser only uses https for this host for a year), **nosniff** (don't guess file types: an uploaded "song" must never run as HTML/JS), **Referrer-Policy same-origin** (tokens in email links don't leak to other sites), `-Server` removes the header that names the server software. The deletion makes Caddy apply this block last, so nothing in it can be overridden per path |
| `@framed` + `header @framed X-Frame-Options DENY` | No embedding in other sites (against clickjacking). Separate, with a matcher, so it can skip `/mailpit*`, which shows mails in a frame of its own |
| `import /etc/caddy/mailpit.caddy` | Mailpit's inbox behind a password when `MAILPIT=true`, otherwise an empty file |
| `request_body … max_size` | `@upload` and `@small` are *named matchers*. Uploads may be up to 2 GB; every other request at most 1 MB, because the backend reads JSON bodies into memory and a huge body could exhaust it |
| `handle /api/*` + `reverse_proxy` | Everything under `/api/` goes to the backend on `127.0.0.1:8000` |
| `header_up X-Real-IP {remote_host}` | The backend's login rate limit counts attempts per IP and reads it from `X-Real-IP` (`backend/app/ratelimit.py`). Caddy *overwrites* the header with the real client address, so a client can't fake it |
| `flush_interval -1` | Pass response data on immediately instead of buffering. Needed for streaming audio |
| `handle` + `try_files` + `file_server` | Everything else is a static file from `/var/www/varsis`. `try_files {path} /index.html` serves `index.html` for paths that aren't files (e.g. `/album/12`), so the Vue router can handle them (single-page app) |
| `log` + `format filter` | Access log as JSON in `/var/log/caddy/varsis-access.log`. Caddy rotates it itself (by default at 100 MB). The `filter` wraps the JSON format and changes two fields first: `token` in the URL's query becomes `REDACTED`, and the `Referer` header is left out. Email links carry a token (`/verify?token=…`, `/reset-password?token=…`), and the JS/CSS that page loads would send the whole link as `Referer`; anyone reading the log could otherwise reset that user's password |

`handle` blocks are mutually exclusive and checked most specific first, so `/api/...` never falls through to the
file server.

**Why Caddy and not nginx:** Caddy gets and renews TLS certificates by itself; with nginx you'd need certbot plus
a renewal timer. It replaces both the old `frontend/nginx.conf` and the Caddy container from the Docker setup.

## 8. systemd service ([`files/varsis-backend.service`](files/varsis-backend.service))

Tells systemd how to run the backend. `setup-backend.sh` copies it to `/etc/systemd/system/` and starts it, after
the code and config exist. ([`files/mailpit.service`](files/mailpit.service) is the same idea for Mailpit, with
`DynamicUser`: systemd creates a throwaway user for it.)

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

## 9. The setup scripts ([`scripts/`](scripts))

`runcmd` (section 10) runs them in this order:

| Script | Step |
|---|---|
| `common.sh` | Not a step: sourced by every script (settings, secrets, `log()`, site address) |
| (runcmd itself) | 9.1 clone the repository (it brings the scripts below) |
| `install-dependencies.sh` | 9.2 Caddy and Node.js apt repositories |
| `firewall.sh` | 9.3 ufw |
| `secrets.sh` | 9.4 generate secrets |
| `setup-mailpit.sh` | 9.5 Mailpit (testing) |
| `setup-postgresql.sh` | 9.6 role and database |
| `setup-backend.sh` | 9.7 Python packages, `backend.env`, service |
| `build-frontend.sh` | 9.8 Vue build |
| `start-caddy.sh` | 9.9 Caddyfile, HTTPS |
| `health-check.sh` | 9.10 wait for the backend, check Caddy |

### Strict mode

Every script starts with:

```bash
set -euo pipefail
```

Bash "strict mode":

- `-e`: stop at the first command that fails (the script then exits with an error, and runcmd's own `set -e`
  stops the remaining steps).
- `-u`: using an unset variable is an error (catches typos).
- `-o pipefail`: a pipeline fails if *any* part fails, not only the last. Without it, a failed `curl` piped into
  `gpg` would go unnoticed.

Each script runs in its own `bash` process, so a variable set in one step doesn't leak into the next. What they
share comes from files, through `common.sh`.

### common.sh

```bash
. "$(dirname "$0")/common.sh"
```

Every script *sources* it (runs it in its own shell, not as a separate program), so its variables become the
script's variables. `$(dirname "$0")` is the scripts folder, wherever the repository is.

```bash
set -a
. /etc/varsis/deploy.env
if [ -f /etc/varsis/secrets.env ]; then . /etc/varsis/secrets.env; fi
set +a
```

`.` reads the settings file as bash. `set -a` auto-exports every variable it defines, `set +a` turns that off
again. The secrets file only exists after `secrets.sh` (9.4). Then:

- `FILES`: the path of [`files/`](files), for the config files the scripts install.
- `log()`: prefixes messages with `[varsis-setup]` so they're easy to find in `/var/log/cloud-init-output.log`.
- The site address: with `DOMAIN`, that name and Let's Encrypt (`TLS` empty). Without, `hostname -I` lists the
  VM's IPs (the first is the one `incus list` shows) and Caddy uses its own CA (`TLS="tls internal"`).
  `SITE_HOST` drops a `:port` (only used with port forwarding).

### 9.1 Get the code (in runcmd)

`git clone --depth 1` fetches only the latest commit (faster, smaller). `[ -d /opt/varsis/.git ] ||` skips it when
it's already there, so runcmd can run again. This brings both the app and the setup scripts, which is why it
happens in runcmd and not in a script.

### 9.2 Third-party apt repositories (`install-dependencies.sh`)

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

### 9.3 Firewall (`firewall.sh`)

- `ufw allow 22/tcp`: SSH. Allowed **before** enabling, otherwise you'd lock yourself out. By port number, not the
  `OpenSSH` profile name: minimal images (e.g. Incus's) have no SSH server and so no such profile.
- `ufw allow 80/tcp`: plain HTTP. Needed for Let's Encrypt's HTTP challenge and the http→https redirect.
- `ufw allow 443`: TCP for HTTPS, and UDP for HTTP/3 (QUIC), which Caddy also offers. On our server the host
  forwards both to the VM (SERVER-SETUP.md, step 7).
- `ufw --force enable`: turn it on without the "are you sure?" prompt. The default policy denies everything else
  incoming, so Postgres (5432) and the backend (8000) aren't reachable from outside even if they listened there.

### 9.4 Secrets (`secrets.sh`)

On the first run, two random values are generated with `openssl rand -hex 32` (32 random bytes = 64 hex
characters):

- `DB_PASSWORD`: for the `varsis` Postgres role.
- `SECRET_KEY`: signs login cookies and email links. Anyone who knows it can log in as any user; the backend
  refuses to start if it's shorter than 32 characters.

`umask 077` makes the new file readable only by root (mode 600) from the moment it's created. Because of the `if`,
secrets are created **once**: a second run must not change the DB password or log everyone out. They're never in
the repo or in user data, so publishing `user-data.yaml` leaks nothing.

### 9.5 Mailpit (`setup-mailpit.sh`)

Only with `MAILPIT=true`; otherwise the service is stopped and disabled. Mailpit isn't in apt, so a pinned release
is downloaded from GitHub (skipped if that version is already installed). The archive goes to a temporary file
first and is checked with `sha256sum -c` against `MAILPIT_SHA256`, the hash GitHub shows for that file on the
release page. Only if it matches is the `mailpit` binary unpacked into `/usr/local/bin`; a replaced or damaged
download stops the setup (`set -e`). A random `MAILPIT_PASSWORD` is appended
to `secrets.env` once; 9.9 puts the inbox at `/mailpit/` behind it. Then `files/mailpit.service` is installed and
started.

### 9.6 Database (`setup-postgresql.sh`)

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
- Then `createdb -O varsis varsis` creates the database `varsis` owned by role `varsis`, unless the `SELECT`
  finds it already exists.

Postgres on Ubuntu listens only on `localhost` by default, and the backend connects to `127.0.0.1` with the
password (`scram-sha-256`).

The **tables** aren't created here: the backend creates them itself at startup (`Base.metadata.create_all` in
`backend/app/main.py`).

### 9.7 Backend (`setup-backend.sh`)

```bash
UV_VERSION=0.13.6
if [ "$(uv --version 2>/dev/null | awk '{print $2}')" != "$UV_VERSION" ]; then
    PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin pipx install --force "uv==$UV_VERSION"
fi
```

Install **uv** (a fast Python package manager) at a pinned version, unless exactly that version is already there
(`uv --version` prints `uv 0.13.6 …`). Pinned, so a new uv release can't change how the backend is installed.
Setting `PIPX_HOME`/`PIPX_BIN_DIR` makes it a system-wide install (`/usr/local/bin/uv`) instead of in root's home.

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

With `MAILPIT=true`, the `SMTP_*` variables are replaced by Mailpit's (`127.0.0.1:1025`, no login, no TLS) before
`backend.env` is written.

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

- `files/varsis-backend.service` is copied to `/etc/systemd/system/`.
- `systemctl daemon-reload`: systemd reads the new unit file.
- `enable --now`: start on boot, and start now.
- `restart`: on a re-run, pick up a changed env file or new code.

### 9.8 Frontend (`build-frontend.sh`)

- `npm ci`: install exactly what `package-lock.json` says (the npm equivalent of `uv sync --frozen`).
  `--no-audit --no-fund` skips network calls that only print messages.
- `npm run build`: Vite compiles the Vue app into plain HTML/JS/CSS in `dist/`.
- The old copy is removed and `dist` is copied to `/var/www/varsis`, where Caddy serves it.

Node is only a **build tool**. Nothing Node-based runs afterwards.

### 9.9 Caddy (`start-caddy.sh`)

- `/etc/caddy/mailpit.caddy`: with Mailpit, a `handle /mailpit*` block with `basic_auth` (the password as a bcrypt
  hash from `caddy hash-password`) and `X-Frame-Options SAMEORIGIN`. Without Mailpit, an empty file.
- `sed` replaces `__SITE__`, `__TLS__` and `__FRAMED__` (which paths get `X-Frame-Options DENY`: all, or all but
  `/mailpit*`) in `files/Caddyfile.tmpl` and writes the real `/etc/caddy/Caddyfile`.
- `runuser -u caddy -- caddy validate` checks the config first. If it's wrong, the script stops (`set -e`) instead
  of breaking the running Caddy. It runs **as the caddy user**: validating opens the access log file, and as root
  it would create it owned by root, so the real Caddy service (user `caddy`) couldn't write it and wouldn't start.
- `reload-or-restart`: Caddy loads the new config without dropping connections. When it first sees the site
  address it gets the certificate: from Let's Encrypt (with a domain) or from its local CA (with an IP).

### 9.10 Health check (`health-check.sh`)

Two checks. If one fails, the script exits with an error, so `cloud-init status` reports the deployment as
**failed** instead of "done" with a broken app. On success it prints the URL.

1. **Backend:** polled up to 30 times, 2 seconds apart, on `http://127.0.0.1:8000/api/health`. `curl -f` fails on
   HTTP errors.
2. **Caddy:** a plain-http request to `127.0.0.1` with the site's name in the `Host` header (`curl -H "Host: …"`)
   must get Caddy's **308** redirect to https. That only happens when Caddy runs and has loaded our Caddyfile for
   that name. `-w '%{http_code}'` prints just the status code.

The check doesn't use https on purpose: with a real domain, the certificate also needs DNS and the host's port
forwards, which can be added after the VM was launched (as on our server). Caddy keeps retrying until then, so a
missing certificate a minute after boot isn't a broken deployment.

## 10. runcmd and final_message

```yaml
runcmd:
  - set -e
  - . /etc/varsis/deploy.env
  - '[ -d /opt/varsis/.git ] || git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" /opt/varsis'
  - cd /opt/varsis/deploy/cloud-init/scripts
  - bash install-dependencies.sh
  # … one line per step …
  - bash health-check.sh
```

cloud-init joins the list into one shell script (`/var/lib/cloud/instance/scripts/runcmd`) and runs it with `sh`
at the end of boot. So the lines share one shell: the variables from `deploy.env` and the `cd` carry over to the
next line.

- `set -e`: without it, runcmd would carry on after a failed step. With it, the first failing step stops the rest
  and cloud-init reports an error.
- The clone line is quoted in YAML because it starts with `[`, which YAML would otherwise read as a list.
- Each step is `bash <script>` from the cloned repository. The scripts are ordinary files, easy to read, test
  (`bash -n`) and run one by one by hand.

**Running it again** (after `git pull`, or after changing `deploy.env`): `sudo sh /var/lib/cloud/instance/scripts/runcmd`.
The clone, secrets and database are skipped because they exist; everything else is redone.

`final_message` is printed to the console and log when cloud-init finishes; `$UPTIME` is the seconds since
boot, a handy measure of deployment speed.

---

## Timeline of a first boot

1. **init:** `/etc/varsis/deploy.env` and the unattended-upgrades config are written; users `ubuntu` and `varsis`
   are created.
2. **config:** the deadsnakes PPA is added; runcmd is saved as a script.
3. **final:** `apt update`; git, curl, gpg, ufw, postgresql, python3.13, pipx are installed (Postgres starts).
4. **final, runcmd:**
   1. clone the repository (app + setup scripts)
   2. `install-dependencies.sh`: Caddy and NodeSource repos → install `caddy`, `nodejs`
   3. `firewall.sh`: firewall on
   4. `secrets.sh`: generate secrets
   5. `setup-mailpit.sh`: Mailpit (if enabled)
   6. `setup-postgresql.sh`: DB role and database
   7. `setup-backend.sh`: backend deps, `backend.env`, start the backend (it creates the tables)
   8. `build-frontend.sh`: build the frontend
   9. `start-caddy.sh`: configure Caddy (certificate)
   10. `health-check.sh`: wait for the backend, check Caddy
5. `final_message` with the total time.

## Where things end up on the VM

| Path | Contents |
|---|---|
| `/etc/varsis/deploy.env` | Your settings (600) |
| `/etc/apt/apt.conf.d/51varsis-upgrades` | Automatic updates: on, and also from Caddy's repo and deadsnakes |
| `/etc/varsis/secrets.env` | Generated DB password and SECRET_KEY (600) |
| `/etc/varsis/backend.env` | Everything the backend gets as environment (600) |
| `/opt/varsis/` | The git checkout; `backend/.venv` is the Python environment; `deploy/cloud-init/scripts/` the setup steps |
| `/var/lib/cloud/instance/scripts/runcmd` | runcmd as cloud-init saved it (run it again to redeploy) |
| `/var/www/varsis/` | Built frontend |
| `/var/lib/varsis/{music,covers}` | Uploaded data (owner `varsis`, 750) |
| `/var/lib/postgresql/16/main` | Database files |
| `/etc/caddy/Caddyfile`, `/var/lib/caddy/` | Caddy config; certificates |
| `/var/log/cloud-init-output.log` | Output of the whole setup |
| `/var/log/caddy/varsis-access.log` | HTTP access log |
| `journalctl -u varsis-backend` | Backend log |

## Likely defense questions

- **Why doesn't uv download Python itself?** It could, but the assignment asks for package managers, and apt's
  Python is updated automatically with the rest of the system (unattended-upgrades also takes the deadsnakes PPA,
  section 6). uv would also put it in `/root/.local/share/uv`, which the `varsis` service user can't reach
  (`ProtectHome=true`).
- **What happens if the setup runs twice?** Clone, secrets, DB role and DB are skipped if they exist; packages,
  build and configs are redone. So it doubles as the update command.
- **Why are the scripts in the repository and not in user-data.yaml?** Readable, testable files, one per step,
  like the Vagrant version, and they update with `git pull`. The cost: the repository must be public (the VM clones
  it without a login), and script changes must be pushed before a new VM sees them.
- **What if user data changes after the first boot?** cloud-init runs the per-instance modules only once per
  instance ID; a new VM is needed (or `cloud-init clean && reboot`).
- **How is the backend protected from the internet?** It listens on 127.0.0.1, ufw blocks everything but
  22/80/443, and it runs as an unprivileged sandboxed user.
- **Where does the certificate come from?** With `DOMAIN`, Let's Encrypt via the ACME HTTP-01 / TLS-ALPN-01
  challenge on ports 80/443, renewed by Caddy before expiry. Without it, from Caddy's local CA (not trusted by
  browsers, so you get a warning).
