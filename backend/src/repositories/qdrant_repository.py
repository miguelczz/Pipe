"""
Repositorio para operaciones con Qdrant (base de datos vectorial)
"""
import uuid
import logging
from typing import List, Dict, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from ..settings import settings
from ..utils.embeddings import embedding_for_text_batch

logger = logging.getLogger(__name__)

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
        
        logger.info(f"[QdrantRepository] URL original: {self._mask_url(original_url)}")
        logger.info(f"[QdrantRepository] URL normalizada: {self._mask_url(qdrant_url)}")
        
        # Configurar cliente con API key si está disponible
        client_kwargs = {
            "url": qdrant_url,
            "prefer_grpc": False
        }
        
        if settings.qdrant_api_key:
            client_kwargs["api_key"] = settings.qdrant_api_key
            logger.info(f"[QdrantRepository] Configurando Qdrant con API key")
        else:
            logger.warning(f"[QdrantRepository] Configurando Qdrant sin API key - puede fallar si Qdrant Cloud requiere autenticación")
        
        try:
            self.client = QdrantClient(**client_kwargs)
            logger.info(f"[QdrantRepository] Cliente Qdrant creado exitosamente")
        except Exception as e:
            logger.error(f"[QdrantRepository] Error al crear cliente Qdrant: {e}")
            raise
        
        self.collection_name = collection_name
        self._ensure_collection()
    
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
            logger.info(f"[QdrantRepository] URL normalizada (puerto 6333 removido para HTTPS): {self._mask_url(url)}")
        
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
                logger.error("[QdrantRepository] Cliente Qdrant no está disponible")
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
            
            logger.debug(f"[QdrantRepository] Buscando en colección '{self.collection_name}' con top_k={top_k}, vector_size={len(query_vector)}")
            
            # Usar query_points() que es el método correcto en versiones recientes de qdrant-client
            # query_points() reemplaza a search() en versiones >= 1.7.0
            if hasattr(self.client, 'query_points'):
                # Método moderno: query_points()
                try:
                    # Formato más simple y compatible: pasar el vector directamente como NamedVector
                    # Si la colección tiene un solo vector, name puede ser vacío o None
                    query_result = self.client.query_points(
                        collection_name=self.collection_name,
                        query=qmodels.NamedVector(
                            name="",  # Vector por defecto (vacío = vector principal)
                            vector=query_vector
                        ),
                        limit=top_k,
                        query_filter=filter_obj
                    )
                    hits = query_result.points if hasattr(query_result, 'points') else []
                except Exception as e:
                    logger.error(f"[QdrantRepository] Error en query_points: {e}", exc_info=True)
                    # Intentar con formato alternativo usando Query wrapper
                    try:
                        query_result = self.client.query_points(
                            collection_name=self.collection_name,
                            query=qmodels.Query(
                                vector=qmodels.NamedVector(
                                    name="",
                                    vector=query_vector
                                )
                            ),
                            limit=top_k,
                            query_filter=filter_obj
                        )
                        hits = query_result.points if hasattr(query_result, 'points') else []
                    except Exception as e2:
                        logger.error(f"[QdrantRepository] Ambos formatos de query_points fallaron: {e}, {e2}")
                        return []
            elif hasattr(self.client, 'search'):
                # Método legacy: search() (versiones antiguas)
                hits = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    limit=top_k,
                    query_filter=filter_obj
                )
            else:
                logger.error(f"[QdrantRepository] Cliente Qdrant no tiene métodos 'query_points' ni 'search'. Métodos disponibles: {[m for m in dir(self.client) if not m.startswith('_')]}")
                return []
            
            logger.debug(f"[QdrantRepository] Búsqueda retornó {len(hits)} resultados")
            
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
            logger.error(f"[QdrantRepository] Error en búsqueda: {e}", exc_info=True)
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
                logger.error("Cliente Qdrant no está disponible")
                return False
            
            # Verificar que la colección existe
            try:
                self.client.get_collection(self.collection_name)
            except Exception as e:
                logger.warning(f"Colección {self.collection_name} no existe: {e}")
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
                    logger.info(f"Vectores eliminados exitosamente para document_id={document_id}")
                    return True
                else:
                    logger.warning(f"Eliminación no completada. Status: {result.status}")
                    # Aún así retornamos True si no hay error de conexión
                    return True
            
            logger.info(f"Vectores eliminados para document_id={document_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error eliminando vectores para document_id={document_id}: {e}", exc_info=True)
            # Si es un error de conexión, retornar False
            # Si es que no hay vectores, considerar éxito
            error_str = str(e).lower()
            if "connection" in error_str or "timeout" in error_str or "network" in error_str:
                logger.error(f"Error de conexión con Qdrant: {e}")
                return False
            # Para otros errores (como que no existan vectores), considerar éxito
            logger.warning(f"Error al eliminar (puede que no existan vectores): {e}")
            return True  # Considerar éxito si no es error de conexión
    
    def get_collection_info(self) -> Dict:
        """Obtiene información sobre la colección"""
        try:
            if not self.client:
                logger.error("[QdrantRepository] Cliente Qdrant no está disponible")
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
            logger.info(f"[QdrantRepository] Información de colección: {result['points_count']} puntos, {result['vectors_count']} vectores, tamaño={result['config']['size']}")
            return result
        except Exception as e:
            logger.error(f"[QdrantRepository] Error al obtener información de colección: {e}", exc_info=True)
            return {"error": str(e)}

