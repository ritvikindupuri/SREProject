import os
import time
import random
import logging
from typing import Dict
from fastapi import FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("inventory-service")

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status_code"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency in seconds", ["endpoint"], buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0])
INVENTORY_STOCK_LEVEL = Gauge("inventory_stock_units", "Current stock level per item", ["item_id"])
RESERVATIONS_TOTAL = Counter("inventory_reservations_total", "Total inventory reservations", ["status"])

app = FastAPI(title="CoreOps Inventory Service", version="1.0.0")

# Initial realistic stock items
inventory_db: Dict[str, Dict] = {
    "ITEM-SRV-01": {"name": "1U Rackmount Server", "stock": 500, "unit_price": 1200.00},
    "ITEM-FW-02":  {"name": "Hardware Security Appliance", "stock": 350, "unit_price": 850.00},
    "ITEM-NIC-03": {"name": "100GbE SmartNIC Card", "stock": 1200, "unit_price": 320.00},
    "ITEM-HSM-04": {"name": "PCIe Hardware Security Module", "stock": 150, "unit_price": 2400.00},
    "ITEM-MEM-05": {"name": "64GB ECC DDR5 RAM Module", "stock": 4000, "unit_price": 180.00},
}

for item_id, data in inventory_db.items():
    INVENTORY_STOCK_LEVEL.labels(item_id=item_id).set(data["stock"])

chaos_state = {
    "error_rate": 0.0,
    "added_latency_ms": 0,
}

@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    start_time = time.time()
    endpoint = request.url.path

    if chaos_state["added_latency_ms"] > 0:
        time.sleep(chaos_state["added_latency_ms"] / 1000.0)

    if chaos_state["error_rate"] > 0 and random.random() < chaos_state["error_rate"] and endpoint.startswith("/api"):
        REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status_code=500).inc()
        return Response(content='{"error": "Database lock contention timeout (Injected Chaos)"}', status_code=500, media_type="application/json")

    response = await call_next(request)
    duration = time.time() - start_time
    
    REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status_code=response.status_code).inc()
    REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)
    return response

class ReserveRequest(BaseModel):
    item_id: str
    quantity: int

class ChaosConfig(BaseModel):
    error_rate: float
    added_latency_ms: int

@app.get("/healthz")
def health_check():
    return {"status": "healthy", "service": "inventory-service", "timestamp": datetime.utcnow().isoformat()}

@app.get("/metrics")
def metrics():
    for item_id, data in inventory_db.items():
        INVENTORY_STOCK_LEVEL.labels(item_id=item_id).set(data["stock"])
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/api/chaos/configure")
def configure_chaos(config: ChaosConfig):
    chaos_state["error_rate"] = max(0.0, min(1.0, config.error_rate))
    chaos_state["added_latency_ms"] = max(0, config.added_latency_ms)
    logger.info(f"Inventory Chaos updated: error_rate={chaos_state['error_rate']}, latency={chaos_state['added_latency_ms']}ms")
    return {"status": "chaos_configured", "config": chaos_state}

@app.get("/api/inventory/items")
def list_inventory():
    return [{"item_id": k, **v} for k, v in inventory_db.items()]

@app.post("/api/inventory/reserve")
def reserve_inventory(reserve: ReserveRequest):
    if reserve.item_id not in inventory_db:
        RESERVATIONS_TOTAL.labels(status="item_not_found").inc()
        raise HTTPException(status_code=404, detail="Item not found in catalog")

    item = inventory_db[reserve.item_id]
    if item["stock"] < reserve.quantity:
        RESERVATIONS_TOTAL.labels(status="insufficient_stock").inc()
        raise HTTPException(status_code=400, detail=f"Insufficient stock for {reserve.item_id}. Available: {item['stock']}")

    # Atomic deduction
    item["stock"] -= reserve.quantity
    INVENTORY_STOCK_LEVEL.labels(item_id=reserve.item_id).set(item["stock"])
    RESERVATIONS_TOTAL.labels(status="reserved").inc()
    
    logger.info(f"Reserved {reserve.quantity} of {reserve.item_id}. Remaining stock: {item['stock']}")
    return {
        "item_id": reserve.item_id,
        "quantity_reserved": reserve.quantity,
        "remaining_stock": item["stock"],
        "status": "RESERVED"
    }

@app.post("/api/inventory/restock")
def restock_inventory(item_id: str, quantity: int):
    if item_id not in inventory_db:
        raise HTTPException(status_code=404, detail="Item not found")
    inventory_db[item_id]["stock"] += quantity
    INVENTORY_STOCK_LEVEL.labels(item_id=item_id).set(inventory_db[item_id]["stock"])
    return {"item_id": item_id, "new_stock": inventory_db[item_id]["stock"]}
