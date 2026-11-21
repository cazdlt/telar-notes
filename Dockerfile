FROM node:24-slim AS frontend
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json vite.config.ts index.html excalidraw-editor.html ./
COPY src ./src
RUN npm run build

FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache
ENV PATH="/app/.venv/bin:$PATH"

COPY telar ./telar
COPY server.py ./
COPY help ./help
COPY --from=frontend /app/web/dist ./web/dist

EXPOSE 7731

ENTRYPOINT ["python", "server.py", "--host", "0.0.0.0", "--port", "7731", "--idle-timeout", "0", "--vault", "/vault"]
