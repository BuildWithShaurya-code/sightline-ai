"""
SightLine AI - Application Configuration & Environment Settings
Validated with Pydantic v2 BaseSettings.
"""

import json
from pathlib import Path
from typing import List, Literal, Optional, Union
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_MEDIA_DIR = (BACKEND_DIR / "storage" / "media").resolve()
DEFAULT_MODEL_PATH = (BACKEND_DIR / "models" / "best.pt").resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    # Application Environment
    storage_backend: Literal['local', 'supabase'] = 'local'
    cloud_database_url: Optional[SecretStr] = None
    cloud_worker: bool = False
    cloud_model_bucket: str = 'sightline-models'
    cloud_model_key: str = 'checkpoints/best.pt'
    cloud_database_ca: Path = BACKEND_DIR / 'certs' / 'supabase-root.crt'

    @model_validator(mode='after')
    def require_cloud_configuration(self):
        if self.storage_backend == 'supabase':
            if not self.cloud_database_url or not self.supabase_url or not self.supabase_secret_key:
                raise ValueError('Cloud persistence requires a database connection and server-side Supabase configuration.')
            if not self.cloud_database_ca.is_file():
                raise ValueError('The trusted Supabase database CA certificate is missing.')
        return self

    environment: Literal["development", "production", "test"] = Field(
        default="development",
        description="Execution environment stage",
    )

    # API Routing
    api_prefix: str = Field(
        default="/api/v1",
        description="Global API route prefix",
    )

    # CORS Origins
    cors_origins: Union[List[str], str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        description="Allowed frontend origins for CORS",
    )

    # Database Configuration (Planned for Phase 2)
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/sightline_db",
        description="Database connection string (PostgreSQL for hosted, SQLite alternative)",
    )

    # Media Storage Configuration
    media_dir: Path = Field(
        default_factory=lambda: DEFAULT_MEDIA_DIR,
        description="Local private media directory for uploaded videos and extracted frames",
    )

    # Neural Detection Model Configuration
    model_path: Path = Field(
        default_factory=lambda: DEFAULT_MODEL_PATH,
        description="Filesystem path to fine-tuned YOLO detection checkpoint",
    )

    # Upload & Media Limits
    max_upload_size_bytes: int = Field(
        default=104_857_600,  # 100 MB
        ge=1_048_576,        # Minimum 1 MB
        le=1_073_741_824,    # Maximum 1 GB
        description="Maximum permitted video upload size in bytes",
    )
    max_media_duration_seconds: int = Field(
        default=300,  # 5 minutes
        ge=5,
        le=3600,
        description="Maximum duration in seconds for uploaded surveillance footage",
    )

    # Asynchronous Job Limits
    job_timeout_seconds: int = Field(
        default=600,  # 10 minutes
        ge=30,
        le=3600,
        description="Timeout threshold for video inference processing jobs",
    )

    max_pending_jobs: int = Field(default=16, ge=1, le=256)
    max_pending_jobs_per_user: int = Field(default=4, ge=1, le=64)

    # Logging Configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Root application logging verbosity",
    )

    # Supabase Project Configuration
    supabase_url: Optional[str] = Field(
        default=None,
        description="Supabase project URL",
    )
    supabase_publishable_key: Optional[str] = Field(
        default=None,
        description="Supabase anonymous/publishable key",
    )
    supabase_secret_key: Optional[str] = Field(
        default=None,
        repr=False,
        description="Supabase privileged service role secret key",
    )
    supabase_jwt_secret: Optional[str] = Field(
        default=None,
        repr=False,
        description="Supabase JWT secret for offline signature verification",
    )

    # Phase 3 Inference Service Configuration
    max_inference_image_bytes: int = Field(
        default=15_728_640,  # 15 MB
        ge=10_240,           # Minimum 10 KB
        le=52_428_800,       # Maximum 50 MB
        description="Maximum permitted single image upload size for inference in bytes",
    )
    max_concurrent_inferences: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Maximum concurrent image inference operations permitted",
    )
    default_confidence_threshold: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Default detection confidence threshold",
    )
    inference_device: str = Field(
        default="cpu",
        description="Compute device for inference ('cpu', 'cuda', 'mps')",
    )

    # Future Session & Security Secrets
    session_secret: str = Field(
        default="development-insecure-placeholder-change-in-production",
        repr=False,
        description="Secret key for signing future session cookies",
    )

    # Phase 6 Notification & Dispatch Provider Settings
    dispatch_provider: Literal["simulation", "telegram"] = Field(
        default="simulation",
        description="Active notification provider ('simulation' or 'telegram')",
    )
    telegram_bot_token: Optional[str] = Field(
        default=None,
        description="Telegram Bot API token for verified notification delivery",
    )
    telegram_chat_id: Optional[str] = Field(
        default=None,
        description="Authorized Telegram test chat ID destination",
    )
    dispatch_timeout_seconds: float = Field(
        default=10.0,
        ge=1.0,
        le=60.0,
        description="HTTP timeout threshold for external notification providers",
    )
    dispatch_retry_limit: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retry attempts for transient provider failures",
    )
    pin_lockout_seconds: int = Field(
        default=60,
        ge=10,
        le=3600,
        description="Lockout duration in seconds after consecutive PIN verification failures",
    )
    pin_max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum consecutive failed PIN attempts permitted before lockout",
    )


    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return []

    @field_validator("session_secret")
    @classmethod
    def validate_session_secret(cls, v: str, info) -> str:
        env = info.data.get("environment", "development")
        if env == "production" and ("placeholder" in v.lower() or len(v) < 32):
            raise ValueError("Production requires a strong session secret with at least 32 characters")
        return v

    @field_validator("model_path", mode="after")
    @classmethod
    def resolve_model_path(cls, v: Path) -> Path:
        p = Path(v)
        if p.exists():
            return p.resolve()
        # If relative, check relative to BACKEND_DIR
        cand1 = (BACKEND_DIR / p).resolve()
        if cand1.exists():
            return cand1
        # If path starts with 'backend' while running inside backend/, strip leading 'backend'
        if p.parts and p.parts[0] == "backend":
            cand2 = (BACKEND_DIR / Path(*p.parts[1:])).resolve()
            if cand2.exists():
                return cand2
        # Check relative to REPO_ROOT
        cand3 = (REPO_ROOT / p).resolve()
        if cand3.exists():
            return cand3
        return p


def get_settings() -> Settings:
    return Settings()
