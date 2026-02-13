"""
Utilities for embedding generation
"""
from typing import List
from openai import OpenAI
from ..settings import settings

# Global OpenAI client for embeddings
_client = OpenAI(api_key=settings.openai_api_key)


def embedding_for_text(text: str) -> List[float]:
    """
    Generates an embedding for a text using OpenAI.
    IMPORTANT: Use dimensions=1536 for text-embedding-3-large to maintain consistency.
    
    Args:
        text: Text to convert to embedding
    
    Returns:
        List of floats representing the embedding (1536 dimensions)
    """
    # text-embedding-3-large by default generates 3072 dimensions
    # We specify dimensions=1536 to maintain consistency with Qdrant configuration
    response = _client.embeddings.create(
        model=settings.embedding_model,
        input=text,
        dimensions=1536  # Force 1536 dimensions instead of 3072 by default
    )
    return response.data[0].embedding


def embedding_for_text_batch(texts: List[str]) -> List[List[float]]:
    """
    Generates embeddings for a list of texts using OpenAI.
    More efficient than calling embedding_for_text multiple times.
    IMPORTANT: Use dimensions=1536 for text-embedding-3-large to maintain consistency.
    
    Args:
        texts: List of texts to convert to embeddings
    
    Returns:
        List of embeddings (each is a list of floats of 1536 dimensions)
    """
    if not texts:
        return []

    # text-embedding-3-large by default generates 3072 dimensions
    # We specify dimensions=1536 to maintain consistency with Qdrant configuration
    response = _client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
        dimensions=1536  # Force 1536 dimensions instead of 3072 by default
    )
    return [d.embedding for d in response.data]

