from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pathlib import Path
import json
import logging
from typing import List, Dict, Any
from io import BytesIO
from ..services.band_steering_service import BandSteeringService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])
service = BandSteeringService()

# Manejar tanto /reports como /reports/
@router.get("", include_in_schema=True)
@router.get("/", include_in_schema=True)
async def list_reports():
    """
    Lista todos los análisis guardados organizados por marca.
    """
    reports = []
    base_dir = service.base_dir
    
    logger.info(f"🔍 [REPORTS] Buscando reportes en: {base_dir}")
    logger.info(f"🔍 [REPORTS] Directorio existe: {base_dir.exists()}")
    
    if not base_dir.exists():
        logger.warning(f"⚠️ [REPORTS] Directorio base no existe: {base_dir}")
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
                            # Extraer info del dispositivo
                            devices = data.get("devices", [])
                            if not devices or len(devices) == 0:
                                logger.warning(f"⚠️ [REPORTS] Archivo {analysis_file} no tiene dispositivos")
                                continue
                            
                            device = devices[0]
                            reports.append({
                                "id": data.get("analysis_id"),
                                "filename": data.get("filename"), # Nombre original del pcap
                                "timestamp": data.get("analysis_timestamp"),
                                "vendor": device.get("vendor", "Unknown"),
                                "model": device.get("device_model", "Unknown"),
                                "verdict": data.get("verdict")
                            })
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ [REPORTS] Error al parsear JSON {analysis_file}: {str(e)}")
                    except Exception as e:
                        logger.error(f"❌ [REPORTS] Error al leer archivo {analysis_file}: {str(e)}", exc_info=True)
        
        # Ordenar por fecha descendente
        reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        logger.info(f"✅ [REPORTS] Total de reportes encontrados: {len(reports)}")
        return reports
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{analysis_id}/download")
async def download_capture(analysis_id: str):
    """
    Descarga el archivo pcap original de un análisis.
    """
    logger.info(f"🔍 [DOWNLOAD] Iniciando descarga para analysis_id: {analysis_id}")
    base_dir = service.base_dir
    logger.info(f"🔍 [DOWNLOAD] Base dir: {base_dir}")
    logger.info(f"🔍 [DOWNLOAD] Base dir existe: {base_dir.exists()}")
    
    try:
        # Buscar el archivo JSON del análisis
        analysis_file = None
        json_files = list(base_dir.glob(f"**/{analysis_id}.json"))
        logger.info(f"🔍 [DOWNLOAD] Archivos JSON encontrados: {len(json_files)}")
        for json_file in json_files:
            logger.info(f"🔍 [DOWNLOAD] Archivo encontrado: {json_file}")
            analysis_file = json_file
            break
        
        if not analysis_file:
            logger.error(f"❌ [DOWNLOAD] No se encontró el archivo JSON para analysis_id: {analysis_id}")
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        
        logger.info(f"✅ [DOWNLOAD] Archivo JSON encontrado: {analysis_file}")
        
        # Leer el JSON para obtener la ruta del archivo pcap
        with open(analysis_file, "r", encoding="utf-8") as f:
            analysis_data = json.load(f)
        
        logger.info(f"🔍 [DOWNLOAD] Claves en analysis_data: {list(analysis_data.keys())}")
        
        # Obtener la ruta del archivo pcap
        pcap_path = analysis_data.get("original_file_path")
        logger.info(f"🔍 [DOWNLOAD] original_file_path encontrado: {pcap_path}")
        
        if not pcap_path:
            # Reporte antiguo sin archivo guardado
            logger.warning(f"⚠️ [DOWNLOAD] Reporte antiguo sin original_file_path para analysis_id: {analysis_id}")
            raise HTTPException(
                status_code=404, 
                detail="Este reporte fue creado antes de implementar la descarga de archivos. Solo los análisis nuevos guardan el archivo pcap original."
            )
        
        pcap_file = Path(pcap_path)
        logger.info(f"🔍 [DOWNLOAD] Ruta del archivo pcap: {pcap_file}")
        logger.info(f"🔍 [DOWNLOAD] Archivo existe: {pcap_file.exists()}")
        logger.info(f"🔍 [DOWNLOAD] Ruta absoluta: {pcap_file.resolve()}")
        
        if not pcap_file.exists():
            logger.error(f"❌ [DOWNLOAD] El archivo pcap no existe: {pcap_file}")
            raise HTTPException(status_code=404, detail="El archivo pcap ya no existe en el servidor")
        
        # Obtener el nombre original del archivo desde el JSON
        original_filename = analysis_data.get("filename", "capture.pcap")
        logger.info(f"🔍 [DOWNLOAD] Nombre original del archivo: {original_filename}")
        
        if not original_filename.endswith((".pcap", ".pcapng")):
            # Asegurar extensión correcta
            if pcap_file.suffix:
                original_filename = original_filename.rsplit(".", 1)[0] + pcap_file.suffix
            else:
                original_filename += pcap_file.suffix or ".pcap"
            logger.info(f"🔍 [DOWNLOAD] Nombre corregido: {original_filename}")
        
        logger.info(f"✅ [DOWNLOAD] Enviando archivo: {pcap_file} como {original_filename}")
        return FileResponse(
            path=str(pcap_file),
            filename=original_filename,
            media_type="application/vnd.tcpdump.pcap"
        )
    except HTTPException as e:
        logger.error(f"❌ [DOWNLOAD] HTTPException: {e.status_code} - {e.detail}")
        raise
    except Exception as e:
        logger.error(f"❌ [DOWNLOAD] Error inesperado: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al descargar el archivo: {str(e)}")

@router.delete("/{analysis_id}")
async def delete_report(analysis_id: str):
    """
    Elimina un reporte específico por su ID.
    """
    base_dir = service.base_dir
    try:
        # Buscar el archivo en la estructura de carpetas
        found = False
        for analysis_file in base_dir.glob(f"**/{analysis_id}.json"):
            analysis_file.unlink()
            found = True
            break
            
        if not found:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
            
        return {"status": "success", "message": f"Reporte {analysis_id} eliminado"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{analysis_id}/pdf")
async def download_pdf(analysis_id: str):
    """
    Genera y descarga un PDF del reporte de análisis.
    """
    logger.info(f"🔍 [PDF] Iniciando generación de PDF para analysis_id: {analysis_id}")
    base_dir = service.base_dir
    
    try:
        # Buscar el archivo JSON del análisis
        analysis_file = None
        json_files = list(base_dir.glob(f"**/{analysis_id}.json"))
        for json_file in json_files:
            analysis_file = json_file
            break
        
        if not analysis_file:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        
        # Leer el JSON
        with open(analysis_file, "r", encoding="utf-8") as f:
            analysis_data = json.load(f)
        
        # Generar HTML formateado que el navegador puede convertir a PDF
        # El frontend manejará la conversión usando la API de impresión del navegador
        html_content = _generate_pdf_html(analysis_data)
        
        # Devolver HTML con media type text/html
        # El frontend puede usar window.print() o una librería como jsPDF para convertir a PDF
        return Response(
            content=html_content,
            media_type="text/html",
            headers={
                "Content-Disposition": f'inline; filename="report_{analysis_id}.html"'
            }
        )
    except HTTPException as e:
        raise
    except Exception as e:
        logger.error(f"❌ [PDF] Error al generar PDF: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al generar el PDF: {str(e)}")

def _generate_pdf_html(analysis_data: Dict[str, Any]) -> str:
    """Genera HTML para el PDF del reporte."""
    filename = analysis_data.get("filename", "Unknown")
    verdict = analysis_data.get("verdict", "UNKNOWN")
    analysis_text = analysis_data.get("analysis_text", "No hay análisis disponible")
    devices = analysis_data.get("devices", [])
    device = devices[0] if devices else {}
    vendor = device.get("vendor", "Unknown")
    model = device.get("device_model", "Unknown")
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Reporte de Análisis - {filename}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 40px;
                color: #333;
            }}
            h1 {{
                color: #2c3e50;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
            }}
            h2 {{
                color: #34495e;
                margin-top: 30px;
            }}
            .header {{
                background: #ecf0f1;
                padding: 20px;
                border-radius: 5px;
                margin-bottom: 30px;
            }}
            .verdict {{
                display: inline-block;
                padding: 5px 15px;
                border-radius: 5px;
                font-weight: bold;
                margin-top: 10px;
            }}
            .success {{
                background: #2ecc71;
                color: white;
            }}
            .failed {{
                background: #e74c3c;
                color: white;
            }}
            .info {{
                margin: 10px 0;
            }}
            .analysis {{
                background: #f8f9fa;
                padding: 20px;
                border-left: 4px solid #3498db;
                margin: 20px 0;
                white-space: pre-wrap;
            }}
        </style>
    </head>
    <body>
        <h1>Reporte de Análisis de Band Steering</h1>
        
        <div class="header">
            <div class="info"><strong>Archivo:</strong> {filename}</div>
            <div class="info"><strong>Fabricante:</strong> {vendor}</div>
            <div class="info"><strong>Modelo:</strong> {model}</div>
            <div class="info">
                <strong>Veredicto:</strong> 
                <span class="verdict {'success' if verdict in ['SUCCESS', 'EXCELLENT', 'GOOD'] else 'failed'}">
                    {verdict}
                </span>
            </div>
        </div>
        
        <h2>Análisis Detallado</h2>
        <div class="analysis">{analysis_text}</div>
        
        <div style="margin-top: 50px; text-align: center; color: #7f8c8d; font-size: 12px;">
            Generado por Pipe - Análisis de Capturas Wireshark
        </div>
    </body>
    </html>
    """
    return html

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
        raise HTTPException(status_code=500, detail=str(e))
