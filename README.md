# Varsis

Self-hosted lossless music server: FastAPI + SQLAlchemy + PostgreSQL, Vue + Tailwind, Docker Compose.

## Run with Docker
```bash
cp .env.example .env        # then set SECRET_KEY, POSTGRES_PASSWORD, ADMIN_EMAILS (and SMTP for production)
docker compose up --build
```
All data is stored in folders under `DATA_DIR` (default `/varsis`): `postgres`, `music`, `covers`, and for torrents `downloads`, `prowlarr`, `qbittorrent`. Docker creates them on first start (owned by root).

| Service | URL |
|---|---|
| App | http://localhost:8080 |
| Mailpit (dev emails) | http://localhost:8025 |
| Prowlarr | http://localhost:9696 |
| qBittorrent | http://localhost:8081 |

### Without torrents
```bash
docker compose -f docker-compose.no-torrents.yml up --build
```
Runs only the app, database and Mailpit. You don't need a VPN key, Prowlarr or qBittorrent. Torrent search is hidden in the UI, and uploads still work.

### Accounts
- **Sign-up:** new users confirm their email, then an admin approves them (account menu → **Admin**). Admins get an email when someone is waiting, and the user gets one when approved.
- **Admins:** the emails in `ADMIN_EMAILS` are admins and skip approval (they still confirm their email). Admins can make other users admins.
- **Library:** shared. Every user can play and download everything, but can only edit or delete the tracks they uploaded (admins: any track).
- **Storage:** each user can upload `DEFAULT_QUOTA_GB` (10 GB). Torrent downloads count too. When it's full they can ask for more (Settings or Upload page), and admins change the limit per user on the Admin page.
- **Settings** (account menu): display name, email (confirmed by a link to the new address), password, "log out on all devices". "Forgot your password?" is on the login page.

### Uploading
- **Upload page:** pick files or a whole folder (subfolders included). Each folder goes up as its own request (big ones in 500 MB parts). Files that aren't supported audio are listed as not uploaded.
- **Tags** come from the audio file. Where they're empty, Varsis fills them from metadata files in the folder: archive.org's `<item>_files.xml` / `<item>_meta.xml` and Kodi/Jellyfin `album.nfo`.
- **Album cover:** a picture in the folder named `cover` / `folder` / `front` (also in an `Artwork`/`Scans` subfolder, or the album folder above `CD1`), or the folder's only picture. Otherwise the art embedded in the first track, then Cover Art Archive. Songs without an album keep their own embedded picture.
- These pictures and XML/NFO files are only read during import. They aren't stored and don't count against storage. Torrent downloads also fetch them (small files next to the songs only).

### One-time setup (torrents)
1. **qBittorrent**: the temporary admin password is printed in `docker compose logs qbittorrent`. Log in, set a password under Options → Web UI, and put it in `.env` as `QBIT_PASS`.
2. **Prowlarr**: open the UI, add indexers (Indexers → Add), copy the API key from Settings → General into `.env` as `PROWLARR_API_KEY`.
3. `docker compose up -d backend` to reload the settings.

## Local development
```bash
docker compose up -d db mailpit prowlarr qbittorrent
cd backend && uv run uvicorn app.main:app --reload   # :8000 (use localhost URLs in backend/.env)
cd frontend && npm run dev                            # :5173, proxies /api to :8000
```

See [TODO.md](TODO.md) for what's left before this can be put on the internet, and for known limitations.
