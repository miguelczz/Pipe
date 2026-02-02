"""
Script para indexar el manual técnico de Band Steering en Qdrant.
Permite que el RAGChat tenga conocimiento sobre los estándares WiFi (802.11k/v/r).
"""
import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import List

# Cargar variables de entorno desde .env antes de importar nada de src
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configurar rutas - buscar .env en la raíz del proyecto
backend_dir = Path(__file__).parent
project_root = backend_dir.parent  # Raíz del proyecto
env_path = project_root / ".env"  # .env en la raíz

# Fallback: buscar también en backend/ por si acaso
backend_env_path = backend_dir / ".env"

if env_path.exists():
    logger.info(f"💾 Cargando configuración desde {env_path}")
    load_dotenv(dotenv_path=env_path)
elif backend_env_path.exists():
    logger.info(f"💾 Cargando configuración desde {backend_env_path}")
    load_dotenv(dotenv_path=backend_env_path)
else:
    logger.warning(f"⚠️ No se encontró el archivo .env. Buscado en:")
    logger.warning(f"   - {env_path}")
    logger.warning(f"   - {backend_env_path}")

# Agregar el directorio backend al path para las importaciones
sys.path.insert(0, str(backend_dir))

# Ahora importamos componentes del proyecto
try:
    from src.repositories.qdrant_repository import get_qdrant_repository
    from src.utils.text_processing import text_splitter, process_pdf_to_text
    from src.utils.embeddings import embedding_for_text_batch
    from src.settings import settings
except ImportError as e:
    logger.error(f"❌ Error al importar módulos del proyecto: {e}")
    sys.exit(1)
except Exception as e:
    logger.error(f"❌ Error de configuración (posiblemente faltan variables en .env): {e}")
    sys.exit(1)

async def index_pdf_file(file_path: Path, qdrant_repo):
    """Indexa un archivo PDF en Qdrant."""
    if not file_path.exists():
        logger.error(f"❌ El archivo no existe: {file_path}")
        return

    logger.info(f"📄 Procesando manual técnico: {file_path.name}")
    
    text = process_pdf_to_text(str(file_path))
    if not text or not text.strip():
        logger.warning(f"⚠️ No se pudo extraer texto del PDF: {file_path}")
        return
    
    # Dividir en chunks para mejor recuperación en el RAG
    chunks = text_splitter(text, chunk_size=500, overlap=50)
    logger.info(f"   - Texto dividido en {len(chunks)} fragmentos.")
    
    # Generar embeddings usando OpenAI (requiere API Key en el .env)
    logger.info("   - Generando vectores de búsqueda (embeddings)...")
    embeddings = embedding_for_text_batch(chunks)
    
    # Preparar puntos para la base de datos vectorial
    document_id = f"manual_band_steering"
    points = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        points.append({
            "vector": emb,
            "payload": {
                "text": chunk,
                "source": file_path.name,
                "chunk_index": i,
                "document_id": document_id,
                "type": "technical_manual"
            }
        })
    
    # Guardar en Qdrant
    logger.info(f"   - Guardando en base de datos Qdrant...")
    qdrant_repo.upsert_points(points)
    logger.info(f"   ✅ '{file_path.name}' indexado correctamente.")

async def main():
    qdrant_repo = get_qdrant_repository()
    
    # Ruta específica del manual solicitado
    docs_dir = backend_dir.parent / "docs"
    manual_path = docs_dir / "pdfs" / "WIRESHARK BANDSTEERING.pdf"
    
    print("\n" + "="*60)
    print("🚀 INDEXACIÓN DE CONOCIMIENTO TÉCNICO - Band Steering")
    print("="*60 + "\n")
    
    await index_pdf_file(manual_path, qdrant_repo)

    print("\n" + "="*60)
    print("✨ PROCESO COMPLETADO EXITOSAMENTE")
    print("🎯 El asistente ahora tiene conocimiento sobre el manual solicitado.")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
