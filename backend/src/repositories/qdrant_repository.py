"""
Repository for operations with Qdrant (vector database).
Centralizes access to the vector database without managing application logging.
"""
import logging
import uuid
from typing import List, Dict, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from ..settings import settings
from ..utils.embeddings import embedding_for_text_batch

QDRANT_COLLECTION = "documents"


class QdrantRepository:
    """
    Repository for managing operations with Qdrant.
    Encapsulates all logic for accessing the vector database.
    """
    
    def __init__(self, collection_name: str = QDRANT_COLLECTION):
        # Normalize Qdrant URL and configure client
        original_url = settings.qdrant_url
        qdrant_url = self._normalize_qdrant_url(original_url)
        
        
        # Configure client with API key if available
        client_kwargs = {
            "url": qdrant_url,
            "prefer_grpc": False
        }
        
        if settings.qdrant_api_key:
            client_kwargs["api_key"] = settings.qdrant_api_key
        
        try:
            self.client = QdrantClient(**client_kwargs)
        except Exception as e:
            raise
        
        self.collection_name = collection_name
        self._ensure_collection()
        
        # Detect which search method is available (once at initialization)
        self._detect_search_method()
    
    def _normalize_qdrant_url(self, url: str) -> str:
        """
        Normalizes the Qdrant URL.
        - If HTTPS, ensures it doesn't have duplicate port
        - If it has port :6333 in HTTPS, removes it (Qdrant Cloud uses 443 by default)
        """
        if not url:
            return url
        
        # If HTTPS and has :6333, remove the port (Qdrant Cloud uses 443)
        if url.startswith('https://') and ':6333' in url:
            url = url.replace(':6333', '')
        
        return url
    
    def _mask_url(self, url: str) -> str:
        """Masks sensitive information in the URL for logging."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.hostname:
                # Show only the domain, not the full path
                return f"{parsed.scheme}://{parsed.hostname}{':' + str(parsed.port) if parsed.port else ''}"
            return url
        except Exception:
            return url
    
    def _ensure_collection(self):
        """Ensures the collection exists with the correct configuration"""
        try:
            # Try to get collection information
            self.client.get_collection(self.collection_name)
        except Exception:
            # If it doesn't exist, create with default size (1536 for text-embedding-3-large)
            # Will automatically adjust when the first vectors are inserted
            try:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=1536,  # Default size for text-embedding-3-large
                        distance=qmodels.Distance.COSINE
                    )
                )
            except Exception:
                # If fails, it likely already exists, continue
                pass
    
    def _detect_search_method(self):
        """
        Detects which search method is available in the Qdrant client.
        This is done only once at initialization to avoid multiple attempts on each search.
        """
        self._search_method = None
        self._search_method_name = None
        
        # Priority: search_points() > query_points() > search()
        if hasattr(self.client, 'search_points'):
            self._search_method = 'search_points'
            self._search_method_name = 'search_points()'
        elif hasattr(self.client, 'query_points'):
            self._search_method = 'query_points'
            self._search_method_name = 'query_points()'
        elif hasattr(self.client, 'search'):
            self._search_method = 'search'
            self._search_method_name = 'search()'
        else:
            self._search_method = None
    
    def upsert_points(
        self, 
        points: List[Dict],
        vector_size: Optional[int] = None
    ) -> bool:
        """
        Inserts or updates points in Qdrant.
        
        Args:
            points: List of dictionaries with structure:
                   {
                       "id": str (optional, generated if not provided),
                       "vector": List[float],
                       "payload": Dict
                   }
            vector_size: Vector size (automatically detected if not provided)
        
        Returns:
            True if operation was successful
        """
        if not points:
            logging.warning("upsert_points: empty points list")
            return True
        
        try:
            # Detect vector size if not provided
            if vector_size is None:
                vector_size = len(points[0]["vector"])
            
            logging.info(f"Inserting {len(points)} points into Qdrant (vector_size: {vector_size})")
            
            # Ensure the collection has the correct size
            try:
                collection_info = self.client.get_collection(self.collection_name)
                if collection_info.config.params.vectors.size != vector_size:
                    logging.warning(
                        f"Vector size mismatch. Collection: {collection_info.config.params.vectors.size}, "
                        f"Expected: {vector_size}. Recreating collection..."
                    )
                    # Recreate collection with correct size
                    self.client.recreate_collection(
                        collection_name=self.collection_name,
                        vectors_config=qmodels.VectorParams(
                            size=vector_size,
                            distance=qmodels.Distance.COSINE
                        )
                    )
                    logging.info(f"Collection recreated with size {vector_size}")
            except Exception as e:
                # If it doesn't exist, create it
                logging.info(f"Collection does not exist, creating it with size {vector_size}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=vector_size,
                        distance=qmodels.Distance.COSINE
                    )
                )
            
            # Qdrant may have batch size limits
            # Split into batches of 100 points to avoid issues
            batch_size = 100
            total_points = len(points)
            inserted_count = 0
            
            for i in range(0, total_points, batch_size):
                batch = points[i:i + batch_size]
                qdrant_points = [
                    qmodels.PointStruct(
                        id=p.get("id") or str(uuid.uuid4()),
                        vector=p["vector"],
                        payload=p["payload"]
                    )
                    for p in batch
                ]
                
                # Insert batch
                try:
                    result = self.client.upsert(
                        collection_name=self.collection_name,
                        points=qdrant_points
                    )
                    inserted_count += len(batch)
                    logging.info(f"Batch {i//batch_size + 1}/{(total_points + batch_size - 1)//batch_size}: {len(batch)} points inserted (total: {inserted_count}/{total_points})")
                except Exception as e:
                    logging.error(f"Error al insertar batch {i//batch_size + 1}: {str(e)}")
                    raise
            
            logging.info(f"✅ All points successfully inserted: {inserted_count}/{total_points}")
            
            # Verify all points were inserted
            if inserted_count != total_points:
                logging.warning(f"⚠️ Warning: Expected {total_points} points but only {inserted_count} were inserted")
            
            return True
            
        except Exception as e:
            logging.error(f"Error en upsert_points: {str(e)}", exc_info=True)
            raise
    
    def search(
        self, 
        query_vector: List[float], 
        top_k: int = 5,
        filter_conditions: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Searches for similar vectors in Qdrant.
        
        Args:
            query_vector: Query vector
            top_k: Number of results to return
            filter_conditions: Filter conditions (optional)
        
        Returns:
            List of results with score and payload
        """
        try:
            # Verify client is available
            if not self.client:
                return []
            
            filter_obj = None
            if filter_conditions:
                # Build Qdrant filter from conditions
                must_conditions = []
                for key, value in filter_conditions.items():
                    must_conditions.append(
                        qmodels.FieldCondition(
                            key=key,
                            match=qmodels.MatchValue(value=value)
                        )
                    )
                filter_obj = qmodels.Filter(must=must_conditions)
            
            
            # Use the method detected during initialization (avoids multiple attempts)
            if not self._search_method:
                return []
            
            hits = []
            
            try:
                if self._search_method == 'search_points':
                    # Modern method: search_points()
                    search_result = self.client.search_points(
                        collection_name=self.collection_name,
                        query_vector=query_vector,
                        limit=top_k,
                        query_filter=filter_obj
                    )
                    hits = search_result if isinstance(search_result, list) else (search_result.points if hasattr(search_result, 'points') else [])
                    
                elif self._search_method == 'query_points':
                    # Alternative method: query_points() with direct vector as list
                    try:
                        # Try first with direct vector (simpler)
                        query_result = self.client.query_points(
                            collection_name=self.collection_name,
                            query=query_vector,  # Direct vector as list
                            limit=top_k,
                            query_filter=filter_obj
                        )
                        hits = query_result.points if hasattr(query_result, 'points') else []
                    except Exception:
                        # If fails, try with Query wrapper (only once more)
                        query_result = self.client.query_points(
                            collection_name=self.collection_name,
                            query=qmodels.Query(vector=query_vector),
                            limit=top_k,
                            query_filter=filter_obj
                        )
                        hits = query_result.points if hasattr(query_result, 'points') else []
                    
                elif self._search_method == 'search':
                    # Legacy method: search()
                    hits = self.client.search(
                        collection_name=self.collection_name,
                        query_vector=query_vector,
                        limit=top_k,
                        query_filter=filter_obj
                    )
                
                
            except Exception as e:
                return []
            
            
            # Process results according to response type
            results = []
            for hit in hits:
                # query_points() returns ScoredPoint, search() also returns ScoredPoint
                # Both have id, score, and payload
                results.append({
                    "id": hit.id if hasattr(hit, 'id') else str(hit.id),
                    "score": hit.score if hasattr(hit, 'score') else 0.0,
                    "payload": hit.payload if hasattr(hit, 'payload') else {}
                })
            
            return results
        except Exception as e:
            return []
    
    def delete_by_document_id(self, document_id: str) -> bool:
        """
        Deletes all vectors associated with a document_id.
        
        Args:
            document_id: ID of the document to delete
        
        Returns:
            True if operation was successful or if there are no vectors to delete,
            False only if there is a critical connection error
        """
        try:
            # Verify client is available
            if not self.client:
                return False
            
            # Verify collection exists
            try:
                self.client.get_collection(self.collection_name)
            except Exception as e:
                # If collection doesn't exist, nothing to delete, consider success
                return True
            
            # Try to delete vectors
            result = self.client.delete(
                collection_name=self.collection_name,
                points_selector=qmodels.FilterSelector(
                    filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(
                                key="document_id",
                                match=qmodels.MatchValue(value=document_id)
                            )
                        ]
                    )
                )
            )
            
            # Verify result
            if hasattr(result, 'status'):
                if result.status == qmodels.UpdateStatus.COMPLETED:
                    return True
                else:
                    # Still return True if no connection error
                    return True
            
            return True
            
        except Exception as e:
            # If it's a connection error, return False
            # If no vectors, consider success
            error_str = str(e).lower()
            if "connection" in error_str or "timeout" in error_str or "network" in error_str:
                return False
            # For other errors (like no vectors), consider success
            return True  # Consider success if not connection error
    
    def get_collection_info(self) -> Dict:
        """Gets information about the collection"""
        try:
            if not self.client:
                return {"error": "Client not available"}
            
            info = self.client.get_collection(self.collection_name)
            
            # points_count is always available
            points_count = info.points_count
            
            # vectors_count might not be available in recent versions
            # In new versions, points_count is used which includes vectors
            vectors_count = getattr(info, 'vectors_count', points_count)
            
            # Get vector size from config
            vector_size = None
            distance = None
            if hasattr(info, 'config') and hasattr(info.config, 'params'):
                if hasattr(info.config.params, 'vectors'):
                    vector_config = info.config.params.vectors
                    if isinstance(vector_config, dict):
                        # Config as dictionary
                        vector_size = vector_config.get('size')
                        distance = str(vector_config.get('distance', 'COSINE'))
                    else:
                        # Config as object
                        vector_size = getattr(vector_config, 'size', None)
                        distance = str(getattr(vector_config, 'distance', 'COSINE'))
            
            result = {
                "name": self.collection_name,
                "points_count": points_count,
                "vectors_count": vectors_count,
                "config": {
                    "size": vector_size,
                    "distance": distance or "COSINE"
                }
            }
            return result
        except Exception as e:
            return {"error": str(e)}


# Singleton instance
_qdrant_repo_instance = None


def get_qdrant_repository() -> QdrantRepository:
    """
    Gets the QdrantRepository singleton instance.
    Ensures that the Qdrant connection is only initialized once.
    """
    global _qdrant_repo_instance
    if _qdrant_repo_instance is None:
        _qdrant_repo_instance = QdrantRepository()
    return _qdrant_repo_instance


