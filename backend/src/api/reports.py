from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi import Body
from pathlib import Path
import json
import logging
from typing import List, Dict, Any, Optional
from io import BytesIO
from datetime import datetime
from collections import Counter
import pytz
from ..services.band_steering_service import BandSteeringService
from ..agent.llm_client import LLMClient

logger = logging.getLogger(__name__)

# WeasyPrint se importará de forma lazy solo cuando se necesite
WEASYPRINT_AVAILABLE = None
HTML = None

def _check_weasyprint():
    """Verifica si WeasyPrint está disponible e importa el módulo."""
    global WEASYPRINT_AVAILABLE, HTML
    if WEASYPRINT_AVAILABLE is not None:
        return WEASYPRINT_AVAILABLE
    
    try:
        from weasyprint import HTML as WeasyHTML
        HTML = WeasyHTML
        WEASYPRINT_AVAILABLE = True
        logger.info("✅ WeasyPrint está disponible")
        return True
    except ImportError as e:
        WEASYPRINT_AVAILABLE = False
        logger.warning(f"⚠️ WeasyPrint no está disponible: {e}")
        return False
    except OSError as e:
        WEASYPRINT_AVAILABLE = False
        logger.error(f"❌ WeasyPrint no puede cargar librerías del sistema: {e}")
        logger.error("💡 Instala las dependencias del sistema: apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info")
        return False

router = APIRouter(prefix="/reports", tags=["reports"])
service = BandSteeringService()
llm_client = LLMClient()

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

@router.post("/{analysis_id}/pdf")
async def save_pdf(analysis_id: str, html_content: str = Body(..., media_type="text/plain")):
    """
    Persiste el PDF del reporte de análisis desde el HTML proporcionado por el frontend.
    Se llama cuando el usuario hace clic en "Exportar PDF" en NetworkAnalysisPage.
    """
    logger.info(f"💾 [PDF] Guardando PDF para analysis_id: {analysis_id}")
    base_dir = service.base_dir
    
    try:
        # Buscar el archivo JSON del análisis para obtener la ruta del directorio
        analysis_file = None
        json_files = list(base_dir.glob(f"**/{analysis_id}.json"))
        for json_file in json_files:
            analysis_file = json_file
            break
        
        if not analysis_file:
            logger.error(f"❌ [PDF] No se encontró el archivo JSON para analysis_id: {analysis_id}")
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        
        logger.info(f"📁 [PDF] Archivo JSON encontrado: {analysis_file}")
        
        # El PDF se guarda en el mismo directorio que el JSON
        pdf_path = analysis_file.parent / f"{analysis_id}.pdf"
        logger.info(f"📄 [PDF] Ruta del PDF: {pdf_path}")
        
        # Verificar WeasyPrint de forma lazy
        if not _check_weasyprint():
            logger.error("❌ [PDF] WeasyPrint no está disponible")
            raise HTTPException(
                status_code=500, 
                detail="WeasyPrint no está disponible. Instala las dependencias del sistema: libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info"
            )
        
        logger.info("✅ [PDF] WeasyPrint está disponible")
        
        # Validar que el HTML no esté vacío
        if not html_content or not html_content.strip():
            logger.error("❌ [PDF] El contenido HTML está vacío")
            raise HTTPException(
                status_code=400,
                detail="El contenido HTML está vacío"
            )
        
        html_length = len(html_content)
        logger.info(f"📝 [PDF] HTML recibido: {html_length} caracteres")
        logger.info(f"📝 [PDF] Primeros 500 caracteres del HTML: {html_content[:500]}")
        
        # Verificar si hay un PDF anterior y eliminarlo
        if pdf_path.exists():
            old_size = pdf_path.stat().st_size
            logger.warning(f"⚠️ [PDF] PDF anterior existe (tamaño: {old_size} bytes). Eliminando...")
            try:
                pdf_path.unlink()
                logger.info("🧹 [PDF] PDF anterior eliminado")
            except Exception as e:
                logger.warning(f"⚠️ [PDF] No se pudo eliminar PDF anterior: {e}")
        
        # Convertir HTML a PDF usando WeasyPrint
        try:
            logger.info("🔄 [PDF] Iniciando conversión HTML a PDF...")
            
            # Crear el documento HTML
            html_doc = HTML(string=html_content, base_url=None)
            logger.info("✅ [PDF] Documento HTML creado")
            
            # Generar el PDF con configuraciones apropiadas
            logger.info("🔄 [PDF] Generando PDF...")
            html_doc.write_pdf(
                pdf_path,
                stylesheets=None,  # Los estilos ya están en el HTML
                presentational_hints=True
            )
            logger.info("✅ [PDF] write_pdf completado")
            
            # Verificar que el PDF se creó correctamente
            if not pdf_path.exists():
                logger.error("❌ [PDF] El archivo PDF no existe después de la generación")
                raise Exception("El PDF no se creó")
            
            pdf_size = pdf_path.stat().st_size
            logger.info(f"📊 [PDF] Tamaño del PDF generado: {pdf_size} bytes")
            
            if pdf_size == 0:
                logger.error("❌ [PDF] El PDF está vacío (0 bytes)")
                try:
                    pdf_path.unlink()
                    logger.info("🧹 [PDF] PDF vacío eliminado")
                except Exception:
                    pass
                raise Exception("El PDF generado está vacío")
            
            # Validar que el PDF tenga el header correcto (debe empezar con %PDF)
            try:
                with open(pdf_path, 'rb') as f:
                    header = f.read(4)
                    if header != b'%PDF':
                        logger.error(f"❌ [PDF] Header inválido. Esperado: %PDF, Obtenido: {header}")
                        try:
                            pdf_path.unlink()
                            logger.info("🧹 [PDF] PDF con header inválido eliminado")
                        except Exception:
                            pass
                        raise Exception(f"El archivo generado no es un PDF válido (header: {header})")
                    logger.info("✅ [PDF] Header del PDF válido")
            except Exception as header_error:
                logger.error(f"❌ [PDF] Error al validar header: {header_error}")
                if pdf_path.exists():
                    try:
                        pdf_path.unlink()
                    except Exception:
                        pass
                raise
            
            logger.info(f"✅ [PDF] PDF guardado exitosamente en: {pdf_path} (tamaño: {pdf_size} bytes)")
            return {
                "status": "success", 
                "message": "PDF guardado correctamente", 
                "path": str(pdf_path),
                "size": pdf_size
            }
        except Exception as pdf_error:
            error_msg = str(pdf_error)
            error_type = type(pdf_error).__name__
            logger.error(f"❌ [PDF] Error al convertir HTML a PDF: {error_type}: {error_msg}", exc_info=True)
            
            # Limpiar archivo corrupto si existe
            if pdf_path.exists():
                try:
                    corrupt_size = pdf_path.stat().st_size
                    logger.warning(f"🧹 [PDF] Eliminando archivo corrupto (tamaño: {corrupt_size} bytes)")
                    pdf_path.unlink()
                    logger.info("🧹 [PDF] Archivo corrupto eliminado")
                except Exception as cleanup_error:
                    logger.error(f"❌ [PDF] Error al eliminar archivo corrupto: {cleanup_error}")
            
            raise HTTPException(
                status_code=500, 
                detail=f"Error al convertir HTML a PDF: {error_msg}"
            )
            
    except HTTPException as e:
        logger.error(f"❌ [PDF] HTTPException: {e.status_code} - {e.detail}")
        raise
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"❌ [PDF] Error inesperado al guardar PDF: {error_type}: {error_msg}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al guardar el PDF: {error_msg}")

@router.get("/{analysis_id}/pdf")
async def download_pdf(analysis_id: str):
    """
    Descarga el PDF persistido del reporte de análisis.
    Si el PDF no existe, lo genera automáticamente desde los datos del análisis.
    """
    logger.info(f"📥 [PDF] Descargando PDF para analysis_id: {analysis_id}")
    base_dir = service.base_dir
    
    try:
        # Buscar el archivo PDF persistido
        pdf_files = list(base_dir.glob(f"**/{analysis_id}.pdf"))
        logger.info(f"🔍 [PDF] Archivos PDF encontrados: {len(pdf_files)}")
        
        # Si el PDF no existe, generarlo automáticamente
        if not pdf_files:
            logger.info(f"🔄 [PDF] PDF no encontrado. Generando automáticamente desde los datos del análisis...")
            
            # Buscar el archivo JSON del análisis
            json_files = list(base_dir.glob(f"**/{analysis_id}.json"))
            if not json_files:
                logger.error(f"❌ [PDF] No se encontró el análisis para analysis_id: {analysis_id}")
                raise HTTPException(
                    status_code=404,
                    detail="Análisis no encontrado"
                )
            
            analysis_file = json_files[0]
            logger.info(f"📄 [PDF] Archivo JSON encontrado: {analysis_file}")
            
            # Leer el JSON del análisis
            try:
                with open(analysis_file, "r", encoding="utf-8") as f:
                    analysis_data = json.load(f)
            except Exception as e:
                logger.error(f"❌ [PDF] Error al leer JSON: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error al leer los datos del análisis: {str(e)}"
                )
            
            # Verificar WeasyPrint
            if not _check_weasyprint():
                logger.error("❌ [PDF] WeasyPrint no está disponible")
                raise HTTPException(
                    status_code=500,
                    detail="WeasyPrint no está disponible. No se puede generar el PDF automáticamente."
                )
            
            # Generar HTML desde los datos del análisis
            html_content = _generate_pdf_html(analysis_data)
            logger.info(f"✅ [PDF] HTML generado ({len(html_content)} caracteres)")
            
            # Ruta donde se guardará el PDF
            pdf_path = analysis_file.parent / f"{analysis_id}.pdf"
            logger.info(f"💾 [PDF] Guardando PDF en: {pdf_path}")
            
            # Convertir HTML a PDF
            try:
                html_doc = HTML(string=html_content, base_url=None)
                html_doc.write_pdf(
                    pdf_path,
                    stylesheets=None,
                    presentational_hints=True
                )
                
                # Verificar que se creó correctamente
                if not pdf_path.exists() or pdf_path.stat().st_size == 0:
                    logger.error("❌ [PDF] El PDF generado está vacío")
                    raise Exception("El PDF generado está vacío")
                
                pdf_size = pdf_path.stat().st_size
                logger.info(f"✅ [PDF] PDF generado exitosamente ({pdf_size} bytes)")
                
                # Validar header
                with open(pdf_path, 'rb') as f:
                    header = f.read(4)
                    if header != b'%PDF':
                        logger.error(f"❌ [PDF] Header inválido: {header}")
                        pdf_path.unlink()
                        raise Exception(f"PDF inválido (header: {header})")
                
                logger.info("✅ [PDF] PDF generado y validado correctamente")
                
            except Exception as pdf_error:
                logger.error(f"❌ [PDF] Error al generar PDF: {pdf_error}", exc_info=True)
                if pdf_path.exists():
                    try:
                        pdf_path.unlink()
                    except Exception:
                        pass
                raise HTTPException(
                    status_code=500,
                    detail=f"Error al generar el PDF: {str(pdf_error)}"
                )
        else:
            # El PDF ya existe, usar el encontrado
            pdf_path = pdf_files[0]
            logger.info(f"✅ [PDF] PDF encontrado: {pdf_path}")
        
        # Validar que el PDF existe y tiene contenido
        if not pdf_path.exists():
            logger.error(f"❌ [PDF] El archivo PDF no existe en la ruta: {pdf_path}")
            raise HTTPException(
                status_code=404,
                detail="El archivo PDF no existe"
            )
        
        pdf_size = pdf_path.stat().st_size
        logger.info(f"📊 [PDF] Tamaño del PDF: {pdf_size} bytes")
        
        if pdf_size == 0:
            logger.error(f"❌ [PDF] El PDF está vacío (0 bytes) - ARCHIVO CORRUPTO")
            raise HTTPException(
                status_code=500,
                detail="El PDF está corrupto (archivo vacío). Por favor, exporta el PDF nuevamente."
            )
        
        # Validar header del PDF (debe empezar con %PDF)
        try:
            with open(pdf_path, 'rb') as f:
                header = f.read(4)
                logger.info(f"📄 [PDF] Header del PDF (primeros 4 bytes): {header} (hex: {header.hex()})")
                if header != b'%PDF':
                    logger.error(f"❌ [PDF] Header inválido - ARCHIVO CORRUPTO. Esperado: %PDF, Obtenido: {header}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"El PDF está corrupto (header inválido: {header}). Por favor, exporta el PDF nuevamente."
                    )
                logger.info("✅ [PDF] Header del PDF válido")
                
                # Leer un poco más para verificar que es un PDF válido
                f.seek(0)
                first_100 = f.read(100)
                logger.info(f"📄 [PDF] Primeros 100 bytes del PDF: {first_100[:50]}...")
        except HTTPException:
            raise
        except Exception as header_error:
            logger.error(f"❌ [PDF] Error al validar header: {header_error}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error al validar el PDF: {str(header_error)}"
            )
        
        # Obtener el nombre del archivo original del JSON para el nombre de descarga
        json_files = list(base_dir.glob(f"**/{analysis_id}.json"))
        filename = f"report_{analysis_id}.pdf"
        if json_files:
            try:
                with open(json_files[0], "r", encoding="utf-8") as f:
                    analysis_data = json.load(f)
                    original_filename = analysis_data.get("filename", "")
                    if original_filename:
                        # Limpiar el nombre del archivo para el PDF
                        clean_name = original_filename.split('.')[0].replace('_', ' ').strip()
                        filename = f"Pipe_{clean_name}.pdf"
            except Exception as e:
                logger.warning(f"⚠️ [PDF] No se pudo obtener nombre del archivo: {e}")
        
        logger.info(f"📤 [PDF] Enviando PDF: {filename} ({pdf_size} bytes)")
        return FileResponse(
            path=str(pdf_path),
            filename=filename,
            media_type="application/pdf"
        )
    except HTTPException as e:
        logger.error(f"❌ [PDF] HTTPException al descargar: {e.status_code} - {e.detail}")
        raise
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"❌ [PDF] Error al descargar PDF: {error_type}: {error_msg}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al descargar el PDF: {error_msg}")

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

# IMPORTANTE: Las rutas específicas (/export, /stats) deben ir ANTES de las rutas con parámetros dinámicos (/{analysis_id})
# para que FastAPI pueda hacer match correctamente

@router.get("/stats")
async def get_reports_stats():
    """
    Obtiene estadísticas agregadas de todos los reportes.
    """
    logger.info(f"📤 [STATS] Solicitud de estadísticas recibida")
    base_dir = service.base_dir
    reports = []
    
    try:
        if not base_dir.exists():
            return {
                "total_reports": 0,
                "verdict_distribution": {},
                "top_vendors": [],
                "last_capture": None,
                "success_rate": 0.0
            }
        
        # Recopilar todos los reportes (similar a list_reports)
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
                            devices = data.get("devices", [])
                            if not devices or len(devices) == 0:
                                continue
                            
                            device = devices[0]
                            reports.append({
                                "id": data.get("analysis_id"),
                                "filename": data.get("filename"),
                                "timestamp": data.get("analysis_timestamp"),
                                "vendor": device.get("vendor", "Unknown"),
                                "model": device.get("device_model", "Unknown"),
                                "verdict": data.get("verdict")
                            })
                    except Exception as e:
                        logger.error(f"Error al leer archivo {analysis_file}: {str(e)}")
        
        if not reports:
            return {
                "total_reports": 0,
                "verdict_distribution": {},
                "top_vendors": [],
                "last_capture": None,
                "success_rate": 0.0
            }
        
        # Calcular estadísticas
        total = len(reports)
        verdict_counter = Counter([r.get("verdict", "UNKNOWN") for r in reports])
        vendor_counter = Counter([r.get("vendor", "Unknown") for r in reports])
        
        # Distribución de veredictos
        verdict_distribution = dict(verdict_counter)
        
        # Top 3 marcas
        top_vendors = [{"vendor": vendor, "count": count} for vendor, count in vendor_counter.most_common(3)]
        
        # Última captura
        sorted_reports = sorted(reports, key=lambda x: x.get("timestamp", ""), reverse=True)
        last_capture = sorted_reports[0].get("timestamp") if sorted_reports else None
        
        # Tasa de éxito (SUCCESS, EXCELLENT, GOOD)
        success_verdicts = ["SUCCESS", "EXCELLENT", "GOOD"]
        success_count = sum(1 for r in reports if r.get("verdict", "").upper() in success_verdicts)
        success_rate = (success_count / total * 100) if total > 0 else 0.0
        
        return {
            "total_reports": total,
            "verdict_distribution": verdict_distribution,
            "top_vendors": top_vendors,
            "last_capture": last_capture,
            "success_rate": round(success_rate, 2)
        }
    except Exception as e:
        logger.error(f"❌ [STATS] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al calcular estadísticas: {str(e)}")

async def generate_ai_report(reports: List[Dict[str, Any]]) -> str:
    """
    Genera un reporte profesional en HTML usando IA basado en los reportes proporcionados.
    
    Esta función utiliza el LLMClient del proyecto para generar un reporte consolidado
    que incluye análisis agregado, estadísticas y conclusiones sobre múltiples reportes
    de análisis de Band Steering.
    
    Args:
        reports: Lista de diccionarios con los datos de los reportes. Cada diccionario
                 debe contener: id, filename, timestamp, vendor, model, verdict, 
                 analysis_text, total_packets.
        
    Returns:
        HTML completo con el reporte generado por IA, listo para descargar.
        
    Raises:
        HTTPException: Si ocurre un error al generar el reporte con IA.
    """
    logger.info(f"🤖 [AI REPORT] Generando reporte con IA para {len(reports)} reporte(s)")
    
    if not reports:
        raise HTTPException(status_code=400, detail="No se proporcionaron reportes para generar el resumen")
    
    # Construir el prompt con todos los datos de los reportes
    reports_data = []
    for i, report in enumerate(reports, 1):
        reports_data.append(f"""
REPORTE {i}:
- ID: {report.get('id', 'N/A')}
- Archivo: {report.get('filename', 'N/A')}
- Fecha: {report.get('timestamp', 'N/A')}
- Marca: {report.get('vendor', 'Unknown')}
- Modelo: {report.get('model', 'Unknown')}
- Veredicto: {report.get('verdict', 'UNKNOWN')}
- Total Paquetes: {report.get('total_packets', 0)}
- Análisis: {report.get('analysis_text', 'No disponible')}
""")
    
    reports_text = "\n".join(reports_data)
    
    # Calcular estadísticas agregadas
    total_reports = len(reports)
    verdicts = [r.get('verdict', 'UNKNOWN') for r in reports]
    success_count = sum(1 for v in verdicts if v in ['SUCCESS', 'EXCELLENT', 'GOOD'])
    failed_count = sum(1 for v in verdicts if v == 'FAILED')
    success_rate = (success_count / total_reports * 100) if total_reports > 0 else 0
    
    vendors = [r.get('vendor', 'Unknown') for r in reports]
    vendor_counts = {v: vendors.count(v) for v in set(vendors)}
    top_vendor = max(vendor_counts.items(), key=lambda x: x[1])[0] if vendor_counts else "N/A"
    
    total_packets = sum(r.get('total_packets', 0) for r in reports)
    
    # Obtener fecha y hora actual en zona horaria de Colombia
    colombia_tz = pytz.timezone('America/Bogota')
    current_time_colombia = datetime.now(colombia_tz)
    formatted_date_time = current_time_colombia.strftime('%d/%m/%Y a las %I:%M %p')
    
    # Construir prompt siguiendo el estilo del proyecto
    # Nota: El LLMClient ya incluye un system message sobre Pipe y análisis de Band Steering
    prompt = f"""Genera un reporte profesional consolidado en HTML completo sobre los siguientes análisis de Band Steering.

FECHA Y HORA DE GENERACIÓN DEL REPORTE:
Este reporte fue generado el {formatted_date_time} (hora de Colombia, UTC-5).

DATOS DE LOS REPORTES:

{reports_text}

ESTADÍSTICAS AGREGADAS:
- Total de reportes analizados: {total_reports}
- Reportes exitosos: {success_count} ({success_rate:.1f}%)
- Reportes fallidos: {failed_count}
- Marca más común: {top_vendor}
- Total de paquetes analizados: {total_packets:,}

INSTRUCCIONES PARA EL REPORTE HTML:

El reporte debe incluir las siguientes secciones en este orden:

1. **TABLA DE RESULTADOS**: 
   Una tabla HTML profesional que muestre para cada dispositivo:
   - Marca y Modelo
   - Veredicto (con colores semánticos: verde para SUCCESS/EXCELLENT/GOOD, rojo para FAILED)
   - Total de paquetes analizados
   - Fecha de análisis
   - Resumen breve de lo que pasó y lo que falló (extraído del analysis_text)

2. **ESTADÍSTICAS OBSERVADAS**: 
   - Distribución de veredictos (tabla o visualización con colores)
   - Análisis por marca (distribución de dispositivos por fabricante)
   - Métricas agregadas de paquetes (total, promedio, rango)
   - Tendencias temporales si hay múltiples fechas

3. **RESUMEN EJECUTIVO**: 
   - Vista general consolidada de todos los reportes
   - Hallazgos principales y patrones detectados
   - Estado general del sistema de Band Steering
   - Indicadores clave de rendimiento

4. **DESCRIPCIÓN DETALLADA**: 
   - Análisis individual de cada reporte (resumir el analysis_text de cada uno)
   - Comparaciones entre dispositivos y marcas
   - Patrones y anomalías detectadas en el conjunto
   - Detalles técnicos relevantes extraídos de los análisis

5. **CONCLUSIÓN**: 
   - Recomendaciones específicas basadas en los hallazgos
   - Hallazgos clave que requieren atención
   - Próximos pasos sugeridos
   - Evaluación general del rendimiento del sistema

FORMATO Y ESTILO REQUERIDO:

- HTML completo y válido (incluir <!DOCTYPE html>, <html>, <head>, <body>)
- CSS embebido en <style> dentro del <head>
- Estilos profesionales: colores corporativos, tipografía legible, espaciado adecuado
- Diseño responsive básico (que se vea bien en diferentes tamaños de pantalla)
- Tablas bien formateadas con bordes y colores alternados para filas
- Secciones claramente separadas con títulos jerárquicos (h1, h2, h3)
- Uso de colores semánticos:
  * Verde (#10b981 o similar) para éxito/positivo
  * Rojo (#ef4444 o similar) para fallos/negativo
  * Azul (#3b82f6 o similar) para información/neutral
- Incluir la fecha y hora de generación del reporte en el encabezado o pie de página con el formato: "Generado el {formatted_date_time} (hora de Colombia, UTC-5)"

IMPORTANTE: 
- El HTML debe ser autocontenido (todo en un solo archivo, sin dependencias externas)
- Usa estilos modernos y profesionales (gradientes sutiles, sombras suaves, bordes redondeados)
- Asegúrate de que el reporte sea claro, fácil de leer y visualmente atractivo
- No uses JavaScript, solo HTML y CSS puro
- Mantén la fidelidad a los datos: no inventes información que no esté en los reportes proporcionados
"""
    
    try:
        # Calcular max_tokens según la cantidad de reportes
        # Más reportes = más contenido a analizar y más tokens necesarios para el HTML
        base_tokens = 4000
        additional_tokens = len(reports) * 500
        max_tokens = min(base_tokens + additional_tokens, 8000)
        
        logger.info(f"🤖 [AI REPORT] Llamando a LLM con max_tokens={max_tokens} para {len(reports)} reporte(s)")
        html_content = await llm_client.agenerate(prompt, max_tokens=max_tokens)
        
        if not html_content or len(html_content.strip()) == 0:
            logger.warning("⚠️ [AI REPORT] El LLM retornó contenido vacío")
            raise HTTPException(
                status_code=500,
                detail="El reporte generado por IA está vacío. Por favor, intenta de nuevo."
            )
        
        logger.info(f"✅ [AI REPORT] Reporte generado exitosamente ({len(html_content)} caracteres)")
        return html_content
        
    except HTTPException:
        # Re-lanzar HTTPException sin modificar
        raise
    except RuntimeError as e:
        # El LLMClient lanza RuntimeError cuando hay problemas con la API
        logger.error(f"❌ [AI REPORT] Error de runtime al generar reporte con IA: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al comunicarse con el servicio de IA: {str(e)}"
        )
    except Exception as e:
        # Capturar cualquier otro error inesperado
        logger.error(f"❌ [AI REPORT] Error inesperado al generar reporte con IA: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error inesperado al generar reporte con IA: {str(e)}"
        )

@router.get("/export")
async def export_reports(
    ids: Optional[str] = Query(None, description="IDs de reportes separados por comas"),
    format: str = Query("html", description="Formato de exportación: html o summary (ambos generan reporte con IA)")
):
    """
    Exporta reportes en formato HTML generado con IA.
    """
    logger.info(f"📤 [EXPORT] Solicitud de exportación recibida: format={format}, ids={ids}")
    base_dir = service.base_dir
    reports_to_export = []
    
    try:
        if not base_dir.exists():
            logger.warning(f"⚠️ [EXPORT] Directorio base no existe: {base_dir}")
            raise HTTPException(status_code=404, detail="No se encontraron reportes")
        
        # Si se proporcionan IDs, exportar solo esos
        target_ids = None
        if ids and ids.strip():
            # Limpiar y dividir IDs
            id_list = [id.strip() for id in ids.split(",") if id.strip()]
            if id_list:
                target_ids = set(id_list)
                logger.info(f"📋 [EXPORT] Exportando {len(target_ids)} reportes específicos")
            else:
                logger.info(f"📋 [EXPORT] IDs proporcionados pero vacíos, exportando todos")
        else:
            logger.info(f"📋 [EXPORT] No se proporcionaron IDs, exportando todos los reportes")
        
        # Recopilar reportes
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
                            analysis_id = data.get("analysis_id")
                            
                            # Filtrar por IDs si se especificaron
                            if target_ids and analysis_id not in target_ids:
                                continue
                            
                            devices = data.get("devices", [])
                            if not devices or len(devices) == 0:
                                continue
                            
                            device = devices[0]
                            reports_to_export.append({
                                "id": analysis_id,
                                "filename": data.get("filename"),
                                "timestamp": data.get("analysis_timestamp"),
                                "vendor": device.get("vendor", "Unknown"),
                                "model": device.get("device_model", "Unknown"),
                                "verdict": data.get("verdict"),
                                "analysis_text": data.get("analysis_text", ""),
                                "total_packets": data.get("total_packets", 0)
                            })
                    except Exception as e:
                        logger.error(f"Error al leer archivo {analysis_file}: {str(e)}")
        
        if not reports_to_export:
            logger.warning(f"⚠️ [EXPORT] No se encontraron reportes para exportar (target_ids={target_ids})")
            raise HTTPException(status_code=404, detail="No se encontraron reportes para exportar")
        
        logger.info(f"✅ [EXPORT] Se encontraron {len(reports_to_export)} reportes para exportar en formato {format}")
        
        # Generar reporte con IA (format=html o format=summary)
        if format.lower() in ["html", "summary"]:
            html_content = await generate_ai_report(reports_to_export)
            html_bytes = html_content.encode('utf-8')
            
            filename = f"reports_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            return Response(
                content=html_bytes,
                media_type="text/html; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Type": "text/html; charset=utf-8"
                }
            )
        else:
            # Formato no soportado
            raise HTTPException(
                status_code=400, 
                detail=f"Formato '{format}' no soportado. Use 'html' o 'summary'."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [EXPORT] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al exportar reportes: {str(e)}")

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

@router.delete("/all")
async def delete_all_reports():
    """
    Elimina todos los reportes del sistema.
    """
    base_dir = service.base_dir
    deleted_count = 0
    
    try:
        if not base_dir.exists():
            return {"status": "success", "message": "No hay reportes para eliminar", "deleted": 0}
        
        # Buscar todos los archivos JSON de análisis
        for analysis_file in base_dir.glob("**/*.json"):
            try:
                analysis_file.unlink()
                deleted_count += 1
            except Exception as e:
                logger.error(f"Error al eliminar {analysis_file}: {str(e)}")
        
        # Limpiar directorios vacíos
        for vendor_dir in base_dir.iterdir():
            if vendor_dir.is_dir():
                for device_dir in vendor_dir.iterdir():
                    if device_dir.is_dir() and not any(device_dir.iterdir()):
                        device_dir.rmdir()
                if not any(vendor_dir.iterdir()):
                    vendor_dir.rmdir()
        
        logger.info(f"✅ [DELETE ALL] Eliminados {deleted_count} reportes")
        return {"status": "success", "message": f"Se eliminaron {deleted_count} reportes", "deleted": deleted_count}
    except Exception as e:
        logger.error(f"❌ [DELETE ALL] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al eliminar todos los reportes: {str(e)}")

@router.delete("/vendor/{vendor}")
async def delete_reports_by_vendor(vendor: str):
    """
    Elimina todos los reportes de una marca específica.
    """
    base_dir = service.base_dir
    deleted_count = 0
    
    try:
        if not base_dir.exists():
            raise HTTPException(status_code=404, detail="No se encontraron reportes")
        
        vendor_dir = base_dir / vendor
        if not vendor_dir.exists() or not vendor_dir.is_dir():
            return {"status": "success", "message": f"No se encontraron reportes para la marca {vendor}", "deleted": 0}
        
        # Buscar todos los archivos JSON en el directorio de la marca
        for analysis_file in vendor_dir.glob("**/*.json"):
            try:
                analysis_file.unlink()
                deleted_count += 1
            except Exception as e:
                logger.error(f"Error al eliminar {analysis_file}: {str(e)}")
        
        # Limpiar directorios vacíos
        for device_dir in vendor_dir.iterdir():
            if device_dir.is_dir() and not any(device_dir.iterdir()):
                device_dir.rmdir()
        
        if not any(vendor_dir.iterdir()):
            vendor_dir.rmdir()
        
        logger.info(f"✅ [DELETE VENDOR] Eliminados {deleted_count} reportes de {vendor}")
        return {"status": "success", "message": f"Se eliminaron {deleted_count} reportes de {vendor}", "deleted": deleted_count}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"❌ [DELETE VENDOR] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al eliminar reportes de {vendor}: {str(e)}")

@router.delete("/batch")
async def delete_batch_reports(request: Dict[str, List[str]]):
    """
    Elimina múltiples reportes por sus IDs.
    Body: {"ids": ["id1", "id2", "id3"]}
    """
    base_dir = service.base_dir
    ids = request.get("ids", [])
    
    if not ids:
        raise HTTPException(status_code=400, detail="Se requiere al menos un ID en el array 'ids'")
    
    deleted_count = 0
    not_found = []
    
    try:
        if not base_dir.exists():
            raise HTTPException(status_code=404, detail="No se encontraron reportes")
        
        for analysis_id in ids:
            found = False
            for analysis_file in base_dir.glob(f"**/{analysis_id}.json"):
                try:
                    analysis_file.unlink()
                    deleted_count += 1
                    found = True
                    break
                except Exception as e:
                    logger.error(f"Error al eliminar {analysis_file}: {str(e)}")
            
            if not found:
                not_found.append(analysis_id)
        
        # Limpiar directorios vacíos
        for vendor_dir in base_dir.iterdir():
            if vendor_dir.is_dir():
                for device_dir in vendor_dir.iterdir():
                    if device_dir.is_dir() and not any(device_dir.iterdir()):
                        device_dir.rmdir()
                if not any(vendor_dir.iterdir()):
                    vendor_dir.rmdir()
        
        message = f"Se eliminaron {deleted_count} reportes"
        if not_found:
            message += f". No se encontraron {len(not_found)} reportes: {', '.join(not_found)}"
        
        logger.info(f"✅ [DELETE BATCH] Eliminados {deleted_count} de {len(ids)} reportes")
        return {
            "status": "success",
            "message": message,
            "deleted": deleted_count,
            "not_found": not_found
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"❌ [DELETE BATCH] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al eliminar reportes: {str(e)}")

# Esta función ya está definida arriba (línea 400), eliminando duplicado
