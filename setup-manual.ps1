# LoadOpt Manual Setup Script
# Run this to set up the project without Docker

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   LoadOpt Manual Setup (No Docker)    " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Function to check if command exists
function Test-Command {
    param($Command)
    $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
}

# Check Python
Write-Host "Checking prerequisites..." -ForegroundColor Yellow
Write-Host ""

if (Test-Command python) {
    $pythonVersion = python --version
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "✗ Python not found!" -ForegroundColor Red
    Write-Host "  Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# Check Node.js
if (Test-Command node) {
    $nodeVersion = node --version
    Write-Host "✓ Node.js found: $nodeVersion" -ForegroundColor Green
} else {
    Write-Host "✗ Node.js not found!" -ForegroundColor Red
    Write-Host "  Download from: https://nodejs.org/" -ForegroundColor Yellow
    exit 1
}

# Check PostgreSQL (optional)
if (Test-Command psql) {
    Write-Host "✓ PostgreSQL found" -ForegroundColor Green
    $hasPostgres = $true
} else {
    Write-Host "⚠ PostgreSQL not found (will use SQLite instead)" -ForegroundColor Yellow
    $hasPostgres = $false
}

Write-Host ""
Write-Host "Setting up backend..." -ForegroundColor Cyan
Write-Host ""

# Navigate to backend
Push-Location backend

# Create virtual environment
if (-not (Test-Path "venv")) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv venv
    Write-Host "✓ Virtual environment created" -ForegroundColor Green
} else {
    Write-Host "✓ Virtual environment already exists" -ForegroundColor Green
}

# Activate virtual environment and install dependencies
Write-Host "Installing Python dependencies (this may take a few minutes)..." -ForegroundColor Yellow
& .\venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\venv\Scripts\pip.exe install -r requirements.txt --quiet

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Python dependencies installed" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to install Python dependencies" -ForegroundColor Red
    Pop-Location
    exit 1
}

# Create .env file
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env file..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    
    # If no PostgreSQL, update to use SQLite
    if (-not $hasPostgres) {
        $envContent = Get-Content ".env" -Raw
        $envContent = $envContent -replace 'DATABASE_URL=postgresql://.*', 'DATABASE_URL=sqlite:///./loadopt.db'
        Set-Content ".env" $envContent
        Write-Host "✓ .env configured for SQLite" -ForegroundColor Green
    } else {
        Write-Host "✓ .env created (using PostgreSQL)" -ForegroundColor Green
        Write-Host "  Note: Make sure PostgreSQL is running and database 'loadopt' exists" -ForegroundColor Yellow
    }
} else {
    Write-Host "✓ .env already exists" -ForegroundColor Green
}

Pop-Location

Write-Host ""
Write-Host "Setting up frontend..." -ForegroundColor Cyan
Write-Host ""

# Navigate to frontend
Push-Location frontend

# Install dependencies
if (Test-Path "node_modules") {
    Write-Host "✓ Node modules already installed" -ForegroundColor Green
} else {
    Write-Host "Installing Node dependencies (this may take a few minutes)..." -ForegroundColor Yellow
    npm install --silent 2>&1 | Out-Null
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Node dependencies installed" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to install Node dependencies" -ForegroundColor Red
        Pop-Location
        exit 1
    }
}

Pop-Location

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   Setup Complete! ✓                   " -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host ""

if ($hasPostgres) {
    Write-Host "1. Make sure PostgreSQL is running and create the database:" -ForegroundColor White
    Write-Host "   psql -U postgres -c `"CREATE DATABASE loadopt;`"" -ForegroundColor Gray
    Write-Host ""
}

Write-Host "2. Start the backend (in a new terminal):" -ForegroundColor White
Write-Host "   cd backend" -ForegroundColor Gray
Write-Host "   .\venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "   uvicorn app.main:app --reload" -ForegroundColor Gray
Write-Host ""

Write-Host "3. Start the frontend (in another new terminal):" -ForegroundColor White
Write-Host "   cd frontend" -ForegroundColor Gray
Write-Host "   npm run dev" -ForegroundColor Gray
Write-Host ""

Write-Host "4. Open your browser:" -ForegroundColor White
Write-Host "   http://localhost:3000" -ForegroundColor Cyan
Write-Host ""

Write-Host "For detailed instructions, see: MANUAL_SETUP.md" -ForegroundColor Yellow
Write-Host ""

# Ask if user wants to start services now
Write-Host "Would you like to start the backend now? (y/n): " -ForegroundColor Yellow -NoNewline
$response = Read-Host

if ($response -eq 'y' -or $response -eq 'Y') {
    Write-Host ""
    Write-Host "Starting backend server..." -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
    Write-Host ""
    
    Push-Location backend
    & .\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    Pop-Location
}
