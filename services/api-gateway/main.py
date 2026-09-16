import os
import time
import logging
from fastapi import FastAPI, Request, Response, HTTPException, status
import httpx
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("api-gateway")

ORDERS_SERVICE_URL = os.getenv("ORDERS_SERVICE_URL", "http://orders-service:8001")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8002")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8003")

REQUEST_COUNT = Counter("gateway_requests_total", "Total requests received at API Gateway", ["method", "path", "status_code"])
REQUEST_LATENCY = Histogram("gateway_request_duration_seconds", "End-to-end request duration through gateway", ["path"])

app = FastAPI(title="CoreOps API Gateway", version="1.0.0")

@app.middleware("http")
async def gateway_metrics_middleware(request: Request, call_next):
    start_time = time.time()
    path = request.url.path
    response = await call_next(request)
    duration = time.time() - start_time
    
    REQUEST_COUNT.labels(method=request.method, path=path, status_code=response.status_code).inc()
    REQUEST_LATENCY.labels(path=path).observe(duration)
    return response

@app.get("/healthz")
def health_check():
    return {"status": "healthy", "service": "api-gateway", "timestamp": datetime.utcnow().isoformat()}

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.api_route("/api/orders{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_orders(request: Request, path: str):
    target_url = f"{ORDERS_SERVICE_URL}/api/orders{path}"
    return await _forward_request(request, target_url)

@app.api_route("/api/inventory{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_inventory(request: Request, path: str):
    target_url = f"{INVENTORY_SERVICE_URL}/api/inventory{path}"
    return await _forward_request(request, target_url)

@app.api_route("/api/payments{path:path}", methods=["GET", "POST"])
async def proxy_payments(request: Request, path: str):
    target_url = f"{PAYMENT_SERVICE_URL}/api/payments{path}"
    return await _forward_request(request, target_url)

async def _forward_request(request: Request, target_url: str):
    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=request.query_params,
                timeout=10.0
            )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers),
                media_type=resp.headers.get("content-type")
            )
        except httpx.RequestError as exc:
            logger.error(f"Downstream connection failure to {target_url}: {exc}")
            raise HTTPException(status_code=502, detail=f"Bad Gateway: Downstream service unavailable ({exc})")
