from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # OpenAI & Qdrant
    openai_api_key: str
    qdrant_url: str
    qdrant_api_key: Optional[str] = None  # API key para Qdrant Cloud (opcional)
    embedding_model: str = "text-embedding-3-large"
    llm_model: str = "gpt-4o-mini"

    # Base de datos
    # Hacer opcionales si DATABASE_URL está presente
    postgres_user: Optional[str] = None
    postgres_password: Optional[str] = None
    postgres_db: Optional[str] = None
    postgres_host: Optional[str] = None
    postgres_port: Optional[str] = None
    database_url: Optional[str] = None

    # App info
    app_name: str = "Enrutador"
    app_version: str = "1.0.0"
    app_port: int = 8000
    app_env: str = "development"
    secret_key: str = ""

    # Procesamiento
    upload_dir: str = "./uploads"
    chunk_size: int = 500
    chunk_overlap: int = 50

    # Cache
    redis_url: Optional[str] = None  # URL de Redis (ej: redis://localhost:6379/0 o redis://user:pass@host:port/db)
    redis_token: Optional[str] = None  # Token para Upstash Redis (si se usa Upstash)
    cache_enabled: bool = True

    # Ragas Evaluation
    ragas_enabled: bool = True  # Habilitar callbacks de Ragas por defecto
    
    # Debug y desarrollo
    debug: bool = False  # Habilitar información detallada de errores
    show_thought_chain: bool = True  # Incluir thought_chain en respuestas por defecto

    class Config:
        env_file = ".env"

    @property
    def sqlalchemy_url(self) -> str:
        # Usar DATABASE_URL si está disponible, sino construir desde variables individuales
        if self.database_url:
            # Convertir postgres:// a postgresql:// para compatibilidad con SQLAlchemy 1.4+
            url = self.database_url
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            return url
        
        # Validar que todas las variables individuales estén presentes
        if not all([self.postgres_user, self.postgres_password, self.postgres_db, 
                self.postgres_host, self.postgres_port]):
            raise ValueError(
                "Debe proporcionar DATABASE_URL o todas las variables individuales de PostgreSQL "
                "(POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOST, POSTGRES_PORT)"
            )
        
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

settings = Settings()