"""
Endpoints para análisis de capturas de red (Wireshark / PCAP) asistido por IA.
"""

import asyncio
import concurrent.futures
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
import json
from fastapi.responses import JSONResponse

from ..services.band_steering_service import BandSteeringService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/network-analysis", tags=["network-analysis"])

# Instanciar el servicio orquestador
band_steering_service = BandSteeringService()

# Thread pool executor para operaciones pesadas de tshark
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="wireshark_analysis")


@router.post("/analyze")
async def analyze_network_capture(
    file: UploadFile = File(...),
    user_metadata: str | None = Form(None),
):
    """
    Sube un archivo de captura y realiza el proceso completo de Band Steering.
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
    
    logger.info(f"🔍 [UPLOAD] Guardando archivo temporal: {temp_path}")
    logger.info(f"🔍 [UPLOAD] Nombre original: {file.filename}")
    logger.info(f"🔍 [UPLOAD] Tamaño: {file.size} bytes")

    try:
        content = await file.read()
        temp_path.write_bytes(content)
        logger.info(f"✅ [UPLOAD] Archivo temporal guardado: {temp_path}, existe: {temp_path.exists()}, tamaño: {temp_path.stat().st_size}")


        # Parsear metadata opcional del usuario (SSID, MAC cliente, etc.)
        metadata_dict = None
        if user_metadata:
            try:
                metadata_dict = json.loads(user_metadata)
            except json.JSONDecodeError:
                metadata_dict = None

        # Ejecutar el servicio en un thread separado (tshark es bloqueante)
        # Asegurar que temp_path sea absoluto antes de pasarlo al servicio
        temp_path_abs = temp_path.resolve()
        logger.info(f"🔍 [UPLOAD] Antes de procesar, verificando archivo temporal: {temp_path_abs.exists()}")
        logger.info(f"🔍 [UPLOAD] Path temporal absoluto: {temp_path_abs}")
        loop = asyncio.get_event_loop()
        result_pkg = await loop.run_in_executor(
            _executor,
            lambda: asyncio.run(
                band_steering_service.process_capture(
                    str(temp_path_abs),
                    user_metadata=metadata_dict,
                    original_filename=file.filename,
                )
            )
        )
        logger.info(f"🔍 [UPLOAD] Después de procesar, archivo temporal todavía existe: {temp_path_abs.exists()}")
        
        # CRÍTICO: El archivo temporal debe existir cuando se guarda el análisis
        # Asegurar que el path sea absoluto y que el archivo exista
        if not temp_path_abs.exists():
            logger.error(f"❌ [UPLOAD] El archivo temporal NO existe después del procesamiento: {temp_path_abs}")
            raise HTTPException(status_code=500, detail="El archivo temporal se perdió durante el procesamiento")

        analysis = result_pkg["analysis"]
        raw_stats = result_pkg["raw_stats"]

        # Formatear respuesta para compatibilidad TOTAL con el frontend actual
        try:
            # Serializar todos los objetos Pydantic de forma segura
            response_data = {
                "file_name": analysis.filename,
                "analysis": analysis.analysis_text,
                "stats": raw_stats,  # Mantenemos la estructura de stats para el dashboard
                "band_steering": {
                    "analysis_id": analysis.analysis_id,
                    "verdict": analysis.verdict,
                    "device": analysis.devices[0].model_dump() if analysis.devices and len(analysis.devices) > 0 else {},
                    "compliance_checks": [c.model_dump(mode='json') for c in analysis.compliance_checks] if analysis.compliance_checks else [],
                    "fragments_count": len(analysis.fragments) if analysis.fragments else 0,
                    # Agregar datos para la gráfica de Band Steering
                    "btm_events": [e.model_dump(mode='json') for e in analysis.btm_events] if analysis.btm_events else [],
                    "transitions": [t.model_dump(mode='json') for t in analysis.transitions] if analysis.transitions else [],
                    "signal_samples": [s.model_dump(mode='json') for s in analysis.signal_samples] if analysis.signal_samples else []
                }
            }
            logger.info(f"✅ [RESPONSE] Respuesta formateada correctamente, analysis_id: {analysis.analysis_id}")
            return JSONResponse(content=response_data)
        except Exception as serialization_error:
            logger.error(f"❌ [SERIALIZATION] Error al serializar respuesta: {str(serialization_error)}", exc_info=True)
            # Intentar respuesta mínima
            try:
                minimal_response = {
                    "file_name": analysis.filename if hasattr(analysis, 'filename') else "unknown",
                    "analysis": analysis.analysis_text if hasattr(analysis, 'analysis_text') else "Error al generar análisis",
                    "stats": raw_stats,
                    "band_steering": {
                        "analysis_id": str(analysis.analysis_id) if hasattr(analysis, 'analysis_id') else "unknown",
                        "verdict": str(analysis.verdict) if hasattr(analysis, 'verdict') else "UNKNOWN",
                        "error": f"Error de serialización: {str(serialization_error)}"
                    }
                }
                return JSONResponse(content=minimal_response)
            except Exception as fallback_error:
                logger.error(f"❌ [FALLBACK] Error incluso en respuesta mínima: {str(fallback_error)}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Error crítico al serializar respuesta: {str(serialization_error)}"
                )
    except RuntimeError as e:
        # Errores típicos de pyshark/tshark no instalado
        raise HTTPException(
            status_code=500,
            detail=(
                "No se pudo analizar la captura porque pyshark/tshark no están disponibles "
                "en el servidor. Contacta al administrador para instalar estas dependencias."
            ),
        )
    except Exception as e:
        logger.error(f"❌ [ERROR] Error al analizar la captura de red: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al analizar la captura de red: {str(e)}",
        )
    finally:
        # NO eliminar el archivo - se guardará para descarga posterior
        # El archivo se moverá a la carpeta del análisis en band_steering_service
        pass


