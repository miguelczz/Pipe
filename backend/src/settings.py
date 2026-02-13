from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path
import os

# Get the project root path (three levels up from backend/src/settings.py)
# This works whether executed from backend/ or from the root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

class Settings(BaseSettings):
    # OpenAI & Qdrant
    openai_api_key: str
    qdrant_url: str
    qdrant_api_key: Optional[str] = None  # API key for Qdrant Cloud (optional)
    qdrant_port: Optional[str] = None  # Qdrant port (optional, can be in the URL)
    embedding_model: str = "text-embedding-3-large"
    llm_model: str = "gpt-4o-mini"
    
    # ==============================
    # LLM Provider Configuration (Phase 1)
    # ==============================
    llm_provider: str = "litellm"  # "litellm" | "openai_direct"
    
    # Provider API Keys
    google_api_key: Optional[str] = None    # Google AI Studio (free tier)
    groq_api_key: Optional[str] = None      # Groq (free tier)
    # openai_api_key already defined above   # OpenAI (paid, fallback only)
    
    # Model Assignments per Tier
    # - routing: Intent classification, JSON structured output (fast)
    # - cheap: Yes/no decisions, single-word responses (fast)
    # - standard: Text generation with context (quality)
    # - quality: Synthesis, long-form reports (best quality)
    # - fallback: Used when primary models fail
    llm_routing_model: str = "groq/llama-3.3-70b-versatile"
    llm_cheap_model: str = "groq/llama-3.3-70b-versatile"
    llm_standard_model: str = "gemini/gemini-2.0-flash-exp"
    llm_quality_model: str = "gpt-4o"  # User requested OpenAI for best quality
    llm_fallback_model: str = "gpt-4o-mini"
    
    # Embeddings Configuration (stays on OpenAI for best quality)
    embedding_provider: str = "openai"  # Qdrant configured for 1536 dims
    
    # ==============================
    # Langfuse Observability (Phase 2)
    # ==============================
    langfuse_host: Optional[str] = None
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None

    # Database
    # Make optional if DATABASE_URL is present
    postgres_user: Optional[str] = None
    postgres_password: Optional[str] = None
    postgres_db: Optional[str] = None
    postgres_host: Optional[str] = None
    postgres_port: Optional[str] = None
    database_url: Optional[str] = None

    # App info
    app_name: str = "PipeAgent"
    app_version: str = "1.0.0"
    app_port: int = 8000
    app_env: str = "development"
    secret_key: str = ""

    # Processing
    upload_dir: str = "./uploads"
    chunk_size: int = 500
    chunk_overlap: int = 50

    # Cache
    redis_url: Optional[str] = None  # Redis URL (e.g.: redis://localhost:6379/0 or redis://user:pass@host:port/db)
    redis_token: Optional[str] = None  # Token for Upstash Redis (if using Upstash)
    redis_port: Optional[str] = None  # Redis port (optional, can be in the URL)
    redis_password: Optional[str] = None  # Redis password (optional)
    cache_enabled: bool = True

    # Ragas Evaluation
    ragas_enabled: bool = False  # Disable Ragas callbacks by default to avoid rate limits
    
    # Debug and development
    debug: bool = False  # Enable detailed error information
    show_thought_chain: bool = True  # Include thought_chain in responses by default

    class Config:
        # Search for .env in the project root first
        # If it doesn't exist, Pydantic will automatically search in the current directory
        env_file = str(ENV_FILE) if ENV_FILE.exists() else (
            str(PROJECT_ROOT / "backend" / ".env") if (PROJECT_ROOT / "backend" / ".env").exists() else ".env"
        )
        env_file_encoding = 'utf-8'
        case_sensitive = False
        # Allow extra fields in .env that are not defined in the class
        extra = "ignore"

    def _is_running_in_docker(self) -> bool:
        """Detects if the application is running inside Docker"""
        # Check if we are in a Docker container
        # Docker creates a /.dockerenv file in containers
        return Path("/.dockerenv").exists() or os.getenv("DOCKER_CONTAINER") == "true"
    
    def _get_postgres_host(self) -> str:
        """Gets the correct PostgreSQL hostname based on the environment"""
        # If the hostname is Docker but we are not in Docker, use localhost
        if self.postgres_host in ["pipe-postgres", "postgres"] and not self._is_running_in_docker():
            # Local development, use localhost
            return "localhost"
        return self.postgres_host
    
    def _get_postgres_port(self) -> str:
        """Gets the correct PostgreSQL port based on the environment"""
        # If we are in Docker, use internal port (5432)
        # If we are outside Docker, use exposed port (5440)
        if self._is_running_in_docker():
            return "5432"
        # If the hostname was Docker but we changed to localhost, use exposed port
        if self.postgres_host in ["pipe-postgres", "postgres"]:
            return "5440"
        return self.postgres_port
    
    @property
    def sqlalchemy_url(self) -> str:
        # Use DATABASE_URL if available, otherwise build from individual variables
        if self.database_url:
            # Convert postgres:// to postgresql:// for compatibility with SQLAlchemy 1.4+
            url = self.database_url
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            
            # If the URL has a Docker hostname but we are not in Docker, adjust it
            if "pipe-postgres" in url and not self._is_running_in_docker():
                url = url.replace("pipe-postgres", "localhost")
                # Change port from 5432 (internal) to 5440 (exposed)
                url = url.replace(":5432/", ":5440/")
            
            return url
        
        # Validate that all individual variables are present
        if not all([self.postgres_user, self.postgres_password, self.postgres_db, 
                self.postgres_host, self.postgres_port]):
            raise ValueError(
                "Must provide DATABASE_URL or all individual PostgreSQL variables "
                "(POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOST, POSTGRES_PORT)"
            )
        
        # Use hostname and port adjusted according to the environment
        host = self._get_postgres_host()
        port = self._get_postgres_port()
        
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{host}:{port}/{self.postgres_db}"
        )

settings = Settings()