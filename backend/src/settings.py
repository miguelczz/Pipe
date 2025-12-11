import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # OpenAI & Qdrant
    # En desarrollo pueden estar vacías, en producción son requeridas
    openai_api_key: str = ""
    qdrant_url: str = ""
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
    app_name: str = "NetMind"
    app_version: str = "1.0.0"
    app_port: int = 8000
    app_env: str = "development"
    secret_key: str = ""

    # Procesamiento
    upload_dir: str = "./databases/uploads"
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
        env_file_encoding = "utf-8"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Detectar entorno automáticamente si no está configurado
        if not self.app_env or self.app_env == "development":
            # En Heroku, DYNO está presente
            if os.getenv("DYNO"):
                self.app_env = "production"
            # En Docker, podemos verificar otras variables
            elif os.getenv("APP_ENV"):
                self.app_env = os.getenv("APP_ENV")
        
        # Ajustar configuración según el entorno
        if self.app_env == "production":
            self.debug = False
            # En producción, validar que las variables críticas estén configuradas
            if not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY es requerida en producción")
            if not self.qdrant_url:
                raise ValueError("QDRANT_URL es requerida en producción")
        else:
            # En desarrollo, activar debug si está configurado
            self.debug = os.getenv("DEBUG", "false").lower() == "true"

    @property
    def sqlalchemy_url(self) -> str:
        """
        Construye la URL de conexión a PostgreSQL.
        Prioriza DATABASE_URL sobre variables individuales.
        """
        # Usar DATABASE_URL si está disponible (común en producción)
        if self.database_url:
            # Convertir postgres:// a postgresql:// para compatibilidad con SQLAlchemy 1.4+
            url = self.database_url
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            return url
        
        # Construir desde variables individuales (común en desarrollo)
        # En desarrollo, algunas variables pueden ser None, así que usamos valores por defecto
        user = self.postgres_user or "pguser"
        password = self.postgres_password or "pgpass"
        db = self.postgres_db or "appdb"
        host = self.postgres_host or "localhost"
        port = self.postgres_port or "5440"
        
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    @property
    def is_production(self) -> bool:
        """Verifica si estamos en producción"""
        return self.app_env == "production"
    
    @property
    def is_development(self) -> bool:
        """Verifica si estamos en desarrollo"""
        return self.app_env == "development"
    
    def validate_required(self):
        """
        Valida que las variables requeridas estén configuradas.
        Útil para verificación sin fallar en tiempo de importación.
        """
        errors = []
        if not self.openai_api_key:
            errors.append("OPENAI_API_KEY no está configurada")
        if not self.qdrant_url:
            errors.append("QDRANT_URL no está configurada")
        return errors

# Crear instancia de settings
# La validación estricta se hace en __init__ solo para producción
settings = Settings()