# LoadOpt 3D Planner - Complete Deployment Guide

This guide provides step-by-step instructions to run LoadOpt locally and with Docker.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development Setup](#local-development-setup)
3. [Docker Deployment](#docker-deployment)
4. [Environment Configuration](#environment-configuration)
5. [Testing the Application](#testing-the-application)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

#### For Local Development:
- **Python 3.9+** - [Download](https://www.python.org/downloads/)
- **Node.js 18+** - [Download](https://nodejs.org/)
- **PostgreSQL 13+** (recommended) or SQLite
- **Redis 6+** - [Download](https://redis.io/download)
- **Git** - [Download](https://git-scm.com/)

#### For Docker Deployment:
- **Docker Desktop** - [Download](https://www.docker.com/products/docker-desktop)
- **Docker Compose** (included with Docker Desktop)

---

## Local Development Setup

### Step 1: Clone the Repository

```bash
# Clone the repository
git clone <your-repo-url>
cd loadopt

# Verify directory structure
ls -la
# You should see: backend/, frontend/, docs/, etc.
```

### Step 2: Set Up Backend (FastAPI)

#### 2.1 Navigate to Backend Directory
```bash
cd backend
```

#### 2.2 Create Python Virtual Environment
```bash
# On Windows
python -m venv venv
venv\Scripts\activate

# On macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

You should see `(venv)` in your terminal prompt.

#### 2.3 Install Python Dependencies
```bash
# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

**Expected packages include:**
- FastAPI
- Uvicorn
- SQLAlchemy
- Pydantic
- python-jose (JWT)
- passlib (password hashing)
- psycopg2-binary (PostgreSQL)
- redis
- celery
- And more...

#### 2.4 Set Up PostgreSQL Database

**Option A: Using PostgreSQL (Recommended for Production)**

```bash
# Install PostgreSQL (if not installed)
# Windows: Download from postgresql.org
# macOS: brew install postgresql
# Linux: sudo apt-get install postgresql

# Start PostgreSQL service
# Windows: Check Services app
# macOS: brew services start postgresql
# Linux: sudo systemctl start postgresql

# Create database
psql -U postgres
CREATE DATABASE loadopt;
CREATE USER loadopt_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE loadopt TO loadopt_user;
\q
```

**Option B: Using SQLite (Quick Start/Development)**

SQLite requires no setup - it will create a file automatically.

#### 2.5 Set Up Redis

```bash
# Install Redis
# Windows: Download from https://github.com/microsoftarchive/redis/releases
# macOS: brew install redis
# Linux: sudo apt-get install redis-server

# Start Redis
# Windows: redis-server.exe
# macOS: brew services start redis
# Linux: sudo systemctl start redis

# Test Redis connection
redis-cli ping
# Should return: PONG
```

#### 2.6 Configure Environment Variables

Create `.env` file in the `backend/` directory:

```bash
# Create .env file
touch .env  # macOS/Linux
type nul > .env  # Windows

# Edit .env file with your favorite editor
```

**Add the following content to `.env`:**

```env
# Application Settings
PROJECT_NAME=LoadOpt 3D Planner
VERSION=1.0.0
API_V1_PREFIX=/api/v1
ENVIRONMENT=development

# Database Configuration
# For PostgreSQL:
DATABASE_URL=postgresql://loadopt_user:your_secure_password@localhost:5432/loadopt

# For SQLite (alternative):
# DATABASE_URL=sqlite:///./loadopt.db

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Security (IMPORTANT: Generate a secure key!)
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
SECRET_KEY=your-super-secret-key-at-least-32-characters-long-change-this
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# CORS Origins (add production URLs later)
CORS_ORIGINS=["http://localhost:3000", "http://localhost:5173"]

# Optimization Settings
MAX_HEURISTIC_ITEMS=200
GA_POPULATION_SIZE=100
GA_GENERATIONS=50
GA_MUTATION_RATE=0.1
GA_CROSSOVER_RATE=0.8
```

**Generate a secure SECRET_KEY:**

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output and replace `SECRET_KEY` value in `.env`.

#### 2.7 Initialize Database

```bash
# The application will automatically create tables on startup
# But you can verify the connection:
python -c "from app.core.database import engine; from sqlalchemy import text; engine.connect().execute(text('SELECT 1')); print('Database connection successful!')"
```

#### 2.8 Start Backend Server

```bash
# Make sure you're in backend/ directory with venv activated
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected output:**
```
INFO:     Will watch for changes in these directories: ['/path/to/loadopt/backend']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345]
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Creating database tables...
INFO:     Database tables created successfully
INFO:     Starting LoadOpt 3D Planner v1.0.0
INFO:     Environment: development
INFO:     API Documentation: Enabled
INFO:     Application startup complete.
```

**Test the backend:**
```bash
# In a new terminal
curl http://localhost:8000/health

# Expected response:
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "development",
  "checks": {
    "database": "ok",
    "redis": "skipped"
  }
}
```

**Access API Documentation:**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

### Step 3: Set Up Frontend (React + TypeScript)

Open a **new terminal** (keep backend running).

#### 3.1 Navigate to Frontend Directory
```bash
cd frontend  # From project root
```

#### 3.2 Install Node.js Dependencies
```bash
# Install packages
npm install

# This may take a few minutes
```

#### 3.3 Configure Frontend Environment (Optional)

The frontend is pre-configured to proxy to `http://localhost:8000`.

If you need to change the API URL, edit `frontend/vite.config.ts`:

```typescript
export default defineConfig({
  // ...
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',  // Change if needed
        changeOrigin: true,
      },
    },
  },
});
```

#### 3.4 Start Frontend Development Server

```bash
npm run dev
```

**Expected output:**
```
VITE v5.x.x  ready in 500 ms

➜  Local:   http://localhost:5173/
➜  Network: use --host to expose
➜  press h + enter to show help
```

**Access the application:**
Open your browser and go to: http://localhost:5173

---

### Step 4: Create Your First User

#### Option A: Using the Frontend UI
1. Go to http://localhost:5173/signup
2. Fill in the signup form:
   - Email: your@email.com
   - Username: yourname
   - Password: your_secure_password
3. Click "Sign Up"
4. Login with your credentials

#### Option B: Using API Directly
```bash
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@loadopt.com",
    "username": "admin",
    "password": "SecurePassword123!",
    "full_name": "Admin User"
  }'
```

---

### Step 5: Verify Everything Works

1. **Backend Health Check:**
   ```bash
   curl http://localhost:8000/health
   ```

2. **Frontend Access:**
   - Open http://localhost:5173
   - Login with your credentials
   - Create a new project

3. **Check Logs:**
   - Backend logs: Terminal running `uvicorn`
   - Backend error logs: `backend/logs/error.log`
   - Backend debug logs: `backend/logs/debug.log`

---

## Docker Deployment

Docker provides an easier way to run the entire application with all dependencies.

### Step 1: Create Docker Configuration Files

#### 1.1 Create `docker-compose.yml` in project root:

```bash
cd /path/to/loadopt  # Go to project root
touch docker-compose.yml  # Create file
```

Add the following content:

```yaml
version: '3.8'

services:
  # PostgreSQL Database
  postgres:
    image: postgres:15-alpine
    container_name: loadopt_postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: loadopt
      POSTGRES_USER: loadopt_user
      POSTGRES_PASSWORD: loadopt_secure_password_123
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U loadopt_user -d loadopt"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis Cache
  redis:
    image: redis:7-alpine
    container_name: loadopt_redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Backend API
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: loadopt_backend
    restart: unless-stopped
    env_file:
      - ./backend/.env
    environment:
      DATABASE_URL: postgresql://loadopt_user:loadopt_secure_password_123@postgres:5432/loadopt
      REDIS_URL: redis://redis:6379/0
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend/logs:/app/logs
      - ./backend/uploads:/app/uploads
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000

  # Frontend Web App
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: loadopt_frontend
    restart: unless-stopped
    ports:
      - "3000:80"
    depends_on:
      - backend
    environment:
      - VITE_API_URL=http://localhost:8000

volumes:
  postgres_data:
  redis_data:
```

#### 1.2 Create Backend Dockerfile

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p logs uploads

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 1.3 Create Frontend Dockerfile

Create `frontend/Dockerfile`:

```dockerfile
# Build stage
FROM node:18-alpine as build

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build production bundle
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built files from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

#### 1.4 Create Nginx Configuration

Create `frontend/nginx.conf`:

```nginx
server {
    listen 80;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # SPA routing - serve index.html for all routes
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxy
    location /api {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

#### 1.5 Create Backend .env for Docker

Create or update `backend/.env`:

```env
PROJECT_NAME=LoadOpt 3D Planner
VERSION=1.0.0
API_V1_PREFIX=/api/v1
ENVIRONMENT=production

# These will be overridden by docker-compose.yml
DATABASE_URL=postgresql://loadopt_user:loadopt_secure_password_123@postgres:5432/loadopt
REDIS_URL=redis://redis:6379/0

# Generate a new secure key for production!
SECRET_KEY=GENERATE_A_NEW_SECURE_KEY_HERE_32_PLUS_CHARACTERS
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

CORS_ORIGINS=["http://localhost:3000", "http://localhost:8000"]

MAX_HEURISTIC_ITEMS=200
GA_POPULATION_SIZE=100
GA_GENERATIONS=50
GA_MUTATION_RATE=0.1
GA_CROSSOVER_RATE=0.8
```

**Important:** Generate a new SECRET_KEY:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

### Step 2: Build and Run with Docker

#### 2.1 Build Docker Images

```bash
# From project root directory
docker-compose build

# This will take several minutes on first build
```

#### 2.2 Start All Services

```bash
# Start in detached mode (background)
docker-compose up -d

# Or start with logs visible
docker-compose up
```

**Expected output:**
```
Creating loadopt_postgres ... done
Creating loadopt_redis    ... done
Creating loadopt_backend  ... done
Creating loadopt_frontend ... done
```

#### 2.3 Verify Containers are Running

```bash
docker-compose ps
```

**Expected output:**
```
NAME                   STATUS              PORTS
loadopt_postgres       Up 30 seconds       0.0.0.0:5432->5432/tcp
loadopt_redis          Up 30 seconds       0.0.0.0:6379->6379/tcp
loadopt_backend        Up 25 seconds       0.0.0.0:8000->8000/tcp
loadopt_frontend       Up 20 seconds       0.0.0.0:3000->80/tcp
```

#### 2.4 Check Logs

```bash
# View all logs
docker-compose logs

# View specific service logs
docker-compose logs backend
docker-compose logs frontend

# Follow logs in real-time
docker-compose logs -f backend
```

#### 2.5 Access the Application

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

---

### Step 3: Docker Management Commands

#### Start/Stop Services
```bash
# Start services
docker-compose start

# Stop services (data persists)
docker-compose stop

# Restart services
docker-compose restart

# Restart specific service
docker-compose restart backend
```

#### Stop and Remove Containers
```bash
# Stop and remove containers (data persists in volumes)
docker-compose down

# Stop and remove containers + volumes (DELETES ALL DATA!)
docker-compose down -v
```

#### View Logs
```bash
# All logs
docker-compose logs

# Specific service
docker-compose logs backend -f  # -f to follow

# Last 100 lines
docker-compose logs --tail=100
```

#### Execute Commands in Containers
```bash
# Access backend shell
docker-compose exec backend bash

# Access PostgreSQL
docker-compose exec postgres psql -U loadopt_user -d loadopt

# Access Redis CLI
docker-compose exec redis redis-cli
```

#### Rebuild After Code Changes
```bash
# Rebuild specific service
docker-compose build backend

# Rebuild and restart
docker-compose up -d --build backend

# Rebuild everything
docker-compose build --no-cache
docker-compose up -d
```

---

## Environment Configuration

### Development vs Production

#### Development (.env)
```env
ENVIRONMENT=development
DATABASE_URL=sqlite:///./loadopt.db  # or PostgreSQL
SECRET_KEY=dev-key-change-in-production
```

#### Production (.env)
```env
ENVIRONMENT=production
DATABASE_URL=postgresql://user:pass@host:5432/dbname
SECRET_KEY=<generate-secure-32-char-key>
```

### Generating Secure Keys

```bash
# Python method
python -c "import secrets; print(secrets.token_urlsafe(32))"

# OpenSSL method
openssl rand -base64 32
```

---

## Testing the Application

### 1. Backend API Tests

```bash
# Test health endpoint
curl http://localhost:8000/health

# Create a user
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "username": "testuser",
    "password": "TestPass123!",
    "full_name": "Test User"
  }'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=testuser&password=TestPass123!"

# Response will include: {"access_token": "...", "token_type": "bearer"}
```

### 2. Frontend Tests

1. Open http://localhost:3000 (Docker) or http://localhost:5173 (local)
2. Click "Sign Up" and create an account
3. Login with your credentials
4. Create a new project
5. Add containers and SKUs
6. Create an optimization plan

### 3. Database Verification

```bash
# Local PostgreSQL
psql -U loadopt_user -d loadopt -c "SELECT * FROM users;"

# Docker PostgreSQL
docker-compose exec postgres psql -U loadopt_user -d loadopt -c "SELECT * FROM users;"

# SQLite
sqlite3 backend/loadopt.db "SELECT * FROM users;"
```

---

## Troubleshooting

### Common Issues

#### 1. Backend Won't Start

**Error:** "Configuration validation failed: SECRET_KEY must be at least 32 characters"

**Solution:**
```bash
# Generate new key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Update .env file with the generated key
```

---

**Error:** "Could not connect to database"

**Solution:**
```bash
# Check PostgreSQL is running
# Local:
pg_isready -h localhost -p 5432

# Docker:
docker-compose ps postgres

# Check DATABASE_URL in .env matches your database
```

---

**Error:** "Redis connection failed"

**Solution:**
```bash
# Check Redis is running
# Local:
redis-cli ping

# Docker:
docker-compose ps redis

# Check REDIS_URL in .env
```

---

#### 2. Frontend Won't Start

**Error:** "Failed to fetch" or CORS errors

**Solution:**
```bash
# Ensure backend is running first
curl http://localhost:8000/health

# Check CORS settings in backend/app/main.py
# Should include frontend URL
```

---

**Error:** "npm install fails"

**Solution:**
```bash
# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm cache clean --force
npm install
```

---

#### 3. Docker Issues

**Error:** "Port already in use"

**Solution:**
```bash
# Find what's using the port
# Windows:
netstat -ano | findstr :8000

# macOS/Linux:
lsof -i :8000

# Kill the process or change port in docker-compose.yml
```

---

**Error:** "Container exits immediately"

**Solution:**
```bash
# Check logs
docker-compose logs backend

# Common causes:
# - Missing .env file
# - Database connection failed
# - Invalid SECRET_KEY
```

---

**Error:** "Cannot connect to database from backend container"

**Solution:**
```bash
# In docker-compose.yml, use service names not 'localhost'
DATABASE_URL=postgresql://user:pass@postgres:5432/loadopt
# NOT: postgresql://user:pass@localhost:5432/loadopt

# Restart services
docker-compose restart backend
```

---

#### 4. Database Issues

**Error:** "Table does not exist"

**Solution:**
```bash
# Tables are auto-created on startup
# Check backend logs during startup

# Or manually create:
# Local:
python -c "from app.core.database import Base, engine; Base.metadata.create_all(bind=engine)"

# Docker:
docker-compose exec backend python -c "from app.core.database import Base, engine; Base.metadata.create_all(bind=engine)"
```

---

#### 5. Permission Issues (Linux/macOS)

**Error:** "Permission denied" when running scripts

**Solution:**
```bash
# Make scripts executable
chmod +x script_name.sh

# Fix log directory permissions
sudo chown -R $USER:$USER backend/logs
```

---

### Getting Help

If you encounter issues:

1. **Check logs:**
   - Backend: `backend/logs/error.log`
   - Docker: `docker-compose logs`

2. **Verify environment:**
   ```bash
   # Check all environment variables are set
   cat backend/.env
   ```

3. **Health checks:**
   ```bash
   # Backend
   curl http://localhost:8000/health

   # Database
   docker-compose exec postgres pg_isready

   # Redis
   docker-compose exec redis redis-cli ping
   ```

4. **Restart everything:**
   ```bash
   # Local
   # Ctrl+C in backend terminal
   # Ctrl+C in frontend terminal
   # Restart both

   # Docker
   docker-compose restart
   ```

---

## Quick Reference Commands

### Local Development
```bash
# Backend
cd backend
source venv/bin/activate  # or venv\Scripts\activate on Windows
uvicorn app.main:app --reload

# Frontend
cd frontend
npm run dev
```

### Docker
```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# View logs
docker-compose logs -f

# Rebuild
docker-compose up -d --build

# Clean restart
docker-compose down
docker-compose up -d --build
```

### Database
```bash
# Local PostgreSQL
psql -U loadopt_user -d loadopt

# Docker PostgreSQL
docker-compose exec postgres psql -U loadopt_user -d loadopt

# Backup
docker-compose exec postgres pg_dump -U loadopt_user loadopt > backup.sql

# Restore
docker-compose exec -T postgres psql -U loadopt_user loadopt < backup.sql
```

---

## Production Deployment Checklist

Before deploying to production:

- [ ] Change ENVIRONMENT to "production" in .env
- [ ] Generate new SECRET_KEY (32+ characters)
- [ ] Use PostgreSQL (not SQLite)
- [ ] Set up SSL/TLS certificates
- [ ] Configure proper CORS origins
- [ ] Set up database backups
- [ ] Configure log rotation
- [ ] Set up monitoring and alerts
- [ ] Use strong database passwords
- [ ] Configure firewall rules
- [ ] Review PRODUCTION_READY.md document

---

## Additional Resources

- **API Documentation:** http://localhost:8000/docs
- **Project Documentation:** See `PRODUCTION_READY.md`
- **Review Summary:** See `REVIEW_SUMMARY.md`

---

**You're all set!** 🚀

Choose your preferred method (Local or Docker) and start building amazing load optimization plans!
