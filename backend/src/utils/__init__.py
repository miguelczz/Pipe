"""
Utilidades y funciones auxiliares del sistema
"""
from .text_processing import text_splitter, process_pdf_to_text
from .embeddings import embedding_for_text, embedding_for_text_batch

__all__ = [
    "text_splitter",
    "process_pdf_to_text",
    "embedding_for_text",
    "embedding_for_text_batch",
]

# Importar evaluador y callback de Ragas (opcional)
try:
    from .ragas_evaluator import RAGASEvaluator, get_evaluator
    from .ragas_callback import RAGASCallbackHandler, get_ragas_callback
    __all__.extend([
        "RAGASEvaluator",
        "get_evaluator",
        "RAGASCallbackHandler",
        "get_ragas_callback",
    ])
except ImportError:
    # Ragas no está disponible, no exportar
    pass

