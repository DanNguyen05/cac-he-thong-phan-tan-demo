FROM node:22-bookworm-slim AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 LAB_DATA=/data KV_RUNTIME=docker
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY --from=frontend /ui/dist ./frontend/dist
RUN useradd --uid 10001 --create-home lab && mkdir /data && chown lab:lab /data
USER lab
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.kv_node:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
