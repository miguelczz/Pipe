import json
from pathlib import Path

from backend.src.services.band_steering_service import BandSteeringService


def _load_sample_analysis_json() -> dict:
    """
    Carga un JSON de análisis ya generado para validar coherencia básica.
    Se usa como prueba de regresión ligera: verifica que los contadores
    expuestos en BandSteeringAnalysis no se desalineen de wireshark_raw.
    """
    # Tomamos un archivo existente en data/analyses (Xiaomi como ejemplo)
    base_dir = Path("backend") / "data" / "analyses"
    # Buscar cualquier archivo JSON disponible
    sample = next(base_dir.rglob("*.json"))
    with sample.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_wireshark_raw_vs_analysis_counters():
    data = _load_sample_analysis_json()

    # Estructura esperada según BandSteeringService._save_analysis_result
    wireshark_raw = data.get("raw_stats", {}).get("diagnostics", {}).get("wireshark_raw", {})
    steering_analysis = data.get("raw_stats", {}).get("steering_analysis", {})

    summary = wireshark_raw.get("summary", {})
    btm_raw = summary.get("btm", {})

    # Verificamos que los contadores principales estén presentes
    assert "steering_attempts" in steering_analysis
    assert "successful_transitions" in steering_analysis

    # Si Wireshark detectó BTM Requests o Accepts, los valores agregados
    # no pueden ser cero al mismo tiempo (coherencia mínima).
    raw_reqs = btm_raw.get("requests", 0)
    raw_accept = btm_raw.get("responses_accept", 0)

    if raw_reqs > 0 or raw_accept > 0:
        assert steering_analysis["steering_attempts"] >= raw_reqs
        assert steering_analysis["successful_transitions"] >= raw_accept

