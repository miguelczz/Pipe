"""
Text processing utilities
"""
from typing import List
from PyPDF2 import PdfReader


def text_splitter(text: str, chunk_size: int = 200, overlap: int = 20) -> List[str]:
    """
    Splits text into chunks with overlap.
    
    Args:
        text: Text to split
        chunk_size: Size of each chunk in tokens/words
        overlap: Number of words that overlap between chunks
    
    Returns:
        List of text chunks
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
    Extracts text from a PDF file.
    
    Args:
        path: Path to the PDF file
    
    Returns:
        Concatenated extracted text from the PDF
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
