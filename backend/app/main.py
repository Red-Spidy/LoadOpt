from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from contextlib import asynccontextmanager
import logging
import time

from app.core.config import settings
from app.core.database import engine, Base, SessionLocal
from app.core.logging_config import setup_logging
from app.api import auth, projects, skus, containers, plans, delivery_groups, loadopt

# Setup logging first
setup_logging()
logger = logging.getLogger(__name__)

# Import models to register them with Base.metadata
from app.models import models  # noqa: F401


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan manager - runs on startup and shutdown"""
    # Startup
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"API Documentation: {'Enabled' if settings.ENVIRONMENT != 'production' else 'Disabled'}")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.PROJECT_NAME}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    description="LoadOpt 3D Load Planning and Optimization API",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)


# Middleware for request logging and timing
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with timing"""
    start_time = time.time()

    # Log request
    logger.info(f"Request: {request.method} {request.url.path}")

    try:
        response = await call_next(request)
        process_time = time.time() - start_time

        # Log response
        logger.info(
            f"Response: {request.method} {request.url.path} "
            f"Status: {response.status_code} "
            f"Duration: {process_time:.3f}s"
        )

        response.headers["X-Process-Time"] = str(process_time)
        return response
    except Exception as e:
        logger.error(f"Request failed: {request.method} {request.url.path} Error: {str(e)}", exc_info=True)
        raise


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(_: Request, exc: Exception):
    """Handle uncaught exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal error occurred. Please try again later.",
            "error_id": f"{int(time.time())}"  # Simple error tracking ID
        }
    )


# CORS middleware - Allow specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["auth"])
app.include_router(projects.router, prefix=f"{settings.API_V1_PREFIX}/projects", tags=["projects"])
app.include_router(skus.router, prefix=f"{settings.API_V1_PREFIX}/skus", tags=["skus"])
app.include_router(containers.router, prefix=f"{settings.API_V1_PREFIX}/containers", tags=["containers"])
app.include_router(plans.router, prefix=f"{settings.API_V1_PREFIX}/plans", tags=["plans"])
app.include_router(delivery_groups.router, prefix=f"{settings.API_V1_PREFIX}/delivery-groups", tags=["delivery-groups"])
app.include_router(loadopt.router, prefix=f"{settings.API_V1_PREFIX}", tags=["loadopt"])


@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "LoadOpt 3D Load Planning API",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs" if settings.ENVIRONMENT != "production" else None
    }


@app.get("/health")
def health_check():
    """Comprehensive health check endpoint"""
    health_status = {
        "status": "healthy",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "checks": {}
    }

    # Check database connectivity
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        health_status["checks"]["database"] = "ok"
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        health_status["checks"]["database"] = "error"
        health_status["status"] = "unhealthy"

    # Check Redis (if available)
    try:
        # Basic Redis connectivity check can be added here if needed
        health_status["checks"]["redis"] = "skipped"
    except Exception:
        health_status["checks"]["redis"] = "error"

    # Return appropriate status code
    status_code = 200 if health_status["status"] == "healthy" else 503

    return JSONResponse(content=health_status, status_code=status_code)
