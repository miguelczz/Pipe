"""
Utilidades para generación de embeddings
"""
from typing import List
from openai import OpenAI
from ..settings import settings

# Cliente OpenAI global para embeddings
_client = OpenAI(api_key=settings.openai_api_key)


def embedding_for_text(text: str) -> List[float]:
    """
    Genera un embedding para un texto usando OpenAI.
    IMPORTANTE: Usa dimensions=1536 para text-embedding-3-large para mantener consistencia.
    
    Args:
        text: Texto a convertir en embedding
    
    Returns:
        Lista de floats representando el embedding (1536 dimensiones)
    """
    # text-embedding-3-large por defecto genera 3072 dimensiones
    # Especificamos dimensions=1536 para mantener consistencia con la configuración de Qdrant
    response = _client.embeddings.create(
        model=settings.embedding_model,
        input=text,
        dimensions=1536  # Forzar 1536 dimensiones en lugar de 3072 por defecto
    )
    return response.data[0].embedding


def embedding_for_text_batch(texts: List[str]) -> List[List[float]]:
    """
    Genera embeddings para una lista de textos usando OpenAI.
    Más eficiente que llamar embedding_for_text múltiples veces.
    IMPORTANTE: Usa dimensions=1536 para text-embedding-3-large para mantener consistencia.
    
    Args:
        texts: Lista de textos a convertir en embeddings
    
    Returns:
        Lista de embeddings (cada uno es una lista de floats de 1536 dimensiones)
    """
    if not texts:
        return []

    # text-embedding-3-large por defecto genera 3072 dimensiones
    # Especificamos dimensions=1536 para mantener consistencia con la configuración de Qdrant
    response = _client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
        dimensions=1536  # Forzar 1536 dimensiones en lugar de 3072 por defecto
    )
    return [d.embedding for d in response.data]

