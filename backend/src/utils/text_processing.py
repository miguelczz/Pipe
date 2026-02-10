"""
Utilidades para procesamiento de texto
"""
from typing import List
from PyPDF2 import PdfReader


def text_splitter(text: str, chunk_size: int = 200, overlap: int = 20) -> List[str]:
    """
    Divide el texto en fragmentos (chunks) con superposición.
    
    Args:
        text: Texto a dividir
        chunk_size: Tamaño de cada chunk en tokens/palabras
        overlap: Número de palabras que se superponen entre chunks
    
    Returns:
        Lista de chunks de texto
    """
    tokens = text.split()
    chunks = []
    i = 0
    while i < len(tokens):
        chunk = " ".join(tokens[i:i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


def process_pdf_to_text(path: str) -> str:
    """
    Extrae texto de un archivo PDF.
    
    Args:
        path: Ruta al archivo PDF
    
    Returns:
        Texto extraído del PDF concatenado
    """
    reader = PdfReader(path)
    texts = []
    for page in reader.pages:
        try:
            extracted = page.extract_text() or ""
            texts.append(extracted)
        except Exception:
            continue
    return "\n".join(texts)

