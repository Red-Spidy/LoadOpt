Write-Host "LoadOpt Manual Setup" -ForegroundColor Cyan
Write-Host "====================" -ForegroundColor Cyan
Write-Host ""

# Check Python
Write-Host "Checking Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "Python not found! Install from https://www.python.org/" -ForegroundColor Red
    exit 1
}

# Check Node
Write-Host "Checking Node.js..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version 2>&1
    Write-Host "Found: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "Node.js not found! Install from https://nodejs.org/" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Setting up backend..." -ForegroundColor Cyan

# Backend setup
Set-Location backend

if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv venv
}

Write-Host "Installing Python packages..."
& .\venv\Scripts\python.exe -m pip install --upgrade pip 2>&1 | Out-Null
& .\venv\Scripts\pip.exe install -r requirements.txt 2>&1 | Out-Null
Write-Host "Backend packages installed!" -ForegroundColor Green

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    $env = Get-Content ".env" -Raw
    $env = $env -replace 'DATABASE_URL=postgresql://.*', 'DATABASE_URL=sqlite:///./loadopt.db'
    Set-Content ".env" $env
    Write-Host ".env created (using SQLite)" -ForegroundColor Green
}

Set-Location ..

Write-Host ""
Write-Host "Setting up frontend..." -ForegroundColor Cyan

# Frontend setup
Set-Location frontend

Write-Host "Installing Node packages (may take a few minutes)..."
npm install 2>&1 | Out-Null
Write-Host "Frontend packages installed!" -ForegroundColor Green

Set-Location ..

Write-Host ""
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To start the application:" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Backend (terminal 1):" -ForegroundColor White
Write-Host "   cd backend"
Write-Host "   .\venv\Scripts\Activate.ps1"
Write-Host "   uvicorn app.main:app --reload"
Write-Host ""
Write-Host "2. Frontend (terminal 2):" -ForegroundColor White
Write-Host "   cd frontend"
Write-Host "   npm run dev"
Write-Host ""
Write-Host "3. Open http://localhost:3000" -ForegroundColor White
Write-Host ""
