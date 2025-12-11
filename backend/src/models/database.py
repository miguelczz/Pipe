"""
Modelos SQLAlchemy para persistencia en base de datos PostgreSQL
"""
import logging
import time
from sqlalchemy import create_engine, Column, String, DateTime, Integer, Text, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session as SQLSession
from datetime import datetime
from typing import Optional
from ..settings import settings

# Configurar logger
logger = logging.getLogger(__name__)

# Base para modelos SQLAlchemy
Base = declarative_base()


# ============================================================================
# Modelos de Base de Datos
# ============================================================================

class Document(Base):
    """
    Modelo para documentos almacenados en la base de datos.
    Almacena metadatos de archivos PDF procesados.
    """
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    document_id = Column(String, unique=True, index=True, nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    source = Column(String, nullable=True)
    chunk_count = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    metadata_json = Column(Text, nullable=True)  # Para almacenar metadatos adicionales como JSON

    def __repr__(self):
        return f"<Document(id={self.id}, document_id={self.document_id}, filename={self.filename})>"


class Session(Base):
    """
    Modelo para sesiones de usuario.
    Permite persistir el estado de las sesiones en la base de datos.
    """
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=True)
    context_json = Column(Text, nullable=True)  # JSON serializado del contexto
    variables_json = Column(Text, nullable=True)  # JSON serializado de variables
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Session(id={self.id}, session_id={self.session_id}, user_id={self.user_id})>"


# ============================================================================
# Configuración de Base de Datos
# ============================================================================

# Variable global para el engine (se inicializa de forma lazy)
engine = None
SessionLocal = None


def get_engine():
    """
    Obtiene o crea el engine de SQLAlchemy.
    Inicialización lazy para evitar errores al importar el módulo.
    """
    global engine
    if engine is None:
        try:
            engine = create_engine(
                settings.sqlalchemy_url,
                pool_pre_ping=True,  # Verifica conexiones antes de usarlas
                pool_size=10,  # Número de conexiones a mantener en el pool
                max_overflow=20,  # Máximo de conexiones adicionales que se pueden crear
                pool_recycle=3600,  # Reciclar conexiones después de 1 hora
                echo=settings.app_env == "development" and settings.debug  # Ver queries SQL en desarrollo si debug está activado
            )
            logger.info(f"Engine de base de datos creado para: {settings.sqlalchemy_url.split('@')[-1] if '@' in settings.sqlalchemy_url else 'configurado'}")
        except Exception as e:
            logger.error(f"Error al crear engine de base de datos: {e}")
            raise
    return engine


def get_session_local():
    """
    Obtiene o crea el sessionmaker.
    """
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return SessionLocal


def get_db() -> SQLSession:
    """
    Dependency para FastAPI que proporciona una sesión de base de datos.
    Uso: @app.get("/endpoint")
         def endpoint(db: Session = Depends(get_db)):
    """
    session_local = get_session_local()
    db = session_local()
    try:
        yield db
    finally:
        db.close()


def init_db(max_retries: int = 5, retry_delay: int = 2):
    """
    Crea todas las tablas en la base de datos.
    Ejecutar una vez al iniciar la aplicación.
    
    Args:
        max_retries: Número máximo de intentos de conexión
        retry_delay: Segundos de espera entre intentos
    
    Raises:
        OperationalError: Si no se puede conectar después de todos los intentos
    """
    is_production = settings.app_env == "production"
    
    for attempt in range(1, max_retries + 1):
        try:
            db_engine = get_engine()
            # Intentar conectar para verificar que la base de datos está disponible
            with db_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            # Si la conexión es exitosa, crear las tablas
            Base.metadata.create_all(bind=db_engine)
            logger.info("Base de datos inicializada correctamente")
            return
            
        except OperationalError as e:
            error_msg = f"Error de conexión a la base de datos (intento {attempt}/{max_retries}): {e}"
            
            if is_production:
                # En producción, es crítico que la base de datos esté disponible
                if attempt == max_retries:
                    logger.error(f"CRÍTICO: No se pudo conectar a la base de datos después de {max_retries} intentos")
                    raise
                else:
                    logger.warning(error_msg)
                    logger.info(f"Reintentando en {retry_delay} segundos...")
                    time.sleep(retry_delay)
            else:
                # En desarrollo, podemos ser más permisivos
                logger.warning(error_msg)
                if attempt == max_retries:
                    logger.warning(
                        "ADVERTENCIA: No se pudo conectar a la base de datos. "
                        "La aplicación continuará, pero algunas funcionalidades pueden no estar disponibles. "
                        "Asegúrate de que PostgreSQL esté ejecutándose."
                    )
                    # En desarrollo, no lanzamos la excepción, solo registramos el error
                    return
                else:
                    logger.info(f"Reintentando en {retry_delay} segundos...")
                    time.sleep(retry_delay)
        
        except Exception as e:
            # Otros errores (no de conexión) se propagan inmediatamente
            logger.error(f"Error inesperado al inicializar la base de datos: {e}")
            raise

