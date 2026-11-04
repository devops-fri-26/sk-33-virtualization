# TODO

Deferred work, manual setup steps and open questions. Items under "Open questions" are **not decided**: ask before building them.

## One-time setup
- [x] Docker access for your user.
- [x] qBittorrent: permanent password set and saved in `.env` as `QBIT_PASS` (username `admin`). Use it to log in at http://localhost:8081.
- [x] Prowlarr: API key saved in `.env` as `PROWLARR_API_KEY`.
- [ ] Prowlarr (http://localhost:9696): set up its login and **add indexers** (Indexers → Add Indexer). Until then, torrent search returns no results.

## Test data left from testing (remove when no longer needed)
- [ ] Users `claude-test@example.com` and `claude-test2@example.com` (password `testpass123`).
- [ ] Nine generated sine-wave tracks: Test Album, Torrent Album, "untagged", "Feat Song", "After Error".
- [ ] The playlists of `claude-test` and its two torrent jobs.

## Local development (backend via `uv run`, outside Docker)
- [ ] Publish the Postgres port: add `ports: ["5432:5432"]` to the `db` service in `docker-compose.yml`.
- [ ] Create `backend/.env` with localhost values: `DATABASE_URL=postgresql+asyncpg://varsis:varsis@localhost:5432/varsis`, `SMTP_HOST=localhost`, `SMTP_PORT=1025`, `APP_URL=http://localhost:5173`, plus `MUSIC_DIR` / `DOWNLOADS_DIR` / `COVERS_DIR` pointing at local folders.

## Before production
- [ ] Replace Mailpit with real SMTP: set `SMTP_HOST/PORT/USER/PASS/FROM` and `SMTP_TLS=true` in `.env`, then remove the `mailpit` service.
- [ ] Set `APP_URL` to the real **https** URL. Verification links and the secure cookie use it, and the prefetch cache only works on https or localhost.
- [ ] Set a long random `SECRET_KEY` and a strong `POSTGRES_PASSWORD`.
- [ ] Pin the image versions of `prowlarr`, `qbittorrent` and `mailpit` (currently `latest`).
- [ ] Prowlarr (9696), qBittorrent (8081) and Mailpit (8025) are published on all network interfaces, so other devices on the network can reach them. Publish them on localhost only, e.g. `"127.0.0.1:9696:9696"` (ask first).
- [ ] Schema changes: `create_all` only creates *new* tables, so changing an existing column needs manual SQL or Alembic.

## Open questions / not built (ask first)
- [ ] Endpoint to resend the verification email. Without it, a user who loses the email can't verify.
- [ ] Password reset ("forgot password").
- [ ] APE / WavPack / AIFF are rejected because browsers can't play them. An option is to convert them to FLAC on import.
- [ ] Torrents: after import the torrent is removed from qBittorrent, so it stops seeding. Private trackers may penalise this. The alternative is to copy the files and keep seeding.
- [ ] Torrents: cancel or remove a download from the UI.
- [ ] Torrents: CUE + single-FLAC album rips import as one long track.
- [ ] Torrents: mark or prefer lossless (FLAC) results in the search list.
- [ ] Torrents: a job stays in "importing" if the backend restarts during an import.
- [ ] Torrents: qBittorrent exposes the server's IP to peers. Use a VPN container?
- [ ] Registration is open to anyone who can reach the site. Make it invite-only or require admin approval?
- [ ] The library is shared by all users (everyone sees all music). Is that intended?
- [ ] Delete tracks, or edit title/album, from the UI.
- [ ] Duplicate detection: the same file uploaded twice creates two tracks.
- [ ] Playlists: drag-and-drop reordering (currently ↑/↓ in the ⋯ menu) and shared/public playlists (currently private).
- [ ] Playlist covers: a 2×2 mosaic of album covers (currently a placeholder icon in the sidebar and library).
- [ ] Upload: drag and drop files onto the page, plus an upload progress bar.
- [ ] Phone: a full-screen "now playing" view (the mini player has play/pause, next, seek and the queue).
- [ ] Artist images (there's no source for them yet, so artists show a placeholder).
- [ ] Automated tests (none yet; testing so far was manual curl + headless-Firefox scripts).

## Notes
- Hover-only effects (card play button sliding in, row highlight) were checked in the code only. Headless screenshots don't render `:hover`, so give them a quick look in a real browser.
