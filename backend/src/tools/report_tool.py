"""
Tool to obtain an analysis report by ID.
Returns a complete and structured summary with all analysis data,
so that the agent can answer specific questions about the report.
"""
import json
from pathlib import Path
from typing import Optional

# Limit: ~8k tokens ≈ 6000 characters. We need to include all the data
# structured for the agent to respond with precision.
MAX_REPORT_CHARS = 6000


def _get_base_dir() -> Path:
    """Same base directory as BandSteeringService (saved reports)."""
    base = Path("data/analyses")
    if not base.is_absolute():
        base = base.resolve()
    return base


def _load_report_json(report_id: str) -> Optional[dict]:
    """Loads report JSON from disk. Returns None if it does not exist."""
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
    Builds a complete and structured summary of the report.
    Includes ALL numerical and technical data so that the agent
    can answer any question about the analysis.
    """
    parts = []

    # ── Header ──
    analysis_id = data.get("analysis_id", data.get("id", "N/A"))
    verdict = data.get("verdict", "N/A")
    filename = data.get("file_name", data.get("filename", "N/A"))
    parts.append(f"=== ANALYSIS REPORT ===\nID: {analysis_id}\nFile: {filename}\nVerdict: {verdict}")

    # ── Devices ──
    devices = data.get("devices", [])
    if devices:
        dev_lines = ["--- Identified Devices ---"]
        for dev in devices[:5]:
            mac = dev.get("mac_address", "N/A")
            vendor = dev.get("vendor", dev.get("device_vendor", "N/A"))
            model = dev.get("device_model", dev.get("model", "N/A"))
            category = dev.get("device_category", "N/A")
            dev_lines.append(f"  MAC: {mac} | Vendor: {vendor} | Model: {model} | Category: {category}")
        parts.append("\n".join(dev_lines))

    # ── KVR Standards ──
    kvr = data.get("kvr_support", {})
    if kvr:
        k = kvr.get("k_support", "N/A")
        v = kvr.get("v_support", "N/A")
        r = kvr.get("r_support", "N/A")
        parts.append(f"--- KVR Standards Support ---\n  802.11k (Neighbor Report): {k}\n  802.11v (BSS Transition): {v}\n  802.11r (Fast Roaming): {r}")

    # ── BTM Statistics ──
    btm_req = data.get("btm_requests", "N/A")
    btm_res = data.get("btm_responses", "N/A")
    btm_rate = data.get("btm_success_rate", "N/A")
    succ_trans = data.get("successful_transitions", "N/A")
    fail_trans = data.get("failed_transitions", "N/A")
    loops = data.get("loops_detected", "N/A")
    parts.append(
        f"--- BTM Statistics ---\n"
        f"  BTM Requests: {btm_req}\n  BTM Responses: {btm_res}\n  BTM Success Rate: {btm_rate}\n"
        f"  Successful transitions: {succ_trans}\n  Failed transitions: {fail_trans}\n"
        f"  Loops detected: {loops}"
    )

    # ── Compliance Checks ──
    checks = data.get("compliance_checks", [])
    # Fallback: in some reports they are inside band_steering
    if not checks:
        bs = data.get("band_steering", {})
        if isinstance(bs, dict):
            checks = bs.get("compliance_checks", [])
    if checks:
        check_lines = ["--- Technical Compliance ---"]
        for c in checks[:10]:
            name = c.get("check_name", c.get("name", ""))
            passed = c.get("passed", c.get("status", "N/A"))
            details = c.get("details", "")
            severity = c.get("severity", "")
            line = f"  [{passed}] {name}"
            if severity:
                line += f" (severity: {severity})"
            if details:
                line += f"\n       Details: {details}"
            check_lines.append(line)
        parts.append("\n".join(check_lines))

    # ── Band transitions ──
    transitions = data.get("transitions", [])
    if not transitions:
        bs = data.get("band_steering", {})
        if isinstance(bs, dict):
            transitions = bs.get("transitions", [])
    if transitions:
        trans_lines = [f"--- Band Transitions ({len(transitions)} total) ---"]
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
                f"Band change: {is_band_change} | Successful: {is_success} | Type: {steering}"
            )
        parts.append("\n".join(trans_lines))

    # ── General statistics ──
    total_pkts = data.get("total_packets", "N/A")
    wlan_pkts = data.get("wlan_packets", "N/A")
    duration = data.get("analysis_duration_ms", "N/A")
    parts.append(f"--- Packets ---\n  Total: {total_pkts} | WLAN: {wlan_pkts} | Analysis duration: {duration} ms")

    # ── Textual analysis (narrative summary) ──
    analysis_text = data.get("analysis_text", "")
    if analysis_text:
        # Include a significant portion of the narrative text
        max_text = 1500
        text_snippet = analysis_text[:max_text].strip()
        if len(analysis_text) > max_text:
            text_snippet += "\n[... full text truncated ...]"
        parts.append(f"--- Narrative Analysis ---\n{text_snippet}")

    raw = "\n\n".join(parts)
    if len(raw) > MAX_REPORT_CHARS:
        raw = raw[:MAX_REPORT_CHARS] + "\n[... summary truncated ...]"
    return raw


def get_report(report_id: str, user_question: Optional[str] = None) -> str:
    """
    Obtains a report by ID and returns a complete summary in plain text
    with all the structured data of the analysis.

    Args:
        report_id: Analysis ID (analysis_id).
        user_question: User question (reserved for future use).

    Returns:
        Report summary in text, or error message if not found.
    """
    if not report_id or not str(report_id).strip():
        return "Error: report ID not provided."
    data = _load_report_json(str(report_id).strip())
    if not data:
        return f"Report with ID '{report_id}' not found. Please verify that the analysis exists in Reports."
    return _build_summary(data, user_question)
