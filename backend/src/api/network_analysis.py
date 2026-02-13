"""
Endpoints for network capture analysis (Wireshark / PCAP) assisted by AI.
Exposes the flow orchestrated by BandSteeringService without additional
logging or business responsibilities.
"""

import asyncio
import concurrent.futures
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
import json
from fastapi.responses import JSONResponse

from ..services.band_steering_service import BandSteeringService

router = APIRouter(prefix="/network-analysis", tags=["network-analysis"])

# Instantiate orchestrator service
band_steering_service = BandSteeringService()

# Thread pool executor for heavy tshark operations
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="wireshark_analysis")


@router.post("/analyze")
async def analyze_network_capture(
    file: UploadFile = File(...),
    user_metadata: str | None = Form(None),
):
    """
    Uploads a capture file and performs the full Band Steering process.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="A capture file must be provided.")

    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".pcap") or filename_lower.endswith(".pcapng")):
        raise HTTPException(
            status_code=400,
            detail="Only .pcap or .pcapng capture files are accepted.",
        )

    # Temporary directory for upload
    base_dir = Path(__file__).resolve().parents[2]
    uploads_dir = base_dir / "databases" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    temp_name = f"{uuid.uuid4()}_{file.filename}"
    temp_path = uploads_dir / temp_name
    
    try:
        content = await file.read()
        temp_path.write_bytes(content)


        # Parse optional user metadata (SSID, client MAC, etc.)
        metadata_dict = None
        if user_metadata:
            try:
                metadata_dict = json.loads(user_metadata)
            except json.JSONDecodeError:
                metadata_dict = None

        # Execute the service in a separate thread (tshark is blocking)
        # Ensure temp_path is absolute before passing it to the service
        temp_path_abs = temp_path.resolve()
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
        # CRITICAL: The temporary file must exist when the analysis is saved
        # Ensure the path is absolute and the file exists
        if not temp_path_abs.exists():
            raise HTTPException(
                status_code=500,
                detail="Temporary file was lost during processing",
            )

        analysis = result_pkg["analysis"]
        raw_stats = result_pkg["raw_stats"]

        # Format response for FULL compatibility with the current frontend
        try:
            # Safely serialize all Pydantic objects
            response_data = {
                "file_name": analysis.filename,
                "analysis": analysis.analysis_text,
                "stats": raw_stats,  # Keep stats structure for the dashboard
                "band_steering": {
                    "analysis_id": analysis.analysis_id,
                    "verdict": analysis.verdict,
                    "device": analysis.devices[0].model_dump() if analysis.devices and len(analysis.devices) > 0 else {},
                    "compliance_checks": [c.model_dump(mode='json') for c in analysis.compliance_checks] if analysis.compliance_checks else [],
                    "fragments_count": len(analysis.fragments) if analysis.fragments else 0,
                    # Add data for Band Steering chart
                    "btm_events": [e.model_dump(mode='json') for e in analysis.btm_events] if analysis.btm_events else [],
                    "transitions": [t.model_dump(mode='json') for t in analysis.transitions] if analysis.transitions else [],
                    "signal_samples": [s.model_dump(mode='json') for s in analysis.signal_samples] if analysis.signal_samples else []
                }
            }
            return JSONResponse(content=response_data)
        except Exception as serialization_error:
            # Try minimal response
            try:
                minimal_response = {
                    "file_name": analysis.filename if hasattr(analysis, 'filename') else "unknown",
                    "analysis": analysis.analysis_text if hasattr(analysis, 'analysis_text') else "Error generating analysis",
                    "stats": raw_stats,
                    "band_steering": {
                        "analysis_id": str(analysis.analysis_id) if hasattr(analysis, 'analysis_id') else "unknown",
                        "verdict": str(analysis.verdict) if hasattr(analysis, 'verdict') else "UNKNOWN",
                        "error": f"Serialization error: {str(serialization_error)}"
                    }
                }
                return JSONResponse(content=minimal_response)
            except Exception:
                raise HTTPException(
                    status_code=500,
                    detail=f"Critical error serializing response: {str(serialization_error)}"
                )
    except RuntimeError as e:
        # Typical errors from pyshark/tshark not installed
        raise HTTPException(
            status_code=500,
            detail=(
                "Capture could not be analyzed because pyshark/tshark are not available "
                "on the server. Contact administrator to install these dependencies."
            ),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing network capture: {str(e)}",
        )
    finally:
        # DO NOT delete the file - it will be saved for later download
        # The file will be moved to the analysis folder in band_steering_service
        pass


