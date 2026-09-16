import os
import time
import random
import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel
import httpx
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("orders-service")

# Database Setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./orders.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class OrderModel(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(String, index=True)
    item_id = Column(String)
    quantity = Column(Integer)
    total_amount = Column(Float)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Service URLs
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8002")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8003")

# Prometheus Metrics (Golden Signals)
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status_code"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency in seconds", ["endpoint"], buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0])
ORDER_COUNT = Counter("orders_processed_total", "Total orders processed", ["status"])
CHAOS_ERROR_INJECTION = Gauge("chaos_error_injection_active", "Flag indicating whether chaos error injection is active")
CHAOS_LATENCY_INJECTION = Gauge("chaos_latency_seconds", "Amount of injected latency in seconds")

app = FastAPI(title="CoreOps Orders Service", version="1.0.0")

# Chaos / Failure Mode State (For real SRE testing)
chaos_state = {
    "error_rate": 0.0,       # 0.0 to 1.0
    "added_latency_ms": 0,  # Milliseconds of artificial latency
}

@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    start_time = time.time()
    endpoint = request.url.path

    # Apply Chaos if configured (Simulating real downstream degradation / network brownout)
    if chaos_state["added_latency_ms"] > 0:
        time.sleep(chaos_state["added_latency_ms"] / 1000.0)
    
    if chaos_state["error_rate"] > 0 and random.random() < chaos_state["error_rate"] and endpoint.startswith("/api"):
        logger.warning(f"Injected chaos 500 error on {endpoint}")
        REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status_code=500).inc()
        return Response(content='{"error": "InternalServerError: Cascading dependency failure (Injected Chaos)"}', status_code=500, media_type="application/json")

    response = await call_next(request)
    duration = time.time() - start_time
    
    REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status_code=response.status_code).inc()
    REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)
    return response

class CreateOrderRequest(BaseModel):
    customer_id: str
    item_id: str
    quantity: int
    unit_price: float

class ChaosConfig(BaseModel):
    error_rate: float
    added_latency_ms: int

@app.get("/healthz")
def health_check():
    return {"status": "healthy", "service": "orders-service", "timestamp": datetime.utcnow().isoformat()}

@app.get("/metrics")
def metrics():
    CHAOS_ERROR_INJECTION.set(1 if chaos_state["error_rate"] > 0 else 0)
    CHAOS_LATENCY_INJECTION.set(chaos_state["added_latency_ms"] / 1000.0)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/api/chaos/configure")
def configure_chaos(config: ChaosConfig):
    chaos_state["error_rate"] = max(0.0, min(1.0, config.error_rate))
    chaos_state["added_latency_ms"] = max(0, config.added_latency_ms)
    logger.info(f"Chaos state updated: error_rate={chaos_state['error_rate']}, latency={chaos_state['added_latency_ms']}ms")
    return {"status": "chaos_configured", "config": chaos_state}

@app.post("/api/orders", status_code=status.HTTP_201_CREATED)
async def create_order(order_req: CreateOrderRequest):
    total = round(order_req.quantity * order_req.unit_price, 2)
    db = SessionLocal()
    try:
        new_order = OrderModel(
            customer_id=order_req.customer_id,
            item_id=order_req.item_id,
            quantity=order_req.quantity,
            total_amount=total,
            status="PENDING"
        )
        db.add(new_order)
        db.commit()
        db.refresh(new_order)
        order_id = new_order.id
    finally:
        db.close()

    # 1. Check Inventory with Inventory Service
    async with httpx.AsyncClient() as client:
        try:
            inv_resp = await client.post(
                f"{INVENTORY_SERVICE_URL}/api/inventory/reserve",
                json={"item_id": order_req.item_id, "quantity": order_req.quantity},
                timeout=3.0
            )
            if inv_resp.status_code != 200:
                db = SessionLocal()
                try:
                    ord_obj = db.query(OrderModel).filter(OrderModel.id == order_id).first()
                    if ord_obj:
                        ord_obj.status = "INVENTORY_REJECTED"
                        db.commit()
                finally:
                    db.close()
                ORDER_COUNT.labels(status="failed_inventory").inc()
                raise HTTPException(status_code=400, detail="Insufficient inventory or inventory reservation failed")
        except httpx.RequestError as exc:
            db = SessionLocal()
            try:
                ord_obj = db.query(OrderModel).filter(OrderModel.id == order_id).first()
                if ord_obj:
                    ord_obj.status = "DEPENDENCY_ERROR"
                    db.commit()
            finally:
                db.close()
            ORDER_COUNT.labels(status="dependency_error").inc()
            logger.error(f"Failed to connect to Inventory Service: {exc}")
            raise HTTPException(status_code=503, detail="Inventory Service unavailable")

        # 2. Process Payment with Payment Service
        try:
            pay_resp = await client.post(
                f"{PAYMENT_SERVICE_URL}/api/payments/process",
                json={
                    "order_id": order_id,
                    "customer_id": order_req.customer_id,
                    "amount": total
                },
                timeout=3.0
            )
            if pay_resp.status_code != 200:
                db = SessionLocal()
                try:
                    ord_obj = db.query(OrderModel).filter(OrderModel.id == order_id).first()
                    if ord_obj:
                        ord_obj.status = "PAYMENT_FAILED"
                        db.commit()
                finally:
                    db.close()
                ORDER_COUNT.labels(status="failed_payment").inc()
                raise HTTPException(status_code=402, detail="Payment processing failed")
        except httpx.RequestError as exc:
            db = SessionLocal()
            try:
                ord_obj = db.query(OrderModel).filter(OrderModel.id == order_id).first()
                if ord_obj:
                    ord_obj.status = "DEPENDENCY_ERROR"
                    db.commit()
            finally:
                db.close()
            ORDER_COUNT.labels(status="dependency_error").inc()
            logger.error(f"Failed to connect to Payment Service: {exc}")
            raise HTTPException(status_code=503, detail="Payment Service unavailable")

    db = SessionLocal()
    try:
        ord_obj = db.query(OrderModel).filter(OrderModel.id == order_id).first()
        if ord_obj:
            ord_obj.status = "COMPLETED"
            db.commit()
            created_at_str = ord_obj.created_at.isoformat()
        else:
            created_at_str = datetime.utcnow().isoformat()
    finally:
        db.close()

    ORDER_COUNT.labels(status="success").inc()
    
    return {
        "order_id": order_id,
        "status": "COMPLETED",
        "customer_id": order_req.customer_id,
        "total_amount": total,
        "created_at": created_at_str
    }

@app.get("/api/orders/{order_id}")
def get_order(order_id: int):
    db = SessionLocal()
    try:
        order = db.query(OrderModel).filter(OrderModel.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        return {
            "order_id": order.id,
            "customer_id": order.customer_id,
            "item_id": order.item_id,
            "quantity": order.quantity,
            "total_amount": order.total_amount,
            "status": order.status,
            "created_at": order.created_at.isoformat()
        }
    finally:
        db.close()

@app.get("/api/orders")
def list_orders(limit: int = 20):
    db = SessionLocal()
    try:
        orders = db.query(OrderModel).order_by(OrderModel.id.desc()).limit(limit).all()
        return [{"order_id": o.id, "customer_id": o.customer_id, "amount": o.total_amount, "status": o.status} for o in orders]
    finally:
        db.close()
