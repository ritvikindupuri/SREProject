import os
import time
import random
import logging
import uuid
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from datetime import datetime

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("payment-service")

# Prometheus Metrics (Golden Signals)
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status_code"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency in seconds", ["endpoint"], buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0])
PAYMENT_PROCESSED_TOTAL = Counter("payment_transactions_total", "Total payments processed", ["status", "payment_method"])
PAYMENT_VOLUME_DOLLARS = Counter("payment_volume_dollars_total", "Total volume of processed payments in USD")
ACTIVE_TRANSACTIONS = Gauge("payment_active_transactions", "Currently in-flight payment transactions")

app = FastAPI(title="CoreOps Payment Service", version="1.0.0")

# In-memory transaction journal / idempotency store (fallback or redis-backed)
transactions_store = {}

# Chaos / Failure Mode State (For SRE SLO testing)
chaos_state = {
    "failure_rate": 0.0,     # Percentage of payments that fail with 402/500
    "added_latency_ms": 0,   # Latency spike
}

@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    start_time = time.time()
    endpoint = request.url.path

    # Injected latency
    if chaos_state["added_latency_ms"] > 0:
        time.sleep(chaos_state["added_latency_ms"] / 1000.0)

    response = await call_next(request)
    duration = time.time() - start_time
    
    REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status_code=response.status_code).inc()
    REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)
    return response

class PaymentRequest(BaseModel):
    order_id: int
    customer_id: str
    amount: float
    currency: Optional[str] = "USD"
    payment_method: Optional[str] = "credit_card"

class ChaosConfig(BaseModel):
    failure_rate: float
    added_latency_ms: int

@app.get("/healthz")
def health_check():
    return {"status": "healthy", "service": "payment-service", "timestamp": datetime.utcnow().isoformat()}

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/api/chaos/configure")
def configure_chaos(config: ChaosConfig):
    chaos_state["failure_rate"] = max(0.0, min(1.0, config.failure_rate))
    chaos_state["added_latency_ms"] = max(0, config.added_latency_ms)
    logger.info(f"Payment Chaos updated: failure_rate={chaos_state['failure_rate']}, latency={chaos_state['added_latency_ms']}ms")
    return {"status": "chaos_configured", "config": chaos_state}

@app.post("/api/payments/process")
async def process_payment(payment: PaymentRequest):
    ACTIVE_TRANSACTIONS.inc()
    try:
        # Check idempotency
        idempotency_key = f"order_{payment.order_id}"
        if idempotency_key in transactions_store:
            logger.info(f"Returning cached idempotent transaction for order {payment.order_id}")
            return transactions_store[idempotency_key]

        # Simulate real payment gateway processing time (20-80ms)
        time.sleep(random.uniform(0.02, 0.08))

        # Check for simulated chaos failure
        if chaos_state["failure_rate"] > 0 and random.random() < chaos_state["failure_rate"]:
            PAYMENT_PROCESSED_TOTAL.labels(status="declined_chaos", payment_method=payment.payment_method).inc()
            logger.error(f"Payment declined due to simulated gateway degradation for order {payment.order_id}")
            raise HTTPException(status_code=402, detail="Payment declined: Gateway timeout or upstream rejection")

        if payment.amount <= 0:
            PAYMENT_PROCESSED_TOTAL.labels(status="invalid_amount", payment_method=payment.payment_method).inc()
            raise HTTPException(status_code=400, detail="Invalid payment amount")

        # Record successful transaction
        tx_id = f"txn_{uuid.uuid4().hex[:12]}"
        tx_record = {
            "transaction_id": tx_id,
            "order_id": payment.order_id,
            "customer_id": payment.customer_id,
            "amount": payment.amount,
            "currency": payment.currency,
            "status": "SETTLED",
            "timestamp": datetime.utcnow().isoformat()
        }
        transactions_store[idempotency_key] = tx_record
        
        PAYMENT_PROCESSED_TOTAL.labels(status="success", payment_method=payment.payment_method).inc()
        PAYMENT_VOLUME_DOLLARS.inc(payment.amount)
        logger.info(f"Successfully processed payment {tx_id} of ${payment.amount} for order {payment.order_id}")
        return tx_record

    finally:
        ACTIVE_TRANSACTIONS.dec()

@app.get("/api/payments/transactions/{transaction_id}")
def get_transaction(transaction_id: str):
    for tx in transactions_store.values():
        if tx["transaction_id"] == transaction_id:
            return tx
    raise HTTPException(status_code=404, detail="Transaction not found")
