# CoreOps Platform Demonstration Runner

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  🛡️ CoreOps: Autonomous SRE & DevSecOps Platform Demo ⚡" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# Step 1: Start full Docker Compose stack
Write-Host "`n[Step 1/5] Building and launching CoreOps Docker stack..." -ForegroundColor Yellow
docker compose up -d --build

Write-Host "Waiting 5s for microservices & Prometheus to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Step 2: Test Endpoints
Write-Host "`n[Step 2/5] Verifying Service Health..." -ForegroundColor Yellow
try {
    $gw = Invoke-RestMethod -Uri "http://localhost:8005/healthz" -TimeoutSec 3
    $op = Invoke-RestMethod -Uri "http://localhost:8088/healthz" -TimeoutSec 3
    Write-Host "✅ API Gateway: $($gw.status)" -ForegroundColor Green
    Write-Host "✅ CoreOps Operator: $($op.status)" -ForegroundColor Green
} catch {
    Write-Host "⚠️ Warning: Services still initializing: $_" -ForegroundColor DarkYellow
}

# Step 3: Run Live Traffic
Write-Host "`n[Step 3/5] Generating live real-time transactions (15 seconds)..." -ForegroundColor Yellow
python traffic-engine/load_generator.py --duration 15 --rate 0.05 --workers 3

# Step 4: Execute Cyber Threat & Auto-Quarantine Demo
Write-Host "`n[Step 4/5] Executing MITRE ATT&CK T1059.004 Runtime Breach Simulation..." -ForegroundColor Yellow
python traffic-engine/attack_simulator.py --attack shell --target orders-service

# Step 5: Execute SRE Chaos & SLO Alerting Demo
Write-Host "`n[Step 5/5] Executing 14.4x SRE Error Budget Burn Rate Experiment..." -ForegroundColor Yellow
python traffic-engine/chaos_injector.py --scenario burn-rate --duration 15

# Final Operator Status
Write-Host "`n================================================================" -ForegroundColor Cyan
Write-Host "🎉 DEMO COMPLETE! Current Operator Control Plane Status:" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
$status = Invoke-RestMethod -Uri "http://localhost:8088/api/v1/status"
$status | ConvertTo-Json -Depth 4

Write-Host "`nAccess Dashboards:" -ForegroundColor Cyan
Write-Host "📊 Grafana:     http://localhost:3000 (admin / admin)" -ForegroundColor White
Write-Host "📈 Prometheus:  http://localhost:9090" -ForegroundColor White
Write-Host "🛡️ Operator:    http://localhost:8088/api/v1/status" -ForegroundColor White
Write-Host "🚪 Gateway:     http://localhost:8005/api/inventory/items" -ForegroundColor White
