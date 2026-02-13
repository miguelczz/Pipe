"""
SQLAlchemy models for PostgreSQL database persistence.
This module defines the schema and initialization helpers without including
logging concerns or business logic.
"""
from sqlalchemy import create_engine, Column, String, DateTime, Integer, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session as SQLSession
from datetime import datetime
from typing import Optional
from ..settings import settings

# Base for SQLAlchemy models
Base = declarative_base()


# ============================================================================
# Database Models
# ============================================================================

class Document(Base):
    """
    Model for documents stored in the database.
    Stores metadata of processed PDF files.
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
    Model for user sessions.
    Allows persisting session state in the database.
    """
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=True)
    context_json = Column(Text, nullable=True)  # Serialized JSON of context
    variables_json = Column(Text, nullable=True)  # Serialized JSON of variables
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Session(id={self.id}, session_id={self.session_id}, user_id={self.user_id})>"


# ============================================================================
# Database Configuration
# ============================================================================

# Create SQLAlchemy engine with optimized pool
# OPTIMIZATION: Configure connection pool for better performance
engine = create_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,  # Verifies connections before using them
    pool_size=10,  # Number of connections to maintain in the pool
    max_overflow=20,  # Maximum additional connections that can be created
    pool_recycle=3600,  # Recycle connections after 1 hour
    echo=False  # Change to True to see SQL queries in development
)

# Factory to create database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> SQLSession:
    """
    FastAPI dependency that provides a database session.
    Usage: @app.get("/endpoint")
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
    Creates all tables in the database.
    Execute once when starting the application.
    """
    Base.metadata.create_all(bind=engine)

