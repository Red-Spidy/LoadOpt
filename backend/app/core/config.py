from pydantic_settings import BaseSettings
from typing import Optional
import sys


class Settings(BaseSettings):
    """Application settings"""

    # App
    PROJECT_NAME: str = "LoadOpt 3D Planner"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS
    CORS_ORIGINS: list = ["http://localhost:3000", "http://localhost:5173"]

    # AWS S3 (Optional)
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    S3_BUCKET_NAME: Optional[str] = None

    # Optimization
    MAX_HEURISTIC_ITEMS: int = 200
    GA_POPULATION_SIZE: int = 100
    GA_GENERATIONS: int = 50
    GA_MUTATION_RATE: float = 0.1
    GA_CROSSOVER_RATE: float = 0.8

    class Config:
        env_file = ".env"
        case_sensitive = True

    def validate_required_settings(self):
        """Validate that all required settings are properly configured"""
        errors = []

        # Validate SECRET_KEY
        if not self.SECRET_KEY or len(self.SECRET_KEY) < 32:
            errors.append("SECRET_KEY must be at least 32 characters long")

        # Validate DATABASE_URL
        if not self.DATABASE_URL:
            errors.append("DATABASE_URL is required")

        # Validate REDIS_URL
        if not self.REDIS_URL:
            errors.append("REDIS_URL is required")

        # Validate ENVIRONMENT
        if self.ENVIRONMENT not in ["development", "staging", "production"]:
            errors.append(f"ENVIRONMENT must be 'development', 'staging', or 'production', got '{self.ENVIRONMENT}'")

        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            print(error_msg, file=sys.stderr)
            sys.exit(1)


settings = Settings()
settings.validate_required_settings()
