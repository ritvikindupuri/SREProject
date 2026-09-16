FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim

RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -M appuser

WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .

RUN mkdir -p /app/forensic_audit_logs && \
    chown -R appuser:appgroup /app
USER 10001:10001

EXPOSE 8088

HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8088/healthz')" || exit 1

CMD ["uvicorn", "controller:app", "--host", "0.0.0.0", "--port", "8088"]
