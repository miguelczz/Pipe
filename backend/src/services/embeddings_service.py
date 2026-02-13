"""
Embeddings service - Refactored to use repositories and utilities.
Only handles PDF processing and storing their embeddings in Qdrant.
"""
import os
import uuid
from typing import List
from ..repositories.qdrant_repository import get_qdrant_repository
from ..utils.text_processing import text_splitter, process_pdf_to_text
from ..utils.embeddings import embedding_for_text_batch
from ..settings import settings

# Global Qdrant repository instance (Lazy loaded via singleton)
# _qdrant_repo can be replaced by direct calls to get_qdrant_repository() but to minimize changes:
_qdrant_repo = get_qdrant_repository()


async def process_and_store_pdf(path: str, document_id: str = None) -> str:
    """
    Processes a PDF, generates embeddings and saves them in Qdrant.
    
    Args:
        path: Path to the PDF file
        document_id: Document ID (generated if not provided)
    
    Returns:
        document_id of the processed document
    """
    if document_id is None:
        document_id = str(uuid.uuid4())

    
    # Extract text from PDF
    try:
        text = process_pdf_to_text(path)
        if not text or not text.strip():
            raise ValueError(f"Could not extract text from PDF or PDF is empty: {path}")
    except Exception as e:
        raise
    
    # Split into chunks
    try:
        chunks = text_splitter(
            text, 
            chunk_size=settings.chunk_size, 
            overlap=settings.chunk_overlap
        )
        if not chunks:
            raise ValueError("No text chunks were generated")
    except Exception as e:
        raise
    
    # Generate embeddings
    try:
        embeddings = embedding_for_text_batch(chunks)
        if not embeddings or len(embeddings) != len(chunks):
            raise ValueError(f"Error generating embeddings: expected {len(chunks)}, got {len(embeddings) if embeddings else 0}")
    except Exception as e:
        raise
    
    # Prepare points for Qdrant (document_type identifies the guide to understand captures and results)
    try:
        points = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            points.append({
                "vector": emb,
                "payload": {
                    "text": chunk,
                    "source": os.path.basename(path),
                    "document_type": "guia_para_entender_capturas_y_resultados",
                    "chunk_index": i,
                    "document_id": document_id
                }
            })
    except Exception as e:
        raise

    # Insert into Qdrant using the repository
    try:
        success = _qdrant_repo.upsert_points(points)
        if not success:
            raise ValueError("upsert_points returned False")
        
        # Verify all points were inserted
        collection_info = _qdrant_repo.get_collection_info()
        if isinstance(collection_info, dict) and "error" not in collection_info:
            points_count = collection_info.get('points_count', 0)
        
    except Exception as e:
        raise
    
    return document_id


def delete_by_id(document_id: str) -> bool:
    """
    Deletes all vectors in Qdrant associated with a document_id.
    
    Args:
        document_id: ID of the document to delete
    
    Returns:
        True if the operation was successful
    """
    return _qdrant_repo.delete_by_document_id(document_id)
