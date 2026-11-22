# Backend plugins

A plugin is a folder here, `app/plugins/<name>/`, with an `__init__.py`. The app imports every such folder at
startup; with none, it runs as it is. What a plugin can define is listed in [`__init__.py`](__init__.py).

Plugin folders are not part of this repository (git ignores them). They come from their own repository:

- **Local run:** link or copy the folder here. Install what it needs with
  `uv run --with-requirements app/plugins/<name>/requirements.txt uvicorn app.main:app --reload`.

A plugin usually has a second half for the web app: see `frontend/src/plugins/README.md`.
