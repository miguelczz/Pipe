"""
Repositorio para gestión de documentos (archivos y metadatos)
"""
import uuid
import os
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from sqlalchemy.orm import Session as SQLSession
from ..models.database import Document, get_db
from ..models.schemas import DocumentMetadata
from datetime import datetime


class DocumentRepository:
    """
    Repositorio para gestionar documentos.
    Maneja tanto el almacenamiento de archivos como metadatos en BD.
    """
    
    def __init__(self, upload_dir: str = "databases/uploads"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
    
    def save_file(
        self, 
        file_content: bytes, 
        filename: str,
        document_id: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Guarda un archivo en el sistema de archivos.
        
        Args:
            file_content: Contenido del archivo en bytes
            filename: Nombre original del archivo
            document_id: ID del documento (se genera si no se proporciona)
        
        Returns:
            Tupla (document_id, file_path) con el ID y ruta del archivo guardado
        """
        if document_id is None:
            document_id = str(uuid.uuid4())
        
        file_path = self.upload_dir / f"{document_id}_{filename}"
        
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        return document_id, str(file_path)
    
    def get_file_path(self, document_id: str) -> Optional[Path]:
        """
        Obtiene la ruta de un archivo por su document_id.
        
        Args:
            document_id: ID del documento
        
        Returns:
            Path del archivo o None si no existe
        """
        # Buscar archivo que comience con document_id
        for file_path in self.upload_dir.glob(f"{document_id}_*"):
            return file_path
        return None
    
    def delete_file(self, document_id: str) -> bool:
        """
        Elimina un archivo del sistema de archivos.
        
        Args:
            document_id: ID del documento a eliminar
        
        Returns:
            True si se eliminó correctamente
        """
        file_path = self.get_file_path(document_id)
        if file_path and file_path.exists():
            file_path.unlink()
            return True
        return False
    
    def create_document_metadata(
        self,
        db: SQLSession,
        document_id: str,
        filename: str,
        file_path: str,
        chunk_count: int = 0,
        source: Optional[str] = None,
        metadata_json: Optional[str] = None
    ) -> Document:
        """
        Crea un registro de documento en la base de datos.
        
        Args:
            db: Sesión de base de datos
            document_id: ID único del documento
            filename: Nombre del archivo
            file_path: Ruta del archivo
            chunk_count: Número de chunks generados
            source: Fuente del documento
            metadata_json: Metadatos adicionales en JSON
        
        Returns:
            Instancia de Document creada
        """
        doc = Document(
            id=str(uuid.uuid4()),
            document_id=document_id,
            filename=filename,
            file_path=file_path,
            source=source or filename,
            chunk_count=chunk_count,
            metadata_json=metadata_json
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc
    
    def get_document_by_id(
        self,
        db: SQLSession,
        document_id: str
    ) -> Optional[Document]:
        """
        Obtiene un documento por su document_id.
        
        Args:
            db: Sesión de base de datos
            document_id: ID del documento
        
        Returns:
            Instancia de Document o None
        """
        return db.query(Document).filter(
            Document.document_id == document_id
        ).first()
    
    def list_documents(
        self,
        db: SQLSession,
        skip: int = 0,
        limit: int = 100
    ) -> List[Document]:
        """
        Lista todos los documentos.
        
        Args:
            db: Sesión de base de datos
            skip: Número de documentos a saltar
            limit: Número máximo de documentos a retornar
        
        Returns:
            Lista de documentos
        """
        return db.query(Document).offset(skip).limit(limit).all()
    
    def delete_document(
        self,
        db: SQLSession,
        document_id: str
    ) -> bool:
        """
        Elimina un documento de la base de datos.
        
        Args:
            db: Sesión de base de datos
            document_id: ID del documento
        
        Returns:
            True si se eliminó correctamente
        """
        doc = self.get_document_by_id(db, document_id)
        if doc:
            db.delete(doc)
            db.commit()
            return True
        return False
    
    def to_schema(self, doc: Document) -> DocumentMetadata:
        """
        Convierte un modelo Document a schema DocumentMetadata.
        
        Args:
            doc: Instancia de Document
        
        Returns:
            Instancia de DocumentMetadata
        """
        return DocumentMetadata(
            document_id=doc.document_id,
            filename=doc.filename,
            source=doc.source or doc.filename,
            chunk_count=doc.chunk_count,
            uploaded_at=doc.uploaded_at
        )

