"""
Specialized tool for BSS Transition Management (802.11v) and Band Steering analysis.

This class encapsulates domain logic related to:
- Construction of BTM events from raw data.
- Analysis of transitions and steering patterns.
- Calculation of metrics and compliance checks.
- Determination of the final analysis verdict.

Data extraction from captures and complete flow orchestration
are delegated to the service and capture tools.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

from ..models.btm_schemas import (
    BandSteeringAnalysis,
    BTMEvent,
    BTMStatusCode,
    SteeringTransition,
    SteeringType,
    ComplianceCheck,
    KVRSupport,
    DeviceInfo,
    DeviceCategory,
    CaptureFragment,
    SignalSample,
)
from ..utils.deauth_validator import DeauthValidator, REASSOC_TIMEOUT_SECONDS


class BTMAnalyzer:
    """
    Specialized analyzer in BTM and Steering.

    Focuses exclusively on business rules and analysis logic,
    keeping data extraction and process orchestration
    responsibilities separate.
    """

    def analyze_btm_events(
        self, 
        steering_events: List[Dict[str, Any]], 
        band_counters: Dict[str, Any],
        filename: str = "unknown.pcap",
        device_info: Optional[DeviceInfo] = None,
        signal_samples: List[Dict[str, Any]] = None,
        wireshark_raw: Optional[Dict[str, Any]] = None
    ) -> BandSteeringAnalysis:
        """
        Main entry point.
        Analyzes raw events and counters to generate a structured BTM report.
        """
        start_time = datetime.now()
        
        # 1. Extract and structure BTM events
        btm_events_list = self._extract_btm_schemas(steering_events)
        
        # 2. Analyze steering transitions (Aggressive vs Assisted)
        transitions = self._analyze_transitions(steering_events, btm_events_list)
        
        # 3. Detect steering patterns
        steering_type = self._detect_steering_pattern(transitions, band_counters)
        
        # 4. Calculate aggregated metrics (Synchronize with WiresharkTool)
        btm_stats = band_counters.get("btm_stats", {})
        btm_responses = btm_stats.get("responses", 0)

        # ============================================================
        # GOLDEN RULE: WiresharkTool/tshark = source of truth
        # ============================================================
        # PRIORITY ORDER for attempts/success metrics:
        # 1) Counters calculated by WiresharkTool in steering_analysis
        # 2) Raw counters from wireshark_raw.summary.btm (if they exist)
        # 3) Local fallback using transitions (only if 1 and 2 do not exist)

        ws_attempts = band_counters.get("steering_attempts", 0)
        ws_success = band_counters.get("successful_transitions", 0)

        # 1) If WiresharkTool provided aggregated values, they are definitive
        if ws_attempts > 0 or ws_success > 0:
            btm_requests = ws_attempts
            successful_transitions = ws_success
        else:
            # 2) Try to use Wireshark raw counters directly
            raw_btm = None
            if isinstance(band_counters.get("wireshark_raw"), dict):
                raw_summary = band_counters["wireshark_raw"].get("summary", {})
                raw_btm = raw_summary.get("btm", {})

            raw_requests = raw_btm.get("requests", 0) if raw_btm else 0
            raw_accepts = raw_btm.get("responses_accept", 0) if raw_btm else 0

            if raw_requests > 0 or raw_accepts > 0:
                btm_requests = raw_requests or btm_stats.get("requests", 0)
                # Consider at least all Accept responses as successful
                successful_transitions = max(
                    raw_accepts,
                    sum(1 for t in transitions if t.is_successful),
                )
            else:
                # 3) Fallback: Only if there is neither aggregated nor raw data,
                # we calculate from transitions. This mode is considered
                # heuristic and is typically used in very small captures.
                btm_requests = max(btm_stats.get("requests", 0), len(transitions))
                successful_transitions = sum(1 for t in transitions if t.is_successful)
        
        failed_transitions = max(0, btm_requests - successful_transitions)
        
        # Re-calculate success rate
        btm_success_rate = (successful_transitions / btm_requests) if btm_requests > 0 else 0.0
        btm_success_rate = max(0.0, min(1.0, float(btm_success_rate)))

        kvr_support = self._evaluate_kvr_support(band_counters, btm_requests > 0 or btm_responses > 0)
        
        # 6. Generate compliance table
        compliance_checks = self._run_compliance_checks(
            btm_requests, btm_responses, btm_success_rate, 
            kvr_support, transitions, band_counters,
            success_count_override=successful_transitions,
            steering_events=steering_events,
            device_info=device_info,
            wireshark_raw=wireshark_raw
        )
        
        # 7. Determine verdict (GOLDEN RULE: 1 success = SUCCESS)
        verdict = self._determine_verdict(compliance_checks, transitions, btm_success_rate, successful_transitions)
        
        # 9. Build final analysis object
        analysis_id = str(uuid.uuid4())
        loops_detected = any(t.returned_to_original for t in transitions) or band_counters.get("loop_detected", False)

        # Prepare device list (simplified, normally would come from DeviceClassifier)
        devices = []
        if device_info:
            devices.append(device_info)
        
        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        return BandSteeringAnalysis(
            analysis_id=analysis_id,
            filename=filename,
            analysis_timestamp=datetime.now(),
            total_packets=band_counters.get("total_packets", 0), # Asumiendo que viene en band_counters o se pasa aparte
            wlan_packets=band_counters.get("total_wlan_packets", 0), 
            analysis_duration_ms=duration_ms,
            devices=devices,
            btm_events=btm_events_list,
            transitions=transitions,
            signal_samples=signal_samples or [],
            btm_requests=btm_requests,
            btm_responses=btm_responses,
            btm_success_rate=btm_success_rate,
            successful_transitions=successful_transitions,
            failed_transitions=failed_transitions,
            loops_detected=loops_detected,
            kvr_support=kvr_support,
            compliance_checks=compliance_checks,
            verdict=verdict,
            fragments=[] # Se llenará después con FragmentExtractor
        )

    def _extract_btm_schemas(self, raw_events: List[Dict[str, Any]]) -> List[BTMEvent]:
        """Converts raw Wireshark events into Pydantic BTMEvent objects."""
        schemas = []
        for e in raw_events:
            is_btm = False
            evt_type = "unknown"
            status = None
            
            # 1. New explicit format (updated WiresharkTool)
            if e.get("type") == "btm":
                is_btm = True
                evt_type = e.get("event_type", "unknown")
                status = e.get("status_code")
            
            # 2. Legacy / Fallback format (based on subtype 13 and old names)
            elif e.get("subtype") == 13:
                if e.get("type") == "BTM Request": 
                    is_btm = True
                    evt_type = "request"
                elif e.get("type") == "BTM Response":
                    is_btm = True
                    evt_type = "response"
                    status = e.get("btm_status_code")
            
            if is_btm:
                # Normalize RSSI (can come as 'rssi' or 'signal_strength')
                rssi_val = e.get("rssi")
                if rssi_val is None:
                    s = e.get("signal_strength")
                    if s:
                        try:
                            rssi_val = int(s)
                        except Exception:
                            pass
                
                try:
                    if status is not None:
                        status_str = str(status)
                        status_code = int(status_str, 16) if status_str.startswith("0x") else int(status_str)
                    else:
                        status_code = None
                except (ValueError, TypeError):
                    status_code = None
                
                schemas.append(BTMEvent(
                    timestamp=float(e.get("timestamp", 0.0)),
                    event_type=evt_type,
                    client_mac=e.get("client_mac", "unknown"),
                    ap_bssid=e.get("ap_bssid") or e.get("bssid", "unknown"),
                    status_code=status_code,
                    band=e.get("band"),
                    frequency=int(e.get("frequency")) if e.get("frequency") else None,
                    rssi=rssi_val
                ))
        return schemas

    def _analyze_transitions(self, raw_events: List[Dict[str, Any]], btm_events: List[BTMEvent]) -> List[SteeringTransition]:
        """
        Analyzes the time sequence to identify complete transitions.
        Detects if it was Aggressive (Deauth) or Assisted (BTM/Reassoc).
        """
        transitions = []
        
        # Group events by client, filtering BSSIDs
        # BSSIDs have the least significant bit of the first octet at 0, but are AP addresses
        # We need to filter addresses that are known BSSIDs
        def is_likely_bssid(mac: str, bssid_list: list = None) -> bool:
            """Determines if a MAC is likely a BSSID (AP) rather than a client"""
            if not mac:
                return True
            # If it's in the list of known BSSIDs, it's a BSSID
            if bssid_list:
                mac_normalized = mac.lower().replace('-', ':')
                for bssid in bssid_list:
                    if bssid.lower().replace('-', ':') == mac_normalized:
                        return True
            return False
        
        # Get list of known BSSIDs from events
        known_bssids = set()
        for e in raw_events:
            bssid = e.get("bssid") or e.get("ap_bssid")
            if bssid:
                known_bssids.add(bssid)
        
        events_by_client = {}
        for e in raw_events:
            c = e.get("client_mac")
            if c and not is_likely_bssid(c, list(known_bssids)):
                if c not in events_by_client: events_by_client[c] = []
                events_by_client[c].append(e)
                
        # Analyze per client
        for client, events in events_by_client.items():
            sorted_events = sorted(events, key=lambda x: x["timestamp"])
            
            # Máquina de estados simple
            last_btm_req = None
            last_deauth = None
            
            
            for i, ev in enumerate(sorted_events):
                etype = ev.get("type")
                subtype = ev.get("subtype")
                event_type = ev.get("event_type")  # For BTM events: "request" or "response"
                timestamp = ev.get("timestamp", 0)
                
                # 1. Detect transition start
                # BTM events have type="btm" and event_type="request" or "response"
                # Also check by subtype 13 and action_code 7 (BTM Request)
                is_btm_request = (
                    (etype == "btm" and event_type == "request") or
                    (subtype == 13 and str(ev.get("action_code", "")) == "7") or
                    (subtype == 13 and ev.get("action_code") == 7)
                )
                
                if is_btm_request:
                    last_btm_req = ev
                elif etype in ["Deauthentication", "Disassociation"] or subtype in [10, 12]:
                    # Validate that deauth is directed to the client and is forced
                    
                    is_forced, classification, desc = DeauthValidator.validate_and_classify(ev, client)
                    
                    # Solo contar como "agresivo" si es forzado Y viene del AP (no del cliente)
                    # If classification == "forced_to_client", it means the AP kicks out the client
                    # If classification == "graceful", it is voluntary client exit
                    if is_forced and classification == "forced_to_client":
                        last_deauth = ev
                    
                # 2. Detect transition end (Reassociation)
                if etype in ["Reassociation Response", "Association Response"] or subtype in [1, 3]:
                    # Check success (Status Code 0)
                    assoc_status = str(ev.get("assoc_status_code", ""))
                    is_success = assoc_status in ["0", "0x00", "0x0", "0x0000"]
                    
                    
                    if is_success:
                        # Check if there are BTM events in the time window that were not detected as Requests
                        window_start = timestamp - REASSOC_TIMEOUT_SECONDS
                        btm_events_in_window = [
                            e for e in sorted_events[:i]
                            if e.get("timestamp", 0) >= window_start
                            and (e.get("type") == "btm" or e.get("subtype") == 13)
                        ]
                        
                        # Also show ALL events in window for diagnostics
                        all_events_in_window = [
                            e for e in sorted_events[:i]
                            if e.get("timestamp", 0) >= window_start
                        ]
                        
                        if all_events_in_window:
                            for idx, ev in enumerate(all_events_in_window):
                                ev_time_diff = timestamp - ev.get("timestamp", 0)
                        
                        # Search for recent BTM Requests in window that were not detected
                        recent_btm_requests = []
                        for btm_ev in btm_events_in_window:
                            btm_etype = btm_ev.get("type")
                            btm_event_type = btm_ev.get("event_type")
                            btm_subtype = btm_ev.get("subtype")
                            btm_action_code = btm_ev.get("action_code")
                            
                            # Check if it's a BTM Request
                            is_btm_req = (
                                (btm_etype == "btm" and btm_event_type == "request") or
                                (btm_subtype == 13 and str(btm_action_code) == "7") or
                                (btm_subtype == 13 and btm_action_code == 7)
                            )
                            
                            if is_btm_req:
                                recent_btm_requests.append(btm_ev)
                        
                        # If there are recent BTM Requests in the window, use the most recent
                        if recent_btm_requests:
                            # Sort by timestamp descending to get the most recent
                            recent_btm_requests.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
                            most_recent_btm = recent_btm_requests[0]
                            btm_time_diff = timestamp - most_recent_btm.get("timestamp", 0)
                            
                            if btm_time_diff < REASSOC_TIMEOUT_SECONDS:
                                # Update last_btm_req with the most recent
                                if not last_btm_req or most_recent_btm.get("timestamp", 0) > last_btm_req.get("timestamp", 0):
                                    last_btm_req = most_recent_btm
                        
                        if btm_events_in_window and not last_btm_req:
                            for btm_ev in btm_events_in_window:
                                pass
                        
                        # Determine type based on previous events
                        time_since_deauth = None
                        time_since_btm = None
                        
                        if last_deauth:
                            time_since_deauth = ev["timestamp"] - last_deauth["timestamp"]
                        
                        if last_btm_req:
                            time_since_btm = ev["timestamp"] - last_btm_req["timestamp"]
                        
                        
                        # Priority: Recent Deauth > Recent BTM > Unknown
                        if last_deauth and time_since_deauth is not None and time_since_deauth < REASSOC_TIMEOUT_SECONDS:
                            # It's Aggressive (there was a recent deauth)
                            start_node = last_deauth
                            s_type = SteeringType.AGGRESSIVE
                        elif last_btm_req and time_since_btm is not None and time_since_btm < REASSOC_TIMEOUT_SECONDS:
                            # It's Assisted (there was a recent BTM req)
                            start_node = last_btm_req
                            s_type = SteeringType.ASSISTED
                        else:
                            # Roaming espontáneo o Asistido sin captura de Request
                            start_node = ev # Usamos el mismo evento como inicio si no hay previo
                            s_type = SteeringType.UNKNOWN
                            if last_btm_req:
                                pass
                            elif last_deauth:
                                pass
                            else:
                                # Mostrar eventos previos con más detalle
                                prev_events = sorted_events[max(0, i-10):i]
                                for prev_idx, prev_ev in enumerate(prev_events):
                                    prev_etype = prev_ev.get('type')
                                    prev_event_type = prev_ev.get('event_type')
                                    prev_subtype = prev_ev.get('subtype')
                                    prev_action_code = prev_ev.get('action_code')
                                    prev_timestamp = prev_ev.get('timestamp', 0)
                                    time_diff = timestamp - prev_timestamp if prev_timestamp else None
                        
                        # Crear transición
                        start_time = start_node["timestamp"]
                        end_time = ev["timestamp"]
                        duration = end_time - start_time
                        
                        # Datos de cambio
                        from_bssid = start_node.get("bssid")
                        to_bssid = ev.get("bssid")
                        
                        # Inferir bandas (si tenemos info)
                        from_band = start_node.get("band")
                        to_band = ev.get("band")
                        
                        is_band_change = False
                        if from_band and to_band and from_band != to_band:
                           is_band_change = True
                           
                        transitions.append(SteeringTransition(
                            client_mac=client,
                            steering_type=s_type,
                            start_time=start_time,
                            end_time=end_time,
                            duration=duration,
                            from_bssid=from_bssid,
                            to_bssid=to_bssid,
                            from_band=from_band,
                            to_band=to_band,
                            is_successful=True,
                            is_band_change=is_band_change,
                        ))
                        
                        # Reset estados SOLO si fueron usados en esta transición Y están fuera de la ventana
                        # Esto permite que múltiples transiciones puedan usar el mismo BTM Request
                        # si están dentro de la ventana de tiempo (puede haber múltiples reassociations
                        # después de un solo BTM Request)
                        if s_type == SteeringType.AGGRESSIVE and last_deauth == start_node:
                            # Se usó el deauth, resetearlo después de usarlo
                            last_deauth = None
                        elif s_type == SteeringType.ASSISTED and last_btm_req == start_node:
                            # Se usó el BTM Request, pero NO resetearlo todavía
                            # porque puede haber más transiciones que lo necesiten dentro de la ventana
                            # El BTM Request se mantendrá activo hasta que expire la ventana de tiempo
                            # o hasta que se detecte un nuevo BTM Request
                            pass  # No resetear, permitir reutilización dentro de la ventana
                        # If it is UNKNOWN, do not reset anything because no previous state was used
        
        # Post-procesamiento: marcar cambios de banda aunque los frames individuales
        # no lo hayan indicado explícitamente. Si vemos que, para un mismo cliente,
        # las transiciones consecutivas usan bandas distintas (por ejemplo, primero
        # 2.4GHz y luego 5GHz), consideramos que hubo un cambio de banda físico
        # entre ellas, aunque cada transición aislada esté etiquetada como
        # \"dentro de la misma banda\".
        if transitions:
            transitions_sorted = sorted(transitions, key=lambda t: t.start_time)
            last_band_by_client = {}
            
            for t in transitions_sorted:
                band = t.to_band or t.from_band
                if not band:
                    continue
                
                client_id = t.client_mac
                last_band = last_band_by_client.get(client_id)
                
                if last_band and last_band != band:
                    # Marcar este salto como cambio de banda si aún no lo estaba
                    if not t.from_band:
                        t.from_band = last_band
                    t.to_band = band
                    t.is_band_change = True
                
                last_band_by_client[client_id] = band
        
        return transitions

    def _detect_steering_pattern(self, transitions: List[SteeringTransition], band_counters: dict) -> SteeringType:
        """Determines the predominant steering pattern in the capture."""
        if not transitions:
            # If no transitions, see if there is preventive steering
            # (Logic brought from existing wireshark_tool)
            if self._check_preventive_steering(band_counters):
                return SteeringType.PREVENTIVE
            return SteeringType.UNKNOWN
            
        counts = {
            SteeringType.AGGRESSIVE: 0,
            SteeringType.ASSISTED: 0
        }
        
        for t in transitions:
            if t.steering_type in counts:
                counts[t.steering_type] += 1
                
        if counts[SteeringType.AGGRESSIVE] > counts[SteeringType.ASSISTED]:
            return SteeringType.AGGRESSIVE
        elif counts[SteeringType.ASSISTED] > 0:
            return SteeringType.ASSISTED
            
        return SteeringType.UNKNOWN

    def _check_preventive_steering(self, band_counters: dict) -> bool:
        """Logic to detect Client Steering / Preventive."""
        # If there is 2.4 beacon but data almost all on 5GHz
        beacon_24 = band_counters.get("beacon_24", 0)
        data_24 = band_counters.get("data_24", 0)
        data_5 = band_counters.get("data_5", 0)
        total_data = data_24 + data_5
        
        if beacon_24 > 0 and total_data > 100:
             if (data_5 / total_data) > 0.95:
                 return True
        return False

    def _evaluate_kvr_support(self, band_counters: dict, has_btm_activity: bool) -> KVRSupport:
        """Evaluates standards support based on counters."""
        stats = band_counters.get("kvr_stats", {})
        
        k = stats.get("11k", False)
        v = stats.get("11v", False) or has_btm_activity
        r = stats.get("11r", False)
        
        # Calculate simple score
        passed_count = sum([k, v, r])
        score = passed_count / 3.0
        
        return KVRSupport(
            k_support=k,
            v_support=v,
            r_support=r
        )

    def _run_compliance_checks(
        self, 
        btm_requests: int, 
        btm_responses: int, 
        btm_success_rate: float,
        kvr: KVRSupport, 
        transitions: List[SteeringTransition],
        band_counters: dict,
        success_count_override: int = 0,
        steering_events: List[Dict[str, Any]] = None,
        device_info: Optional[DeviceInfo] = None,
        wireshark_raw: Optional[Dict[str, Any]] = None
    ) -> List[ComplianceCheck]:
        """Genera la tabla de resumen de cumplimiento."""
        # Usar datos raw de Wireshark si están disponibles, sino usar procesados
        raw_summary = wireshark_raw.get("summary", {}) if wireshark_raw else {}
        raw_btm = raw_summary.get("btm", {})

        checks: List[ComplianceCheck] = []

        # 1. Soporte BTM (802.11v)
        checks.append(
            self._build_btm_support_check(
                btm_requests=btm_requests,
                btm_responses=btm_responses,
                raw_btm=raw_btm,
                band_counters=band_counters,
            )
        )

        # 2. Association and Reassociation
        checks.append(
            self._build_association_check(
                raw_summary=raw_summary,
                steering_events=steering_events or [],
                device_info=device_info,
                band_counters=band_counters,
            )
        )

        # 3. Effective steering (band transition)
        checks.append(
            self._build_steering_effective_check(
                transitions=transitions,
                raw_btm=raw_btm,
                steering_events=steering_events or [],
                success_count_override=success_count_override,
            )
        )

        # 4. KVR Standards
        checks.append(self._build_kvr_check(kvr))

        return checks

    def _build_btm_support_check(
        self,
        btm_requests: int,
        btm_responses: int,
        raw_btm: Dict[str, Any],
        band_counters: dict,
    ) -> ComplianceCheck:
        """Builds the BTM support (802.11v) check."""
        raw_btm_requests = raw_btm.get("requests", btm_requests)
        raw_btm_responses = raw_btm.get("responses", btm_responses)
        raw_btm_accept = raw_btm.get("responses_accept", 0)

        btm_stats = band_counters.get("btm_stats", {})

        # Collect all detected codes (successes and rejections)
        status_codes_raw = btm_stats.get("status_codes", [])
        status_lines = []
        if status_codes_raw:
            unique_codes = list(dict.fromkeys(status_codes_raw))
            for code in unique_codes:
                desc = BTMStatusCode.get_description(code)
                status_lines.append(f"Code: {code} ({desc})")

        status_info = "\n" + "\n".join(status_lines) if status_lines else ""

        # Logic based ONLY on what Wireshark sees:
        # - PASSED: there are Requests, there are Responses and at least one Accept (status 0)
        # - FAILED: there were Requests but 0 Responses, or only Rejects
        # - Capture without BTM: mark as FAILED but explaining that BTM was not observed
        if raw_btm_requests == 0 and raw_btm_responses == 0:
            passed_btm = False
            details = "BTM not observed in the capture (REQUESTS: 0, RESPONSES: 0)"
        elif raw_btm_requests > 0 and raw_btm_responses == 0:
            passed_btm = False
            details = (
                "BTM requested but no response from client. "
                f"REQUESTS: {raw_btm_requests}, RESPONSES: 0{status_info}"
            )
        else:
            has_accept = raw_btm_accept > 0
            passed_btm = has_accept
            if has_accept:
                details = (
                    f"REQUESTS: {raw_btm_requests}, RESPONSES: {raw_btm_responses}, "
                    f"ACCEPT: {raw_btm_accept}{status_info}"
                )
            else:
                details = (
                    "BTM RESPONSES without Accept (only reject). "
                    f"REQUESTS: {raw_btm_requests}, RESPONSES: {raw_btm_responses}, "
                    f"ACCEPT: 0{status_info}"
                )

        return ComplianceCheck(
            check_name="BTM Support (802.11v)",
            description="The device must demonstrate active BSS Transition Management support",
            category="btm",
            passed=passed_btm,
            severity="high",
            details=details,
            recommendation=(
                "The client ignores or rejects BTM requests. Review status codes."
                if not passed_btm
                else "Enable 802.11v"
            ),
        )

    def _build_association_check(
        self,
        raw_summary: Dict[str, Any],
        steering_events: List[Dict[str, Any]],
        device_info: Optional[DeviceInfo],
        band_counters: dict,
    ) -> ComplianceCheck:
        """Builds the association and reassociation check."""
        raw_assoc = raw_summary.get("assoc", {}) if raw_summary else {}
        raw_reassoc = raw_summary.get("reassoc", {}) if raw_summary else {}

        # Counters from raw Wireshark
        assoc_req = raw_assoc.get("requests", 0)
        assoc_resp = raw_assoc.get("responses", 0)
        assoc_resp_success = raw_assoc.get("responses_success", 0)

        reassoc_req = raw_reassoc.get("requests", 0)
        reassoc_resp = raw_reassoc.get("responses", 0)
        reassoc_resp_success = raw_reassoc.get("responses_success", 0)

        primary_client = device_info.mac_address if device_info else None

        # Smart filters for Deauth/Disassoc
        forced_deauth_count = 0
        forced_disassoc_count = 0
        client_directed_deauth_count = 0
        client_directed_disassoc_count = 0

        for e in steering_events or []:
            st = e.get("subtype")
            # Disconnection analysis (ONLY IF IT IS THE ANALYZED CLIENT)
            if st in [10, 12] and primary_client:
                is_forced, classification, desc = DeauthValidator.validate_and_classify(
                    e, primary_client
                )

                # Check if it's directed to the client (even if not forced)
                is_directed = DeauthValidator.is_directed_to_client(e, primary_client)

                if is_directed:
                    if st == 10:
                        client_directed_disassoc_count += 1
                        if is_forced:
                            forced_disassoc_count += 1
                    else:
                        client_directed_deauth_count += 1
                        if is_forced:
                            forced_deauth_count += 1

        assoc_failures = band_counters.get("association_failures", [])
        failure_count = len(assoc_failures)

        # A handshake is considered complete if there is at least one successful cycle
        has_complete_handshake = (assoc_req > 0 and assoc_resp > 0) or (
            reassoc_req > 0 and reassoc_resp > 0
        )

        # SUCCESS CRITERIA: Complete handshake AND no disconnections directed to client
        assoc_passed = (
            has_complete_handshake
            and failure_count == 0
            and (
                client_directed_deauth_count == 0
                and client_directed_disassoc_count == 0
            )
        )

        # Precise technical recommendation
        if (client_directed_deauth_count + client_directed_disassoc_count) > 0:
            forced_text = ""
            if (forced_deauth_count + forced_disassoc_count) > 0:
                forced_text = (
                    f" ({forced_deauth_count + forced_disassoc_count} forced)"
                )
            rec = (
                "Test FAILED: Detected "
                f"{client_directed_deauth_count} Deauth and "
                f"{client_directed_disassoc_count} Disassoc DIRECTED to client"
                f"{forced_text}, indicating connection instability."
            )
        elif failure_count > 0:
            rec = "Explicit association failures detected (Status Code != 0)."
        elif not has_complete_handshake:
            rec = (
                "Incomplete handshake or partial capture; complete association "
                "cycle was not detected."
            )
        else:
            rec = None

        return ComplianceCheck(
            check_name="Association and Reassociation",
            description="Verifies complete association and reassociation cycles",
            category="association",
            passed=assoc_passed,
            severity="medium",
            details=(
                f"ASSOC: {assoc_req}/{assoc_resp_success}, "
                f"REASSOC: {reassoc_req}/{reassoc_resp_success} "
                f"DISASSOC: {client_directed_disassoc_count} (forced: {forced_disassoc_count}), "
                f"DEAUTH: {client_directed_deauth_count} (forced: {forced_deauth_count})"
            ),
            recommendation=rec,
        )

    def _build_steering_effective_check(
        self,
        transitions: List[SteeringTransition],
        raw_btm: Dict[str, Any],
        steering_events: List[Dict[str, Any]],
        success_count_override: int = 0,
    ) -> ComplianceCheck:
        """Builds the effective steering (band transition) check."""

        def normalize_band(band: Optional[str]) -> Optional[str]:
            if not band:
                return None
            band_str = str(band).lower()
            if "5" in band_str:
                return "5GHz"
            if "2.4" in band_str or "2,4" in band_str:
                return "2.4GHz"
            return band

        # Sort transitions by time
        sorted_transitions = sorted(
            [t for t in transitions if t.is_successful],
            key=lambda x: x.start_time,
        )
        band_change_transitions = 0

        # A transition is a band change if:
        # 1. It has different from_band and to_band (explicit change), OR
        # 2. It is marked as is_band_change=True (client history)
        for t in sorted_transitions:
            from_band = normalize_band(t.from_band)
            to_band = normalize_band(t.to_band)

            has_band_change = False

            if from_band and to_band and from_band != to_band:
                has_band_change = True
            elif t.is_band_change:
                has_band_change = True

            if has_band_change:
                band_change_transitions += 1

        # Use raw Wireshark data for successful BTM responses
        raw_btm_accept = raw_btm.get("responses_accept", 0)
        btm_successful_responses = (
            raw_btm_accept
            if raw_btm_accept > 0
            else sum(
                1
                for e in (steering_events or [])
                if e.get("type") == "btm"
                and e.get("event_type") == "response"
                and (
                    e.get("status_code") == 0 or str(e.get("status_code")) == "0"
                )
            )
        )

        # Count total successful transitions
        successful_transitions_count = (
            success_count_override
            if success_count_override > 0
            else sum(1 for t in transitions if t.is_successful)
        )

        # EFFECTIVE STEERING CRITERIA:
        # Option 1: 1 physical band change + BTM Accept
        # Option 2: 2+ physical band changes (even if no explicit BTM)
        has_btm_cooperation = btm_successful_responses > 0
        has_band_changes = band_change_transitions > 0
        has_multiple_band_changes = band_change_transitions >= 2

        if has_multiple_band_changes:
            steering_passed = True
            rec_steering = None
        elif has_band_changes and has_btm_cooperation:
            steering_passed = True
            rec_steering = None
        else:
            steering_passed = False
            if band_change_transitions == 0:
                if btm_successful_responses > 0:
                    rec_steering = (
                        "The client cooperated (BTM Accept) but no physical "
                        "band changes were detected. Verify that the capture "
                        "contains the full steering flow."
                    )
                else:
                    rec_steering = (
                        "No physical band changes or BTM cooperation detected. "
                        "At least 1 band change (2.4 <-> 5 GHz) with BTM Accept, "
                        "or 2+ band changes are required to consider steering effective."
                    )
            elif band_change_transitions == 1 and not has_btm_cooperation:
                rec_steering = (
                    "1 band change was detected but without BTM cooperation "
                    "(Accept). BTM Accept is required to validate steering, "
                    "or at least 2 band changes."
                )
            else:
                rec_steering = "Effective steering criterion not met."

        details = (
            f"BAND CHANGE TRANSITIONS: {band_change_transitions} | "
            f"TOTAL TRANSITIONS: {successful_transitions_count} | "
            f"BTM ACCEPT: {raw_btm_accept}"
        )

        return ComplianceCheck(
            check_name="Effective Steering",
            description=(
                "Steering is successful if there is at least 1 band change "
                "(2.4 <-> 5 GHz) with BTM cooperation, or 2+ band changes"
            ),
            category="performance",
            passed=steering_passed,
            severity="high",
            details=details,
            recommendation=rec_steering,
        )

    def _build_kvr_check(self, kvr: KVRSupport) -> ComplianceCheck:
        """Builds the KVR standards check."""
        kvr_passed = sum([kvr.k_support, kvr.v_support, kvr.r_support]) >= 1

        return ComplianceCheck(
            check_name="KVR Standards",
            description="Support for mobility standards (Minimum 1 of 3: k, v, r)",
            category="kvr",
            passed=kvr_passed,
            severity="medium",
            details=f"k={kvr.k_support}, v={kvr.v_support}, r={kvr.r_support}",
            recommendation=(
                "It is recommended to enable the missing standard for optimal roaming"
                if not kvr_passed
                else None
            ),
        )


    def _determine_verdict(self, checks: List[ComplianceCheck], transitions: List[SteeringTransition], btm_rate: float, success_count: int = 0) -> str:
        """Determines the final verdict based on business rules."""
        # Get checks by category to avoid issues with matching by accents
        assoc_check = next((c for c in checks if c.category == "association"), None)
        btm_check = next((c for c in checks if c.category == "btm"), None)
        kvr_check = next((c for c in checks if c.category == "kvr"), None)
        performance_check = next((c for c in checks if c.category == "performance"), None)

        # Rule 1: If there are critical association failures (Deauth/Disassoc/Status Error) -> FAILED
        # Stability is most important.
        if assoc_check and not assoc_check.passed:
            return "FAILED"
            
        # Rule 2: If BTM support explicitly failed (Requested but ignored or rejected) -> FAILED
        if btm_check and not btm_check.passed:
            return "FAILED"

        # Rule 3: If there is effective steering (successful transitions OR successful BTM responses)
        # The "Effective Steering" check now considers:
        # - Successful band changes
        # - Successful transitions (with or without band change)
        # - Successful BTM responses (status_code 0)
        if performance_check and performance_check.passed:
            # If performance check passed, there is effective steering
            # Check KVR only if critical (may be optional depending on context)
            if kvr_check and not kvr_check.passed:
                # Still SUCCESS because steering worked, just missing full KVR
                pass
            return "SUCCESS"
            
        # Rule 4: If there are successful transitions directly (fallback)
        # IMPORTANT: Only SUCCESS if there is real effective steering
        if success_count > 0:
            # Check if there is effective steering before giving SUCCESS
            if performance_check and performance_check.passed:
                # Effective steering exists, it's SUCCESS
                if kvr_check and not kvr_check.passed:
                    pass
                return "SUCCESS"
            # If there are successful transitions but NO effective steering, it's PARTIAL
            if btm_check and btm_check.passed:
                return "PARTIAL"
            # If there is no BTM but there are transitions, it could be spontaneous roaming
            # In this case, if not effective, it's FAILED
            return "FAILED"
            
        # Rule 5: Success via BTM even if we didn't see complete reassociation
        # IMPORTANT: BTM Accept without physical change is PARTIAL, not SUCCESS
        if btm_check and btm_check.passed and btm_rate > 0.5:
            if performance_check and not performance_check.passed:
                # Client cooperated (BTM Accept) but did not execute physical change
                return "PARTIAL"
            # If there is effective steering, SUCCESS was already returned above in Rule 3
            # If we get here and performance_check doesn't exist, it's an edge case
            return "SUCCESS"
            
        # Rule 6: If there are no transitions but confirmed preventive steering
        if performance_check and performance_check.passed:
            # If performance check passed it's because it detected traffic-based preventive steering
            return "SUCCESS"
            
        return "FAILED"
