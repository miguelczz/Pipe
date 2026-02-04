"""
Herramienta especializada para el análisis de BSS Transition Management (802.11v) y Band Steering.
Implementa lógica detección de patrones, clasificación de códigos y evaluación de cumplimiento.
"""
import logging
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
    SignalSample
)
from ..utils.deauth_validator import DeauthValidator, REASSOC_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

class BTMAnalyzer:
    """
    Analizador especializado en BTM y Steering.
    Sigue el diseño para separar la lógica de análisis de la extracción de datos.
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
        Punto de entrada principal.
        Analiza eventos crudos y contadores para generar un reporte estructurado BTM.
        """
        start_time = datetime.now()
        
        # 1. Extraer y estructurar eventos BTM
        btm_events_list = self._extract_btm_schemas(steering_events)
        
        # 2. Analizar transiciones de steering (Agresivo vs Asistido)
        transitions = self._analyze_transitions(steering_events, btm_events_list)
        
        # 3. Detectar patrones de steering
        steering_type = self._detect_steering_pattern(transitions, band_counters)
        
        # 4. Calcular métricas agregadas (Sincronizar con WiresharkTool)
        btm_stats = band_counters.get("btm_stats", {})
        btm_responses = btm_stats.get("responses", 0)

        # ============================================================
        # REGLA DE ORO: WiresharkTool/tshark = fuente de verdad
        # ============================================================
        # ORDEN DE PRIORIDAD para métricas de intentos/éxitos:
        # 1) Contadores calculados por WiresharkTool en steering_analysis
        # 2) Contadores crudos de wireshark_raw.summary.btm (si existen)
        # 3) Fallback local usando transitions (solo si 1 y 2 no existen)

        ws_attempts = band_counters.get("steering_attempts", 0)
        ws_success = band_counters.get("successful_transitions", 0)

        # 1) Si WiresharkTool proporcionó valores agregados, son definitivos
        if ws_attempts > 0 or ws_success > 0:
            btm_requests = ws_attempts
            successful_transitions = ws_success
        else:
            # 2) Intentar usar directamente los contadores crudos de Wireshark
            raw_btm = None
            if isinstance(band_counters.get("wireshark_raw"), dict):
                raw_summary = band_counters["wireshark_raw"].get("summary", {})
                raw_btm = raw_summary.get("btm", {})

            raw_requests = raw_btm.get("requests", 0) if raw_btm else 0
            raw_accepts = raw_btm.get("responses_accept", 0) if raw_btm else 0

            if raw_requests > 0 or raw_accepts > 0:
                btm_requests = raw_requests or btm_stats.get("requests", 0)
                # Considerar como exitosas al menos todas las respuestas Accept
                successful_transitions = max(
                    raw_accepts,
                    sum(1 for t in transitions if t.is_successful),
                )
            else:
                # 3) Fallback: Solo si no hay datos ni agregados ni crudos,
                # calculamos desde transitions. Este modo se considera
                # heurístico y se usa típicamente en capturas muy pequeñas.
                btm_requests = max(btm_stats.get("requests", 0), len(transitions))
                successful_transitions = sum(1 for t in transitions if t.is_successful)
        
        failed_transitions = max(0, btm_requests - successful_transitions)
        
        # Re-calcular success rate
        btm_success_rate = (successful_transitions / btm_requests) if btm_requests > 0 else 0.0
        btm_success_rate = max(0.0, min(1.0, float(btm_success_rate)))

        kvr_support = self._evaluate_kvr_support(band_counters, btm_requests > 0 or btm_responses > 0)
        
        # 6. Generar tabla de cumplimiento
        compliance_checks = self._run_compliance_checks(
            btm_requests, btm_responses, btm_success_rate, 
            kvr_support, transitions, band_counters,
            success_count_override=successful_transitions,
            steering_events=steering_events,
            device_info=device_info,
            wireshark_raw=wireshark_raw
        )
        
        # 7. Determinar veredicto (REGLA DE ORO: 1 éxito = SUCCESS)
        verdict = self._determine_verdict(compliance_checks, transitions, btm_success_rate, successful_transitions)
        
        # 9. Construir objeto de análisis final
        analysis_id = str(uuid.uuid4())
        loops_detected = any(t.returned_to_original for t in transitions) or band_counters.get("loop_detected", False)

        # Preparar lista de dispositivos (simplificado, normalmente vendría del DeviceClassifier)
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
        """Convierte eventos crudos de Wireshark en objetos BTMEvent Pydantic."""
        schemas = []
        for e in raw_events:
            is_btm = False
            evt_type = "unknown"
            status = None
            
            # 1. Nuevo formato explícito (WiresharkTool actualizado)
            if e.get("type") == "btm":
                is_btm = True
                evt_type = e.get("event_type", "unknown")
                status = e.get("status_code")
            
            # 2. Formato Legacy / Fallback (basado en subtype 13 y nombres antiguos)
            elif e.get("subtype") == 13:
                if e.get("type") == "BTM Request": 
                    is_btm = True
                    evt_type = "request"
                elif e.get("type") == "BTM Response":
                    is_btm = True
                    evt_type = "response"
                    status = e.get("btm_status_code")
            
            if is_btm:
                # Normalizar RSSI (puede venir como 'rssi' o 'signal_strength')
                rssi_val = e.get("rssi")
                if rssi_val is None:
                    s = e.get("signal_strength")
                    if s:
                        try: rssi_val = int(s)
                        except: pass
                
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
        Analiza la secuencia temporal para identificar transiciones completas.
        Detecta si fue Agresivo (Deauth) o Asistido (BTM/Reassoc).
        """
        transitions = []
        
        # Agrupar eventos por cliente, filtrando BSSIDs
        # Los BSSIDs tienen el bit menos significativo del primer octeto en 0, pero son direcciones de APs
        # Necesitamos filtrar direcciones que sean BSSIDs conocidos
        def is_likely_bssid(mac: str, bssid_list: list = None) -> bool:
            """Determina si una MAC es probablemente un BSSID (AP) en lugar de un cliente"""
            if not mac:
                return True
            # Si está en la lista de BSSIDs conocidos, es un BSSID
            if bssid_list:
                mac_normalized = mac.lower().replace('-', ':')
                for bssid in bssid_list:
                    if bssid.lower().replace('-', ':') == mac_normalized:
                        return True
            return False
        
        # Obtener lista de BSSIDs conocidos de los eventos
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
                
        # Analizar por cliente
        for client, events in events_by_client.items():
            sorted_events = sorted(events, key=lambda x: x["timestamp"])
            
            # Máquina de estados simple
            last_btm_req = None
            last_deauth = None
            
            
            for i, ev in enumerate(sorted_events):
                etype = ev.get("type")
                subtype = ev.get("subtype")
                event_type = ev.get("event_type")  # Para eventos BTM: "request" o "response"
                timestamp = ev.get("timestamp", 0)
                
                # 1. Detectar inicio de transición
                # Los eventos BTM tienen type="btm" y event_type="request" o "response"
                # También verificar por subtype 13 y action_code 7 (BTM Request)
                is_btm_request = (
                    (etype == "btm" and event_type == "request") or
                    (subtype == 13 and str(ev.get("action_code", "")) == "7") or
                    (subtype == 13 and ev.get("action_code") == 7)
                )
                
                if is_btm_request:
                    last_btm_req = ev
                elif etype in ["Deauthentication", "Disassociation"] or subtype in [10, 12]:
                    # Validar que el deauth esté dirigido al cliente y sea forzado
                    
                    is_forced, classification, desc = DeauthValidator.validate_and_classify(ev, client)
                    
                    # Solo contar como "agresivo" si es forzado Y viene del AP (no del cliente)
                    # Si classification == "forced_to_client", significa que el AP destierra al cliente
                    # Si classification == "graceful", es salida voluntaria del cliente
                    if is_forced and classification == "forced_to_client":
                        last_deauth = ev
                    
                # 2. Detectar fin de transición (Reassociation)
                if etype in ["Reassociation Response", "Association Response"] or subtype in [1, 3]:
                    # Verificar éxito (Status Code 0)
                    assoc_status = str(ev.get("assoc_status_code", ""))
                    is_success = assoc_status in ["0", "0x00", "0x0", "0x0000"]
                    
                    
                    if is_success:
                        # Verificar si hay eventos BTM en la ventana de tiempo que no se detectaron como Requests
                        window_start = timestamp - REASSOC_TIMEOUT_SECONDS
                        btm_events_in_window = [
                            e for e in sorted_events[:i]
                            if e.get("timestamp", 0) >= window_start
                            and (e.get("type") == "btm" or e.get("subtype") == 13)
                        ]
                        
                        # También mostrar TODOS los eventos en la ventana para diagnóstico
                        all_events_in_window = [
                            e for e in sorted_events[:i]
                            if e.get("timestamp", 0) >= window_start
                        ]
                        
                        if all_events_in_window:
                            for idx, ev in enumerate(all_events_in_window):
                                ev_time_diff = timestamp - ev.get("timestamp", 0)
                        
                        # Buscar BTM Requests en la ventana que no se detectaron
                        recent_btm_requests = []
                        for btm_ev in btm_events_in_window:
                            btm_etype = btm_ev.get("type")
                            btm_event_type = btm_ev.get("event_type")
                            btm_subtype = btm_ev.get("subtype")
                            btm_action_code = btm_ev.get("action_code")
                            
                            # Verificar si es un BTM Request
                            is_btm_req = (
                                (btm_etype == "btm" and btm_event_type == "request") or
                                (btm_subtype == 13 and str(btm_action_code) == "7") or
                                (btm_subtype == 13 and btm_action_code == 7)
                            )
                            
                            if is_btm_req:
                                recent_btm_requests.append(btm_ev)
                        
                        # Si hay BTM Requests recientes en la ventana, usar el más reciente
                        if recent_btm_requests:
                            # Ordenar por timestamp descendente para obtener el más reciente
                            recent_btm_requests.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
                            most_recent_btm = recent_btm_requests[0]
                            btm_time_diff = timestamp - most_recent_btm.get("timestamp", 0)
                            
                            if btm_time_diff < REASSOC_TIMEOUT_SECONDS:
                                # Actualizar last_btm_req con el más reciente
                                if not last_btm_req or most_recent_btm.get("timestamp", 0) > last_btm_req.get("timestamp", 0):
                                    last_btm_req = most_recent_btm
                        
                        if btm_events_in_window and not last_btm_req:
                            for btm_ev in btm_events_in_window:
                                pass
                        
                        # Determinar tipo basado en eventos previos
                        time_since_deauth = None
                        time_since_btm = None
                        
                        if last_deauth:
                            time_since_deauth = ev["timestamp"] - last_deauth["timestamp"]
                        
                        if last_btm_req:
                            time_since_btm = ev["timestamp"] - last_btm_req["timestamp"]
                        
                        
                        # Prioridad: Deauth reciente > BTM reciente > Unknown
                        if last_deauth and time_since_deauth is not None and time_since_deauth < REASSOC_TIMEOUT_SECONDS:
                            # Es Agresivo (hubo deauth reciente)
                            start_node = last_deauth
                            s_type = SteeringType.AGGRESSIVE
                        elif last_btm_req and time_since_btm is not None and time_since_btm < REASSOC_TIMEOUT_SECONDS:
                            # Es Asistido (hubo BTM req reciente)
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
                            # TODO: Logica de detection de ping-pong (returned_to_original)
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
                        # Si es UNKNOWN, no resetear nada porque no se usó ningún estado previo
        
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
        """Determina el patrón predominante de steering en la captura."""
        if not transitions:
            # Si no hay transiciones, ver si hay steering preventivo
            # (Lógica traida de wireshark_tool existente)
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
        """Lógica para detectar Client Steering / Preventive."""
        # Si hay beacon 2.4 pero data casi todo en 5GHz
        beacon_24 = band_counters.get("beacon_24", 0)
        data_24 = band_counters.get("data_24", 0)
        data_5 = band_counters.get("data_5", 0)
        total_data = data_24 + data_5
        
        if beacon_24 > 0 and total_data > 100:
             if (data_5 / total_data) > 0.95:
                 return True
        return False

    def _evaluate_kvr_support(self, band_counters: dict, has_btm_activity: bool) -> KVRSupport:
        """Evalúa soporte de estándares basándose en contadores."""
        stats = band_counters.get("kvr_stats", {})
        
        k = stats.get("11k", False)
        v = stats.get("11v", False) or has_btm_activity
        r = stats.get("11r", False)
        
        # Calcular score simple
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
        checks = []
        
        # Usar datos raw de Wireshark si están disponibles, sino usar procesados
        raw_summary = wireshark_raw.get("summary", {}) if wireshark_raw else {}
        raw_btm = raw_summary.get("btm", {})
        
        # BTM Requests y Responses desde raw Wireshark
        raw_btm_requests = raw_btm.get("requests", btm_requests)
        raw_btm_responses = raw_btm.get("responses", btm_responses)
        raw_btm_accept = raw_btm.get("responses_accept", 0)
        raw_btm_reject = raw_btm.get("responses_reject", 0)
        
        # 1. BTM Support (802.11v)
        btm_stats = band_counters.get("btm_stats", {})
        has_btm_responses = raw_btm_responses > 0
        
        # Recopilar todos los códigos detectados (éxitos y rechazos)
        status_codes_raw = btm_stats.get("status_codes", [])
        status_lines = []
        if status_codes_raw:
            unique_codes = list(dict.fromkeys(status_codes_raw))
            for code in unique_codes:
                desc = BTMStatusCode.get_description(code)
                status_lines.append(f"Code: {code} ({desc})")
        
        status_info = "\n" + "\n".join(status_lines) if status_lines else ""
        
        # Nueva lógica estricta basada SOLO en lo que ve Wireshark:
        # - PASÓ: hay Requests, hay Responses y al menos un Accept (status 0)
        # - FALLÓ: hubo Requests pero 0 Responses, o solo Rejects
        # - Captura sin BTM: marcar como FALLÓ pero explicando que no se observó BTM
        if raw_btm_requests == 0 and raw_btm_responses == 0:
            passed_btm = False
            details = "BTM no observado en la captura (REQUESTS: 0, RESPONSES: 0)"
        elif raw_btm_requests > 0 and raw_btm_responses == 0:
            passed_btm = False
            details = f"BTM solicitado pero sin respuesta del cliente. REQUESTS: {raw_btm_requests}, RESPONSES: 0{status_info}"
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
                    f"RESPUESTAS BTM sin Accept (solo rechazo). "
                    f"REQUESTS: {raw_btm_requests}, RESPONSES: {raw_btm_responses}, "
                    f"ACCEPT: 0{status_info}"
                )
        
        checks.append(ComplianceCheck(
            check_name="Soporte BTM (802.11v)",
            description="El dispositivo debe demostrar soporte activo de BSS Transition Management",
            category="btm",
            passed=passed_btm,
            severity="high",
            details=details,
            recommendation="El cliente ignora o rechaza solicitudes BTM. Revisar códigos de estado." if not passed_btm else "Habilitar 802.11v"
        ))
        
        # 2. Asociación y Reasociación (Lógica Refinada y Segura)
        # Usar datos raw de Wireshark si están disponibles
        raw_assoc = raw_summary.get("assoc", {}) if raw_summary else {}
        raw_reassoc = raw_summary.get("reassoc", {}) if raw_summary else {}
        raw_deauth = raw_summary.get("deauth", {}) if raw_summary else {}
        raw_disassoc = raw_summary.get("disassoc", {}) if raw_summary else {}
        
        # Contadores desde raw Wireshark
        assoc_req = raw_assoc.get("requests", 0)
        assoc_resp = raw_assoc.get("responses", 0)
        assoc_resp_success = raw_assoc.get("responses_success", 0)
        assoc_resp_fail = raw_assoc.get("responses_fail", 0)
        
        reassoc_req = raw_reassoc.get("requests", 0)
        reassoc_resp = raw_reassoc.get("responses", 0)
        reassoc_resp_success = raw_reassoc.get("responses_success", 0)
        reassoc_resp_fail = raw_reassoc.get("responses_fail", 0)
        
        deauth_count = raw_deauth.get("count", 0)
        disassoc_count = raw_disassoc.get("count", 0)
        
        primary_client = device_info.mac_address if device_info else None
        
        # Filtros inteligentes para Deauth/Disassoc
        # Siempre usamos DeauthValidator sobre los eventos crudos para detectar
        # desconexiones FORZADAS y NO FORZADAS dirigidas al cliente
        forced_deauth_count = 0
        forced_disassoc_count = 0
        client_directed_deauth_count = 0  # Total de deauths dirigidos al cliente (forzados o no)
        client_directed_disassoc_count = 0  # Total de disassocs dirigidos al cliente (forzados o no)
        
        
        for e in (steering_events or []):
            st = e.get("subtype")
            # Análisis de desconexiones (SOLO SI ES EL CLIENTE ANALIZADO)
            if st in [10, 12] and primary_client:
                event_type = "Disassoc" if st == 10 else "Deauth"
                timestamp = e.get("timestamp", 0)
                da = e.get("da", "")
                sa = e.get("sa", "")
                reason_code = e.get("reason_code", "")
                bssid = e.get("bssid", "")
                
                
                is_forced, classification, desc = DeauthValidator.validate_and_classify(e, primary_client)
                
                
                # Verificar si está dirigido al cliente (incluso si no es forzado)
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
        
        # Un handshake se considera completo si hay al menos un ciclo exitoso
        has_complete_handshake = (assoc_req > 0 and assoc_resp > 0) or (reassoc_req > 0 and reassoc_resp > 0)
        
        # CRITERIO DE ÉXITO: Handshake completo Y sin desconexiones dirigidas al cliente
        # Cualquier desconexión (forzada o no) dirigida al cliente indica inestabilidad
        assoc_passed = (
            has_complete_handshake 
            and failure_count == 0 
            and (client_directed_deauth_count == 0 and client_directed_disassoc_count == 0)
        )
        
        # Recomendación técnica precisa
        if (client_directed_deauth_count + client_directed_disassoc_count) > 0:
            forced_text = ""
            if (forced_deauth_count + forced_disassoc_count) > 0:
                forced_text = f" ({forced_deauth_count + forced_disassoc_count} forzados)"
            rec = f"Prueba FALLIDA: Se detectaron {client_directed_deauth_count} Deauth y {client_directed_disassoc_count} Disassoc DIRIGIDOS al cliente{forced_text}, indicando inestabilidad en la conexión."
        elif failure_count > 0:
            rec = "Se detectaron fallos explícitos de asociación (Status Code != 0)."
        elif not has_complete_handshake:
            rec = "Handshake incompleto o captura parcial; no se detectó el ciclo completo de asociación."
        else:
            rec = None

        checks.append(ComplianceCheck(
            check_name="Asociación y Reasociación",
            description="Verifica ciclos completos de asociación y reasociación",
            category="association",
            passed=assoc_passed,
            severity="medium",
            details=(
                f"ASSOC: {assoc_req}/{assoc_resp_success}, REASSOC: {reassoc_req}/{reassoc_resp_success} "
                f"DISASSOC: {client_directed_disassoc_count} (forzados: {forced_disassoc_count}), "
                f"DEAUTH: {client_directed_deauth_count} (forzados: {forced_deauth_count})"
            ),
            recommendation=rec
        ))
        
        # 3. Transición de Bandas (Steering Efectivo)
        # FILOSOFÍA CORREGIDA Y PEGADA A WIRESHARK:
        # - El criterio de éxito se basa en lo que efectivamente se ve en la captura:
        #   * Cambios de banda físicos (2.4 <-> 5 GHz)
        #   * Roaming entre BSSIDs distintos (misma banda)
        #   * Respuestas BTM Accept (status 0) como evidencia de cooperación del cliente.
        # - Los contadores deben ser fácilmente reconciliables con los resúmenes de Wireshark.
        
        # Contar transiciones con cambio de banda exitosas (vista reconstruida)
        # CORRECCIÓN: Usar la misma lógica que el frontend - comparar transiciones consecutivas
        # para detectar cambios de banda reales incluso si is_band_change no está marcado correctamente
        def normalize_band(band: Optional[str]) -> Optional[str]:
            if not band:
                return None
            band_str = str(band).lower()
            if '5' in band_str:
                return '5GHz'
            if '2.4' in band_str or '2,4' in band_str:
                return '2.4GHz'
            return band
        
        # Ordenar transiciones por tiempo
        sorted_transitions = sorted([t for t in transitions if t.is_successful], key=lambda x: x.start_time)
        band_change_transitions = 0
        
        for idx, t in enumerate(sorted_transitions):
            from_band = normalize_band(t.from_band)
            to_band = normalize_band(t.to_band)
            is_band_change = t.is_band_change
            
            # Comparar con la transición anterior para detectar cambios de banda reales
            if idx > 0:
                prev_transition = sorted_transitions[idx - 1]
                if prev_transition.to_band:
                    prev_band = normalize_band(prev_transition.to_band)
                    current_band = to_band or from_band
                    
                    if prev_band and current_band and prev_band != current_band:
                        # Hay un cambio de banda real comparando con la transición anterior
                        is_band_change = True
                    elif is_band_change and from_band == to_band:
                        if prev_band == to_band:
                            is_band_change = False
                        elif prev_band and prev_band != to_band:
                            is_band_change = True
            elif not is_band_change and from_band and to_band and from_band != to_band:
                is_band_change = True
            
            # Contar solo si realmente hay un cambio de banda válido
            if is_band_change and from_band and to_band and from_band != to_band:
                band_change_transitions += 1
        
        # Contar transiciones exitosas entre BSSIDs distintos (roaming dentro de la misma banda, vista reconstruida)
        bssid_change_transitions = sum(
            1
            for t in transitions
            if t.is_successful
            and t.from_bssid
            and t.to_bssid
            and t.from_bssid != t.to_bssid
        )
        
        # Usar datos raw de Wireshark para BTM responses exitosos
        btm_successful_responses = raw_btm_accept if raw_btm_accept > 0 else sum(1 for e in (steering_events or []) 
                                       if e.get("type") == "btm" 
                                       and e.get("event_type") == "response"
                                       and (e.get("status_code") == 0 or str(e.get("status_code")) == "0"))
        
        # Contar transiciones exitosas totales (para información general / dashboards)
        successful_transitions_count = success_count_override if success_count_override > 0 else sum(1 for t in transitions if t.is_successful)
        
        # Steering efectivo SOLO si hay:
        # Al menos 2 cambios de banda físicos exitosos (2.4 <-> 5 GHz)
        # NOTA: BTM Accept solo cuenta si también hay cambios de banda físicos.
        # Un BTM Accept sin cambio físico NO se considera steering efectivo.
        # Roaming entre BSSIDs (misma banda) NO cuenta para este criterio.
        
        # Si hay BTM Accept PERO no hay suficientes cambios de banda físicos, no es steering efectivo
        if btm_successful_responses > 0 and band_change_transitions < 2:
            # BTM Accept sin suficientes cambios de banda físicos: no es steering efectivo
            steering_passed = False
        else:
            # Requiere al menos 2 cambios de banda físicos para ser exitoso
            steering_passed = band_change_transitions >= 2
        
        # Recomendación solo si no hubo steering efectivo
        if not steering_passed:
            if band_change_transitions == 0:
                rec_steering = "No se detectaron cambios de banda físicos. Se requieren al menos 2 cambios de banda (2.4 <-> 5 GHz) para considerar steering efectivo. Verificar que la captura contenga el flujo completo de steering."
            elif band_change_transitions == 1:
                rec_steering = "Solo se detectó 1 cambio de banda físico. Se requieren al menos 2 cambios de banda (2.4 <-> 5 GHz) para considerar steering efectivo."
            else:
                rec_steering = "No se cumplió el criterio de steering efectivo. Se requieren al menos 2 cambios de banda físicos."
        else:
            rec_steering = None

        # Detalle tipo Wireshark: expresar explícitamente qué se contó.
        # Formato: TRANSICIONES CON CAMBIO DE BANDA | TRANSICIONES TOTALES | BTM ACCEPT
        details = (
            f"TRANSICIONES CON CAMBIO DE BANDA: {band_change_transitions} | "
            f"TRANSICIONES TOTALES: {successful_transitions_count} | "
            f"BTM ACCEPT: {raw_btm_accept}"
        )
        
        checks.append(ComplianceCheck(
            check_name="Steering Efectivo",
            description="Se deben realizar al menos 2 cambios de banda físicos exitosos (2.4 <-> 5 GHz) para considerar steering efectivo",
            category="performance",
            passed=steering_passed,
            severity="high",
            details=details,
            recommendation=rec_steering
        ))

        # 4. KVR Suficiente (Flexible: 1 de 3 es éxito)
        kvr_passed = sum([kvr.k_support, kvr.v_support, kvr.r_support]) >= 1
        checks.append(ComplianceCheck(
            check_name="Estándares KVR",
            description="Soporte de estándares de movilidad (Mínimo 1 de 3: k, v, r)",
            category="kvr",
            passed=kvr_passed,
            severity="medium",
            details=f"k={kvr.k_support}, v={kvr.v_support}, r={kvr.r_support}",
            recommendation="Se recomienda habilitar el estándar faltante para roaming óptimo" if not kvr_passed else None
        ))
        
        return checks


    def _determine_verdict(self, checks: List[ComplianceCheck], transitions: List[SteeringTransition], btm_rate: float, success_count: int = 0) -> str:
        """Determina el veredicto final basado en reglas de negocio."""
        # Obtener checks por categoría para evitar problemas de matching por acentos
        assoc_check = next((c for c in checks if c.category == "association"), None)
        btm_check = next((c for c in checks if c.category == "btm"), None)
        kvr_check = next((c for c in checks if c.category == "kvr"), None)
        performance_check = next((c for c in checks if c.category == "performance"), None)

        # Regla 1: Si hay fallos de asociación críticos (Deauth/Disassoc/Status Error) -> FAILED
        # La estabilidad es lo más importante.
        if assoc_check and not assoc_check.passed:
            return "FAILED"
            
        # Regla 2: Si el soporte BTM falló explícitamente (Solicitado pero ignorado o rechazado) -> FAILED
        if btm_check and not btm_check.passed:
            return "FAILED"

        # Regla 3: Si hay steering efectivo (transiciones exitosas O BTM responses exitosos)
        # El check de "Steering Efectivo" ahora considera:
        # - Cambios de banda exitosos
        # - Transiciones exitosas (con o sin cambio de banda)
        # - BTM responses exitosos (status_code 0)
        if performance_check and performance_check.passed:
            # Si el check de performance pasó, hay steering efectivo
            # Verificar KVR solo si es crítico (puede ser opcional dependiendo del contexto)
            if kvr_check and not kvr_check.passed:
                # Aún es SUCCESS porque el steering funcionó, solo falta KVR completo
                pass
            return "SUCCESS"
            
        # Regla 4: Si hay transiciones exitosas directamente (fallback)
        # IMPORTANTE: Solo es SUCCESS si hay steering efectivo real
        if success_count > 0:
            # Verificar si hay steering efectivo antes de dar SUCCESS
            if performance_check and performance_check.passed:
                # Hay steering efectivo, es SUCCESS
                if kvr_check and not kvr_check.passed:
                    pass
                return "SUCCESS"
            # Si hay transiciones exitosas pero NO hay steering efectivo, es PARTIAL
            if btm_check and btm_check.passed:
                return "PARTIAL"
            # Si no hay BTM pero hay transiciones, puede ser roaming espontáneo
            # En este caso, si no es efectivo, es FAILED
            return "FAILED"
            
        # Regla 5: Éxito vía BTM aunque no hayamos visto la reasociación completa
        # IMPORTANTE: BTM Accept sin cambio físico no es SUCCESS, es PARTIAL
        if btm_check and btm_check.passed and btm_rate > 0.5:
            if performance_check and not performance_check.passed:
                # Cliente cooperó (BTM Accept) pero no ejecutó cambio físico
                return "PARTIAL"
            # Si hay steering efectivo, ya se retornó SUCCESS arriba en Regla 3
            # Si llegamos aquí y performance_check no existe, es un caso edge
            return "SUCCESS"
            
        # Regla 6: Si no hay transiciones pero hay steering preventivo confirmado
        if performance_check and performance_check.passed:
            # Si el check de performance pasó es porque detectó steering preventivo basado en tráfico
            return "SUCCESS"
            
        return "FAILED"
