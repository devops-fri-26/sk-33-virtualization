# Varsis

Self-hosted lossless music server: FastAPI + SQLAlchemy + PostgreSQL, Vue + Tailwind.

## Deployment

| How | Guide |
|---|---|
| A VM set up by cloud-init (our production server), or by Vagrant (development) | [deploy/README.md](deploy/README.md) |
| Docker Compose (on your computer, or on a server with HTTPS) | [deploy/docker/README.md](deploy/docker/README.md) |

## How it works

### Plugins
Optional features live in their own repositories and are added as plugins: a folder for the API (`backend/app/plugins/<name>/`) and one for the web app (`frontend/src/plugins/<name>/`). Without plugins the app runs as described here. How a plugin is written and built in: [backend](backend/app/plugins/README.md), [frontend](frontend/src/plugins/README.md).

### Accounts
- **Sign-up:** new users confirm their email, then an admin approves them (account menu → **Admin**). Admins get an email when someone is waiting, and the user gets one when approved.
- **Admins:** the emails in `ADMIN_EMAILS` are admins and skip approval (they still confirm their email). Admins can make other users admins.
- **Library:** shared. Every user can play and download everything (**Browse** lists every album and artist), but can only edit or delete the tracks they uploaded (admins: any track). "Edit details" in a track's menu changes its title, artists and album in the library; the audio file and its tags stay as uploaded.
- **Storage:** each user can upload `DEFAULT_QUOTA_GB` (10 GB). When it's full they can ask for more (Settings or Upload page), and admins change the limit per user on the Admin page.
- **Settings** (account menu): display name, email (confirmed by a link to the new address), password, "log out on all devices", delete your account (its playlists go with it; the music you uploaded stays in the library). "Forgot your password?" is on the login page.

### Uploading
- **Upload page:** pick files or a whole folder (subfolders included). Each folder goes up as its own request (big ones in 500 MB parts). Files that aren't supported audio are listed as not uploaded.
- **Tags** come from the audio file (WAV: its ID3 tags or RIFF INFO fields). Where they're empty, Varsis fills them from metadata files in the folder: archive.org's `<item>_files.xml` / `<item>_meta.xml` and Kodi/Jellyfin `album.nfo`.
- **Album cover:** a picture in the folder named `cover` / `folder` / `front` (also in an `Artwork`/`Scans` subfolder, or the album folder above `CD1`), or the folder's only picture. Otherwise the art embedded in the first track, then Cover Art Archive. Songs without an album keep their own embedded picture.
- **Compilations:** tracks of one folder with the same album title become one album even when their tags name no album artist. It is filed under "Various Artists" when a compilation flag is set or no artist has more than half of the tracks, else under that artist.
- **Duplicates:** a file that is already in the library, byte for byte, is not imported again (whoever uploaded it first).
- These pictures and XML/NFO files are only read during import. They aren't stored and don't count against storage.

## Local development
```bash
cd backend && uv run uvicorn app.main:app --reload   # :8000 (use localhost URLs in backend/.env)
cd frontend && npm run dev                            # :5173, proxies /api to :8000
```

The backend needs a PostgreSQL, and Mailpit for the mails: `docker compose up -d db mailpit` in `deploy/docker`.
