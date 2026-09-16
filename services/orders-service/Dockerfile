# Stage 1: Build & Dependencies
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Hardened Runtime Image
FROM python:3.11-slim

# Create dedicated non-root user for Zero-Trust compliance
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -M appuser

WORKDIR /app
COPY --from=builder /install /usr/local
COPY main.py .

# Change ownership and set non-root user
RUN chown -R appuser:appgroup /app
USER 10001:10001

EXPOSE 8001

# Healthcheck for container orchestrator
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/healthz')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
