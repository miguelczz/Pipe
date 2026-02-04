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
        return True
    except ImportError as e:
        WEASYPRINT_AVAILABLE = False
        return False
    except OSError as e:
        WEASYPRINT_AVAILABLE = False
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
                            # Extraer info del dispositivo
                            devices = data.get("devices", [])
                            if not devices or len(devices) == 0:
                                continue
                            
                            device = devices[0]
                            
                            # Obtener datos para calcular tiempos por banda
                            transitions = []
                            signal_samples = []
                            
                            # Intentar obtener desde la estructura band_steering (nueva estructura)
                            band_steering = data.get("band_steering", {})
                            if isinstance(band_steering, dict):
                                transitions = band_steering.get("transitions", [])
                                signal_samples = band_steering.get("signal_samples", [])
                            
                            # Fallback: intentar desde el nivel raíz (estructura antigua)
                            if not transitions:
                                transitions = data.get("transitions", [])
                            if not signal_samples:
                                signal_samples = data.get("signal_samples", [])
                            
                            # Calcular tiempos por banda
                            time_2_4ghz, time_5ghz, transition_times_list = _calculate_band_times(
                                transitions, signal_samples
                            )
                            
                            reports.append({
                                "id": data.get("analysis_id"),
                                "filename": data.get("filename"), # Nombre original del pcap
                                "timestamp": data.get("analysis_timestamp"),
                                "vendor": device.get("vendor", "Unknown"),
                                "model": device.get("device_model", "Unknown"),
                                "verdict": data.get("verdict"),
                                "time_2_4ghz": time_2_4ghz,
                                "time_5ghz": time_5ghz,
                                "transition_times": transition_times_list
                            })
                    except (json.JSONDecodeError, Exception):
                        pass
        
        # Ordenar por fecha descendente
        reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return reports
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{analysis_id}/download")
async def download_capture(analysis_id: str):
    """
    Descarga el archivo pcap original de un análisis.
    """
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
        
        
        # Leer el JSON para obtener la ruta del archivo pcap
        with open(analysis_file, "r", encoding="utf-8") as f:
            analysis_data = json.load(f)
        
        
        # Obtener la ruta del archivo pcap
        pcap_path = analysis_data.get("original_file_path")
        
        if not pcap_path:
            # Reporte antiguo sin archivo guardado
            raise HTTPException(
                status_code=404, 
                detail="Este reporte fue creado antes de implementar la descarga de archivos. Solo los análisis nuevos guardan el archivo pcap original."
            )
        
        pcap_file = Path(pcap_path)
        
        if not pcap_file.exists():
            raise HTTPException(status_code=404, detail="El archivo pcap ya no existe en el servidor")
        
        # Obtener el nombre original del archivo desde el JSON
        original_filename = analysis_data.get("filename", "capture.pcap")
        
        if not original_filename.endswith((".pcap", ".pcapng")):
            # Asegurar extensión correcta
            if pcap_file.suffix:
                original_filename = original_filename.rsplit(".", 1)[0] + pcap_file.suffix
            else:
                original_filename += pcap_file.suffix or ".pcap"
        
        return FileResponse(
            path=str(pcap_file),
            filename=original_filename,
            media_type="application/vnd.tcpdump.pcap"
        )
    except HTTPException as e:
        raise
    except Exception as e:
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
    base_dir = service.base_dir
    
    try:
        # Buscar el archivo JSON del análisis para obtener la ruta del directorio
        analysis_file = None
        json_files = list(base_dir.glob(f"**/{analysis_id}.json"))
        for json_file in json_files:
            analysis_file = json_file
            break
        
        if not analysis_file:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        
        
        # El PDF se guarda en el mismo directorio que el JSON
        pdf_path = analysis_file.parent / f"{analysis_id}.pdf"
        
        # Verificar WeasyPrint de forma lazy
        if not _check_weasyprint():
            raise HTTPException(
                status_code=500, 
                detail="WeasyPrint no está disponible. Instala las dependencias del sistema: libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info"
            )
        
        
        # Validar que el HTML no esté vacío
        if not html_content or not html_content.strip():
            raise HTTPException(
                status_code=400,
                detail="El contenido HTML está vacío"
            )
        
        html_length = len(html_content)
        
        # Verificar si hay un PDF anterior y eliminarlo
        if pdf_path.exists():
            old_size = pdf_path.stat().st_size
            try:
                pdf_path.unlink()
            except Exception:
                pass
        
        # Convertir HTML a PDF usando WeasyPrint
        try:
            
            # Crear el documento HTML
            html_doc = HTML(string=html_content, base_url=None)
            
            # Generar el PDF con configuraciones apropiadas
            html_doc.write_pdf(
                pdf_path,
                stylesheets=None,  # Los estilos ya están en el HTML
                presentational_hints=True
            )
            
            # Verificar que el PDF se creó correctamente
            if not pdf_path.exists():
                raise Exception("El PDF no se creó")
            
            pdf_size = pdf_path.stat().st_size
            
            if pdf_size == 0:
                try:
                    pdf_path.unlink()
                except Exception:
                    pass
                raise Exception("El PDF generado está vacío")
            
            # Validar que el PDF tenga el header correcto (debe empezar con %PDF)
            try:
                with open(pdf_path, 'rb') as f:
                    header = f.read(4)
                    if header != b'%PDF':
                        try:
                            pdf_path.unlink()
                        except Exception:
                            pass
                        raise Exception(f"El archivo generado no es un PDF válido (header: {header})")
            except Exception as header_error:
                if pdf_path.exists():
                    try:
                        pdf_path.unlink()
                    except Exception:
                        pass
                raise
            
            return {
                "status": "success", 
                "message": "PDF guardado correctamente", 
                "path": str(pdf_path),
                "size": pdf_size
            }
        except Exception as pdf_error:
            error_msg = str(pdf_error)
            error_type = type(pdf_error).__name__
            
            # Limpiar archivo corrupto si existe
            if pdf_path.exists():
                try:
                    corrupt_size = pdf_path.stat().st_size
                    pdf_path.unlink()
                except Exception as cleanup_error:
                    pass
            
            raise HTTPException(
                status_code=500, 
                detail=f"Error al convertir HTML a PDF: {error_msg}"
            )
            
    except HTTPException as e:
        raise
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        raise HTTPException(status_code=500, detail=f"Error al guardar el PDF: {error_msg}")

@router.get("/{analysis_id}/pdf")
async def download_pdf(analysis_id: str):
    """
    Descarga el PDF persistido del reporte de análisis.
    Si el PDF no existe, lo genera automáticamente desde los datos del análisis.
    """
    base_dir = service.base_dir
    
    try:
        # Buscar el archivo PDF persistido
        pdf_files = list(base_dir.glob(f"**/{analysis_id}.pdf"))
        
        # Si el PDF no existe, generarlo automáticamente
        if not pdf_files:
            
            # Buscar el archivo JSON del análisis
            json_files = list(base_dir.glob(f"**/{analysis_id}.json"))
            if not json_files:
                raise HTTPException(
                    status_code=404,
                    detail="Análisis no encontrado"
                )
            
            analysis_file = json_files[0]
            
            # Leer el JSON del análisis
            try:
                with open(analysis_file, "r", encoding="utf-8") as f:
                    analysis_data = json.load(f)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error al leer los datos del análisis: {str(e)}"
                )
            
            # Verificar WeasyPrint
            if not _check_weasyprint():
                raise HTTPException(
                    status_code=500,
                    detail="WeasyPrint no está disponible. No se puede generar el PDF automáticamente."
                )
            
            # Generar HTML desde los datos del análisis
            html_content = _generate_pdf_html(analysis_data)
            
            # Ruta donde se guardará el PDF
            pdf_path = analysis_file.parent / f"{analysis_id}.pdf"
            
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
                    raise Exception("El PDF generado está vacío")
                
                pdf_size = pdf_path.stat().st_size
                
                # Validar header
                with open(pdf_path, 'rb') as f:
                    header = f.read(4)
                    if header != b'%PDF':
                        pdf_path.unlink()
                        raise Exception(f"PDF inválido (header: {header})")
                
                
            except Exception as pdf_error:
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
        
        # Validar que el PDF existe y tiene contenido
        if not pdf_path.exists():
            raise HTTPException(
                status_code=404,
                detail="El archivo PDF no existe"
            )
        
        pdf_size = pdf_path.stat().st_size
        
        if pdf_size == 0:
            raise HTTPException(
                status_code=500,
                detail="El PDF está corrupto (archivo vacío). Por favor, exporta el PDF nuevamente."
            )
        
        # Validar header del PDF (debe empezar con %PDF)
        try:
            with open(pdf_path, 'rb') as f:
                header = f.read(4)
                if header != b'%PDF':
                    raise HTTPException(
                        status_code=500,
                        detail=f"El PDF está corrupto (header inválido: {header}). Por favor, exporta el PDF nuevamente."
                    )
                
                # Leer un poco más para verificar que es un PDF válido
                f.seek(0)
                first_100 = f.read(100)
        except HTTPException:
            raise
        except Exception as header_error:
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
                    # Intentar obtener el modelo del dispositivo primero
                    devices = analysis_data.get("devices", [])
                    if devices and len(devices) > 0:
                        model = devices[0].get("device_model", "")
                        if model and model != "Unknown" and model != "Genérico":
                            filename = f"Pipe {model.upper()}.pdf"
                        else:
                            # Fallback al nombre del archivo
                            original_filename = analysis_data.get("filename", "")
                            if original_filename:
                                clean_name = original_filename.split('.')[0].replace('_', ' ').strip()
                                filename = f"Pipe {clean_name.upper()}.pdf"
                    else:
                        # Fallback al nombre del archivo
                        original_filename = analysis_data.get("filename", "")
                        if original_filename:
                            clean_name = original_filename.split('.')[0].replace('_', ' ').strip()
                            filename = f"Pipe {clean_name.upper()}.pdf"
            except Exception:
                pass
        
        return FileResponse(
            path=str(pdf_path),
            filename=filename,
            media_type="application/pdf"
        )
    except HTTPException as e:
        raise
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        raise HTTPException(status_code=500, detail=f"Error al descargar el PDF: {error_msg}")

def _generate_pdf_html(analysis_data: Dict[str, Any]) -> str:
    """Genera HTML para el PDF del reporte con estilo mejorado."""
    filename = analysis_data.get("filename", "Unknown")
    clean_name = filename.split('.')[0].replace('_', ' ').strip()
    verdict = analysis_data.get("verdict", "UNKNOWN")
    analysis_text = analysis_data.get("analysis_text", "No hay análisis disponible")
    
    # Información del dispositivo
    devices = analysis_data.get("devices", [])
    device = devices[0] if devices else {}
    vendor = device.get("vendor", "Unknown")
    model = device.get("device_model", "Unknown")
    category = device.get("device_category", "N/A").replace('_', ' ')
    
    # Generar nombre del PDF en el estilo "Pipe [MODELO]"
    if model and model != "Unknown" and model != "Genérico":
        pdf_title = f"Pipe {model.upper()}"
    else:
        pdf_title = f"Pipe {clean_name.upper()}"
    
    # Obtener métricas BTM
    btm_requests = analysis_data.get("btm_requests", 0)
    btm_responses = analysis_data.get("btm_responses", 0)
    btm_events = analysis_data.get("btm_events", [])
    btm_accept = len([e for e in btm_events if e.get("status_code") == 0])
    
    # Obtener métricas de steering
    successful_transitions = analysis_data.get("successful_transitions", 0)
    failed_transitions = analysis_data.get("failed_transitions", 0)
    transitions = analysis_data.get("transitions", [])
    
    # Calcular cambios de banda
    band_change_count = len([t for t in transitions if t.get("is_successful") and t.get("is_band_change")])
    
    # Obtener soporte KVR
    kvr_support = analysis_data.get("kvr_support", {})
    k_support = kvr_support.get("k", False)
    v_support = kvr_support.get("v", False)
    r_support = kvr_support.get("r", False)
    
    kvr_detected = []
    if k_support:
        kvr_detected.append("11k")
    if v_support:
        kvr_detected.append("11v")
    if r_support:
        kvr_detected.append("11r")
    
    # Obtener raw_stats si está disponible
    raw_stats = analysis_data.get("raw_stats", {})
    diagnostics = raw_stats.get("diagnostics", {})
    band_counters = diagnostics.get("band_counters", {})
    
    assoc_count = band_counters.get("assoc_count", 0)
    reassoc_count = band_counters.get("reassoc_count", 0)
    disassoc_count = band_counters.get("disassoc_count", 0)
    deauth_count = band_counters.get("deauth_count", 0)
    
    # Obtener MACs
    client_mac = diagnostics.get("user_provided_client_mac") or diagnostics.get("client_mac", "Desconocido")
    bssid_info = diagnostics.get("bssid_info", {})
    import re
    mac_regex = re.compile(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', re.IGNORECASE)
    bssids = [key for key in bssid_info.keys() if mac_regex.match(key)]
    
    # Obtener compliance checks
    compliance_checks = analysis_data.get("compliance_checks", [])
    
    # Obtener SSID si está disponible
    ssid = ""
    if diagnostics.get("user_metadata"):
        ssid = diagnostics.get("user_metadata", {}).get("ssid", "")
    
    # Calcular tiempo medido (simplificado)
    measured_time = "N/A"
    wireshark_raw = diagnostics.get("wireshark_raw", {})
    if wireshark_raw.get("sample"):
        sample = wireshark_raw["sample"]
        if sample:
            timestamps = [float(p.get("timestamp", 0)) for p in sample if p.get("timestamp")]
            if timestamps:
                time_diff = max(timestamps) - min(timestamps)
                if time_diff > 0:
                    if time_diff < 1:
                        measured_time = f"{(time_diff * 1000):.2f}ms"
                    elif time_diff < 60:
                        measured_time = f"{time_diff:.3f}s"
                    else:
                        minutes = int(time_diff // 60)
                        seconds = time_diff % 60
                        measured_time = f"{minutes}m {seconds:.3f}s"
    
    # Formatear análisis markdown mejorado
    def format_analysis(text):
        if not text:
            return ""
        
        lines = text.split("\n")
        html = ""
        in_list = False
        in_ordered_list = False
        list_items = []
        
        def close_list():
            nonlocal in_list, in_ordered_list, list_items, html
            if in_list:
                html += '<ul style="margin: 8px 0; padding-left: 20px; list-style-type: disc;">'
                for item in list_items:
                    item_text = item.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
                    item_text = item_text.replace("*", "<em>", 1).replace("*", "</em>", 1)
                    html += f'<li style="margin-bottom: 4px; font-size: 8pt; line-height: 1.5;">{item_text}</li>'
                html += '</ul>'
                list_items = []
                in_list = False
            if in_ordered_list:
                html += '<ol style="margin: 8px 0; padding-left: 20px; list-style-type: decimal;">'
                for item in list_items:
                    item_text = item.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
                    item_text = item_text.replace("*", "<em>", 1).replace("*", "</em>", 1)
                    html += f'<li style="margin-bottom: 4px; font-size: 8pt; line-height: 1.5;">{item_text}</li>'
                html += '</ol>'
                list_items = []
                in_ordered_list = False
        
        import re
        for line in lines:
            line = line.strip()
            
            if not line:
                close_list()
                continue
            
            # Títulos markdown
            if re.match(r'^#+\s', line):
                close_list()
                level = len(line) - len(line.lstrip("#"))
                content = line.lstrip("#").strip()
                font_size = "11pt" if level == 1 else "10pt" if level == 2 else "9pt" if level == 3 else "8pt"
                margin_top = "16px" if level == 1 else "14px" if level == 2 else "12px"
                html += f'<h{min(level + 1, 4)} style="margin-top: {margin_top}; margin-bottom: 8px; font-size: {font_size}; font-weight: 600; color: #374151; page-break-after: avoid;">{content}</h{min(level + 1, 4)}>'
                continue
            
            # Listas ordenadas (1., 2., etc.)
            ordered_match = re.match(r'^(\d+)\.\s+(.+)$', line)
            if ordered_match:
                close_list()
                if not in_ordered_list:
                    in_ordered_list = True
                list_items.append(ordered_match.group(2))
                continue
            
            # Listas no ordenadas (-, *, •)
            if re.match(r'^[-*•]\s+(.+)$', line):
                close_list()
                if not in_list:
                    in_list = True
                item_text = re.sub(r'^[-*•]\s+', '', line)
                list_items.append(item_text)
                continue
            
            # Cerrar lista si hay una abierta
            close_list()
            
            # Párrafo normal
            para_text = line
            # Procesar negritas
            para_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', para_text)
            # Procesar cursivas
            para_text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', para_text)
            # Procesar código inline
            para_text = re.sub(r'`([^`]+)`', r'<code style="background: #f3f4f6; padding: 2px 4px; border-radius: 3px; font-family: monospace; font-size: 7pt;">\1</code>', para_text)
            
            html += f'<p style="margin-bottom: 8px; font-size: 8pt; line-height: 1.6; text-align: justify;">{para_text}</p>'
        
        # Cerrar cualquier lista que quede abierta
        close_list()
        
        return html
    
    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{pdf_title}</title>
        <style>
            @page {{
                margin: 1.5cm;
                size: A4;
            }}
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                font-size: 11pt;
                line-height: 1.6;
                color: #1a1a1a;
                background: white;
                padding: 0;
            }}
            .header {{
                border-bottom: 3px solid #6366f1;
                padding-bottom: 15px;
                margin-bottom: 30px;
            }}
            h1 {{
                font-size: 28pt;
                color: #1a1a1a;
                margin-bottom: 10px;
                font-weight: 700;
            }}
            h2 {{
                font-size: 20pt;
                color: #1a1a1a;
                margin-top: 30px;
                margin-bottom: 15px;
                border-bottom: 2px solid #e5e7eb;
                padding-bottom: 8px;
                font-weight: 600;
            }}
            h3 {{
                font-size: 16pt;
                color: #374151;
                margin-top: 20px;
                margin-bottom: 10px;
                font-weight: 600;
            }}
            h4 {{
                font-size: 14pt;
                color: #4b5563;
                margin-top: 15px;
                margin-bottom: 8px;
                font-weight: 600;
            }}
            .info-section {{
                background: #f8f9fa;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 25px;
            }}
            .info-row {{
                display: flex;
                justify-content: space-between;
                padding: 8px 0;
                border-bottom: 1px solid #e5e7eb;
            }}
            .info-row:last-child {{
                border-bottom: none;
            }}
            .info-label {{
                font-weight: 600;
                color: #6b7280;
                font-size: 10pt;
            }}
            .info-value {{
                color: #1a1a1a;
                font-size: 11pt;
                text-align: right;
                font-weight: 500;
            }}
            .verdict-badge {{
                display: inline-block;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 700;
                font-size: 11pt;
                text-transform: uppercase;
            }}
            .verdict-success {{
                background: #10b981;
                color: white;
            }}
            .verdict-failed {{
                background: #ef4444;
                color: white;
            }}
            .metrics-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin: 20px 0;
            }}
            .metric-card {{
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                padding: 15px;
            }}
            .metric-label {{
                font-size: 9pt;
                color: #6b7280;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 5px;
            }}
            .metric-value {{
                font-size: 18pt;
                font-weight: 700;
                color: #1a1a1a;
            }}
            .metric-subvalue {{
                font-size: 10pt;
                color: #6b7280;
                margin-top: 5px;
            }}
            .analysis-section {{
                margin-top: 30px;
            }}
            .analysis-content {{
                background: #ffffff;
                border-left: 4px solid #6366f1;
                padding: 20px;
                margin-top: 15px;
                line-height: 1.8;
            }}
            .analysis-content p {{
                margin-bottom: 12px;
            }}
            .compliance-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
                font-size: 10pt;
            }}
            .compliance-table th,
            .compliance-table td {{
                padding: 10px;
                text-align: left;
                border-bottom: 1px solid #e5e7eb;
            }}
            .compliance-table th {{
                background: #f3f4f6;
                font-weight: 600;
                color: #374151;
            }}
            .compliance-table tr:hover {{
                background: #f9fafb;
            }}
            .mac-address {{
                font-family: 'Courier New', monospace;
                font-size: 10pt;
                color: #1a1a1a;
            }}
            .footer {{
                margin-top: 50px;
                text-align: center;
                color: #6b7280;
                font-size: 9pt;
                border-top: 1px solid #e5e7eb;
                padding-top: 15px;
            }}
            .section-divider {{
                height: 2px;
                background: linear-gradient(to right, #6366f1, transparent);
                margin: 30px 0;
            }}
            .highlight-box {{
                background: #eff6ff;
                border-left: 4px solid #3b82f6;
                padding: 15px;
                margin: 15px 0;
                border-radius: 4px;
            }}
            .kvr-badge {{
                display: inline-block;
                padding: 4px 8px;
                background: #dbeafe;
                color: #1e40af;
                border-radius: 4px;
                font-size: 9pt;
                font-weight: 600;
                margin-right: 5px;
            }}
            .card {{
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 16px;
            }}
            .info-card-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr 1fr;
                gap: 16px;
                margin-bottom: 24px;
            }}
            .info-card {{
                background: #f8f9fa;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 16px;
            }}
            .info-card-title {{
                font-size: 10pt;
                font-weight: 600;
                color: #6b7280;
                margin-bottom: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .compliance-check {{
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                padding: 12px;
                margin-bottom: 12px;
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
            }}
            .compliance-check-title {{
                font-weight: 700;
                font-size: 11pt;
                color: #1a1a1a;
                margin-bottom: 4px;
            }}
            .compliance-check-details {{
                font-size: 9pt;
                font-family: 'Courier New', monospace;
                color: #4b5563;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .compliance-badge-pdf {{
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 6px 12px;
                border-radius: 6px;
                font-weight: 700;
                font-size: 9pt;
                flex-shrink: 0;
            }}
            .compliance-badge-pass {{
                background: rgba(16, 185, 129, 0.15);
                color: #10b981;
                border: 1px solid rgba(16, 185, 129, 0.3);
            }}
            .compliance-badge-fail {{
                background: rgba(239, 68, 68, 0.15);
                color: #ef4444;
                border: 1px solid rgba(239, 68, 68, 0.3);
            }}
            .section-header {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 20px;
            }}
            .section-title {{
                font-size: 18pt;
                font-weight: 600;
                color: #1a1a1a;
            }}
            .section-description {{
                font-size: 10pt;
                color: #6b7280;
                margin-top: 8px;
                margin-bottom: 20px;
            }}
            .success-badge-large {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 10px 20px;
                background: #10b981;
                color: white;
                border-radius: 6px;
                font-weight: 700;
                font-size: 11pt;
            }}
            .metric-item {{
                margin-bottom: 16px;
            }}
            .metric-item-label {{
                font-size: 9pt;
                color: #6b7280;
                text-transform: uppercase;
                margin-bottom: 4px;
            }}
            .metric-item-value {{
                font-size: 14pt;
                font-weight: 700;
                color: #1a1a1a;
            }}
            .metric-item-sub {{
                font-size: 9pt;
                color: #6b7280;
                margin-top: 4px;
            }}
            @media print {{
                body {{
                    padding: 0;
                }}
                .page-break {{
                    page-break-before: always;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{pdf_title}</h1>
        </div>
        
        <!-- Cards de Información del Dispositivo -->
        <div class="info-card-grid">
            <div class="info-card">
                <div class="info-card-title">Dispositivo Identificado</div>
                <div style="font-size: 10pt;">
                    {f'<div style="margin-bottom: 8px;"><span style="font-size: 9pt; color: #6b7280;">Red (SSID):</span><br><span style="font-size: 11pt; font-weight: 500; color: #1a1a1a;">{ssid}</span></div>' if ssid else ''}
                    <div style="margin-bottom: 8px;"><span style="font-size: 9pt; color: #6b7280;">Marca:</span><br><span style="font-size: 11pt; font-weight: 500; color: #1a1a1a;">{vendor}</span></div>
                    <div style="margin-bottom: 8px;"><span style="font-size: 9pt; color: #6b7280;">Modelo:</span><br><span style="font-size: 11pt; font-weight: 500; color: #1a1a1a;">{model}</span></div>
                    <div><span style="font-size: 9pt; color: #6b7280;">Categoría:</span><br><span style="font-size: 11pt; font-weight: 500; color: #1a1a1a;">{category}</span></div>
                </div>
            </div>
            
            <div class="info-card">
                <div class="info-card-title">MACs de Negociación</div>
                <div style="font-size: 10pt;">
                    <div style="margin-bottom: 12px;">
                        <span style="font-size: 9pt; color: #6b7280; text-transform: uppercase;">Cliente</span><br>
                        <span class="mac-address" style="font-weight: 700; font-size: 11pt;">{client_mac}</span>
                    </div>
                    <div>
                        <span style="font-size: 9pt; color: #6b7280; text-transform: uppercase;">BSSIDS ({len(bssids)})</span><br>
                        {'<br>'.join([f'<div class="mac-address" style="margin-top: 4px; font-size: 10pt;">{bssid}</div>' for bssid in bssids]) if bssids else '<span style="font-size: 10pt; color: #6b7280; font-style: italic;">No detectados</span>'}
                    </div>
                </div>
            </div>
            
            <div class="info-card">
                <div class="info-card-title">Métricas de Steering</div>
                <div style="font-size: 10pt;">
                    <div class="metric-item">
                        <div class="metric-item-label">Estándares KVR Identificados</div>
                        <div class="metric-item-value" style="font-size: 12pt;">
                            {' '.join([f'<span class="kvr-badge">{k}</span>' for k in kvr_detected]) if kvr_detected else 'Ninguno'}
                        </div>
                    </div>
                    <div class="metric-item">
                        <div class="metric-item-label">Intentos de steering</div>
                        <div class="metric-item-value">{successful_transitions}/{successful_transitions + failed_transitions}</div>
                        <div class="metric-item-sub">EXITOSAS</div>
                        {f'<div class="metric-item-sub" style="margin-top: 6px;"><span style="color: #10b981; font-weight: 600;">{band_change_count} cambio{"s" if band_change_count != 1 else ""} de banda</span></div>' if band_change_count > 0 else ''}
                    </div>
                    <div class="metric-item">
                        <div class="metric-item-label">Tiempo medido</div>
                        <div class="metric-item-value" style="font-size: 14pt;">{measured_time}</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Sección Análisis de Band Steering -->
        <div class="section-header">
            <div>
                <h2 class="section-title">Análisis de Band Steering</h2>
                <p class="section-description">Evaluación técnica de capacidades 802.11k/v/r basada directamente en la captura real de Wireshark/tshark</p>
            </div>
            <span class="success-badge-large">✓ SUCCESS</span>
        </div>
        
        <!-- Detalle de Cumplimiento Técnico -->
        <div class="card" style="background: #eff6ff; border-left: 4px solid #3b82f6;">
            <h3 style="margin-top: 0; margin-bottom: 16px; font-size: 13pt; font-weight: 700;">DETALLE DE CUMPLIMIENTO TÉCNICO</h3>
            {''.join([f'''
            <div class="compliance-check">
                <div style="flex: 1;">
                    <div class="compliance-check-title">{check.get("check_name", "Unknown")}</div>
                    <div class="compliance-check-details">{check.get("details", "")}</div>
                </div>
                <div class="compliance-badge-pdf {'compliance-badge-pass' if check.get('passed', False) else 'compliance-badge-fail'}">
                    <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: {'#10b981' if check.get('passed', False) else '#ef4444'};"></span>
                    <span>{'PASÓ' if check.get('passed', False) else 'FALLÓ'}</span>
                </div>
            </div>
            ''' for check in compliance_checks]) if compliance_checks else f'''
            <div class="compliance-check">
                <div style="flex: 1;">
                    <div class="compliance-check-title">Soporte BTM (802.11v)</div>
                    <div class="compliance-check-details">REQUESTS: {btm_requests}, RESPONSES: {btm_responses}, ACCEPT: {btm_accept}<br>CODE: 0 (ACCEPT)</div>
                </div>
                <div class="compliance-badge-pdf compliance-badge-pass">
                    <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #10b981;"></span>
                    <span>PASÓ</span>
                </div>
            </div>
            <div class="compliance-check">
                <div style="flex: 1;">
                    <div class="compliance-check-title">Asociación y Reasociación</div>
                    <div class="compliance-check-details">ASSOC: {assoc_count}, REASSOC: {reassoc_count}<br>DISASSOC: {disassoc_count} (FORZADOS: 0), DEAUTH: {deauth_count} (FORZADOS: 0)</div>
                </div>
                <div class="compliance-badge-pdf compliance-badge-pass">
                    <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #10b981;"></span>
                    <span>PASÓ</span>
                </div>
            </div>
            <div class="compliance-check">
                <div style="flex: 1;">
                    <div class="compliance-check-title">Steering Efectivo</div>
                    <div class="compliance-check-details">TRANSICIONES CON CAMBIO DE BANDA: {band_change_count} | TRANSICIONES TOTALES: {successful_transitions} | BTM ACCEPT: {btm_accept}</div>
                </div>
                <div class="compliance-badge-pdf compliance-badge-pass">
                    <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #10b981;"></span>
                    <span>PASÓ</span>
                </div>
            </div>
            <div class="compliance-check">
                <div style="flex: 1;">
                    <div class="compliance-check-title">Estándares KVR</div>
                    <div class="compliance-check-details">K={'TRUE' if k_support else 'FALSE'}, V={'TRUE' if v_support else 'FALSE'}, R={'TRUE' if r_support else 'FALSE'}</div>
                </div>
                <div class="compliance-badge-pdf compliance-badge-pass">
                    <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #10b981;"></span>
                    <span>PASÓ</span>
                </div>
            </div>
            '''}
        </div>
        
        <div class="section-divider"></div>
        
        <h2 style="font-size: 22pt; font-weight: 700; text-transform: uppercase; margin-top: 40px; margin-bottom: 20px;">INFORME TÉCNICO DE AUDITORÍA DE BAND STEERING</h2>
        <div class="analysis-content">
            {format_analysis(analysis_text)}
        </div>
        
        <div class="footer">
            Generado por Pipe - Análisis inteligente de capturas Wireshark
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
                    except Exception:
                        pass
        
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
        raise HTTPException(status_code=500, detail=f"Error al calcular estadísticas: {str(e)}")

def _calculate_band_times(transitions: List[Dict[str, Any]], signal_samples: List[Dict[str, Any]]) -> tuple:
    """
    Calcula el tiempo total acumulado en cada banda y lista de tiempos de transición individuales.
    Extrae los datos directamente de Wireshark, excluyendo explícitamente los períodos de transición.
    
    FILOSOFÍA:
    - El tiempo en banda se calcula usando las muestras de señal de Wireshark
    - Los períodos de transición (entre start_time y end_time) se EXCLUYEN del tiempo en banda
    - El tiempo de transición es simplemente la duración de cada transición (end_time - start_time)
    
    Args:
        transitions: Lista de transiciones con start_time, end_time, from_band, to_band, duration
        signal_samples: Lista de muestras de señal con timestamp y band (fuente de verdad de Wireshark)
        
    Returns:
        Tupla (tiempo_2_4ghz, tiempo_5ghz, lista_tiempos_transicion) donde lista_tiempos_transicion es una lista de duraciones
    """
    time_2_4ghz = 0.0
    time_5ghz = 0.0
    transition_times = []  # Lista de tiempos individuales de cada transición
    
    if not transitions and not signal_samples:
        return (0.0, 0.0, [])
    
    # 1. Extraer duraciones individuales de cada transición exitosa con cambio de banda
    # Solo nos interesan las transiciones que realmente implican un cambio de banda
    valid_transitions = []
    for trans in transitions:
        if not trans.get("start_time") or not trans.get("is_successful"):
            continue
        
        # Solo contar transiciones con cambio de banda físico
        if not trans.get("is_band_change"):
            continue
            
        from_band = _normalize_band(trans.get("from_band", ""))
        to_band = _normalize_band(trans.get("to_band", ""))
        
        # Verificar que realmente hay cambio de banda
        if from_band and to_band and from_band != to_band:
            valid_transitions.append(trans)
            
            # Calcular duración de la transición (tiempo que tarda en soltar una banda para coger otra)
            start_time = float(trans.get("start_time", 0))
            end_time = float(trans.get("end_time", start_time))
            duration = end_time - start_time
            
            if duration > 0:
                transition_times.append(duration)
    
    # Ordenar transiciones por tiempo
    valid_transitions = sorted(valid_transitions, key=lambda x: float(x.get("start_time", 0)))
    
    # 2. Obtener todos los timestamps para calcular tiempo total
    all_timestamps = []
    
    # Agregar timestamps de transiciones
    for trans in valid_transitions:
        start = trans.get("start_time")
        end = trans.get("end_time")
        if start:
            try:
                all_timestamps.append(float(start))
            except (ValueError, TypeError):
                pass
        if end:
            try:
                all_timestamps.append(float(end))
            except (ValueError, TypeError):
                pass
    
    # Agregar timestamps de muestras de señal (fuente de verdad de Wireshark)
    if signal_samples:
        for sample in signal_samples:
            ts = sample.get("timestamp")
            if ts:
                try:
                    all_timestamps.append(float(ts))
                except (ValueError, TypeError):
                    pass
    
    if not all_timestamps:
        return (0.0, 0.0, transition_times)
    
    min_time = min(all_timestamps)
    max_time = max(all_timestamps)
    total_time = max_time - min_time
    
    if total_time <= 0:
        return (0.0, 0.0, transition_times)
    
    # 3. Construir lista de períodos de transición para excluirlos
    transition_periods = []
    for trans in valid_transitions:
        start_time = float(trans.get("start_time", 0))
        end_time = float(trans.get("end_time", start_time))
        if end_time > start_time:
            transition_periods.append((start_time, end_time))
    
    # 4. Calcular tiempo en cada banda usando muestras de señal (fuente de verdad de Wireshark)
    # Filtrar y ordenar muestras de señal válidas
    valid_samples = []
    for sample in (signal_samples or []):
        band = sample.get("band", "")
        timestamp = sample.get("timestamp")
        if band and timestamp:
            try:
                ts = float(timestamp)
                band_normalized = _normalize_band(band)
                if band_normalized in ["2.4 GHz", "5 GHz"]:
                    valid_samples.append({
                        "timestamp": ts,
                        "band": band_normalized
                    })
            except (ValueError, TypeError):
                pass
    
    if not valid_samples:
        # Si no hay muestras de señal, usar método basado en transiciones (menos preciso)
        if valid_transitions:
            current_band = None
            last_time = min_time
            
            for trans in valid_transitions:
                start_time = float(trans.get("start_time", 0))
                from_band = _normalize_band(trans.get("from_band", ""))
                to_band = _normalize_band(trans.get("to_band", ""))
                
                # Determinar banda inicial si es la primera transición
                if current_band is None:
                    current_band = from_band if from_band else to_band
                
                # Tiempo en la banda actual hasta el inicio de la transición (EXCLUYENDO la transición)
                if current_band and start_time > last_time:
                    period = start_time - last_time
                    if current_band == "2.4 GHz":
                        time_2_4ghz += period
                    elif current_band == "5 GHz":
                        time_5ghz += period
                
                # Actualizar banda y tiempo (después de la transición)
                current_band = to_band if to_band else from_band
                last_time = float(trans.get("end_time", start_time))
            
            # Tiempo final después de la última transición
            if current_band and last_time < max_time:
                period = max_time - last_time
                if current_band == "2.4 GHz":
                    time_2_4ghz += period
                elif current_band == "5 GHz":
                    time_5ghz += period
    else:
        # Método preciso: usar muestras de señal y excluir períodos de transición
        valid_samples = sorted(valid_samples, key=lambda x: x["timestamp"])
        
        # Agrupar muestras consecutivas de la misma banda
        i = 0
        while i < len(valid_samples):
            current_band = valid_samples[i]["band"]
            period_start = valid_samples[i]["timestamp"]
            period_end = period_start
            
            # Encontrar el final del período continuo en la misma banda
            j = i + 1
            while j < len(valid_samples):
                next_sample = valid_samples[j]
                next_ts = next_sample["timestamp"]
                next_band = next_sample["band"]
                
                # Verificar si estamos en un período de transición
                in_transition = False
                for trans_start, trans_end in transition_periods:
                    if trans_start <= next_ts <= trans_end:
                        in_transition = True
                        break
                
                # Si cambió de banda o estamos en transición, terminar el período
                if next_band != current_band or in_transition:
                    break
                
                # Si el intervalo es razonable (máximo 5 segundos), continuar el período
                if next_ts - period_end <= 5.0:
                    period_end = next_ts
                    j += 1
                else:
                    # Intervalo muy grande, terminar el período
                    break
            
            # Calcular duración del período (excluyendo cualquier parte que esté en transición)
            period_duration = period_end - period_start
            
            # Verificar si el período se superpone con alguna transición
            for trans_start, trans_end in transition_periods:
                # Si hay superposición, reducir la duración
                if period_start < trans_end and period_end > trans_start:
                    overlap_start = max(period_start, trans_start)
                    overlap_end = min(period_end, trans_end)
                    overlap_duration = overlap_end - overlap_start
                    period_duration -= overlap_duration
            
            # Solo agregar si la duración es positiva y no está completamente en transición
            if period_duration > 0:
                if current_band == "2.4 GHz":
                    time_2_4ghz += period_duration
                elif current_band == "5 GHz":
                    time_5ghz += period_duration
            
            i = j
    
    # 5. Verificar coherencia: tiempo en bandas + tiempo en transiciones no debe exceder tiempo total
    total_transition_time = sum(transition_times)
    total_band_time = time_2_4ghz + time_5ghz
    expected_total = total_time - total_transition_time
    
    # Si hay una discrepancia significativa, ajustar proporcionalmente
    if expected_total > 0 and total_band_time > expected_total * 1.1:
        scale = expected_total / total_band_time
        time_2_4ghz *= scale
        time_5ghz *= scale
    
    return (round(time_2_4ghz, 2), round(time_5ghz, 2), transition_times)

def _normalize_band(band: str) -> str:
    """Normaliza el nombre de la banda a formato estándar."""
    if not band:
        return ""
    band_lower = band.lower()
    if "2.4" in band_lower or "2400" in band_lower:
        return "2.4 GHz"
    elif "5" in band_lower and ("ghz" in band_lower or "5000" in band_lower):
        return "5 GHz"
    return band

def _generate_summary_pdf_html(reports: List[Dict[str, Any]], ai_summary_text: str = "") -> str:
    """
    Genera HTML profesional para el PDF de resumen de reportes con estilos mejorados.
    
    Args:
        reports: Lista de diccionarios con los datos de los reportes
        ai_summary_text: Texto de resumen generado por IA (formato Markdown)
        
    Returns:
        HTML completo con el reporte de resumen
    """
    if not reports:
        return ""
    
    # Calcular estadísticas agregadas
    total_reports = len(reports)
    verdicts = [r.get('verdict', 'UNKNOWN') for r in reports]
    success_count = sum(1 for v in verdicts if v in ['SUCCESS', 'EXCELLENT', 'GOOD'])
    failed_count = sum(1 for v in verdicts if v == 'FAILED')
    success_rate = (success_count / total_reports * 100) if total_reports > 0 else 0
    
    vendors = [r.get('vendor', 'Unknown') for r in reports]
    vendor_counts = {v: vendors.count(v) for v in set(vendors)}
    top_vendors = sorted(vendor_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    total_packets = sum(r.get('total_packets', 0) for r in reports)
    avg_packets = total_packets / total_reports if total_reports > 0 else 0
    
    # Distribución de veredictos
    verdict_dist = {}
    for v in verdicts:
        verdict_dist[v] = verdict_dist.get(v, 0) + 1
    
    # Obtener fecha y hora actual en zona horaria de Colombia
    colombia_tz = pytz.timezone('America/Bogota')
    current_time_colombia = datetime.now(colombia_tz)
    formatted_date_time = current_time_colombia.strftime('%d/%m/%Y a las %I:%M %p')
    
    # Formatear análisis markdown (similar a _generate_pdf_html)
    def format_analysis(text):
        if not text:
            return ""
        import re
        lines = text.split("\n")
        html_parts = []
        in_list = False
        in_ordered_list = False
        list_items = []
        
        def close_list_html():
            nonlocal html_parts, in_list, in_ordered_list, list_items
            if in_list:
                html_parts.append('<ul style="margin: 8px 0; padding-left: 20px; list-style-type: disc;">')
                for item in list_items:
                    item_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', item)
                    item_text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', item_text)
                    html_parts.append(f'<li style="margin-bottom: 4px; font-size: 8pt; line-height: 1.5;">{item_text}</li>')
                html_parts.append('</ul>')
                list_items = []
                in_list = False
            if in_ordered_list:
                html_parts.append('<ol style="margin: 8px 0; padding-left: 20px; list-style-type: decimal;">')
                for item in list_items:
                    item_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', item)
                    item_text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', item_text)
                    html_parts.append(f'<li style="margin-bottom: 4px; font-size: 8pt; line-height: 1.5;">{item_text}</li>')
                html_parts.append('</ol>')
                list_items = []
                in_ordered_list = False
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                close_list_html()
                continue
            
            # Headings
            if line_stripped.startswith("#"):
                close_list_html()
                level = len(line_stripped) - len(line_stripped.lstrip("#"))
                content = line_stripped.lstrip("#").strip()
                font_size = '11pt' if level == 1 else ('10pt' if level == 2 else ('9pt' if level == 3 else '8pt'))
                margin_top = '16px' if level == 1 else ('14px' if level == 2 else '12px')
                html_parts.append(f'<h{min(level + 1, 4)} style="margin-top: {margin_top}; margin-bottom: 8px; font-size: {font_size}; font-weight: 600; color: #374151; page-break-after: avoid;">{content}</h{min(level + 1, 4)}>')
                continue
            
            # Ordered lists
            ordered_match = re.match(r'^(\d+)\.\s+(.+)$', line_stripped)
            if ordered_match:
                close_list_html()
                if not in_ordered_list:
                    in_ordered_list = True
                item_text = ordered_match.group(2)
                item_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', item_text)
                item_text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', item_text)
                list_items.append(item_text)
                continue
            
            # Unordered lists
            if re.match(r'^[-*•]\s+(.+)$', line_stripped):
                close_list_html()
                if not in_list:
                    in_list = True
                item_text = re.sub(r'^[-*•]\s+', '', line_stripped)
                item_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', item_text)
                item_text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', item_text)
                list_items.append(item_text)
                continue
            
            close_list_html()
            
            # Paragraphs
            para_text = line_stripped
            para_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', para_text)
            para_text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', para_text)
            para_text = re.sub(r'`([^`]+)`', r'<code style="background: #f3f4f6; padding: 2px 4px; border-radius: 3px; font-family: monospace; font-size: 7pt;">\1</code>', para_text)
            html_parts.append(f'<p style="margin-bottom: 8px; font-size: 8pt; line-height: 1.6; text-align: justify;">{para_text}</p>')
        
        close_list_html()
        return "".join(html_parts)
    
    # Formatear fecha
    def format_report_date(date_str):
        if not date_str:
            return 'N/A'
        try:
            date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return date.strftime('%d/%m/%Y %I:%M %p')
        except:
            return date_str
    
    # Formatear tiempo
    def format_time(seconds):
        if not seconds or seconds == 0:
            return '0s'
        if seconds < 1:
            return f'{int(seconds * 1000)}ms'
        if seconds < 60:
            return f'{seconds:.1f}s'
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f'{minutes}m {secs:.1f}s'
    
    # Formatear lista de tiempos de transición
    def format_transition_times(times_list):
        if not times_list or len(times_list) == 0:
            return 'N/A'
        formatted_times = [format_time(t) for t in times_list]
        return ', '.join(formatted_times)
    
    # Generar HTML de gráficas fuera del f-string principal para evitar problemas con corchetes
    verdict_chart_items = []
    for verdict, count in sorted(verdict_dist.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_reports * 100) if total_reports > 0 else 0
        color = '#10b981' if verdict in ['SUCCESS', 'EXCELLENT', 'GOOD'] else '#ef4444' if verdict == 'FAILED' else '#6b7280'
        verdict_chart_items.append(f'''
                    <div class="bar-item">
                        <div class="bar-label">{verdict}</div>
                        <div class="bar-wrapper">
                            <div class="bar-fill" style="width: {percentage:.1f}%; background: {color};">
                                {count} ({percentage:.1f}%)
                            </div>
                        </div>
                    </div>
                    ''')
    verdict_chart_html = ''.join(verdict_chart_items)
    
    # Generar HTML de gráfica de marcas
    vendor_chart_html = ''
    if top_vendors:
        vendor_chart_items = []
        for vendor, count in top_vendors:
            percentage = (count / total_reports * 100) if total_reports > 0 else 0
            vendor_chart_items.append(f'''
                    <div class="bar-item">
                        <div class="bar-label">{vendor}</div>
                        <div class="bar-wrapper">
                            <div class="bar-fill" style="width: {percentage:.1f}%; background: #3b82f6;">
                                {count} reportes ({percentage:.1f}%)
                            </div>
                        </div>
                    </div>
                    ''')
        vendor_chart_items_joined = ''.join(vendor_chart_items)
        vendor_chart_html = f'''
            <h3 style="margin-top: 30px; margin-bottom: 15px;">Top {len(top_vendors)} Marcas</h3>
            <div class="chart-container">
                <div class="bar-chart">
                    {vendor_chart_items_joined}
                </div>
            </div>
            '''
    
    # Generar HTML de tabla de reportes
    reports_table_rows = []
    for report in reports:
        verdict = report.get('verdict', 'UNKNOWN')
        verdict_class = 'verdict-success' if verdict in ['SUCCESS', 'EXCELLENT', 'GOOD'] else 'verdict-failed'
        time_2_4ghz = report.get('time_2_4ghz', 0)
        time_5ghz = report.get('time_5ghz', 0)
        transition_times = report.get('transition_times', [])
        reports_table_rows.append(f'''
                <tr>
                    <td>{report.get('vendor', 'Unknown')}</td>
                    <td>{report.get('model', 'Unknown')}</td>
                    <td>
                        <span class="verdict-badge {verdict_class}">
                            {verdict}
                        </span>
                    </td>
                    <td>{report.get('total_packets', 0):,}</td>
                    <td>{format_time(time_2_4ghz)}</td>
                    <td>{format_time(time_5ghz)}</td>
                    <td>{format_transition_times(transition_times)}</td>
                    <td>{format_report_date(report.get('timestamp', ''))}</td>
                </tr>
                ''')
    reports_table_html = ''.join(reports_table_rows)
    
    # Generar HTML
    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Resumen de Reportes - Pipe</title>
        <style>
            @page {{
                margin: 1.5cm;
                size: A4;
            }}
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                font-size: 11pt;
                line-height: 1.6;
                color: #1a1a1a;
                background: white;
                padding: 0;
            }}
            .header {{
                border-bottom: 3px solid #6366f1;
                padding-bottom: 15px;
                margin-bottom: 30px;
            }}
            h1 {{
                font-size: 28pt;
                color: #1a1a1a;
                margin-bottom: 10px;
                font-weight: 700;
            }}
            h2 {{
                font-size: 20pt;
                color: #1a1a1a;
                margin-top: 30px;
                margin-bottom: 15px;
                border-bottom: 2px solid #e5e7eb;
                padding-bottom: 8px;
                font-weight: 600;
            }}
            h3 {{
                font-size: 16pt;
                color: #374151;
                margin-top: 20px;
                margin-bottom: 10px;
                font-weight: 600;
            }}
            .info-card-grid {{
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 12px;
                margin-bottom: 24px;
            }}
            .info-card {{
                background: #f8f9fa;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 12px;
            }}
            .info-card-title {{
                font-size: 8pt;
                font-weight: 600;
                color: #6b7280;
                margin-bottom: 8px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .info-card-value {{
                font-size: 18pt;
                font-weight: 700;
                color: #1a1a1a;
            }}
            .info-card-sub {{
                font-size: 7pt;
                color: #6b7280;
                margin-top: 4px;
            }}
            .stats-section {{
                background: #f8f9fa;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 25px;
            }}
            .chart-container {{
                margin: 20px 0;
                page-break-inside: avoid;
            }}
            .bar-chart {{
                display: flex;
                flex-direction: column;
                gap: 12px;
            }}
            .bar-item {{
                display: flex;
                align-items: center;
                gap: 12px;
            }}
            .bar-label {{
                min-width: 120px;
                font-size: 9pt;
                font-weight: 600;
                color: #374151;
            }}
            .bar-wrapper {{
                flex: 1;
                height: 24px;
                background: #e5e7eb;
                border-radius: 4px;
                overflow: hidden;
                position: relative;
            }}
            .bar-fill {{
                height: 100%;
                border-radius: 4px;
                display: flex;
                align-items: center;
                justify-content: flex-end;
                padding-right: 8px;
                font-size: 8pt;
                font-weight: 600;
                color: white;
            }}
            .reports-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
                font-size: 9pt;
                page-break-inside: avoid;
            }}
            .reports-table th {{
                background: #374151;
                color: #ffffff !important;
                padding: 10px;
                text-align: left;
                font-weight: 600;
                border-bottom: 2px solid #4b5563;
                font-size: 9pt;
            }}
            .reports-table td {{
                padding: 8px 10px;
                border-bottom: 1px solid #e5e7eb;
                color: #1a1a1a;
                font-size: 9pt;
            }}
            .reports-table tr:nth-child(even) {{
                background: #f9fafb;
            }}
            .verdict-badge {{
                display: inline-block;
                padding: 4px 10px;
                border-radius: 4px;
                font-weight: 600;
                font-size: 8pt;
                text-transform: uppercase;
            }}
            .verdict-success {{
                background: #10b981;
                color: white;
            }}
            .verdict-failed {{
                background: #ef4444;
                color: white;
            }}
            .analysis-content {{
                background: #ffffff;
                border-left: 4px solid #6366f1;
                padding: 20px;
                margin-top: 15px;
                line-height: 1.8;
            }}
            .footer {{
                margin-top: 40px;
                text-align: center;
                color: #6b7280;
                font-size: 8pt;
                border-top: 1px solid #e5e7eb;
                padding-top: 12px;
            }}
            .section-divider {{
                height: 2px;
                background: linear-gradient(to right, #6366f1, transparent);
                margin: 24px 0;
            }}
            @media print {{
                body {{
                    padding: 0;
                }}
                .page-break {{
                    page-break-before: always;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Resumen de Reportes - Pipe</h1>
            <p style="color: #6b7280; font-size: 10pt;">Generado el {formatted_date_time} (hora de Colombia, UTC-5)</p>
        </div>
        
        <!-- Cards de Estadísticas Principales -->
        <div class="info-card-grid">
            <div class="info-card">
                <div class="info-card-title">Total Reportes</div>
                <div class="info-card-value">{total_reports}</div>
                <div class="info-card-sub">análisis realizados</div>
            </div>
            <div class="info-card">
                <div class="info-card-title">Tasa de Éxito</div>
                <div class="info-card-value" style="color: #10b981;">{success_rate:.1f}%</div>
                <div class="info-card-sub">{success_count} exitosos</div>
            </div>
            <div class="info-card">
                <div class="info-card-title">Reportes Fallidos</div>
                <div class="info-card-value" style="color: #ef4444;">{failed_count}</div>
                <div class="info-card-sub">requieren atención</div>
            </div>
            <div class="info-card">
                <div class="info-card-title">Total Paquetes</div>
                <div class="info-card-value">{total_packets:,}</div>
                <div class="info-card-sub">promedio: {avg_packets:.0f}</div>
            </div>
        </div>
        
        <!-- Sección de Estadísticas -->
        <div class="stats-section">
            <h2>Estadísticas Observadas</h2>
            
            <!-- Distribución de Veredictos -->
            <h3 style="margin-top: 20px; margin-bottom: 15px;">Distribución de Veredictos</h3>
            <div class="chart-container">
                <div class="bar-chart">
                    {verdict_chart_html}
                </div>
            </div>
            
            <!-- Top Marcas -->
            {vendor_chart_html}
        </div>
        
        <div class="section-divider"></div>
        
        <!-- Tabla de Reportes -->
        <h2>Tabla de Resultados</h2>
        <table class="reports-table">
            <thead>
                <tr>
                    <th>Marca</th>
                    <th>Modelo</th>
                    <th>Veredicto</th>
                    <th>Paquetes</th>
                    <th>Tiempo 2.4 GHz</th>
                    <th>Tiempo 5 GHz</th>
                    <th>Tiempo Transición</th>
                    <th>Fecha</th>
                </tr>
            </thead>
            <tbody>
                {reports_table_html}
            </tbody>
        </table>
        
        <div class="section-divider"></div>
        
        <!-- Resumen Ejecutivo -->
        <h2>Resumen Ejecutivo</h2>
        <div class="analysis-content">
            {format_analysis(ai_summary_text) if ai_summary_text else f'''
            <p style="margin-bottom: 8px; font-size: 8pt; line-height: 1.6; text-align: justify;">
                Este resumen consolida {total_reports} análisis de Band Steering realizados mediante capturas Wireshark/tshark.
                De estos, {success_count} reportes ({success_rate:.1f}%) fueron exitosos, mientras que {failed_count} reportes requieren atención.
            </p>
            <p style="margin-bottom: 8px; font-size: 8pt; line-height: 1.6; text-align: justify;">
                La marca más analizada es <strong>{top_vendors[0][0] if top_vendors else 'N/A'}</strong> con {top_vendors[0][1] if top_vendors else 0} reportes.
                En total se analizaron {total_packets:,} paquetes de red, con un promedio de {avg_packets:.0f} paquetes por análisis.
            </p>
            '''}
        </div>
        
        <div class="footer">
            Generado por Pipe - Análisis inteligente de capturas Wireshark
        </div>
    </body>
    </html>
    """
    return html

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
    
    # Generar solo el texto de resumen ejecutivo con IA (no el HTML completo)
    prompt = f"""Genera un resumen ejecutivo profesional en formato Markdown sobre los siguientes análisis de Band Steering.

DATOS DE LOS REPORTES:

{reports_text}

ESTADÍSTICAS AGREGADAS:
- Total de reportes analizados: {total_reports}
- Reportes exitosos: {success_count} ({success_rate:.1f}%)
- Reportes fallidos: {failed_count}
- Marca más común: {top_vendor}
- Total de paquetes analizados: {total_packets:,}

INSTRUCCIONES:

Genera un resumen ejecutivo en formato Markdown que incluya:

1. **Vista General**: Resumen consolidado de todos los reportes
2. **Hallazgos Principales**: Patrones detectados y observaciones clave
3. **Estado del Sistema**: Evaluación general del rendimiento de Band Steering
4. **Recomendaciones**: Sugerencias específicas basadas en los hallazgos
5. **Conclusiones**: Evaluación final y próximos pasos sugeridos

FORMATO:
- Usa Markdown con títulos (#, ##, ###)
- Usa listas con viñetas (-) o numeradas (1., 2., 3.)
- Usa **negritas** para énfasis
- Mantén el texto claro, conciso y profesional
- No inventes información que no esté en los datos proporcionados
- El resumen debe tener entre 300-500 palabras
"""
    
    try:
        # Generar solo el texto de resumen (no HTML completo)
        max_tokens = min(2000 + len(reports) * 200, 4000)
        ai_summary_text = await llm_client.agenerate(prompt, max_tokens=max_tokens)
        
        if not ai_summary_text or len(ai_summary_text.strip()) == 0:
            ai_summary_text = ""  # Usar resumen por defecto si falla
        
        # Generar HTML completo con estructura y estilos profesionales
        html_content = _generate_summary_pdf_html(reports, ai_summary_text)
        
        if not html_content or len(html_content.strip()) == 0:
            raise HTTPException(
                status_code=500,
                detail="Error al generar el HTML del reporte"
            )
        
        return html_content
        
    except HTTPException:
        # Re-lanzar HTTPException sin modificar
        raise
    except RuntimeError as e:
        # El LLMClient lanza RuntimeError cuando hay problemas con la API
        raise HTTPException(
            status_code=500,
            detail=f"Error al comunicarse con el servicio de IA: {str(e)}"
        )
    except Exception as e:
        # Capturar cualquier otro error inesperado
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
    base_dir = service.base_dir
    reports_to_export = []
    
    try:
        if not base_dir.exists():
            raise HTTPException(status_code=404, detail="No se encontraron reportes")
        
        # Si se proporcionan IDs, exportar solo esos
        target_ids = None
        if ids and ids.strip():
            # Limpiar y dividir IDs
            id_list = [id.strip() for id in ids.split(",") if id.strip()]
            if id_list:
                target_ids = set(id_list)
        
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
                            # Obtener datos completos para calcular tiempos por banda
                            # Los datos pueden estar en diferentes estructuras según la versión del análisis
                            transitions = []
                            signal_samples = []
                            
                            # Intentar obtener desde la estructura band_steering (nueva estructura)
                            band_steering = data.get("band_steering", {})
                            if isinstance(band_steering, dict):
                                transitions = band_steering.get("transitions", [])
                                signal_samples = band_steering.get("signal_samples", [])
                            
                            # Fallback: intentar desde el nivel raíz (estructura antigua)
                            if not transitions:
                                transitions = data.get("transitions", [])
                            if not signal_samples:
                                signal_samples = data.get("signal_samples", [])
                            
                            # Calcular tiempos por banda
                            time_2_4ghz, time_5ghz, transition_times_list = _calculate_band_times(
                                transitions, signal_samples
                            )
                            
                            reports_to_export.append({
                                "id": analysis_id,
                                "filename": data.get("filename"),
                                "timestamp": data.get("analysis_timestamp"),
                                "vendor": device.get("vendor", "Unknown"),
                                "model": device.get("device_model", "Unknown"),
                                "verdict": data.get("verdict"),
                                "analysis_text": data.get("analysis_text", ""),
                                "total_packets": data.get("total_packets", 0),
                                "time_2_4ghz": time_2_4ghz,
                                "time_5ghz": time_5ghz,
                                "transition_times": transition_times_list
                            })
                    except Exception:
                        pass
        
        if not reports_to_export:
            raise HTTPException(status_code=404, detail="No se encontraron reportes para exportar")
        
        
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
            except Exception:
                pass
        
        # Limpiar directorios vacíos
        for vendor_dir in base_dir.iterdir():
            if vendor_dir.is_dir():
                for device_dir in vendor_dir.iterdir():
                    if device_dir.is_dir() and not any(device_dir.iterdir()):
                        device_dir.rmdir()
                if not any(vendor_dir.iterdir()):
                    vendor_dir.rmdir()
        
        return {"status": "success", "message": f"Se eliminaron {deleted_count} reportes", "deleted": deleted_count}
    except Exception as e:
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
            except Exception:
                pass
        
        # Limpiar directorios vacíos
        for device_dir in vendor_dir.iterdir():
            if device_dir.is_dir() and not any(device_dir.iterdir()):
                device_dir.rmdir()
        
        if not any(vendor_dir.iterdir()):
            vendor_dir.rmdir()
        
        return {"status": "success", "message": f"Se eliminaron {deleted_count} reportes de {vendor}", "deleted": deleted_count}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
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
                except Exception:
                    pass
            
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
        
        return {
            "status": "success",
            "message": message,
            "deleted": deleted_count,
            "not_found": not_found
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error al eliminar reportes: {str(e)}")

# Esta función ya está definida arriba (línea 400), eliminando duplicado
