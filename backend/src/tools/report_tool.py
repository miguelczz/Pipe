"""
Herramienta para obtener un reporte de análisis por ID.
Devuelve un resumen completo y estructurado con todos los datos del análisis,
para que el agente pueda responder preguntas específicas sobre el reporte.
"""
import json
from pathlib import Path
from typing import Optional

# Límite: ~8k tokens ≈ 6000 caracteres. Necesitamos incluir todos los datos
# estructurados para que el agente responda con precisión.
MAX_REPORT_CHARS = 6000


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
    Construye un resumen completo y estructurado del reporte.
    Incluye TODOS los datos numéricos y técnicos para que el agente
    pueda responder cualquier pregunta sobre el análisis.
    """
    parts = []

    # ── Cabecera ──
    analysis_id = data.get("analysis_id", data.get("id", "N/A"))
    verdict = data.get("verdict", "N/A")
    filename = data.get("file_name", data.get("filename", "N/A"))
    parts.append(f"=== REPORTE DE ANÁLISIS ===\nID: {analysis_id}\nArchivo: {filename}\nVeredicto: {verdict}")

    # ── Dispositivos ──
    devices = data.get("devices", [])
    if devices:
        dev_lines = ["--- Dispositivos Identificados ---"]
        for dev in devices[:5]:
            mac = dev.get("mac_address", "N/A")
            vendor = dev.get("vendor", dev.get("device_vendor", "N/A"))
            model = dev.get("device_model", dev.get("model", "N/A"))
            category = dev.get("device_category", "N/A")
            dev_lines.append(f"  MAC: {mac} | Marca: {vendor} | Modelo: {model} | Categoría: {category}")
        parts.append("\n".join(dev_lines))

    # ── Estándares KVR ──
    kvr = data.get("kvr_support", {})
    if kvr:
        k = kvr.get("k_support", "N/A")
        v = kvr.get("v_support", "N/A")
        r = kvr.get("r_support", "N/A")
        parts.append(f"--- Soporte Estándares KVR ---\n  802.11k (Neighbor Report): {k}\n  802.11v (BSS Transition): {v}\n  802.11r (Fast Roaming): {r}")

    # ── Estadísticas BTM ──
    btm_req = data.get("btm_requests", "N/A")
    btm_res = data.get("btm_responses", "N/A")
    btm_rate = data.get("btm_success_rate", "N/A")
    succ_trans = data.get("successful_transitions", "N/A")
    fail_trans = data.get("failed_transitions", "N/A")
    loops = data.get("loops_detected", "N/A")
    parts.append(
        f"--- Estadísticas BTM ---\n"
        f"  BTM Requests: {btm_req}\n  BTM Responses: {btm_res}\n  BTM Success Rate: {btm_rate}\n"
        f"  Transiciones exitosas: {succ_trans}\n  Transiciones fallidas: {fail_trans}\n"
        f"  Loops detectados: {loops}"
    )

    # ── Compliance Checks ──
    checks = data.get("compliance_checks", [])
    # Fallback: en algunos reportes están dentro de band_steering
    if not checks:
        bs = data.get("band_steering", {})
        if isinstance(bs, dict):
            checks = bs.get("compliance_checks", [])
    if checks:
        check_lines = ["--- Cumplimiento Técnico ---"]
        for c in checks[:10]:
            name = c.get("check_name", c.get("name", ""))
            passed = c.get("passed", c.get("status", "N/A"))
            details = c.get("details", "")
            severity = c.get("severity", "")
            line = f"  [{passed}] {name}"
            if severity:
                line += f" (severidad: {severity})"
            if details:
                line += f"\n       Detalles: {details}"
            check_lines.append(line)
        parts.append("\n".join(check_lines))

    # ── Transiciones de banda ──
    transitions = data.get("transitions", [])
    if not transitions:
        bs = data.get("band_steering", {})
        if isinstance(bs, dict):
            transitions = bs.get("transitions", [])
    if transitions:
        trans_lines = [f"--- Transiciones de Banda ({len(transitions)} total) ---"]
        for i, t in enumerate(transitions[:8], 1):
            fr_band = t.get("from_band", "?")
            to_band = t.get("to_band", "?")
            fr_bssid = t.get("from_bssid", "?")
            to_bssid = t.get("to_bssid", "?")
            is_band_change = t.get("is_band_change", "?")
            is_success = t.get("is_successful", "?")
            steering = t.get("steering_type", "?")
            trans_lines.append(
                f"  {i}. {fr_band} → {to_band} | BSSID: {fr_bssid} → {to_bssid} | "
                f"Cambio de banda: {is_band_change} | Exitosa: {is_success} | Tipo: {steering}"
            )
        parts.append("\n".join(trans_lines))

    # ── Estadísticas generales ──
    total_pkts = data.get("total_packets", "N/A")
    wlan_pkts = data.get("wlan_packets", "N/A")
    duration = data.get("analysis_duration_ms", "N/A")
    parts.append(f"--- Paquetes ---\n  Total: {total_pkts} | WLAN: {wlan_pkts} | Duración análisis: {duration} ms")

    # ── Análisis textual (resumen narrativo) ──
    analysis_text = data.get("analysis_text", "")
    if analysis_text:
        # Incluir porción significativa del texto narrativo
        max_text = 1500
        text_snippet = analysis_text[:max_text].strip()
        if len(analysis_text) > max_text:
            text_snippet += "\n[... texto completo truncado ...]"
        parts.append(f"--- Análisis Narrativo ---\n{text_snippet}")

    raw = "\n\n".join(parts)
    if len(raw) > MAX_REPORT_CHARS:
        raw = raw[:MAX_REPORT_CHARS] + "\n[... resumen truncado ...]"
    return raw


def get_report(report_id: str, user_question: Optional[str] = None) -> str:
    """
    Obtiene un reporte por ID y devuelve un resumen completo en texto plano
    con todos los datos estructurados del análisis.

    Args:
        report_id: ID del análisis (analysis_id).
        user_question: Pregunta del usuario (reservado para uso futuro).

    Returns:
        Resumen del reporte en texto, o mensaje de error si no se encuentra.
    """
    if not report_id or not str(report_id).strip():
        return "Error: no se proporcionó ID de reporte."
    data = _load_report_json(str(report_id).strip())
    if not data:
        return f"No se encontró el reporte con ID '{report_id}'. Verifica que el análisis exista en Reportes."
    return _build_summary(data, user_question)
