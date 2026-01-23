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

from ..services.band_steering_service import BandSteeringService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/network-analysis", tags=["network-analysis"])

# Instanciar el servicio orquestador (AIDLC)
band_steering_service = BandSteeringService()

# Thread pool executor para operaciones pesadas de tshark
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="wireshark_analysis")


@router.post("/analyze")
async def analyze_network_capture(file: UploadFile = File(...)):
    """
    Sube un archivo de captura y realiza el proceso AIDLC completo de Band Steering.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Debe proporcionar un archivo de captura.")

    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".pcap") or filename_lower.endswith(".pcapng")):
        raise HTTPException(
            status_code=400,
            detail="Solo se aceptan archivos de captura .pcap o .pcapng.",
        )

    # Directorio temporal para la subida
    base_dir = Path(__file__).resolve().parents[2]
    uploads_dir = base_dir / "databases" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    temp_name = f"{uuid.uuid4()}_{file.filename}"
    temp_path = uploads_dir / temp_name

    try:
        content = await file.read()
        temp_path.write_bytes(content)

        logger.info(f"[NetworkAnalysis] Iniciando proceso AIDLC para: {file.filename}")

        # Ejecutar el servicio en un thread separado (tshark es bloqueante)
        loop = asyncio.get_event_loop()
        result_pkg = await loop.run_in_executor(
            _executor,
            lambda: asyncio.run(band_steering_service.process_capture(
                str(temp_path),
                original_filename=file.filename
            ))
        )

        analysis = result_pkg["analysis"]
        raw_stats = result_pkg["raw_stats"]

        # Formatear respuesta para compatibilidad TOTAL con el frontend actual
        return JSONResponse(
            content={
                "file_name": analysis.filename,
                "analysis": analysis.analysis_text,
                "stats": raw_stats,  # Mantenemos la estructura de stats para el dashboard
                "aidlc": {
                    "analysis_id": analysis.analysis_id,
                    "verdict": analysis.verdict,
                    "device": analysis.devices[0].model_dump() if analysis.devices else {},
                    "compliance_checks": [c.model_dump() for c in analysis.compliance_checks],
                    "fragments_count": len(analysis.fragments)
                }
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


