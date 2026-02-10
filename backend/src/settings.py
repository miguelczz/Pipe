from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path
import os

# Obtener la ruta raíz del proyecto (tres niveles arriba desde backend/src/settings.py)
# Esto funciona tanto si se ejecuta desde backend/ como desde la raíz
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

class Settings(BaseSettings):
    # OpenAI & Qdrant
    openai_api_key: str
    qdrant_url: str
    qdrant_api_key: Optional[str] = None  # API key para Qdrant Cloud (opcional)
    qdrant_port: Optional[str] = None  # Puerto de Qdrant (opcional, puede estar en la URL)
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
    redis_port: Optional[str] = None  # Puerto de Redis (opcional, puede estar en la URL)
    redis_password: Optional[str] = None  # Contraseña de Redis (opcional)
    cache_enabled: bool = True

    # Ragas Evaluation
    ragas_enabled: bool = True  # Habilitar callbacks de Ragas por defecto
    
    # Debug y desarrollo
    debug: bool = False  # Habilitar información detallada de errores
    show_thought_chain: bool = True  # Incluir thought_chain en respuestas por defecto

    class Config:
        # Buscar el .env en la raíz del proyecto primero
        # Si no existe, Pydantic buscará automáticamente en el directorio actual
        env_file = str(ENV_FILE) if ENV_FILE.exists() else (
            str(PROJECT_ROOT / "backend" / ".env") if (PROJECT_ROOT / "backend" / ".env").exists() else ".env"
        )
        env_file_encoding = 'utf-8'
        case_sensitive = False
        # Permitir campos extra en el .env que no estén definidos en la clase
        extra = "ignore"

    def _is_running_in_docker(self) -> bool:
        """Detecta si la aplicación está ejecutándose dentro de Docker"""
        # Verificar si estamos en un contenedor Docker
        # Docker crea un archivo /.dockerenv en contenedores
        return Path("/.dockerenv").exists() or os.getenv("DOCKER_CONTAINER") == "true"
    
    def _get_postgres_host(self) -> str:
        """Obtiene el hostname correcto de PostgreSQL según el entorno"""
        # Si el hostname es de Docker pero no estamos en Docker, usar localhost
        if self.postgres_host in ["pipe-postgres", "postgres"] and not self._is_running_in_docker():
            # Estamos en desarrollo local, usar localhost
            return "localhost"
        return self.postgres_host
    
    def _get_postgres_port(self) -> str:
        """Obtiene el puerto correcto de PostgreSQL según el entorno"""
        # Si estamos en Docker, usar puerto interno (5432)
        # Si estamos fuera de Docker, usar puerto expuesto (5440)
        if self._is_running_in_docker():
            return "5432"
        # Si el hostname era de Docker pero cambiamos a localhost, usar puerto expuesto
        if self.postgres_host in ["pipe-postgres", "postgres"]:
            return "5440"
        return self.postgres_port
    
    @property
    def sqlalchemy_url(self) -> str:
        # Usar DATABASE_URL si está disponible, sino construir desde variables individuales
        if self.database_url:
            # Convertir postgres:// a postgresql:// para compatibilidad con SQLAlchemy 1.4+
            url = self.database_url
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            
            # Si la URL tiene hostname de Docker pero no estamos en Docker, ajustarlo
            if "pipe-postgres" in url and not self._is_running_in_docker():
                url = url.replace("pipe-postgres", "localhost")
                # Cambiar puerto de 5432 (interno) a 5440 (expuesto)
                url = url.replace(":5432/", ":5440/")
            
            return url
        
        # Validar que todas las variables individuales estén presentes
        if not all([self.postgres_user, self.postgres_password, self.postgres_db, 
                self.postgres_host, self.postgres_port]):
            raise ValueError(
                "Debe proporcionar DATABASE_URL o todas las variables individuales de PostgreSQL "
                "(POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOST, POSTGRES_PORT)"
            )
        
        # Usar hostname y puerto ajustados según el entorno
        host = self._get_postgres_host()
        port = self._get_postgres_port()
        
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{host}:{port}/{self.postgres_db}"
        )

settings = Settings()