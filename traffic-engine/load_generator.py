#!/usr/bin/env python3
"""
SentinelMesh Real-Time Production Traffic Generator
Simulates realistic synthetic user sessions against the API Gateway:
- Browsing inventory catalog
- Placing orders with varying quantities and items
- Checking order fulfillment status
- Handling realistic concurrency and burst patterns
"""

import os
import sys
import time
import random
import logging
import argparse
import requests
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [TRAFFIC-ENGINE]: %(message)s")
logger = logging.getLogger("load-generator")

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8005")

ITEMS = [
    {"item_id": "ITEM-SRV-01", "unit_price": 1200.00},
    {"item_id": "ITEM-FW-02",  "unit_price": 850.00},
    {"item_id": "ITEM-NIC-03", "unit_price": 320.00},
    {"item_id": "ITEM-HSM-04", "unit_price": 2400.00},
    {"item_id": "ITEM-MEM-05", "unit_price": 180.00},
]

def simulate_user_session(user_id: int):
    customer_id = f"cust_enterprise_{random.randint(1000, 9999)}"
    
    try:
        # Step 1: Browse Inventory
        inv_resp = requests.get(f"{GATEWAY_URL}/api/inventory/items", timeout=5)
        if inv_resp.status_code != 200:
            logger.warning(f"User {user_id}: Inventory browse returned {inv_resp.status_code}")
        
        # Step 2: Select 1-2 random items and place an order
        selected_item = random.choice(ITEMS)
        quantity = random.randint(1, 3)
        
        order_payload = {
            "customer_id": customer_id,
            "item_id": selected_item["item_id"],
            "quantity": quantity,
            "unit_price": selected_item["unit_price"]
        }
        
        order_resp = requests.post(f"{GATEWAY_URL}/api/orders", json=order_payload, timeout=6)
        
        if order_resp.status_code == 201:
            order_data = order_resp.json()
            order_id = order_data.get("order_id")
            logger.info(f"[SUCCESS] User {user_id} ({customer_id}) placed Order #{order_id} for {quantity}x {selected_item['item_id']} (${order_data.get('total_amount')})")
            
            # Step 3: Check Order Status
            time.sleep(random.uniform(0.05, 0.2))
            requests.get(f"{GATEWAY_URL}/api/orders/{order_id}", timeout=5)
        elif order_resp.status_code == 500 or order_resp.status_code == 503:
            logger.error(f"[SRE ALERT EVENT] User {user_id}: Order creation failed with HTTP {order_resp.status_code} ({order_resp.text})")
        else:
            logger.warning(f"[REJECTED] User {user_id}: Order rejected HTTP {order_resp.status_code}: {order_resp.text}")

    except requests.exceptions.RequestException as e:
        logger.error(f"[NETWORK ERROR] User {user_id}: Failed to reach gateway: {e}")

def run_traffic_loop(workers: int = 5, duration_sec: int = 0, rps_delay: float = 0.2):
    logger.info(f"Starting CoreOps Live Traffic Engine against {GATEWAY_URL}")
    logger.info(f"Concurrency: {workers} workers, Base inter-request sleep: {rps_delay}s")
    
    start_time = time.time()
    user_counter = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        while True:
            if duration_sec > 0 and (time.time() - start_time) > duration_sec:
                logger.info("Traffic generation completed desired duration.")
                break
            
            user_counter += 1
            executor.submit(simulate_user_session, user_counter)
            
            # Realistic Poisson jitter in traffic inter-arrival
            jitter = random.uniform(rps_delay * 0.5, rps_delay * 1.5)
            time.sleep(jitter)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CoreOps Live Traffic Generator")
    parser.add_argument("--gateway", type=str, default=GATEWAY_URL, help="API Gateway URL")
    parser.add_argument("--workers", type=int, default=5, help="Concurrent worker threads")
    parser.add_argument("--duration", type=int, default=0, help="Duration in seconds (0 = continuous)")
    parser.add_argument("--rate", type=float, default=0.2, help="Sleep delay between requests in seconds")
    args = parser.parse_args()

    GATEWAY_URL = args.gateway
    run_traffic_loop(workers=args.workers, duration_sec=args.duration, rps_delay=args.rate)
