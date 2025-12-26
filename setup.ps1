# Run this script to set up the development environment on Windows

Write-Host "LoadOpt Setup Script" -ForegroundColor Green
Write-Host "===================" -ForegroundColor Green
Write-Host ""

# Check prerequisites
Write-Host "Checking prerequisites..." -ForegroundColor Yellow

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python not found. Please install Python 3.11+" -ForegroundColor Red
    exit 1
}

# Check Node.js
try {
    $nodeVersion = node --version 2>&1
    Write-Host "✓ Node.js found: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Node.js not found. Please install Node.js 20+" -ForegroundColor Red
    exit 1
}

# Check Docker
try {
    $dockerVersion = docker --version 2>&1
    Write-Host "✓ Docker found: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "⚠ Docker not found. Docker is optional but recommended" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setting up backend..." -ForegroundColor Yellow

# Setup backend
Set-Location backend

# Create virtual environment
if (-not (Test-Path "venv")) {
    Write-Host "Creating Python virtual environment..."
    python -m venv venv
}

# Activate virtual environment
Write-Host "Activating virtual environment..."
.\venv\Scripts\Activate.ps1

# Install dependencies
Write-Host "Installing Python dependencies..."
pip install -r requirements.txt

# Create .env if not exists
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env file..."
    Copy-Item ".env.example" ".env"
    Write-Host "⚠ Please edit backend/.env with your configuration" -ForegroundColor Yellow
}

Set-Location ..

Write-Host ""
Write-Host "Setting up frontend..." -ForegroundColor Yellow

# Setup frontend
Set-Location frontend

# Install dependencies
Write-Host "Installing Node dependencies..."
npm install

Set-Location ..

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Start PostgreSQL and Redis (or use Docker Compose)"
Write-Host "   docker-compose up postgres redis"
Write-Host ""
Write-Host "2. Start backend (in backend/ directory):"
Write-Host "   .\venv\Scripts\Activate.ps1"
Write-Host "   uvicorn app.main:app --reload"
Write-Host ""
Write-Host "3. Start frontend (in frontend/ directory):"
Write-Host "   npm run dev"
Write-Host ""
Write-Host "Or use Docker Compose to start everything:"
Write-Host "   docker-compose up"
Write-Host ""
Write-Host "Access the application at http://localhost:3000" -ForegroundColor Green
