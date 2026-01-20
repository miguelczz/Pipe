"""
Endpoints para análisis de capturas de red (Wireshark / PCAP) asistido por IA.
"""

import asyncio
import concurrent.futures
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from ..tools.wireshark_tool import WiresharkTool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/network-analysis", tags=["network-analysis"])

wireshark_tool = WiresharkTool()

# Thread pool executor para ejecutar análisis de capturas en threads separados
# Esto evita conflictos con el event loop de FastAPI y problemas con pyshark
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="wireshark_analysis")


@router.post("/analyze")
async def analyze_network_capture(file: UploadFile = File(...)):
    """
    Sube un archivo de captura de red (pcap/pcapng) y devuelve un análisis
    generado por la IA a partir de las estadísticas básicas de la captura.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Debe proporcionar un archivo de captura.")

    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".pcap") or filename_lower.endswith(".pcapng")):
        raise HTTPException(
            status_code=400,
            detail="Solo se aceptan archivos de captura .pcap o .pcapng.",
        )

    # Directorio temporal/local para guardar la captura
    base_dir = Path(__file__).resolve().parents[2]
    uploads_dir = base_dir / "databases" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    temp_name = f"{uuid.uuid4()}_{file.filename}"
    temp_path = uploads_dir / temp_name

    try:
        content = await file.read()
        temp_path.write_bytes(content)

        logger.info(f"[NetworkAnalysis] Archivo de captura guardado en: {temp_path}")

        # Ejecutar el análisis en un thread separado usando ThreadPoolExecutor
        # Esto evita conflictos con el event loop de FastAPI y problemas con pyshark/tshark
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor,
            wireshark_tool.analyze_capture,
            str(temp_path)
        )

        return JSONResponse(
            content={
                "file_name": result.get("file_name"),
                "analysis": result.get("analysis"),
                "stats": result.get("stats"),
            }
        )
    except RuntimeError as e:
        # Errores típicos de pyshark/tshark no instalado
        logger.error(f"[NetworkAnalysis] Error de entorno al analizar captura: {e}")
        raise HTTPException(
            status_code=500,
            detail=(
                "No se pudo analizar la captura porque pyshark/tshark no están disponibles "
                "en el servidor. Contacta al administrador para instalar estas dependencias."
            ),
        )
    except Exception as e:
        logger.error(f"[NetworkAnalysis] Error al procesar captura: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al analizar la captura de red: {str(e)}",
        )
    finally:
        # Intentar eliminar el archivo temporal
        try:
            if temp_path.exists():
                os.remove(temp_path)
        except Exception:
            logger.warning(f"No se pudo eliminar el archivo temporal: {temp_path}")


