# LoadOpt 3D Planner 📦

> **Enterprise-grade 3D load planning and optimization system**

LoadOpt is a production-ready web application for optimizing container and truck loading with advanced multi-stop route planning, 3D visualization, and intelligent packing algorithms.

---

## ✨ Features

### 🎯 Core Functionality
- **3D Load Planning** - Intelligent bin packing algorithms for container optimization
- **Multi-Stop Route Optimization** - Advanced planning for delivery routes with multiple stops
- **3D Visualization** - Interactive 3D viewer using Three.js/React Three Fiber
- **Real-time Optimization** - Background processing with Celery task queue
- **SKU Management** - Comprehensive product/package management
- **Delivery Group Management** - Organize items by delivery location and priority

### 🛡️ Production Features
- **Comprehensive Logging** - Structured logging with file rotation
- **Health Monitoring** - Database connectivity and service health checks
- **Environment Validation** - Startup validation of all configuration
- **Global Error Handling** - Graceful error handling with tracking
- **JWT Authentication** - Secure user authentication and authorization
- **Request Timing** - Performance monitoring on all endpoints

---

## 🚀 Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone and start
git clone <your-repo-url>
cd loadopt
docker-compose up -d

# Access:
# Frontend: http://localhost:3000
# Backend: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### Option 2: Local Development

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

**📖 Complete setup:** See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** | **START HERE** - Complete step-by-step setup |
| [PRODUCTION_READY.md](PRODUCTION_READY.md) | Production deployment checklist |
| [REVIEW_SUMMARY.md](REVIEW_SUMMARY.md) | Code review summary |

---

## 🏗️ Tech Stack

**Backend:** FastAPI • SQLAlchemy • PostgreSQL • Redis • Celery • JWT

**Frontend:** React • TypeScript • Vite • React Three Fiber • Tailwind CSS

**Infrastructure:** Docker • Docker Compose • Nginx

---

## 🔑 Environment Setup

Create `backend/.env`:

```env
ENVIRONMENT=development
DATABASE_URL=postgresql://user:pass@localhost:5432/loadopt
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=<generate-secure-32-char-key>
```

Generate SECRET_KEY:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 📊 API Endpoints

- `POST /api/v1/auth/signup` - Create user
- `POST /api/v1/auth/login` - Login
- `GET /api/v1/projects/` - List projects
- `POST /api/v1/plans/` - Create optimization plan
- `GET /health` - Health check

**Full API docs:** http://localhost:8000/docs

---

## 🐛 Troubleshooting

```bash
# Check health
curl http://localhost:8000/health

# View logs
docker-compose logs backend

# Restart services
docker-compose restart
```

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md#troubleshooting) for more help.

---

## 📞 Support

- 📖 **Documentation:** [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- 🚀 **Quick Start:** See above
- 🐛 **Issues:** GitHub Issues

---

**Built with ❤️ for logistics optimization**

[Get Started](DEPLOYMENT_GUIDE.md) • [Production Guide](PRODUCTION_READY.md) • [API Docs](http://localhost:8000/docs)
