# Varsis

Self-hosted lossless music server: FastAPI + SQLAlchemy + PostgreSQL, Vue + Tailwind, Docker Compose.

## Run with Docker
```bash
cp .env.example .env        # then set SECRET_KEY (and SMTP for production)
docker compose up --build
```
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

### One-time setup
1. **qBittorrent**: the temporary admin password is printed in `docker compose logs qbittorrent`. Log in, set a password under Options → Web UI, and put it in `.env` as `QBIT_PASS`.
2. **Prowlarr**: open the UI, add indexers (Indexers → Add), copy the API key from Settings → General into `.env` as `PROWLARR_API_KEY`.
3. `docker compose up -d backend` to reload the settings.

## Local development
```bash
docker compose up -d db mailpit prowlarr qbittorrent
cd backend && uv run uvicorn app.main:app --reload   # :8000 (use localhost URLs in backend/.env)
cd frontend && npm run dev                            # :5173, proxies /api to :8000
```

See [TODO.md](TODO.md) for open setup steps, production checklist and open questions.
