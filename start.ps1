# LoadOpt Quick Start Script
# This script starts all services needed for development

Write-Host "`n=== LoadOpt Quick Start ===" -ForegroundColor Cyan
Write-Host "Starting all services...`n" -ForegroundColor Green

# Check if we're in the loadopt directory
if (-not (Test-Path "backend") -or -not (Test-Path "frontend")) {
    Write-Host "Error: Please run this script from the loadopt root directory" -ForegroundColor Red
    exit 1
}

# Function to check if port is in use
function Test-Port {
    param([int]$Port)
    $connection = Test-NetConnection -ComputerName localhost -Port $Port -WarningAction SilentlyContinue
    return $connection.TcpTestSucceeded
}

# Check if services are already running
$portsInUse = @()
if (Test-Port 8000) { $portsInUse += "8000 (Backend)" }
if (Test-Port 5173) { $portsInUse += "5173 (Frontend)" }
if (Test-Port 5432) { $portsInUse += "5432 (PostgreSQL)" }
if (Test-Port 6379) { $portsInUse += "6379 (Redis)" }

if ($portsInUse.Count -gt 0) {
    Write-Host "Warning: The following ports are already in use:" -ForegroundColor Yellow
    $portsInUse | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host ""
    $response = Read-Host "Continue anyway? (y/n)"
    if ($response -ne "y") {
        exit 0
    }
}

Write-Host "`n1. Starting Backend API Server..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
`$host.ui.RawUI.WindowTitle='LoadOpt Backend'
Write-Host 'Starting Backend API Server...' -ForegroundColor Green
cd '$PWD\backend'
if (Test-Path 'venv\Scripts\Activate.ps1') {
    .\venv\Scripts\Activate.ps1
    Write-Host 'Virtual environment activated' -ForegroundColor Green
} else {
    Write-Host 'Error: Virtual environment not found. Run setup.ps1 first!' -ForegroundColor Red
    pause
    exit
}
Write-Host 'Starting uvicorn server...' -ForegroundColor Cyan
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
"@

Start-Sleep -Seconds 2

Write-Host "`n2. Starting Celery Worker (Optional)..." -ForegroundColor Cyan
$response = Read-Host "Do you want to start Celery worker for async optimization? (y/n)"
if ($response -eq "y") {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
`$host.ui.RawUI.WindowTitle='LoadOpt Celery Worker'
Write-Host 'Starting Celery Worker...' -ForegroundColor Green
cd '$PWD\backend'
.\venv\Scripts\Activate.ps1
Write-Host 'Starting worker with --pool=solo (Windows compatible)...' -ForegroundColor Cyan
celery -A app.workers.celery_app worker --loglevel=info --pool=solo
"@
    Start-Sleep -Seconds 2
}

Write-Host "`n3. Starting Frontend Dev Server..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", @"
`$host.ui.RawUI.WindowTitle='LoadOpt Frontend'
Write-Host 'Starting Frontend Development Server...' -ForegroundColor Green
cd '$PWD\frontend'
if (Test-Path 'node_modules') {
    Write-Host 'Dependencies found, starting Vite...' -ForegroundColor Green
} else {
    Write-Host 'Installing dependencies first...' -ForegroundColor Yellow
    npm install
}
Write-Host 'Starting Vite dev server...' -ForegroundColor Cyan
npm run dev
"@

Start-Sleep -Seconds 3

Write-Host "`n=== Services Started ===" -ForegroundColor Green
Write-Host ""
Write-Host "Backend API:   http://localhost:8000" -ForegroundColor Cyan
Write-Host "API Docs:      http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "Frontend:      http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "Check the separate terminal windows for each service." -ForegroundColor Yellow
Write-Host "Press Ctrl+C in each window to stop the services." -ForegroundColor Yellow
Write-Host ""
Write-Host "To stop all services:" -ForegroundColor White
Write-Host "  Get-Process python,node -ErrorAction SilentlyContinue | Stop-Process" -ForegroundColor Gray
Write-Host ""

# Wait and provide helpful info
Start-Sleep -Seconds 5
Write-Host "Checking service health..." -ForegroundColor Cyan

$maxAttempts = 10
$attempt = 0
$backendReady = $false

while (-not $backendReady -and $attempt -lt $maxAttempts) {
    $attempt++
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 2 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $backendReady = $true
            Write-Host "✓ Backend API is ready!" -ForegroundColor Green
        }
    } catch {
        Write-Host "  Waiting for backend... (attempt $attempt/$maxAttempts)" -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
}

if (-not $backendReady) {
    Write-Host "⚠ Backend may take longer to start. Check the Backend terminal window." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Quick Start Guide ===" -ForegroundColor Cyan
Write-Host "1. Open http://localhost:5173 in your browser" -ForegroundColor White
Write-Host "2. Click 'Sign Up' to create an account" -ForegroundColor White
Write-Host "3. Create a new project" -ForegroundColor White
Write-Host "4. Import SKUs using sample_skus.csv" -ForegroundColor White
Write-Host "5. Add a container (e.g., 1200x235x270 cm, 28000 kg)" -ForegroundColor White
Write-Host "6. Create a loading plan and watch the magic!" -ForegroundColor White
Write-Host ""
Write-Host "Happy planning! 🚀" -ForegroundColor Green
