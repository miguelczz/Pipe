from fastapi import APIRouter, HTTPException
from pathlib import Path
import json
import logging
from typing import List, Dict, Any
from ..services.band_steering_service import BandSteeringService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])
service = BandSteeringService()

@router.get("/")
async def list_reports():
    """
    Lista todos los análisis guardados organizados por marca.
    """
    reports = []
    base_dir = service.base_dir
    
    if not base_dir.exists():
        return []
        
    try:
        # Recorrer Marca / Dispositivo / Analisis.json
        for vendor_dir in base_dir.iterdir():
            if not vendor_dir.is_dir():
                continue
            
            for device_dir in vendor_dir.iterdir():
                if not device_dir.is_dir():
                    continue
                
                for analysis_file in device_dir.glob("*.json"):
                    try:
                        with open(analysis_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            reports.append({
                                "id": data.get("analysis_id"),
                                "filename": data.get("filename"),
                                "timestamp": data.get("analysis_timestamp"),
                                "vendor": data.get("devices", [{}])[0].get("vendor"),
                                "verdict": data.get("verdict"),
                                "score": data.get("overall_compliance_score")
                            })
                    except Exception as e:
                        logger.warning(f"Error al leer reporte {analysis_file}: {e}")
        
        # Ordenar por fecha descendente
        reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return reports
    except Exception as e:
        logger.error(f"Error al listar reportes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{analysis_id}")
async def get_report(analysis_id: str):
    """
    Obtiene el detalle de un reporte específico por su ID.
    """
    base_dir = service.base_dir
    
    try:
        # Buscar el archivo en la estructura de carpetas
        for analysis_file in base_dir.glob(f"**/{analysis_id}.json"):
            with open(analysis_file, "r", encoding="utf-8") as f:
                return json.load(f)
                
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"Error al obtener reporte {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
