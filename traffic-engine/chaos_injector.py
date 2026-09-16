#!/usr/bin/env python3
"""
SentinelMesh SRE Chaos Engineering Engine
Injects controlled failure modes and latency spikes to test:
- Multi-Window Multi-Burn-Rate SLO alerting
- Self-healing & auto-remediation controllers
- Error budget burndown rates in Prometheus & Grafana
"""

import os
import sys
import time
import logging
import argparse
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [CHAOS-INJECTOR]: %(message)s")
logger = logging.getLogger("chaos-injector")

ORDERS_URL = os.getenv("ORDERS_URL", "http://localhost:8001")
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://localhost:8002")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8003")

def set_service_chaos(service_name: str, url: str, error_rate: float, latency_ms: int):
    endpoint = f"{url}/api/chaos/configure"
    payload = {"error_rate": error_rate, "added_latency_ms": latency_ms}
    if "payment" in service_name.lower():
        payload = {"failure_rate": error_rate, "added_latency_ms": latency_ms}
    
    try:
        resp = requests.post(endpoint, json=payload, timeout=5)
        if resp.status_code == 200:
            logger.info(f"[{service_name.upper()}] Chaos configured: Error Rate={error_rate*100}%, Added Latency={latency_ms}ms")
        else:
            logger.error(f"[{service_name.upper()}] Failed to configure chaos: HTTP {resp.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"[{service_name.upper()}] Connection error reaching {endpoint}: {e}")

def run_burn_rate_simulation(duration_sec: int = 60):
    logger.info("===============================================================")
    logger.info("🚀 EXECUTING SRE EXPERIMENT: 14.4x SLO Error Budget Burn Rate")
    logger.info("   Target: 99.9% Availability SLO | Allowed Budget: 0.1%")
    logger.info(f"   Injecting 15% error rate on Orders & Payment for {duration_sec}s")
    logger.info("===============================================================")
    
    # Inject errors
    set_service_chaos("Orders Service", ORDERS_URL, error_rate=0.15, latency_ms=150)
    set_service_chaos("Payment Service", PAYMENT_URL, error_rate=0.20, latency_ms=200)

    for remaining in range(duration_sec, 0, -10):
        logger.info(f"Chaos active... Remaining duration: {remaining}s")
        time.sleep(min(10, remaining))

    logger.info("===============================================================")
    logger.info("🛑 RECOVERING SYSTEM: Clearing all chaos state")
    logger.info("===============================================================")
    set_service_chaos("Orders Service", ORDERS_URL, error_rate=0.0, latency_ms=0)
    set_service_chaos("Payment Service", PAYMENT_URL, error_rate=0.0, latency_ms=0)
    set_service_chaos("Inventory Service", INVENTORY_URL, error_rate=0.0, latency_ms=0)
    logger.info("System recovered to nominal baseline.")

def run_latency_spike(duration_sec: int = 45, latency_ms: int = 1500):
    logger.info(f"🚀 EXECUTING SRE EXPERIMENT: Critical P99 Latency Degradation ({latency_ms}ms)")
    set_service_chaos("Orders Service", ORDERS_URL, error_rate=0.0, latency_ms=latency_ms)
    time.sleep(duration_sec)
    set_service_chaos("Orders Service", ORDERS_URL, error_rate=0.0, latency_ms=0)
    logger.info("Latency experiment completed.")

def reset_all():
    logger.info("Clearing all chaos configurations...")
    set_service_chaos("Orders Service", ORDERS_URL, error_rate=0.0, latency_ms=0)
    set_service_chaos("Payment Service", PAYMENT_URL, error_rate=0.0, latency_ms=0)
    set_service_chaos("Inventory Service", INVENTORY_URL, error_rate=0.0, latency_ms=0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SentinelMesh SRE Chaos Injector")
    parser.add_argument("--scenario", type=str, choices=["burn-rate", "latency", "reset"], default="burn-rate", help="Chaos scenario to execute")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--latency-ms", type=int, default=1500, help="Latency in ms for latency scenario")
    args = parser.parse_args()

    if args.scenario == "burn-rate":
        run_burn_rate_simulation(duration_sec=args.duration)
    elif args.scenario == "latency":
        run_latency_spike(duration_sec=args.duration, latency_ms=args.latency_ms)
    elif args.scenario == "reset":
        reset_all()
