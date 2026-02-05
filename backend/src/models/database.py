"""
Modelos SQLAlchemy para persistencia en base de datos PostgreSQL.
Este módulo define el esquema y helpers de inicialización sin incluir
preocupaciones de logging o lógica de negocio.
"""
from sqlalchemy import create_engine, Column, String, DateTime, Integer, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session as SQLSession
from datetime import datetime
from typing import Optional
from ..settings import settings

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

# Crear engine de SQLAlchemy con pool optimizado
# OPTIMIZACIÓN: Configurar pool de conexiones para mejor rendimiento
engine = create_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,  # Verifica conexiones antes de usarlas
    pool_size=10,  # Número de conexiones a mantener en el pool
    max_overflow=20,  # Máximo de conexiones adicionales que se pueden crear
    pool_recycle=3600,  # Reciclar conexiones después de 1 hora
    echo=False  # Cambiar a True para ver queries SQL en desarrollo
)

# Factory para crear sesiones de base de datos
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> SQLSession:
    """
    Dependency para FastAPI que proporciona una sesión de base de datos.
    Uso: @app.get("/endpoint")
         def endpoint(db: Session = Depends(get_db)):
             pass
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Crea todas las tablas en la base de datos.
    Ejecutar una vez al iniciar la aplicación.
    """
    Base.metadata.create_all(bind=engine)

