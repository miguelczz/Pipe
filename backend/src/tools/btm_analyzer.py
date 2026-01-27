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
        signal_samples: List[Dict[str, Any]] = None
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
        # REGLA DE ORO: WiresharkTool es la ÚNICA fuente de verdad
        # ============================================================
        # Si WiresharkTool ya calculó steering_attempts y successful_transitions,
        # esos valores son DEFINITIVOS y NO se recalculan.
        
        ws_attempts = band_counters.get("steering_attempts", 0)
        ws_success = band_counters.get("successful_transitions", 0)
        
        # Si WiresharkTool proporcionó valores, usarlos directamente
        if ws_attempts > 0 or ws_success > 0:
            btm_requests = ws_attempts
            successful_transitions = ws_success
            logger.info(f"📊 Usando valores de WiresharkTool: {ws_success}/{ws_attempts} transiciones")
        else:
            # Fallback: Solo si WiresharkTool no detectó nada, calcular desde transitions
            btm_requests = max(btm_stats.get("requests", 0), len(transitions))
            successful_transitions = sum(1 for t in transitions if t.is_successful)
            logger.info(f"📊 Calculando desde transitions locales: {successful_transitions}/{btm_requests}")
        
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
            device_info=device_info
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
        
        # Agrupar eventos por cliente
        events_by_client = {}
        for e in raw_events:
            c = e.get("client_mac")
            if c:
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
                
                # 1. Detectar inicio de transición
                if etype == "BTM Request" or (subtype == 13 and ev.get("action_code") == 7):
                    last_btm_req = ev
                elif etype in ["Deauthentication", "Disassociation"] or subtype in [10, 12]:
                    last_deauth = ev
                    
                # 2. Detectar fin de transición (Reassociation)
                if etype in ["Reassociation Response", "Association Response"] or subtype in [1, 3]:
                    # Verificar éxito (Status Code 0)
                    assoc_status = str(ev.get("assoc_status_code", ""))
                    is_success = assoc_status in ["0", "0x00", "0x0", "0x0000"]
                    
                    if is_success:
                        # Determinar tipo
                        if last_deauth and (ev["timestamp"] - last_deauth["timestamp"] < REASSOC_TIMEOUT_SECONDS):
                            # Es Agresivo (hubo deauth reciente)
                            start_node = last_deauth
                            s_type = SteeringType.AGGRESSIVE
                        elif last_btm_req and (ev["timestamp"] - last_btm_req["timestamp"] < REASSOC_TIMEOUT_SECONDS):
                            # Es Asistido (hubo BTM req reciente)
                            start_node = last_btm_req
                            s_type = SteeringType.ASSISTED
                        else:
                            # Roaming espontáneo o Asistido sin captura de Request
                            start_node = ev # Usamos el mismo evento como inicio si no hay previo
                            s_type = SteeringType.UNKNOWN
                        
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
                        
                        # Reset estados
                        last_btm_req = None
                        last_deauth = None
        
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
        device_info: Optional[DeviceInfo] = None
    ) -> List[ComplianceCheck]:
        """Genera la tabla de resumen de cumplimiento."""
        checks = []
        
        # 1. BTM Support (802.11v)
        btm_stats = band_counters.get("btm_stats", {})
        has_btm_responses = btm_responses > 0
        
        # Recopilar todos los códigos detectados (éxitos y rechazos)
        status_codes_raw = btm_stats.get("status_codes", [])
        status_lines = []
        if status_codes_raw:
            unique_codes = list(dict.fromkeys(status_codes_raw))
            for code in unique_codes:
                desc = BTMStatusCode.get_description(code)
                status_lines.append(f"Code: {code} ({desc})")
        
        status_info = "\n" + "\n".join(status_lines) if status_lines else ""
        
        # Si hubo peticiones pero 0 respuestas, falla. Si hubo respuestas pero todas rechazo, también se muestran.
        if btm_requests > 0 and btm_responses == 0:
            passed_btm = False
            details = f"Request: {btm_requests}, Response: {btm_responses}{status_info}"
        else:
            passed_btm = has_btm_responses or kvr.v_support
            details = f"Requests: {btm_requests}, Responses: {btm_responses}{status_info}"
        
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
        primary_client = device_info.mac_address if device_info else None
        
        # Filtros inteligentes para Deauth/Disassoc
        forced_deauth_count = 0
        forced_disassoc_count = 0
        
        # Contadores brutos para el detalle visual
        assoc_req = 0
        assoc_resp = 0
        reassoc_req = 0
        reassoc_resp = 0
        
        for e in (steering_events or []):
            st = e.get("subtype")
            # Contar ráfaga de handshakes (esto es general)
            if st == 0: assoc_req += 1
            elif st == 1: assoc_resp += 1
            elif st == 2: reassoc_req += 1
            elif st == 3: reassoc_resp += 1
            
            # Análisis de desconexiones (SOLO SI ES EL CLIENTE ANALIZADO)
            elif st in [10, 12] and primary_client:
                is_forced, classification, desc = DeauthValidator.validate_and_classify(e, primary_client)
                
                if is_forced:
                    if st == 10: forced_disassoc_count += 1
                    else: forced_deauth_count += 1
                else:
                    logger.debug(f"Deauth/Disassoc ignorado en cumplimiento: {desc}")
        
        assoc_failures = band_counters.get("association_failures", [])
        failure_count = len(assoc_failures)
        
        # Un handshake se considera completo si hay al menos un ciclo exitoso
        has_complete_handshake = (assoc_req > 0 and assoc_resp > 0) or (reassoc_req > 0 and reassoc_resp > 0)
        
        # CRITERIO DE ÉXITO: Handshake completo Y sin desconexiones forzadas REALES
        assoc_passed = has_complete_handshake and failure_count == 0 and (forced_deauth_count == 0 and forced_disassoc_count == 0)
        
        # Recomendación técnica precisa
        if (forced_deauth_count + forced_disassoc_count) > 0:
            rec = f"Prueba FALLIDA: Se detectaron {forced_deauth_count} Deauth y {forced_disassoc_count} Disassoc DIRIGIDOS al cliente, indicando inestabilidad forzada."
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
            details=f"Assoc: {assoc_req}/{assoc_resp}, Reassoc: {reassoc_req}/{reassoc_resp}\nDisassoc: {forced_disassoc_count}, Deauth: {forced_deauth_count}",
            recommendation=rec
        ))
        
        # 3. Transición de Bandas (Steering Efectivo)
        # FILOSOFÍA SIMPLE: Si hubo cambios exitosos de banda, el steering funcionó
        band_changes = success_count_override
        
        # CRITERIO DE ÉXITO SIMPLIFICADO: ¿Hubo al menos 1 cambio exitoso?
        steering_passed = band_changes >= 1
        
        # Logging para diagnóstico
        logger.info(f"🔍 Evaluación Steering Efectivo: cambios_exitosos={band_changes}, resultado={'PASÓ' if steering_passed else 'FALLÓ'}")
        
        # Recomendación solo si no hubo cambios
        if band_changes == 0:
            rec_steering = "No se detectaron transiciones de banda efectivas. Verificar que la captura contenga el flujo completo de steering."
        else:
            rec_steering = None

        checks.append(ComplianceCheck(
            check_name="Steering Efectivo",
            description="Se deben realizar cambios de banda estables (2.4 -> 5GHz)",
            category="performance",
            passed=steering_passed,
            severity="high",
            details=f"Cambios detectados: {band_changes}",
            recommendation=rec_steering
        ))

        # 4. KVR Suficiente (Flexible: 2 de 3 es éxito)
        kvr_passed = sum([kvr.k_support, kvr.v_support, kvr.r_support]) >= 2
        checks.append(ComplianceCheck(
            check_name="Estándares KVR",
            description="Soporte de estándares de movilidad (Mínimo 2 de 3: k, v, r)",
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
            logger.warning("❌ Fallo crítico en Asociación/Reasociación detectado -> FAILED")
            return "FAILED"
            
        # Regla 2: Si el soporte BTM falló explícitamente (Solicitado pero ignorado o rechazado) -> FAILED
        if btm_check and not btm_check.passed:
            logger.warning("❌ Soporte BTM fallido -> FAILED")
            return "FAILED"

        # Regla 3: Si hay transiciones exitosas (Criterio del usuario)
        if success_count > 0:
            # Si KVR no pasó, aún es FAILED (el agente explicará en texto que hubo transiciones pero faltaron protocolos)
            if kvr_check and not kvr_check.passed:
                logger.warning("⚠️ Transición exitosa pero sin soporte KVR adecuado -> FAILED (se explicará en el análisis)")
                return "FAILED" 
            return "SUCCESS"
            
        # Regla 4: Éxito vía BTM aunque no hayamos visto la reasociación completa
        if btm_check and btm_check.passed and btm_rate > 0.5:
            return "SUCCESS"
            
        # Regla 5: Si no hay transiciones pero hay steering preventivo confirmado
        if performance_check and performance_check.passed:
            # Si el check de performance pasó es porque detectó steering preventivo basado en tráfico
            return "SUCCESS"
            
        return "FAILED"
