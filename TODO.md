# TODO

What's left before Varsis can be put on the internet for other people. The current setup is for development on
your own machine. Sections are ordered by importance; inside a section, top items first.

## 1. Blockers: do these before anyone else gets the address

- [ ] **HTTPS.** The app speaks plain HTTP on port 8080, so passwords and the login cookie travel unencrypted.
      Put a reverse proxy with certificates in front (Caddy, Traefik, Cloudflare Tunnel), then:
  - [ ] set `APP_URL` to the `https://` address (email links use it, and it turns on the cookie's `Secure` flag);
  - [ ] uncomment `set_real_ip_from` / `real_ip_header` in `frontend/nginx.conf`, or every visitor shares one
        login rate limit (they all look like the proxy);
  - [ ] change the port mapping to `127.0.0.1:8080:80` if the proxy runs on the same machine, so the plain-HTTP
        port isn't reachable from outside;
  - [ ] turn on HSTS in the proxy.
- [ ] **Real email.** Replace Mailpit: set `SMTP_HOST/PORT/USER/PASS/FROM` and `SMTP_TLS=true`, remove the
      `mailpit` service from both compose files. Set up SPF/DKIM for the sender domain, or sign-up mails land in spam.
- [ ] **Fresh secrets.** New `SECRET_KEY` and `POSTGRES_PASSWORD` for production (`openssl rand -hex 32`), and a
      new qBittorrent password. Don't reuse the values from the development `.env`.
- [ ] **Register the admin accounts first.** Sign up and verify every address in `ADMIN_EMAILS` yourself before
      opening the site. An address listed there that has no account yet can be registered by anyone; they can't
      verify it, but if the owner later clicks that verification mail, the stranger's password works on an admin
      account until the owner resets it.
- [ ] **Remove development leftovers.** Test accounts and test tracks in the database (check the Admin page;
      earlier testing used `claude-test@example.com` and `claude-test2@example.com`), or start from an empty `DATA_DIR`.
- [ ] **Backups.** Nothing is backed up. Schedule `pg_dump` of the database plus copies of `DATA_DIR/music` and
      `DATA_DIR/covers`, and try a restore once.
- [ ] **Database migrations.** The schema is created with `create_all` plus the `ALTER TABLE … IF NOT EXISTS`
      list in `models.py`. That can add columns but can't change or remove one. Move to Alembic before the first
      real users, while the schema is still easy to change.
- [ ] **Automated tests + CI.** There are none. At least cover sign-up/login/reset, upload with the storage limit,
      permissions (edit/delete only your own tracks, admin-only API) and the torrent poller. Run them and
      `ruff check` / `npm run build` on every push.
- [ ] **Decide the legal side** of offering torrent search and a shared music library to other people, and who is
      allowed to sign up. For a public site in the EU you also need a privacy notice and a way to delete an account
      (see section 3).

## 2. Should do: hardening and operations

- [ ] **Content-Security-Policy header.** `nosniff`, frame blocking and `Referrer-Policy` are set in nginx; a CSP
      is not, because it needs testing in a browser (the app uses inline styles, blob: audio and remote poster images).
- [ ] **Run the backend as a non-root user** in its container, and add `security_opt: [no-new-privileges:true]`.
      The folders under `DATA_DIR` are owned by root today, so their ownership has to change with it.
- [ ] **Pin image versions.** `postgres:17`, `nginx:alpine`, `python:3.13-slim`, `node:24-alpine` and
      `qmcgaw/gluetun:v3` are moving tags. Pin exact versions and update them on purpose.
- [ ] **Logs and monitoring.** Add log rotation to the compose services (`logging: max-size`), watch the backend
      log for errors, and add an uptime check on `/api/health`.
- [ ] **Sessions.** "Log out" only removes the cookie from that browser; a copied cookie keeps working for up to
      30 days. Only "log out on all devices" and a password change end it on the server. Consider shorter
      sessions or a server-side session list.
- [ ] **Login lockout can be abused.** 10 wrong passwords in 15 minutes block that email's login for everyone,
      so someone can keep another user locked out. Options: a captcha after a few failures, or limit per
      email + IP pair.
- [ ] **Rate limits and the "stalled download" timer live in memory.** They reset when the backend restarts and
      only work with one backend process. Move them to Redis or the database before running more than one worker.
- [ ] **Unverified accounts are never removed.** Delete accounts that haven't confirmed their email after a few days.
- [ ] **Tell the old address when an account's email changes** (the change itself needs the password and a link
      sent to the new address).
- [ ] **Torrent traffic that doesn't go through the VPN.** Prowlarr's searches, and the `.torrent` files the
      backend fetches through it, use the server's real IP. Only qBittorrent is behind gluetun.
- [ ] **Database indexes** for larger libraries: `tracks.album_id`, `tracks.uploaded_by`,
      `track_artists.artist_id`, `playlist_tracks.track_id`, `torrent_jobs.status`.
- [ ] **Slow work on the server's main loop.** Reading tags and covers during an import runs between requests
      and can make playback stutter for others during big imports. Move it to a worker thread.
- [ ] **Cover thumbnails.** Covers are stored and served at full size (a 10 MB embedded picture is sent for a
      40 px thumbnail). Resize on import, and send long cache headers.
- [ ] **Static file caching and gzip** in nginx for the built frontend.

## 3. Missing features users will expect

- [ ] Delete my own account (and its playlists) from Settings.
- [ ] Torrents: cancel or remove a download from the UI. A magnet link that never finds its file list stays
      "downloading" forever, and counts against the limit of 5 running downloads.
- [ ] Torrents: for magnet links every file in the torrent is downloaded (the "best version of each song" choice
      only works for `.torrent` links). Pick the files once qBittorrent has the file list.
- [ ] Upload: progress bar, drag and drop, resume after a failed part.
- [ ] Edit a track's title and album from the UI (only artists can be edited).
- [ ] Browse the whole library (all albums / all artists). Today there's search and "recently added".
- [ ] Duplicate detection: the same file uploaded twice becomes two tracks.
- [ ] WAV files: their tags aren't read, so they're imported with the file name as title and no artist.
- [ ] Compilation albums without an "album artist" tag are split into one album per track artist.
- [ ] Playlists: drag-and-drop ordering, shared playlists, a cover made from the album covers.
- [ ] Phone: a full-screen "now playing" view.
- [ ] Artist pictures.
- [ ] Show Prowlarr indexer errors in the app (a failing indexer looks like "No matching torrents").

## 4. Known limitations to decide on (not bugs)

- The library is shared: every approved user can play and download everything.
- After import the torrent is removed from qBittorrent, so nothing is seeded. Private trackers may penalise that.
- APE / WavPack / AIFF / DSD are rejected because browsers can't play them; converting to FLAC on import would fix it.
- CUE + single-file album rips are imported as one long track.
- Album titles and artist names of new albums without a cover are sent to MusicBrainz / Cover Art Archive to
  look up the cover.
- Track paths are stored as absolute paths (`/music/…`), so `MUSIC_DIR` can't be changed without updating the database.
- An admin listed in `ADMIN_EMAILS` gets admin rights back at every restart, even if another admin removed them.
  Removing an address from `ADMIN_EMAILS` does not take the rights away; do that on the Admin page.
- Prowlarr's Internet Archive definition: sort "created" is rejected by archive.org and items without a
  `publicdate` pause the indexer. Use sort "downloads". archive.org also throttles Prowlarr (30–90 s per search).

## Local development (backend outside Docker)

- [ ] Publish the Postgres port: add `ports: ["127.0.0.1:5432:5432"]` to the `db` service.
- [ ] Create `backend/.env` with localhost values: `DATABASE_URL=postgresql+asyncpg://varsis:<password>@localhost:5432/varsis`,
      `SMTP_HOST=localhost`, `SMTP_PORT=1025`, `APP_URL=http://localhost:5173`, and `MUSIC_DIR` / `DOWNLOADS_DIR` /
      `COVERS_DIR` pointing at local folders.
- [ ] Prowlarr (http://localhost:9696): set up its login and add indexers. Until then torrent search finds nothing.
