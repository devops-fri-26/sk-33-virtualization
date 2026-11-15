# Plugins (see app/plugins/README.md): this stage is all an image gets in app/plugins/. A build can replace it
# with a folder of plugin folders by passing a build context named "plugins".
FROM scratch AS plugins
COPY app/plugins/__init__.py /

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv
WORKDIR /srv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev
COPY app ./app
COPY --from=plugins / ./app/plugins/
# A plugin's packages aren't in uv.lock, so its requirements.txt has to pin and hash every one of them itself.
# --no-deps: only what the file lists is installed, so a plugin can't quietly pull in more or change the app's own.
RUN for r in app/plugins/*/requirements.txt; do \
      if [ -f "$r" ]; then uv pip install --require-hashes --no-deps -r "$r"; fi; \
    done
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
