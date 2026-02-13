"""
Repository for document management (files and metadata)
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
    Repository for managing documents.
    Handles both file storage and metadata in DB.
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
        Saves a file in the file system.
        
        Args:
            file_content: File content in bytes
            filename: Original filename
            document_id: Document ID (generated if not provided)
        
        Returns:
            Tuple (document_id, file_path) with the ID and path of the saved file
        """
        if document_id is None:
            document_id = str(uuid.uuid4())
        
        file_path = self.upload_dir / f"{document_id}_{filename}"
        
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        return document_id, str(file_path)
    
    def get_file_path(self, document_id: str) -> Optional[Path]:
        """
        Gets the path of a file by its document_id.
        
        Args:
            document_id: Document ID
        
        Returns:
            Path of the file or None if it doesn't exist
        """
        # Search for file starting with document_id
        for file_path in self.upload_dir.glob(f"{document_id}_*"):
            return file_path
        return None
    
    def delete_file(self, document_id: str) -> bool:
        """
        Deletes a file from the file system.
        
        Args:
            document_id: ID of the document to delete
        
        Returns:
            True if deleted successfully
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
        Creates a document record in the database.
        
        Args:
            db: Database session
            document_id: Unique document ID
            filename: Filename
            file_path: File path
            chunk_count: Number of generated chunks
            source: Document source
            metadata_json: Additional metadata in JSON
        
        Returns:
            Created Document instance
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
        Gets a document by its document_id.
        
        Args:
            db: Database session
            document_id: Document ID
        
        Returns:
            Document instance or None
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
        Lists all documents.
        
        Args:
            db: Database session
            skip: Number of documents to skip
            limit: Maximum number of documents to return
        
        Returns:
            List of documents
        """
        return db.query(Document).offset(skip).limit(limit).all()
    
    def delete_document(
        self,
        db: SQLSession,
        document_id: str
    ) -> bool:
        """
        Deletes a document from the database.
        
        Args:
            db: Database session
            document_id: Document ID
        
        Returns:
            True if deleted successfully
        """
        doc = self.get_document_by_id(db, document_id)
        if doc:
            db.delete(doc)
            db.commit()
            return True
        return False
    
    def to_schema(self, doc: Document) -> DocumentMetadata:
        """
        Converts a Document model to DocumentMetadata schema.
        
        Args:
            doc: Document instance
        
        Returns:
            DocumentMetadata instance
        """
        return DocumentMetadata(
            document_id=doc.document_id,
            filename=doc.filename,
            source=doc.source or doc.filename,
            chunk_count=doc.chunk_count,
            uploaded_at=doc.uploaded_at
        )

