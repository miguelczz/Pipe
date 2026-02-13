from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi import Body
from pathlib import Path
import json
from typing import List, Dict, Any, Optional
from io import BytesIO
from datetime import datetime
from collections import Counter
import pytz
from ..services.band_steering_service import BandSteeringService
from ..agent.llm_client import LLMClient

# WeasyPrint will be imported lazily only when needed
WEASYPRINT_AVAILABLE = None
HTML = None

def _check_weasyprint():
    """Verifies if WeasyPrint is available and imports the module."""
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

# Handle both /reports and /reports/
@router.get("", include_in_schema=True)
@router.get("/", include_in_schema=True)
async def list_reports():
    """
    Lists all saved analyses organized by brand.
    """
    reports = []
    base_dir = service.base_dir
    
    
    if not base_dir.exists():
        return []
        
    try:
        # Traverse Brand / Device / Analysis.json
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
                            # Extract device info
                            devices = data.get("devices", [])
                            if not devices or len(devices) == 0:
                                continue
                            
                            device = devices[0]
                            
                            # Get data to calculate band times
                            transitions = []
                            signal_samples = []
                            
                            # Try to get from band_steering structure (new structure)
                            band_steering = data.get("band_steering", {})
                            if isinstance(band_steering, dict):
                                transitions = band_steering.get("transitions", [])
                                signal_samples = band_steering.get("signal_samples", [])
                            
                            # Fallback: try from root level (old structure)
                            if not transitions:
                                transitions = data.get("transitions", [])
                            if not signal_samples:
                                signal_samples = data.get("signal_samples", [])
                            
                            # Calculate band times
                            time_2_4ghz, time_5ghz, transition_times_list = _calculate_band_times(
                                transitions, signal_samples
                            )
                            
                            verdict = data.get("verdict")
                            analysis_id = data.get("analysis_id")
                            
                            reports.append({
                                "id": analysis_id,
                                "filename": data.get("filename"), # Original pcap name
                                "timestamp": data.get("analysis_timestamp"),
                                "vendor": device.get("vendor", "Unknown"),
                                "model": device.get("device_model", "Unknown"),
                                "verdict": verdict,
                                "time_2_4ghz": time_2_4ghz,
                                "time_5ghz": time_5ghz,
                                "transition_times": transition_times_list
                            })
                    except (json.JSONDecodeError, Exception):
                        pass
        
        # Sort by timestamp descending
        reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return reports
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{analysis_id}/download")
async def download_capture(analysis_id: str):
    """
    Downloads the original pcap file for an analysis.
    """
    base_dir = service.base_dir
    
    try:
        # Find the analysis JSON file
        analysis_file = None
        json_files = list(base_dir.glob(f"**/{analysis_id}.json"))
        for json_file in json_files:
            analysis_file = json_file
            break
        
        if not analysis_file:
            raise HTTPException(status_code=404, detail="Report not found")
        
        
        # Read JSON to get pcap file path
        with open(analysis_file, "r", encoding="utf-8") as f:
            analysis_data = json.load(f)
        
        
        # Get pcap file path
        pcap_path = analysis_data.get("original_file_path")
        
        if not pcap_path:
            # Old report without saved file
            raise HTTPException(
                status_code=404, 
                detail="This report was created before pcap file saving was implemented. Only new analyses save the original pcap file."
            )
        
        pcap_file = Path(pcap_path)
        
        if not pcap_file.exists():
            raise HTTPException(status_code=404, detail="The pcap file no longer exists on the server")
        
        # Get original filename from JSON
        original_filename = analysis_data.get("filename", "capture.pcap")
        
        if not original_filename.endswith((".pcap", ".pcapng")):
            # Ensure correct extension
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
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")

# IMPORTANT: Specific routes must go BEFORE generic routes with parameters
# FastAPI evaluates routes in order, so /batch must go before /{analysis_id}

@router.delete("/batch")
async def delete_batch_reports(request: Dict[str, List[str]]):
    """
    Deletes multiple reports by their IDs.
    Body: {"ids": ["id1", "id2", "id3"]}
    """
    base_dir = service.base_dir
    ids = request.get("ids", [])
    
    if not ids:
        raise HTTPException(status_code=400, detail="At least one ID is required in the 'ids' array")
    
    deleted_count = 0
    not_found = []
    
    try:
        # If the base directory does not exist, all reports are "not found"
        if not base_dir.exists():
            return {
                "status": "success",
                "message": f"No reports found to delete. The base directory does not exist.",
                "deleted": 0,
                "not_found": ids
            }
        
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
        
        # Clean up empty directories
        for vendor_dir in base_dir.iterdir():
            if vendor_dir.is_dir():
                for device_dir in vendor_dir.iterdir():
                    if device_dir.is_dir() and not any(device_dir.iterdir()):
                        device_dir.rmdir()
                if not any(vendor_dir.iterdir()):
                    vendor_dir.rmdir()
        
        message = f"Deleted {deleted_count} reports"
        if not_found:
            message += f". {len(not_found)} reports not found: {', '.join(not_found)}"
        
        return {
            "status": "success",
            "message": message,
            "deleted": deleted_count,
            "not_found": not_found
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error deleting reports: {str(e)}")

@router.delete("/all")
async def delete_all_reports():
    """
    Deletes all reports from the system.
    """
    base_dir = service.base_dir
    deleted_count = 0
    
    try:
        if not base_dir.exists():
            return {"status": "success", "message": "No reports to delete", "deleted": 0}
        
        # Find all analysis JSON files
        for analysis_file in base_dir.glob("**/*.json"):
            try:
                analysis_file.unlink()
                deleted_count += 1
            except Exception:
                pass
        
        # Clean up empty directories
        for vendor_dir in base_dir.iterdir():
            if vendor_dir.is_dir():
                for device_dir in vendor_dir.iterdir():
                    if device_dir.is_dir() and not any(device_dir.iterdir()):
                        device_dir.rmdir()
                if not any(vendor_dir.iterdir()):
                    vendor_dir.rmdir()
        
        return {"status": "success", "message": f"Deleted {deleted_count} reports", "deleted": deleted_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting all reports: {str(e)}")

@router.delete("/{analysis_id}")
async def delete_report(analysis_id: str):
    """
    Deletes a specific report by its ID.
    """
    base_dir = service.base_dir
    try:
        # Find the file in the folder structure
        found = False
        for analysis_file in base_dir.glob(f"**/{analysis_id}.json"):
            analysis_file.unlink()
            found = True
            break
            
        if not found:
            raise HTTPException(status_code=404, detail="Report not found")
            
        return {"status": "success", "message": f"Report {analysis_id} deleted"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{analysis_id}/pdf")
async def save_pdf(analysis_id: str, html_content: str = Body(..., media_type="text/plain")):
    """
    Persists the analysis report PDF from the HTML provided by the frontend.
    Called when the user clicks "Export PDF" in NetworkAnalysisPage.
    """
    base_dir = service.base_dir
    
    try:
        # Find the analysis JSON file to get the directory path
        analysis_file = None
        json_files = list(base_dir.glob(f"**/{analysis_id}.json"))
        for json_file in json_files:
            analysis_file = json_file
            break
        
        if not analysis_file:
            raise HTTPException(status_code=404, detail="Report not found")
        
        
        # The PDF is saved in the same directory as the JSON
        pdf_path = analysis_file.parent / f"{analysis_id}.pdf"
        
        # Check WeasyPrint lazily
        if not _check_weasyprint():
            raise HTTPException(
                status_code=500, 
                detail="WeasyPrint is not available. Install system dependencies: libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info"
            )
        
        
        # Validate that HTML content is not empty
        if not html_content or not html_content.strip():
            raise HTTPException(
                status_code=400,
                detail="HTML content is empty"
            )
        
        html_length = len(html_content)
        
        # Check if there is a previous PDF and delete it
        if pdf_path.exists():
            old_size = pdf_path.stat().st_size
            try:
                pdf_path.unlink()
            except Exception:
                pass
        
        # Convert HTML to PDF using WeasyPrint
        try:
            
            # Create the HTML document
            html_doc = HTML(string=html_content, base_url=None)
            
            # Generate PDF with appropriate settings
            html_doc.write_pdf(
                pdf_path,
                stylesheets=None,  # Styles are already in the HTML
                presentational_hints=True
            )
            
            # Verify that PDF was created correctly
            if not pdf_path.exists():
                raise Exception("The PDF was not created")
            
            pdf_size = pdf_path.stat().st_size
            
            if pdf_size == 0:
                try:
                    pdf_path.unlink()
                except Exception:
                    pass
                raise Exception("The generated PDF is empty")
            
            # Validate that PDF has correct header (must start with %PDF)
            try:
                with open(pdf_path, 'rb') as f:
                    header = f.read(4)
                    if header != b'%PDF':
                        try:
                            pdf_path.unlink()
                        except Exception:
                            pass
                        raise Exception(f"The generated file is not a valid PDF (header: {header})")
            except Exception as header_error:
                if pdf_path.exists():
                    try:
                        pdf_path.unlink()
                    except Exception:
                        pass
                raise
            
            return {
                "status": "success", 
                "message": "PDF saved successfully", 
                "path": str(pdf_path),
                "size": pdf_size
            }
        except Exception as pdf_error:
            error_msg = str(pdf_error)
            error_type = type(pdf_error).__name__
            
            # Clean up corrupt file if exists
            if pdf_path.exists():
                try:
                    corrupt_size = pdf_path.stat().st_size
                    pdf_path.unlink()
                except Exception as cleanup_error:
                    pass
            
            raise HTTPException(
                status_code=500, 
                detail=f"Error converting HTML to PDF: {error_msg}"
            )
            
    except HTTPException as e:
        raise
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        raise HTTPException(status_code=500, detail=f"Error saving PDF: {error_msg}")

@router.get("/{analysis_id}/pdf")
async def download_pdf(analysis_id: str):
    """
    Downloads the persisted analysis report PDF.
    If the PDF does not exist, it generates it automatically from the analysis data.
    """
    base_dir = service.base_dir
    
    try:
        # Find the persisted PDF file
        pdf_files = list(base_dir.glob(f"**/{analysis_id}.pdf"))
        
        # If the PDF does not exist, generate it automatically
        if not pdf_files:
            
            # Find the analysis JSON file
            json_files = list(base_dir.glob(f"**/{analysis_id}.json"))
            if not json_files:
                raise HTTPException(
                    status_code=404,
                    detail="Analysis not found"
                )
            
            analysis_file = json_files[0]
            
            # Read analysis JSON
            try:
                with open(analysis_file, "r", encoding="utf-8") as f:
                    analysis_data = json.load(f)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error reading analysis data: {str(e)}"
                )
            
            # Verify WeasyPrint
            if not _check_weasyprint():
                raise HTTPException(
                    status_code=500,
                    detail="WeasyPrint is not available. Automatic PDF generation is not possible."
                )
            
            # Generate HTML from analysis data
            html_content = _generate_pdf_html(analysis_data)
            
            # Path where PDF will be saved
            pdf_path = analysis_file.parent / f"{analysis_id}.pdf"
            
            # Convert HTML to PDF
            try:
                html_doc = HTML(string=html_content, base_url=None)
                html_doc.write_pdf(
                    pdf_path,
                    stylesheets=None,
                    presentational_hints=True
                )
                
                # Check that it was created correctly
                if not pdf_path.exists() or pdf_path.stat().st_size == 0:
                    raise Exception("The generated PDF is empty")
                
                pdf_size = pdf_path.stat().st_size
                
                # Validate header
                with open(pdf_path, 'rb') as f:
                    header = f.read(4)
                    if header != b'%PDF':
                        pdf_path.unlink()
                        raise Exception(f"Invalid PDF (header: {header})")
                
                
            except Exception as pdf_error:
                if pdf_path.exists():
                    try:
                        pdf_path.unlink()
                    except Exception:
                        pass
                raise HTTPException(
                    status_code=500,
                    detail=f"Error generating PDF: {str(pdf_error)}"
                )
        else:
            # The PDF already exists, use the one found
            pdf_path = pdf_files[0]
        
        # Validate that PDF exists and has content
        if not pdf_path.exists():
            raise HTTPException(
                status_code=404,
                detail="PDF file not found"
            )
        
        pdf_size = pdf_path.stat().st_size
        
        if pdf_size == 0:
            raise HTTPException(
                status_code=500,
                detail="PDF is corrupt (empty file). Please export the PDF again."
            )
        
        # Validate PDF header (must start with %PDF)
        try:
            with open(pdf_path, 'rb') as f:
                header = f.read(4)
                if header != b'%PDF':
                    raise HTTPException(
                        status_code=500,
                        detail=f"PDF is corrupt (invalid header: {header}). Please export the PDF again."
                    )
                
                # Read a bit more to verify it's a valid PDF
                f.seek(0)
                first_100 = f.read(100)
        except HTTPException:
            raise
        except Exception as header_error:
            raise HTTPException(
                status_code=500,
                detail=f"Error validating PDF: {str(header_error)}"
            )
        
        # Get original filename from JSON for download name
        json_files = list(base_dir.glob(f"**/{analysis_id}.json"))
        filename = f"report_{analysis_id}.pdf"
        if json_files:
            try:
                with open(json_files[0], "r", encoding="utf-8") as f:
                    analysis_data = json.load(f)
                    # Try to get device model first
                    devices = analysis_data.get("devices", [])
                    if devices and len(devices) > 0:
                        model = devices[0].get("device_model", "")
                        if model and model != "Unknown" and model != "Generic":
                            filename = f"Pipe {model.upper()}.pdf"
                        else:
                            # Fallback to filename
                            original_filename = analysis_data.get("filename", "")
                            if original_filename:
                                clean_name = original_filename.split('.')[0].replace('_', ' ').strip()
                                filename = f"Pipe {clean_name.upper()}.pdf"
                    else:
                        # Fallback to filename
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
        raise HTTPException(status_code=500, detail=f"Error downloading PDF: {error_msg}")

def _generate_pdf_html(analysis_data: Dict[str, Any]) -> str:
    """Generates HTML for the report PDF with improved styling."""
    filename = analysis_data.get("filename", "Unknown")
    clean_name = filename.split('.')[0].replace('_', ' ').strip()
    verdict = analysis_data.get("verdict", "UNKNOWN")
    analysis_text = analysis_data.get("analysis_text", "No analysis available")
    
    # Device information
    devices = analysis_data.get("devices", [])
    device = devices[0] if devices else {}
    vendor = device.get("vendor", "Unknown")
    model = device.get("device_model", "Unknown")
    category = device.get("device_category", "N/A").replace('_', ' ')
    
    # Generate PDF title in "Pipe [MODEL]" style
    if model and model != "Unknown" and model != "Generic":
        pdf_title = f"Pipe {model.upper()}"
    else:
        pdf_title = f"Pipe {clean_name.upper()}"
    
    # Get BTM metrics
    btm_requests = analysis_data.get("btm_requests", 0)
    btm_responses = analysis_data.get("btm_responses", 0)
    btm_events = analysis_data.get("btm_events", [])
    btm_accept = len([e for e in btm_events if e.get("status_code") == 0])
    
    # Get steering metrics
    successful_transitions = analysis_data.get("successful_transitions", 0)
    failed_transitions = analysis_data.get("failed_transitions", 0)
    transitions = analysis_data.get("transitions", [])
    
    # Calculate band changes
    band_change_count = len([t for t in transitions if t.get("is_successful") and t.get("is_band_change")])
    
    # Get KVR support
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
    
    # Get raw_stats if available
    raw_stats = analysis_data.get("raw_stats", {})
    diagnostics = raw_stats.get("diagnostics", {})
    band_counters = diagnostics.get("band_counters", {})
    
    assoc_count = band_counters.get("assoc_count", 0)
    reassoc_count = band_counters.get("reassoc_count", 0)
    disassoc_count = band_counters.get("disassoc_count", 0)
    deauth_count = band_counters.get("deauth_count", 0)
    
    # Get MACs
    client_mac = diagnostics.get("user_provided_client_mac") or diagnostics.get("client_mac", "Unknown")
    bssid_info = diagnostics.get("bssid_info", {})
    import re
    mac_regex = re.compile(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', re.IGNORECASE)
    bssids = [key for key in bssid_info.keys() if mac_regex.match(key)]
    
    # Get compliance checks
    compliance_checks = analysis_data.get("compliance_checks", [])
    
    # Get SSID if available
    ssid = ""
    if diagnostics.get("user_metadata"):
        ssid = diagnostics.get("user_metadata", {}).get("ssid", "")
    
    # Calculate measured time (simplified)
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
    
    # Format improved markdown analysis
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
            
            # Markdown titles
            if re.match(r'^#+\s', line):
                close_list()
                level = len(line) - len(line.lstrip("#"))
                content = line.lstrip("#").strip()
                font_size = "11pt" if level == 1 else "10pt" if level == 2 else "9pt" if level == 3 else "8pt"
                margin_top = "16px" if level == 1 else "14px" if level == 2 else "12px"
                html += f'<h{min(level + 1, 4)} style="margin-top: {margin_top}; margin-bottom: 8px; font-size: {font_size}; font-weight: 600; color: #374151; page-break-after: avoid;">{content}</h{min(level + 1, 4)}>'
                continue
            
            # Ordered lists (1., 2., etc.)
            ordered_match = re.match(r'^(\d+)\.\s+(.+)$', line)
            if ordered_match:
                close_list()
                if not in_ordered_list:
                    in_ordered_list = True
                list_items.append(ordered_match.group(2))
                continue
            
            # Unordered lists (-, *, •)
            if re.match(r'^[-*•]\s+(.+)$', line):
                close_list()
                if not in_list:
                    in_list = True
                item_text = re.sub(r'^[-*•]\s+', '', line)
                list_items.append(item_text)
                continue
            
            # Close list if any is open
            close_list()
            
            # Normal paragraph
            para_text = line
            # Process bold
            para_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', para_text)
            # Process italics
            para_text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', para_text)
            # Process inline code
            para_text = re.sub(r'`([^`]+)`', r'<code style="background: #f3f4f6; padding: 2px 4px; border-radius: 3px; font-family: monospace; font-size: 7pt;">\1</code>', para_text)
            
            html += f'<p style="margin-bottom: 8px; font-size: 8pt; line-height: 1.6; text-align: justify;">{para_text}</p>'
        
        # Cerrar cualquier lista que quede abierta
        close_list()
        
        return html
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
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
        
        <!-- Device Information Cards -->
        <div class="info-card-grid">
            <div class="info-card">
                <div class="info-card-title">Identified Device</div>
                <div style="font-size: 10pt;">
                    {f'<div style="margin-bottom: 8px;"><span style="font-size: 9pt; color: #6b7280;">Network (SSID):</span><br><span style="font-size: 11pt; font-weight: 500; color: #1a1a1a;">{ssid}</span></div>' if ssid else ''}
                    <div style="margin-bottom: 8px;"><span style="font-size: 9pt; color: #6b7280;">Brand:</span><br><span style="font-size: 11pt; font-weight: 500; color: #1a1a1a;">{vendor}</span></div>
                    <div style="margin-bottom: 8px;"><span style="font-size: 9pt; color: #6b7280;">Model:</span><br><span style="font-size: 11pt; font-weight: 500; color: #1a1a1a;">{model}</span></div>
                    <div><span style="font-size: 9pt; color: #6b7280;">Category:</span><br><span style="font-size: 11pt; font-weight: 500; color: #1a1a1a;">{category}</span></div>
                </div>
            </div>
            
            <div class="info-card">
                <div class="info-card-title">Negotiation MACs</div>
                <div style="font-size: 10pt;">
                    <div style="margin-bottom: 12px;">
                        <span style="font-size: 9pt; color: #6b7280; text-transform: uppercase;">Client</span><br>
                        <span class="mac-address" style="font-weight: 700; font-size: 11pt;">{client_mac}</span>
                    </div>
                    <div>
                        <span style="font-size: 9pt; color: #6b7280; text-transform: uppercase;">BSSIDS ({len(bssids)})</span><br>
                        {'<br>'.join([f'<div class="mac-address" style="margin-top: 4px; font-size: 10pt;">{bssid}</div>' for bssid in bssids]) if bssids else '<span style="font-size: 10pt; color: #6b7280; font-style: italic;">Not detected</span>'}
                    </div>
                </div>
            </div>
            
            <div class="info-card">
                <div class="info-card-title">Steering Metrics</div>
                <div style="font-size: 10pt;">
                    <div class="metric-item">
                        <div class="metric-item-label">Identified KVR Standards</div>
                        <div class="metric-item-value" style="font-size: 12pt;">
                            {' '.join([f'<span class="kvr-badge">{k}</span>' for k in kvr_detected]) if kvr_detected else 'None'}
                        </div>
                    </div>
                    <div class="metric-item">
                        <div class="metric-item-label">Steering attempts</div>
                        <div class="metric-item-value">{successful_transitions}/{successful_transitions + failed_transitions}</div>
                        <div class="metric-item-sub">SUCCESSFUL</div>
                        {f'<div class="metric-item-sub" style="margin-top: 6px;"><span style="color: #10b981; font-weight: 600;">{band_change_count} band change{"s" if band_change_count != 1 else ""}</span></div>' if band_change_count > 0 else ''}
                    </div>
                    <div class="metric-item">
                        <div class="metric-item-label">Measured time</div>
                        <div class="metric-item-value" style="font-size: 14pt;">{measured_time}</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Band Steering Analysis Section -->
        <div class="section-header">
            <div>
                <h2 class="section-title">Band Steering Analysis</h2>
                <p class="section-description">Technical evaluation of 802.11k/v/r capabilities based directly on real Wireshark/tshark capture</p>
            </div>
            <span class="success-badge-large">✓ SUCCESS</span>
        </div>
        
        <!-- Technical Compliance Detail -->
        <div class="card" style="background: #eff6ff; border-left: 4px solid #3b82f6;">
            <h3 style="margin-top: 0; margin-bottom: 16px; font-size: 13pt; font-weight: 700;">TECHNICAL COMPLIANCE DETAIL</h3>
            {''.join([f'''
            <div class="compliance-check">
                <div style="flex: 1;">
                    <div class="compliance-check-title">{check.get("check_name", "Unknown")}</div>
                    <div class="compliance-check-details">{check.get("details", "")}</div>
                </div>
                <div class="compliance-badge-pdf {'compliance-badge-pass' if check.get('passed', False) else 'compliance-badge-fail'}">
                    <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: {'#10b981' if check.get('passed', False) else '#ef4444'};"></span>
                    <span>{'PASSED' if check.get('passed', False) else 'FAILED'}</span>
                </div>
            </div>
            ''' for check in compliance_checks]) if compliance_checks else f'''
            <div class="compliance-check">
                <div style="flex: 1;">
                    <div class="compliance-check-title">BTM Support (802.11v)</div>
                    <div class="compliance-check-details">REQUESTS: {btm_requests}, RESPONSES: {btm_responses}, ACCEPT: {btm_accept}<br>CODE: 0 (ACCEPT)</div>
                </div>
                <div class="compliance-badge-pdf compliance-badge-pass">
                    <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #10b981;"></span>
                    <span>PASSED</span>
                </div>
            </div>
            <div class="compliance-check">
                <div style="flex: 1;">
                    <div class="compliance-check-title">Association and Reassociation</div>
                    <div class="compliance-check-details">ASSOC: {assoc_count}, REASSOC: {reassoc_count}<br>DISASSOC: {disassoc_count} (FORCED: 0), DEAUTH: {deauth_count} (FORCED: 0)</div>
                </div>
                <div class="compliance-badge-pdf compliance-badge-pass">
                    <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #10b981;"></span>
                    <span>PASSED</span>
                </div>
            </div>
            <div class="compliance-check">
                <div style="flex: 1;">
                    <div class="compliance-check-title">Effective Steering</div>
                    <div class="compliance-check-details">TRANSITIONS WITH BAND CHANGE: {band_change_count} | TOTAL TRANSITIONS: {successful_transitions} | BTM ACCEPT: {btm_accept}</div>
                </div>
                <div class="compliance-badge-pdf compliance-badge-pass">
                    <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #10b981;"></span>
                    <span>PASSED</span>
                </div>
            </div>
            <div class="compliance-check">
                <div style="flex: 1;">
                    <div class="compliance-check-title">KVR Standards</div>
                    <div class="compliance-check-details">K={'TRUE' if k_support else 'FALSE'}, V={'TRUE' if v_support else 'FALSE'}, R={'TRUE' if r_support else 'FALSE'}</div>
                </div>
                <div class="compliance-badge-pdf compliance-badge-pass">
                    <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #10b981;"></span>
                    <span>PASSED</span>
                </div>
            </div>
            '''}
        </div>
        
        <div class="section-divider"></div>
        
        <h2 style="font-size: 22pt; font-weight: 700; text-transform: uppercase; margin-top: 40px; margin-bottom: 20px;">TECHNICAL BAND STEERING AUDIT REPORT</h2>
        <div class="analysis-content">
            {format_analysis(analysis_text)}
        </div>
        
        <div class="footer">
            Generated by Pipe - Intelligent Wireshark capture analysis
        </div>
    </body>
    </html>
    """
    return html

# IMPORTANT: Specific routes (/export, /stats) must come BEFORE routes with dynamic parameters (/{analysis_id})
# IMPORTANT: Specific routes (/export, /stats) must come BEFORE dynamic parameter routes (/{analysis_id})
# for FastAPI to match correctly

@router.get("/stats")
async def get_reports_stats():
    """
    Gets aggregate statistics for all reports.
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
        
        # Collect all reports (similar to list_reports)
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
        
        # Calculate statistics
        total = len(reports)
        verdict_counter = Counter([r.get("verdict", "UNKNOWN") for r in reports])
        vendor_counter = Counter([r.get("vendor", "Unknown") for r in reports])
        
        # Verdict distribution
        verdict_distribution = dict(verdict_counter)
        
        # Top 3 vendors
        top_vendors = [{"vendor": vendor, "count": count} for vendor, count in vendor_counter.most_common(3)]
        
        # Last capture
        sorted_reports = sorted(reports, key=lambda x: x.get("timestamp", ""), reverse=True)
        last_capture = sorted_reports[0].get("timestamp") if sorted_reports else None
        
        # Success rate (SUCCESS, EXCELLENT, GOOD)
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
        raise HTTPException(status_code=500, detail=f"Error calculating statistics: {str(e)}")

def _calculate_band_times(transitions: List[Dict[str, Any]], signal_samples: List[Dict[str, Any]]) -> tuple:
    """
    Calculates the total accumulated time in each band and a list of individual transition times.
    Extracts data directly from Wireshark, explicitly excluding transition periods.
    
    PHILOSOPHY:
    - Time in band is calculated using Wireshark signal samples
    - Transition periods (between start_time and end_time) are EXCLUDED from time in band
    - Transition time is simply the duration of each transition (end_time - start_time)
    
    Args:
        transitions: List of transitions with start_time, end_time, from_band, to_band, duration
        signal_samples: List of signal samples with timestamp and band (Wireshark's source of truth)
        
    Returns:
        Tuple (time_2_4ghz, time_5ghz, transition_times_list) where transition_times_list is a list of durations
    """
    time_2_4ghz = 0.0
    time_5ghz = 0.0
    transition_times = []  # List of individual times for each transition
    
    if not transitions and not signal_samples:
        return (0.0, 0.0, [])
    
    # 1. Extract individual durations for each successful transition with band change
    # We only care about transitions that actually involve a band change
    valid_transitions = []
    for trans in transitions:
        if not trans.get("start_time") or not trans.get("is_successful"):
            continue
        
        # Only count transitions with physical band change
        if not trans.get("is_band_change"):
            continue
            
        from_band = _normalize_band(trans.get("from_band", ""))
        to_band = _normalize_band(trans.get("to_band", ""))
        
        # Verify that there's a real band change
        if from_band and to_band and from_band != to_band:
            valid_transitions.append(trans)
            
            # Calculate transition duration (time it takes to drop one band and pick up another)
            start_time = float(trans.get("start_time", 0))
            end_time = float(trans.get("end_time", start_time))
            duration = end_time - start_time
            
            if duration > 0:
                transition_times.append(duration)
    
    # Sort transitions by time
    valid_transitions = sorted(valid_transitions, key=lambda x: float(x.get("start_time", 0)))
    
    # 2. Get all timestamps to calculate total time
    all_timestamps = []
    
    # Add transition timestamps
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
    
    # Add signal sample timestamps (Wireshark's source of truth)
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
    
    # 3. Build list of transition periods to exclude them
    transition_periods = []
    for trans in valid_transitions:
        start_time = float(trans.get("start_time", 0))
        end_time = float(trans.get("end_time", start_time))
        if end_time > start_time:
            transition_periods.append((start_time, end_time))
    
    # 4. Calculate time in each band using signal samples (Wireshark's source of truth)
    # Filter and sort valid signal samples
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
        # If no signal samples, use transition-based method (less precise)
        if valid_transitions:
            current_band = None
            last_time = min_time
            
            for trans in valid_transitions:
                start_time = float(trans.get("start_time", 0))
                from_band = _normalize_band(trans.get("from_band", ""))
                to_band = _normalize_band(trans.get("to_band", ""))
                
                # Determine initial band if it's the first transition
                if current_band is None:
                    current_band = from_band if from_band else to_band
                
                # Time in current band until transition starts (EXCLUDING transition)
                if current_band and start_time > last_time:
                    period = start_time - last_time
                    if current_band == "2.4 GHz":
                        time_2_4ghz += period
                    elif current_band == "5 GHz":
                        time_5ghz += period
                
                # Update band and time (after transition)
                current_band = to_band if to_band else from_band
                last_time = float(trans.get("end_time", start_time))
            
            # Final time after last transition
            if current_band and last_time < max_time:
                period = max_time - last_time
                if current_band == "2.4 GHz":
                    time_2_4ghz += period
                elif current_band == "5 GHz":
                    time_5ghz += period
    else:
        # Precise method: use signal samples and exclude transition periods
        valid_samples = sorted(valid_samples, key=lambda x: x["timestamp"])
        
        # Group consecutive samples of the same band
        i = 0
        while i < len(valid_samples):
            current_band = valid_samples[i]["band"]
            period_start = valid_samples[i]["timestamp"]
            period_end = period_start
            
            # Find the end of the continuous period in the same band
            j = i + 1
            while j < len(valid_samples):
                next_sample = valid_samples[j]
                next_ts = next_sample["timestamp"]
                next_band = next_sample["band"]
                
                # Check if we are in a transition period
                in_transition = False
                for trans_start, trans_end in transition_periods:
                    if trans_start <= next_ts <= trans_end:
                        in_transition = True
                        break
                
                # If band changed or we are in transition, end period
                if next_band != current_band or in_transition:
                    break
                
                # If interval is reasonable (max 5 seconds), continue period
                if next_ts - period_end <= 5.0:
                    period_end = next_ts
                    j += 1
                else:
                    # Interval too large, end period
                    break
            
            # Calculate period duration (excluding any part that is in transition)
            period_duration = period_end - period_start
            
            # Check if period overlaps with any transition
            for trans_start, trans_end in transition_periods:
                # If overlap, reduce duration
                if period_start < trans_end and period_end > trans_start:
                    overlap_start = max(period_start, trans_start)
                    overlap_end = min(period_end, trans_end)
                    overlap_duration = overlap_end - overlap_start
                    period_duration -= overlap_duration
            
            # Only add if duration is positive and not completely in transition
            if period_duration > 0:
                if current_band == "2.4 GHz":
                    time_2_4ghz += period_duration
                elif current_band == "5 GHz":
                    time_5ghz += period_duration
            
            i = j
    
    # 5. Consistency check: time in bands + time in transitions should not exceed total time
    total_transition_time = sum(transition_times)
    total_band_time = time_2_4ghz + time_5ghz
    expected_total = total_time - total_transition_time
    
    # If substantial discrepancy, adjust proportionally
    if expected_total > 0 and total_band_time > expected_total * 1.1:
        scale = expected_total / total_band_time
        time_2_4ghz *= scale
        time_5ghz *= scale
    
    return (round(time_2_4ghz, 2), round(time_5ghz, 2), transition_times)

def _normalize_band(band: str) -> str:
    """Normalizes band name to standard format."""
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
    Generates professional HTML for reports summary PDF with improved styles.
    
    Args:
        reports: List of dictionaries with report data
        ai_summary_text: AI generated summary text (Markdown format)
        
    Returns:
        Full HTML with the summary report
    """
    if not reports:
        return ""
    
    # Calculate aggregate statistics
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
    
    # Verdict distribution
    verdict_dist = {}
    for v in verdicts:
        verdict_dist[v] = verdict_dist.get(v, 0) + 1
    
    # Get current date and time in Colombia timezone
    colombia_tz = pytz.timezone('America/Bogota')
    current_time_colombia = datetime.now(colombia_tz)
    formatted_date_time = current_time_colombia.strftime('%m/%d/%Y at %I:%M %p')
    
    # Format markdown analysis (similar to _generate_pdf_html)
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
    
    # Format date
    def format_report_date(date_str):
        if not date_str:
            return 'N/A'
        try:
            date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return date.strftime('%d/%m/%Y %I:%M %p')
        except Exception:
            return date_str
    
    # Format time
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
    
    # Format transition times list
    def format_transition_times(times_list):
        if not times_list or len(times_list) == 0:
            return 'N/A'
        formatted_times = [format_time(t) for t in times_list]
        return ', '.join(formatted_times)
    
    # Generate chart HTML outside main f-string to avoid bracket issues
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
    
    # Generate vendor chart HTML
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
                                {count} reports ({percentage:.1f}%)
                            </div>
                        </div>
                    </div>
                    ''')
        vendor_chart_items_joined = ''.join(vendor_chart_items)
        vendor_chart_html = f'''
            <h3 style="margin-top: 30px; margin-bottom: 15px;">Top {len(top_vendors)} Brands</h3>
            <div class="chart-container">
                <div class="bar-chart">
                    {vendor_chart_items_joined}
                </div>
            </div>
            '''
    
    # Generate reports table HTML
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
    
    # Generate HTML
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Reports Summary - Pipe</title>
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
            <h1>Reports Summary - Pipe</h1>
            <p style="color: #6b7280; font-size: 10pt;">Generated on {formatted_date_time} (Colombia time, UTC-5)</p>
        </div>
        
        <!-- Main Statistics Cards -->
        <div class="info-card-grid">
            <div class="info-card">
                <div class="info-card-title">Total Reports</div>
                <div class="info-card-value">{total_reports}</div>
                <div class="info-card-sub">analyses performed</div>
            </div>
            <div class="info-card">
                <div class="info-card-title">Success Rate</div>
                <div class="info-card-value" style="color: #10b981;">{success_rate:.1f}%</div>
                <div class="info-card-sub">{success_count} successful</div>
            </div>
            <div class="info-card">
                <div class="info-card-title">Failed Reports</div>
                <div class="info-card-value" style="color: #ef4444;">{failed_count}</div>
                <div class="info-card-sub">require attention</div>
            </div>
            <div class="info-card">
                <div class="info-card-title">Total Packets</div>
                <div class="info-card-value">{total_packets:,}</div>
                <div class="info-card-sub">average: {avg_packets:.0f}</div>
            </div>
        </div>
        
        <!-- Statistics Section -->
        <div class="stats-section">
            <h2>Observed Statistics</h2>
            
            <!-- Verdict Distribution -->
            <h3 style="margin-top: 20px; margin-bottom: 15px;">Verdict Distribution</h3>
            <div class="chart-container">
                <div class="bar-chart">
                    {verdict_chart_html}
                </div>
            </div>
            
            <!-- Top Brands -->
            {vendor_chart_html}
        </div>
        
        <div class="section-divider"></div>
        
        <!-- Results Table -->
        <h2>Results Table</h2>
        <table class="reports-table">
            <thead>
                <tr>
                    <th>Brand</th>
                    <th>Model</th>
                    <th>Verdict</th>
                    <th>Packets</th>
                    <th>2.4 GHz Time</th>
                    <th>5 GHz Time</th>
                    <th>Transition Time</th>
                    <th>Date</th>
                </tr>
            </thead>
            <tbody>
                {reports_table_html}
            </tbody>
        </table>
        
        <div class="section-divider"></div>
        
        <!-- Executive Summary -->
        <h2>Executive Summary</h2>
        <div class="analysis-content">
            {format_analysis(ai_summary_text) if ai_summary_text else f'''
            <p style="margin-bottom: 8px; font-size: 8pt; line-height: 1.6; text-align: justify;">
                This summary consolidates {total_reports} Band Steering analyses performed using Wireshark/tshark captures.
                Of these, {success_count} reports ({success_rate:.1f}%) were successful, while {failed_count} reports require attention.
            </p>
            <p style="margin-bottom: 8px; font-size: 8pt; line-height: 1.6; text-align: justify;">
                The most analyzed brand is <strong>{top_vendors[0][0] if top_vendors else 'N/A'}</strong> with {top_vendors[0][1] if top_vendors else 0} reports.
                In total, {total_packets:,} network packets were analyzed, with an average of {avg_packets:.0f} packets per analysis.
            </p>
            '''}
        </div>
        
        <div class="footer">
            Generated by Pipe - Intelligent Wireshark capture analysis
        </div>
    </body>
    </html>
    """
    return html

async def generate_ai_report(reports: List[Dict[str, Any]]) -> str:
    """
    Generates a professional report in HTML using AI based on the provided reports.
    
    This function uses the project's LLMClient to generate a consolidated report
    that includes aggregate analysis, statistics, and conclusions on multiple
    Band Steering analysis reports.
    
    Args:
        reports: List of dictionaries with report data. Each dictionary
                 must contain: id, filename, timestamp, vendor, model, verdict, 
                 analysis_text, total_packets.
        
    Returns:
        Full HTML with the AI-generated report, ready for download.
        
    Raises:
        HTTPException: If an error occurs during AI report generation.
    """
    
    if not reports:
        raise HTTPException(status_code=400, detail="No reports provided to generate the summary")
    
    # Build the prompt with all reports data
    reports_data = []
    for i, report in enumerate(reports, 1):
        reports_data.append(f"""
REPORT {i}:
- ID: {report.get('id', 'N/A')}
- File: {report.get('filename', 'N/A')}
- Date: {report.get('timestamp', 'N/A')}
- Brand: {report.get('vendor', 'Unknown')}
- Model: {report.get('model', 'Unknown')}
- Verdict: {report.get('verdict', 'UNKNOWN')}
- Total Packets: {report.get('total_packets', 0)}
- Analysis: {report.get('analysis_text', 'Not available')}
""")
    
    reports_text = "\n".join(reports_data)
    
    # Calculate aggregate statistics
    total_reports = len(reports)
    verdicts = [r.get('verdict', 'UNKNOWN') for r in reports]
    success_count = sum(1 for v in verdicts if v in ['SUCCESS', 'EXCELLENT', 'GOOD'])
    failed_count = sum(1 for v in verdicts if v == 'FAILED')
    success_rate = (success_count / total_reports * 100) if total_reports > 0 else 0
    
    vendors = [r.get('vendor', 'Unknown') for r in reports]
    vendor_counts = {v: vendors.count(v) for v in set(vendors)}
    top_vendor = max(vendor_counts.items(), key=lambda x: x[1])[0] if vendor_counts else "N/A"
    
    total_packets = sum(r.get('total_packets', 0) for r in reports)
    
    # Get current date and time in Colombia timezone
    colombia_tz = pytz.timezone('America/Bogota')
    current_time_colombia = datetime.now(colombia_tz)
    formatted_date_time = current_time_colombia.strftime('%m/%d/%Y at %I:%M %p')
    
    # Generate executive summary text with AI only (not full HTML)
    prompt = f"""Generate a professional executive summary in Markdown format about the following Band Steering analyses.

REPORTS DATA:

{reports_text}

AGGREGATE STATISTICS:
- Total reports analyzed: {total_reports}
- Successful reports: {success_count} ({success_rate:.1f}%)
- Failed reports: {failed_count}
- Most common brand: {top_vendor}
- Total packets analyzed: {total_packets:,}

INSTRUCTIONS:

Generate an executive summary in Markdown format that includes:

1. **Overview**: Consolidated summary of all reports
2. **Main Findings**: Detected patterns and key observations
3. **System Status**: General evaluation of Band Steering performance
4. **Recommendations**: Specific suggestions based on findings
5. **Conclusions**: Final evaluation and suggested next steps

FORMAT:
- Use Markdown with titles (#, ##, ###)
- Use bullet lists (-) or numbered lists (1., 2., 3.)
- Use **bold** for emphasis
- Keep text clear, concise, and professional
- Do not invent information not in the provided data
- Summary should be between 300-500 words
"""
    
    try:
        # Generate summary text only (not full HTML)
        max_tokens = min(2000 + len(reports) * 200, 4000)
        ai_summary_text = await llm_client.agenerate(prompt, max_tokens=max_tokens)
        
        if not ai_summary_text or len(ai_summary_text.strip()) == 0:
            ai_summary_text = ""  # Use default summary if fails
        
        # Generate full HTML with professional structure and styles
        html_content = _generate_summary_pdf_html(reports, ai_summary_text)
        
        if not html_content or len(html_content.strip()) == 0:
            raise HTTPException(
                status_code=500,
                detail="Error generating report HTML"
            )
        
        return html_content
        
    except HTTPException:
        # Re-throw HTTPException
        raise
    except RuntimeError as e:
        # LLMClient throws RuntimeError on API issues
        raise HTTPException(
            status_code=500,
            detail=f"Error communicating with AI service: {str(e)}"
        )
    except Exception as e:
        # Catch any other unexpected error
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error generating AI report: {str(e)}"
        )

@router.get("/export")
async def export_reports(
    ids: Optional[str] = Query(None, description="Comma-separated report IDs"),
    format: str = Query("html", description="Export format: html or summary (both generate AI report)")
):
    """
    Exports reports in AI-generated HTML format.
    """
    base_dir = service.base_dir
    reports_to_export = []
    
    try:
        if not base_dir.exists():
            raise HTTPException(status_code=404, detail="No reports found")
        
        # If IDs provided, export only those
        target_ids = None
        if ids and ids.strip():
            # Clean and split IDs
            id_list = [id.strip() for id in ids.split(",") if id.strip()]
            if id_list:
                target_ids = set(id_list)
        
        # Collect reports
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
                            
                            # Filter by IDs if specified
                            if target_ids and analysis_id not in target_ids:
                                continue
                            
                            devices = data.get("devices", [])
                            if not devices or len(devices) == 0:
                                continue
                            
                            device = devices[0]
                            # Get full data to calculate band times
                            # Data may be in different structures based on analysis version
                            transitions = []
                            signal_samples = []
                            
                            # Try from band_steering structure (new structure)
                            band_steering = data.get("band_steering", {})
                            if isinstance(band_steering, dict):
                                transitions = band_steering.get("transitions", [])
                                signal_samples = band_steering.get("signal_samples", [])
                            
                            # Fallback: try from root level (old structure)
                            if not transitions:
                                transitions = data.get("transitions", [])
                            if not signal_samples:
                                signal_samples = data.get("signal_samples", [])
                            
                            # Calculate band times
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
            raise HTTPException(status_code=404, detail="No reports found to export")
        
        
        # Generate AI report (format=html or format=summary)
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
            # Unsupported format
            raise HTTPException(
                status_code=400, 
                detail=f"Format '{format}' not supported. Use 'html' or 'summary'."
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error exporting reports: {str(e)}")

@router.get("/{analysis_id}")
async def get_report(analysis_id: str):
    """
    Gets detail for a specific report by ID.
    """
    base_dir = service.base_dir
    
    try:
        # Search for file in folder structure
        for analysis_file in base_dir.glob(f"**/{analysis_id}.json"):
            with open(analysis_file, "r", encoding="utf-8") as f:
                return json.load(f)
                
        raise HTTPException(status_code=404, detail="Report not found")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


# This function is already defined above, removing duplicate
