"""
Herramienta para obtener un reporte de análisis por ID.
Devuelve un resumen acotado en tokens (4k-6k aprox.) y opcionalmente enfocado en la pregunta del usuario.
"""
import json
from pathlib import Path
from typing import Optional

# Límite aproximado: ~4k-6k tokens ≈ 2000-3000 caracteres para el resumen
MAX_REPORT_CHARS = 2800


def _get_base_dir() -> Path:
    """Mismo directorio base que BandSteeringService (reportes guardados)."""
    base = Path("data/analyses")
    if not base.is_absolute():
        base = base.resolve()
    return base


def _load_report_json(report_id: str) -> Optional[dict]:
    """Carga el JSON del reporte desde disco. Retorna None si no existe."""
    base_dir = _get_base_dir()
    if not base_dir.exists():
        return None
    for path in base_dir.glob(f"**/{report_id}.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _build_summary(data: dict, user_question: Optional[str] = None) -> str:
    """
    Construye un resumen estructurado del reporte.
    Si user_question está informado, prioriza secciones relevantes (por palabras clave).
    """
    parts = []
    q_lower = (user_question or "").lower()

    # Siempre incluir cabecera breve
    analysis_id = data.get("analysis_id", data.get("id", "N/A"))
    verdict = data.get("verdict", "N/A")
    filename = data.get("file_name", data.get("filename", "N/A"))
    parts.append(f"Reporte: {analysis_id}\nArchivo: {filename}\nVeredicto: {verdict}")

    # Dispositivo
    device = data.get("band_steering", {}).get("device", {}) if isinstance(data.get("band_steering"), dict) else {}
    if not device:
        device = data.get("device", {})
    if device:
        vendor = device.get("vendor", device.get("device_vendor", "N/A"))
        model = device.get("device_model", device.get("model", "N/A"))
        parts.append(f"Dispositivo: {vendor} - {model}")

    # Análisis textual (siempre útil)
    analysis_text = data.get("analysis_text", "")
    if analysis_text:
        # Si hay pregunta, priorizar párrafos que mencionen términos de la pregunta
        if q_lower and len(analysis_text) > 800:
            words = [w.strip() for w in q_lower.split() if len(w) > 2]
            if words:
                # Incluir los primeros 400 chars y luego los que contengan palabras clave
                parts.append("Análisis:")
                parts.append(analysis_text[:400].strip())
                rest = analysis_text[400:]
                for w in words[:5]:
                    if w in rest.lower():
                        idx = rest.lower().find(w)
                        start = max(0, idx - 80)
                        end = min(len(rest), idx + 120)
                        snippet = rest[start:end].strip()
                        if snippet and snippet not in "\n".join(parts):
                            parts.append("..." + snippet + "...")
        else:
            parts.append("Análisis:")
            parts.append(analysis_text[:1200].strip() if len(analysis_text) > 1200 else analysis_text)

    # Compliance / BTM si la pregunta lo menciona o si hay espacio
    focus_btm = not q_lower or any(k in q_lower for k in ["btm", "cumplimiento", "compliance", "802.11", "kvr", "transición", "transicion"])
    band_steering = data.get("band_steering") or {}
    if isinstance(band_steering, dict) and (focus_btm or len(parts) < 5):
        checks = band_steering.get("compliance_checks", [])
        if checks:
            parts.append("Cumplimiento técnico:")
            for c in checks[:8]:
                name = c.get("check_name", c.get("name", ""))
                status = c.get("status", c.get("passed", ""))
                parts.append(f"  - {name}: {status}")
        transitions = band_steering.get("transitions", [])
        if transitions:
            parts.append(f"Transiciones de banda: {len(transitions)}")
            for t in transitions[:5]:
                fr = t.get("fromBand", t.get("from_band", ""))
                to = t.get("toBand", t.get("to_band", ""))
                parts.append(f"  {fr} → {to}")

    raw = "\n\n".join(parts)
    if len(raw) > MAX_REPORT_CHARS:
        raw = raw[:MAX_REPORT_CHARS] + "\n[... resumen truncado ...]"
    return raw


def get_report(report_id: str, user_question: Optional[str] = None) -> str:
    """
    Obtiene un reporte por ID y devuelve un resumen en texto plano,
    acotado a ~4k-6k tokens y opcionalmente enfocado en user_question.

    Args:
        report_id: ID del análisis (analysis_id).
        user_question: Pregunta del usuario para priorizar secciones relevantes.

    Returns:
        Resumen del reporte en texto, o mensaje de error si no se encuentra.
    """
    if not report_id or not str(report_id).strip():
        return "Error: no se proporcionó ID de reporte."
    data = _load_report_json(str(report_id).strip())
    if not data:
        return f"No se encontró el reporte con ID '{report_id}'. Verifica que el análisis exista en Reportes."
    return _build_summary(data, user_question)
