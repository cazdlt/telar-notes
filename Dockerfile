FROM node:24-slim AS frontend
WORKDIR /app

COPY package.json package-lock.json tsconfig.json vite.config.ts index.html excalidraw-editor.html ./
COPY public ./public
COPY src ./src

RUN npm ci && npm run build

FROM python:3.14-slim
WORKDIR /app

RUN pip install --no-cache-dir "fastapi>=0.165.0" "pyyaml>=6.0.3" "uvicorn>=0.54.0"

COPY telar ./telar
COPY server.py ./
COPY help ./help
COPY --from=frontend /app/web/dist ./web/dist

EXPOSE 7731

ENTRYPOINT ["python", "server.py", "--host", "0.0.0.0", "--port", "7731", "--idle-timeout", "0", "--vault", "/vault"]
