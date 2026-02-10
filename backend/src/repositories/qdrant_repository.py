"""
Repositorio para operaciones con Qdrant (base de datos vectorial).
Centraliza el acceso a la base vectorial sin gestionar logging de aplicación.
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
    Repositorio para gestionar operaciones con Qdrant.
    Encapsula toda la lógica de acceso a la base de datos vectorial.
    """
    
    def __init__(self, collection_name: str = QDRANT_COLLECTION):
        # Normalizar URL de Qdrant y configurar cliente
        original_url = settings.qdrant_url
        qdrant_url = self._normalize_qdrant_url(original_url)
        
        
        # Configurar cliente con API key si está disponible
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
        
        # Detectar qué método de búsqueda está disponible (una sola vez al inicializar)
        self._detect_search_method()
    
    def _normalize_qdrant_url(self, url: str) -> str:
        """
        Normaliza la URL de Qdrant.
        - Si es HTTPS, asegura que no tenga puerto duplicado
        - Si tiene puerto :6333 en HTTPS, lo quita (Qdrant Cloud usa 443 por defecto)
        """
        if not url:
            return url
        
        # Si es HTTPS y tiene :6333, quitar el puerto (Qdrant Cloud usa 443)
        if url.startswith('https://') and ':6333' in url:
            url = url.replace(':6333', '')
        
        return url
    
    def _mask_url(self, url: str) -> str:
        """Enmascara información sensible en la URL para logging."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.hostname:
                # Mostrar solo el dominio, no el path completo
                return f"{parsed.scheme}://{parsed.hostname}{':' + str(parsed.port) if parsed.port else ''}"
            return url
        except Exception:
            return url
    
    def _ensure_collection(self):
        """Asegura que la colección existe con la configuración correcta"""
        try:
            # Intentar obtener información de la colección
            self.client.get_collection(self.collection_name)
        except Exception:
            # Si no existe, crear con tamaño por defecto (1536 para text-embedding-3-large)
            # Se ajustará automáticamente cuando se inserten los primeros vectores
            try:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=1536,  # Tamaño por defecto para text-embedding-3-large
                        distance=qmodels.Distance.COSINE
                    )
                )
            except Exception:
                # Si falla, probablemente ya existe, continuar
                pass
    
    def _detect_search_method(self):
        """
        Detecta qué método de búsqueda está disponible en el cliente Qdrant.
        Esto se hace una sola vez al inicializar para evitar intentos múltiples en cada búsqueda.
        """
        self._search_method = None
        self._search_method_name = None
        
        # Prioridad: search_points() > query_points() > search()
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
        Inserta o actualiza puntos en Qdrant.
        
        Args:
            points: Lista de diccionarios con estructura:
                   {
                       "id": str (opcional, se genera si no se proporciona),
                       "vector": List[float],
                       "payload": Dict
                   }
            vector_size: Tamaño del vector (se detecta automáticamente si no se proporciona)
        
        Returns:
            True si la operación fue exitosa
        """
        if not points:
            logging.warning("upsert_points: lista de puntos vacía")
            return True
        
        try:
            # Detectar tamaño del vector si no se proporciona
            if vector_size is None:
                vector_size = len(points[0]["vector"])
            
            logging.info(f"Insertando {len(points)} puntos en Qdrant (vector_size: {vector_size})")
            
            # Asegurar que la colección tiene el tamaño correcto
            try:
                collection_info = self.client.get_collection(self.collection_name)
                if collection_info.config.params.vectors.size != vector_size:
                    logging.warning(
                        f"Tamaño de vector no coincide. Colección: {collection_info.config.params.vectors.size}, "
                        f"Esperado: {vector_size}. Recreando colección..."
                    )
                    # Recrear colección con el tamaño correcto
                    self.client.recreate_collection(
                        collection_name=self.collection_name,
                        vectors_config=qmodels.VectorParams(
                            size=vector_size,
                            distance=qmodels.Distance.COSINE
                        )
                    )
                    logging.info(f"Colección recreada con tamaño {vector_size}")
            except Exception as e:
                # Si no existe, crearla
                logging.info(f"Colección no existe, creándola con tamaño {vector_size}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=vector_size,
                        distance=qmodels.Distance.COSINE
                    )
                )
            
            # Qdrant puede tener límites en el tamaño del batch
            # Dividir en batches de 100 puntos para evitar problemas
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
                
                # Insertar batch
                try:
                    result = self.client.upsert(
                        collection_name=self.collection_name,
                        points=qdrant_points
                    )
                    inserted_count += len(batch)
                    logging.info(f"Batch {i//batch_size + 1}/{(total_points + batch_size - 1)//batch_size}: {len(batch)} puntos insertados (total: {inserted_count}/{total_points})")
                except Exception as e:
                    logging.error(f"Error al insertar batch {i//batch_size + 1}: {str(e)}")
                    raise
            
            logging.info(f"✅ Todos los puntos insertados exitosamente: {inserted_count}/{total_points}")
            
            # Verificar que se insertaron todos los puntos
            if inserted_count != total_points:
                logging.warning(f"⚠️ Advertencia: Se esperaban {total_points} puntos pero se insertaron {inserted_count}")
            
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
        Busca vectores similares en Qdrant.
        
        Args:
            query_vector: Vector de consulta
            top_k: Número de resultados a retornar
            filter_conditions: Condiciones de filtro (opcional)
        
        Returns:
            Lista de resultados con score y payload
        """
        try:
            # Verificar que el cliente esté disponible
            if not self.client:
                return []
            
            filter_obj = None
            if filter_conditions:
                # Construir filtro Qdrant desde condiciones
                must_conditions = []
                for key, value in filter_conditions.items():
                    must_conditions.append(
                        qmodels.FieldCondition(
                            key=key,
                            match=qmodels.MatchValue(value=value)
                        )
                    )
                filter_obj = qmodels.Filter(must=must_conditions)
            
            
            # Usar el método detectado al inicializar (evita intentos múltiples)
            if not self._search_method:
                return []
            
            hits = []
            
            try:
                if self._search_method == 'search_points':
                    # Método más moderno: search_points()
                    search_result = self.client.search_points(
                        collection_name=self.collection_name,
                        query_vector=query_vector,
                        limit=top_k,
                        query_filter=filter_obj
                    )
                    hits = search_result if isinstance(search_result, list) else (search_result.points if hasattr(search_result, 'points') else [])
                    
                elif self._search_method == 'query_points':
                    # Método alternativo: query_points() con vector directo como lista
                    try:
                        # Intentar primero con vector directo (más simple)
                        query_result = self.client.query_points(
                            collection_name=self.collection_name,
                            query=query_vector,  # Vector directo como lista
                            limit=top_k,
                            query_filter=filter_obj
                        )
                        hits = query_result.points if hasattr(query_result, 'points') else []
                    except Exception:
                        # Si falla, intentar con Query wrapper (solo una vez más)
                        query_result = self.client.query_points(
                            collection_name=self.collection_name,
                            query=qmodels.Query(vector=query_vector),
                            limit=top_k,
                            query_filter=filter_obj
                        )
                        hits = query_result.points if hasattr(query_result, 'points') else []
                    
                elif self._search_method == 'search':
                    # Método legacy: search()
                    hits = self.client.search(
                        collection_name=self.collection_name,
                        query_vector=query_vector,
                        limit=top_k,
                        query_filter=filter_obj
                    )
                
                
            except Exception as e:
                return []
            
            
            # Procesar resultados según el tipo de respuesta
            results = []
            for hit in hits:
                # query_points() retorna ScoredPoint, search() retorna ScoredPoint también
                # Ambos tienen id, score y payload
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
        Elimina todos los vectores asociados a un document_id.
        
        Args:
            document_id: ID del documento a eliminar
        
        Returns:
            True si la operación fue exitosa o si no hay vectores que eliminar,
            False solo si hay un error de conexión crítico
        """
        try:
            # Verificar que el cliente esté disponible
            if not self.client:
                return False
            
            # Verificar que la colección existe
            try:
                self.client.get_collection(self.collection_name)
            except Exception as e:
                # Si la colección no existe, no hay nada que eliminar, consideramos éxito
                return True
            
            # Intentar eliminar los vectores
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
            
            # Verificar el resultado
            if hasattr(result, 'status'):
                if result.status == qmodels.UpdateStatus.COMPLETED:
                    return True
                else:
                    # Aún así retornamos True si no hay error de conexión
                    return True
            
            return True
            
        except Exception as e:
            # Si es un error de conexión, retornar False
            # Si es que no hay vectores, considerar éxito
            error_str = str(e).lower()
            if "connection" in error_str or "timeout" in error_str or "network" in error_str:
                return False
            # Para otros errores (como que no existan vectores), considerar éxito
            return True  # Considerar éxito si no es error de conexión
    
    def get_collection_info(self) -> Dict:
        """Obtiene información sobre la colección"""
        try:
            if not self.client:
                return {"error": "Cliente no disponible"}
            
            info = self.client.get_collection(self.collection_name)
            
            # points_count siempre está disponible
            points_count = info.points_count
            
            # vectors_count puede no estar disponible en versiones recientes
            # En versiones nuevas, se usa points_count que incluye los vectores
            vectors_count = getattr(info, 'vectors_count', points_count)
            
            # Obtener tamaño del vector desde la configuración
            vector_size = None
            distance = None
            if hasattr(info, 'config') and hasattr(info.config, 'params'):
                if hasattr(info.config.params, 'vectors'):
                    vector_config = info.config.params.vectors
                    if isinstance(vector_config, dict):
                        # Configuración como diccionario
                        vector_size = vector_config.get('size')
                        distance = str(vector_config.get('distance', 'COSINE'))
                    else:
                        # Configuración como objeto
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
    Obtiene la instancia singleton de QdrantRepository.
    Garantiza que solo se inicialice una vez la conexión con Qdrant.
    """
    global _qdrant_repo_instance
    if _qdrant_repo_instance is None:
        _qdrant_repo_instance = QdrantRepository()
    return _qdrant_repo_instance


