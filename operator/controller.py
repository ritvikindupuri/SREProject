import os
import logging
from typing import Dict, Any
from fastapi import FastAPI, Request, Response, status
from pydantic import BaseModel
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from datetime import datetime

from quarantine import QuarantineEngine
from self_healer import SRESelfHealer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [COREOPS-OPERATOR]: %(message)s")
logger = logging.getLogger("coreops-operator")

# Prometheus Operator Telemetry
SECURITY_INCIDENTS_TOTAL = Counter("coreops_security_incidents_total", "Total runtime security threats intercepted", ["rule", "priority"])
SRE_INCIDENTS_TOTAL = Counter("coreops_sre_incidents_total", "Total SRE SLO burn alerts intercepted", ["service", "severity"])
AUTO_REMEDIATION_TOTAL = Counter("sentinel_auto_remediations_total", "Total incidents autonomously resolved", ["type"])
QUARANTINED_WORKLOADS = Gauge("sentinel_quarantined_workloads_active", "Number of currently isolated compromised workloads")

app = FastAPI(title="CoreOps Autonomous SRE & Security Operator", version="1.0.0")

quarantine_engine = QuarantineEngine()
self_healer = SRESelfHealer()

@app.get("/healthz")
def health_check():
    return {"status": "healthy", "operator": "CoreOps-Controller-v1", "timestamp": datetime.utcnow().isoformat()}

@app.get("/metrics")
def metrics():
    QUARANTINED_WORKLOADS.set(len(quarantine_engine.quarantined_targets))
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/api/v1/security-events")
async def handle_security_event(event: Dict[str, Any]):
    """
    Webhook endpoint for Falco eBPF runtime threat detection stream.
    """
    rule = event.get("rule", "Unknown")
    priority = event.get("priority", "Critical")
    SECURITY_INCIDENTS_TOTAL.labels(rule=rule, priority=priority).inc()

    # Execute automated zero-trust quarantine
    result = quarantine_engine.isolate_workload(event)
    AUTO_REMEDIATION_TOTAL.labels(type="security_quarantine").inc()
    
    return {
        "status": "INCIDENT_INTERCEPTED_AND_CONTAINED",
        "action": "ZERO_TRUST_QUARANTINE_APPLIED",
        "incident": result
    }

@app.post("/api/v1/sre-alerts")
async def handle_sre_alert(alert: Dict[str, Any]):
    """
    Webhook endpoint for Prometheus Alertmanager multi-window burn rate alerts.
    """
    service = alert.get("service", "orders-service")
    severity = alert.get("severity", "critical")
    SRE_INCIDENTS_TOTAL.labels(service=service, severity=severity).inc()

    result = await self_healer.handle_slo_burn_alert(alert)
    AUTO_REMEDIATION_TOTAL.labels(type="sre_self_healing").inc()

    return {
        "status": "SLO_BURN_MITIGATED",
        "action": "AUTONOMOUS_SELF_HEALING_COMPLETED",
        "incident": result
    }

@app.get("/api/v1/status")
def get_operator_status():
    return {
        "operator": "CoreOps Autonomous Controller",
        "active_quarantines": quarantine_engine.get_quarantined_list(),
        "sre_incidents_remediated": self_healer.get_sre_incidents(),
        "total_quarantined_count": len(quarantine_engine.quarantined_targets),
        "total_sre_remediated_count": len(self_healer.get_sre_incidents()),
        "status": "ONLINE_MONITORING"
    }

@app.post("/api/v1/quarantine/release")
def release_target(target_name: str):
    success = quarantine_engine.release_quarantine(target_name)
    return {"target": target_name, "released": success}
