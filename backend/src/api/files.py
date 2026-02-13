"""
API endpoints for file management - Refactored to use repositories.
Exposes upload, list and delete operations without logging logic.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from typing import List
from sqlalchemy.orm import Session as SQLSession
from ..models.schemas import FileUploadResponse, FileListResponse
from ..models.database import get_db
from ..repositories.document_repository import DocumentRepository
from ..repositories.qdrant_repository import get_qdrant_repository
from ..services.embeddings_service import process_and_store_pdf, delete_by_id
from datetime import datetime

router = APIRouter(prefix="/files", tags=["files"])

# Repository instances
document_repo = DocumentRepository()
qdrant_repo = get_qdrant_repository()

@router.post("/upload", status_code=201, response_model=FileUploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    db: SQLSession = Depends(get_db)
):
    """
    Uploads and processes a PDF file.
    Saves the file, generates embeddings and stores metadata in DB.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Read file content
    content = await file.read()
    
    # Save file using the repository
    document_id, file_path = document_repo.save_file(content, file.filename)
    
    # Process PDF (chunk + embeddings + store in Qdrant)
    chunk_count = 0
    try:
        # Get point count before inserting
        collection_info_before = qdrant_repo.get_collection_info()
        points_before = collection_info_before.get('points_count', 0) if isinstance(collection_info_before, dict) else 0
        
        processed_doc_id = await process_and_store_pdf(file_path, document_id=document_id)
        
        # Verify data was inserted in Qdrant
        collection_info_after = qdrant_repo.get_collection_info()
        if "error" in collection_info_after:
            raise ValueError(f"Error getting Qdrant info: {collection_info_after.get('error')}")
        
        points_after = collection_info_after.get('points_count', 0)
        chunk_count = points_after - points_before
        
        if chunk_count == 0:
            raise ValueError("No chunks were inserted into Qdrant. Check logs for details.")
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error processing PDF: {str(e)}"
        )
    
    # Store metadata in DB
    document_repo.create_document_metadata(
        db=db,
        document_id=document_id,
        filename=file.filename,
        file_path=file_path,
        chunk_count=chunk_count,
        source=file.filename
    )
    
    return FileUploadResponse(
        document_id=document_id,
        filename=file.filename,
        status="processed",
        uploaded_at=datetime.utcnow()
    )


@router.post("/upload-multiple", status_code=201, response_model=List[FileUploadResponse])
async def upload_pdfs(
    files: List[UploadFile] = File(...),
    db: SQLSession = Depends(get_db)
):
    """
    Uploads and processes multiple PDF files.
    Each file is saved, split into chunks, embeddings are generated and stored in Qdrant.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    results = []
    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            results.append(FileUploadResponse(
                document_id="",
                filename=file.filename or "unknown",
                status="skipped",
                uploaded_at=datetime.utcnow()
            ))
            continue
        content = await file.read()
        document_id, file_path = document_repo.save_file(content, file.filename)
        chunk_count = 0
        try:
            collection_info_before = qdrant_repo.get_collection_info()
            points_before = collection_info_before.get('points_count', 0) if isinstance(collection_info_before, dict) else 0
            await process_and_store_pdf(file_path, document_id=document_id)
            collection_info_after = qdrant_repo.get_collection_info()
            if "error" in collection_info_after:
                raise ValueError(collection_info_after.get('error', 'Qdrant error'))
            points_after = collection_info_after.get('points_count', 0)
            chunk_count = points_after - points_before
            if chunk_count == 0:
                raise ValueError("No chunks were inserted into Qdrant.")
        except Exception as e:
            document_repo.delete_file(document_id)
            results.append(FileUploadResponse(
                document_id=document_id,
                filename=file.filename,
                status=f"error: {str(e)}",
                uploaded_at=datetime.utcnow()
            ))
            continue
        document_repo.create_document_metadata(
            db=db,
            document_id=document_id,
            filename=file.filename,
            file_path=file_path,
            chunk_count=chunk_count,
            source=file.filename
        )
        results.append(FileUploadResponse(
            document_id=document_id,
            filename=file.filename,
            status="processed",
            uploaded_at=datetime.utcnow()
        ))
    return results


@router.get("/", response_model=List[FileListResponse])
async def list_files(db: SQLSession = Depends(get_db)):
    """
    Lists all files with their metadata.
    """
    documents = document_repo.list_documents(db)
    return [
        FileListResponse(
            document_id=doc.document_id,
            filename=doc.filename,
            uploaded_at=doc.uploaded_at
        )
        for doc in documents
    ]


@router.delete("/{document_id}")
async def delete_file(
    document_id: str,
    db: SQLSession = Depends(get_db)
):
    """
    Deletes a file and all its associated vectors.
    """
    # Verify document exists
    doc = document_repo.get_document_by_id(db, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete file from filesystem
    document_repo.delete_file(document_id)
    
    # Delete vectors from Qdrant (non-critical if it fails)
    try:
        delete_by_id(document_id)
    except Exception as e:
        # Continue with deletion even if Qdrant fails
        pass

    # Delete metadata from DB
    document_repo.delete_document(db, document_id)
    
    return {
        "status": "deleted",
        "document_id": document_id,
        "filename": doc.filename
    }
