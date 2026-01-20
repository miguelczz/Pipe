"""
Herramienta para análisis de capturas de red (Wireshark / PCAP) asistido por IA.
Enfocada específicamente en auditoría de Band Steering (802.11).
"""

import logging
import os
from collections import Counter
from typing import Dict, Any

from openai import OpenAI
from ..settings import settings

logger = logging.getLogger(__name__)


class WiresharkTool:

    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            max_retries=2,
        )
        self.llm_model = settings.llm_model

    def _extract_basic_stats(self, file_path: str, max_packets: int = 2000) -> Dict[str, Any]:
        """
        Extrae estadísticas detalladas de la captura con enfoque en band steering.
        Analiza secuencias temporales, transiciones de BSSID, y métricas de calidad.
        """
        import subprocess
        import shutil
        from datetime import datetime

        tshark_path = shutil.which("tshark")
        if not tshark_path:
            raise RuntimeError("tshark no está disponible en el PATH.")

        protocol_counter = Counter()
        src_counter = Counter()
        dst_counter = Counter()

        total_packets = 0
        total_bytes = 0
        total_tcp_packets = 0
        total_wlan_packets = 0

        tcp_retransmissions = 0
        wlan_retries = 0
        dns_errors = 0

        # Estructuras para análisis de band steering
        steering_events = []  # Lista de eventos ordenados temporalmente
        client_sessions = {}  # Sesiones por MAC de cliente
        bssid_info = {}  # Información de cada BSSID (banda, canal)
        
        cmd = [
            tshark_path,
            "-r", file_path,
            "-T", "fields",
            "-e", "frame.time_epoch",
            "-e", "frame.protocols",
            "-e", "ip.src",
            "-e", "ip.dst",
            "-e", "frame.len",
            "-e", "tcp.analysis.retransmission",
            "-e", "wlan.fc.retry",
            "-e", "dns.flags.rcode",
            "-e", "wlan.fc.type_subtype",
            "-e", "wlan.bssid",
            "-e", "wlan.sa",  # Source Address (cliente)
            "-e", "wlan.da",  # Destination Address
            "-e", "wlan_radio.frequency",  # Frecuencia (2.4GHz vs 5GHz)
            "-e", "wlan.fixed.reason_code",  # Reason code para deauth/disassoc
            "-e", "wlan.ssid",  # SSID
            # Campos BTM (802.11v) - Campos reales de Wireshark 4.6.2
            "-e", "wlan.fixed.category_code",                # Category (10 = WNM)
            "-e", "wlan.fixed.action_code",                  # Action (7=Req, 8=Resp)
            "-e", "wlan.fixed.bss_transition_status_code",   # BTM Status Code
            "-e", "wlan.fixed.publicact",                    # Public Action (para debug Cat 4)
            "-c", str(max_packets)
        ]

        logger.info(f"Ejecutando tshark en: {file_path}")
        logger.debug(f"Comando tshark: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False
        )

        if result.returncode != 0:
            logger.error(f"Error en tshark: {result.stderr}")
            raise RuntimeError(result.stderr or "Error ejecutando tshark")

        # Logging de diagnóstico
        lines = result.stdout.splitlines()
        logger.info(f"Total de líneas extraídas por tshark: {len(lines)}")
        
        # Mostrar primeras 3 líneas para diagnóstico
        if lines:
            logger.debug("Primeras líneas de salida de tshark:")
            for i, line in enumerate(lines[:3], 1):
                logger.debug(f"  Línea {i}: {line[:200]}")  # Primeros 200 caracteres

        # Contador de paquetes WLAN para diagnóstico
        wlan_packets_with_subtype = 0
        wlan_packets_without_subtype = 0
        subtype_counter = Counter()  # Contador de tipos de frames
        
        # Contadores para detección de Steering Preventivo (Client Steering)
        band_counters = {
            "beacon_24": 0, "beacon_5": 0,
            "probe_req": 0,
            "probe_resp_24": 0, "probe_resp_5": 0,
            "data_24": 0, "data_5": 0,
        }

        for line in lines:
            if not line.strip():
                continue

            fields = line.split("\t")
            # Ajustar para 19 campos (15 base + 3 BTM + 1 PublicAct)
            while len(fields) < 19:
                fields.append("")

            (timestamp, protocols, ip_src, ip_dst, frame_len, tcp_r, wlan_r, 
             dns_r, subtype, bssid, wlan_sa, wlan_da, frequency, reason_code, ssid,
             category_code, action_code, btm_status_code, public_action_code) = fields

            total_packets += 1
            # ... (código existente) ...

            # ... (lógica de protocolos/contadores igual) ...

            # Análisis detallado de eventos 802.11
            if subtype:
                try:
                    # Conversion subtype (igual)
                    if subtype.startswith('0x'):
                        subtype_int = int(subtype, 16)
                    else:
                        subtype_int = int(subtype)
                    
                    wlan_packets_with_subtype += 1
                    subtype_counter[subtype_int] += 1  # Contar este tipo de frame
                    
                    # --- DETECCIÓN DE BTM (802.11v) ---
                    # Subtype 13 = Action Frame, Category 10 = WNM
                    if subtype_int == 13 and category_code == "10": # Category 10 = WNM
                        # Normalizar action_code (dec/hex)
                        ac_val = None
                        try:
                            if action_code:
                                ac_val = int(action_code) if action_code.isdigit() else int(action_code, 16)
                        except: 
                            pass

                        if ac_val == 7: # BTM Request
                             logger.info(f"✅ BTM REQUEST detectado")
                             if "btm_stats" not in band_counters:
                                band_counters["btm_stats"] = {"requests": 0, "responses": 0, "status_codes": []}
                             band_counters["btm_stats"]["requests"] += 1
                             
                        elif ac_val == 8: # BTM Response
                            logger.info(f"✅ BTM RESPONSE detectado. Status Code={btm_status_code}")
                            if "btm_stats" not in band_counters:
                                band_counters["btm_stats"] = {"requests": 0, "responses": 0, "status_codes": []}
                            band_counters["btm_stats"]["responses"] += 1
                            
                            # Guardar status code si existe
                            if btm_status_code:
                                band_counters["btm_stats"]["status_codes"].append(btm_status_code)
                    # ----------------------------------

                    # --- LÓGICA DE STEERING PREVENTIVO ---
                    # Determinar banda del paquete actual
                    current_band = None
                    if frequency:
                        try:
                            freq_mhz_val = int(frequency)
                            if 2400 <= freq_mhz_val <= 2500:
                                current_band = "2.4GHz"
                            elif 5000 <= freq_mhz_val <= 6000:
                                current_band = "5GHz"
                        except ValueError:
                            pass

                    # Contar frames clave por banda
                    if subtype_int == 8:  # Beacon
                        if current_band == "2.4GHz":
                            band_counters["beacon_24"] += 1
                        elif current_band == "5GHz":
                            band_counters["beacon_5"] += 1
                    
                    elif subtype_int == 4:  # Probe Request
                        band_counters["probe_req"] += 1
                    
                    elif subtype_int == 5:  # Probe Response
                        if current_band == "2.4GHz":
                            band_counters["probe_resp_24"] += 1
                        elif current_band == "5GHz":
                            band_counters["probe_resp_5"] += 1
                            
                    elif subtype_int in [0x28, 0x20]:  # QoS Data (40) o Data (32)
                        if current_band == "2.4GHz":
                            band_counters["data_24"] += 1
                        elif current_band == "5GHz":
                            band_counters["data_5"] += 1
                    # -------------------------------------
                    
                    event_type = None
                    
                    if subtype_int == 0:
                        event_type = "Association Request"
                    elif subtype_int == 1:
                        event_type = "Association Response"
                    elif subtype_int == 2:
                        event_type = "Reassociation Request"
                    elif subtype_int == 3:
                        event_type = "Reassociation Response"
                    elif subtype_int == 10:
                        event_type = "Disassociation"
                    elif subtype_int == 12:
                        event_type = "Deauthentication"
                    
                    if event_type:
                        # Determinar banda
                        band = None
                        if frequency:
                            try:
                                freq_mhz = float(frequency)
                                if 2400 <= freq_mhz <= 2500:
                                    band = "2.4GHz"
                                elif 5000 <= freq_mhz <= 6000:
                                    band = "5GHz"
                            except ValueError:
                                pass
                        
                        event = {
                            "timestamp": float(timestamp) if timestamp else 0,
                            "type": event_type,
                            "subtype": subtype_int,
                            "client_mac": wlan_sa or wlan_da,
                            "bssid": bssid,
                            "ssid": ssid,
                            "band": band,
                            "frequency": frequency,
                            "reason_code": reason_code
                        }
                        steering_events.append(event)
                        
                        # Registrar información del BSSID (incluso sin banda)
                        if bssid:
                            if bssid not in bssid_info:
                                bssid_info[bssid] = {
                                    "band": band,  # Puede ser None
                                    "ssid": ssid,
                                    "frequency": frequency
                                }
                            # Actualizar banda si ahora tenemos información y antes no
                            elif band and not bssid_info[bssid].get("band"):
                                bssid_info[bssid]["band"] = band
                                bssid_info[bssid]["frequency"] = frequency
                except (ValueError, AttributeError):
                    # Si no se puede parsear, ignorar este paquete
                    wlan_packets_without_subtype += 1
            elif is_wlan:
                wlan_packets_without_subtype += 1

        # Logging de resultados
        logger.info(f"Paquetes procesados: {total_packets}")
        logger.info(f"Paquetes WLAN: {total_wlan_packets}")
        logger.info(f"Paquetes WLAN con subtype: {wlan_packets_with_subtype}")
        logger.info(f"Paquetes WLAN sin subtype: {wlan_packets_without_subtype}")
        logger.info(f"Eventos 802.11 capturados: {len(steering_events)}")
        logger.info(f"BSSIDs únicos: {len(bssid_info)}")
        logger.info(f"Contadores BTM capturados: {band_counters.get('btm_stats', 'Ninguno')}")
        
        # Mostrar tipos de frames más comunes
        if subtype_counter:
            logger.info("Tipos de frames WLAN detectados (top 10):")
            for subtype_val, count in subtype_counter.most_common(10):
                frame_name = {
                    0: "Association Request",
                    1: "Association Response",
                    2: "Reassociation Request",
                    3: "Reassociation Response",
                    8: "Beacon",
                    10: "Disassociation",
                    12: "Deauthentication",
                    4: "Probe Request",
                    5: "Probe Response",
                    13: "Action",
                    24: "Block Ack Request",
                    25: "Block Ack",
                    28: "QoS Data"
                }.get(subtype_val, f"Unknown (0x{subtype_val:02x})")
                logger.info(f"  - {frame_name}: {count}")
        
        if len(steering_events) > 0:
            logger.debug(f"Primeros eventos capturados: {steering_events[:3]}")

        # Análisis de sesiones de clientes y transiciones
        steering_analysis = self._analyze_steering_patterns(steering_events, bssid_info, band_counters)
        
        # Evaluación de calidad de captura para band steering
        capture_quality = self._evaluate_capture_quality(steering_analysis, steering_events)

        diagnostics = {
            "tcp_retransmissions": tcp_retransmissions,
            "wlan_retries": wlan_retries,
            "dns_errors": dns_errors,
            "steering_events_count": len(steering_events),
            "unique_bssid_count": len(bssid_info),
            "bssid_info": bssid_info,
            "capture_quality": capture_quality,
            "band_counters": band_counters,  # Nuevo: Contadores para steering preventivo
        }

        return {
            "total_packets": total_packets,
            "total_tcp_packets": total_tcp_packets,
            "total_wlan_packets": total_wlan_packets,
            "approx_total_bytes": total_bytes,
            "diagnostics": diagnostics,
            "steering_analysis": steering_analysis,
            "steering_events": steering_events,
            "top_protocols": protocol_counter.most_common(10),
            "top_sources": src_counter.most_common(10),
            "top_destinations": dst_counter.most_common(10),
        }

    def _analyze_steering_patterns(self, events: list, bssid_info: dict, band_counters: dict = None) -> Dict[str, Any]:
        """
        Analiza patrones de band steering en los eventos capturados.
        
        Soporta:
        1. Steering agresivo (Deauth → Reassoc)
        2. Steering asistido (Reassoc directa)
        3. Steering preventivo (Client Steering silenciando 2.4GHz)
        """
        
        # Detectar Steering Preventivo (siempre se chequea, incluso sin eventos de transición)
        preventive_detected = False
        if band_counters:
            preventive_detected = self._detect_preventive_steering(band_counters)

        if not events and not preventive_detected:
            return {
                "transitions": [],
                "steering_attempts": 0,
                "successful_transitions": 0,
                "failed_transitions": 0,
                "loop_detected": False,
                "avg_transition_time": 0,
                "max_transition_time": 0,
                "transition_times": [],
                "verdict": "NO_DATA",
                "clients_analyzed": 0,
                "preventive_steering": False
            }
        
        # Ordenar eventos por timestamp
        sorted_events = sorted(events, key=lambda x: x["timestamp"])
        
        # Agrupar por cliente
        client_events = {}
        for event in sorted_events:
            client = event["client_mac"]
            if client and client != "":
                if client not in client_events:
                    client_events[client] = []
                client_events[client].append(event)
        
        transitions = []
        total_steering_attempts = 0
        successful_transitions = 0
        failed_transitions = 0
        loop_detected = False
        transition_times = []
        
        # Analizar cada cliente
        for client_mac, client_event_list in client_events.items():
            if len(client_event_list) < 2:
                continue
            
            # Rastrear BSSID actual del cliente
            current_bssid = None
            last_reassoc_time = None
            
            for i, event in enumerate(client_event_list):
                event_subtype = event["subtype"]
                
                # CASO 1: Steering agresivo (Deauth/Disassoc → Reassoc)
                if event_subtype in [10, 12]:  # Disassoc o Deauth
                    total_steering_attempts += 1
                    
                    deauth_time = event["timestamp"]
                    deauth_bssid = event["bssid"]
                    deauth_band = event["band"]
                    reason_code = event["reason_code"]
                    
                    # Buscar reassociation subsecuente
                    reassoc_found = False
                    reassoc_time = None
                    new_bssid = None
                    new_band = None
                    
                    for j in range(i + 1, min(i + 10, len(client_event_list))):
                        next_event = client_event_list[j]
                        
                        if next_event["subtype"] in [0, 2]:  # Assoc o Reassoc
                            reassoc_found = True
                            reassoc_time = next_event["timestamp"]
                            new_bssid = next_event["bssid"]
                            new_band = next_event["band"]
                            break
                    
                    transition_time = (reassoc_time - deauth_time) if reassoc_time else None
                    is_band_change = (deauth_band and new_band and deauth_band != new_band)
                    is_bssid_change = (deauth_bssid and new_bssid and deauth_bssid != new_bssid)
                    
                    # Detectar bucles
                    returned_to_original = False
                    if reassoc_found and new_bssid and current_bssid:
                        if new_bssid == current_bssid:
                            returned_to_original = True
                            loop_detected = True
                    
                    # Clasificar transición
                    status = self._classify_transition(
                        reassoc_found, transition_time, is_band_change, 
                        is_bssid_change, returned_to_original
                    )
                    
                    if status == "SUCCESS":
                        successful_transitions += 1
                    elif status in ["LOOP", "TIMEOUT", "NO_REASSOC"]:
                        failed_transitions += 1
                    
                    if transition_time:
                        transition_times.append(transition_time)
                    
                    transitions.append({
                        "client": client_mac,
                        "type": "aggressive",  # Steering con Deauth
                        "deauth_time": deauth_time,
                        "reassoc_time": reassoc_time,
                        "transition_time": transition_time,
                        "from_bssid": deauth_bssid,
                        "to_bssid": new_bssid,
                        "from_band": deauth_band,
                        "to_band": new_band,
                        "is_band_change": is_band_change,
                        "reason_code": reason_code,
                        "status": status,
                        "returned_to_original": returned_to_original
                    })
                    
                    if reassoc_found and new_bssid:
                        current_bssid = new_bssid
                
                # CASO 2: Steering asistido (Reassociation directa - 802.11k/v/r)
                elif event_subtype in [2, 3]:  # Reassoc Request o Response
                    new_bssid = event["bssid"]
                    new_band = event["band"]
                    reassoc_time = event["timestamp"]
                    
                    # Solo contar si hay cambio de BSSID (no es la primera asociación)
                    if current_bssid and new_bssid and current_bssid != new_bssid:
                        total_steering_attempts += 1
                        
                        # Calcular tiempo desde última reassoc
                        transition_time = None
                        if last_reassoc_time:
                            transition_time = reassoc_time - last_reassoc_time
                        
                        # Determinar banda anterior (del BSSID anterior)
                        old_band = None
                        if current_bssid in bssid_info:
                            old_band = bssid_info[current_bssid].get("band")
                        
                        is_band_change = (old_band and new_band and old_band != new_band)
                        is_bssid_change = True  # Por definición, ya verificamos que cambió
                        
                        # Detectar bucles (volver a BSSID anterior)
                        returned_to_original = False
                        # Buscar si vuelve al BSSID anterior en los próximos eventos
                        for k in range(i + 1, min(i + 5, len(client_event_list))):
                            if client_event_list[k]["bssid"] == current_bssid:
                                returned_to_original = True
                                loop_detected = True
                                break
                        
                        # Clasificar (para steering asistido, siempre hay "reassoc")
                        status = self._classify_transition(
                            True, transition_time, is_band_change,
                            is_bssid_change, returned_to_original
                        )
                        
                        if status == "SUCCESS":
                            successful_transitions += 1
                        elif status in ["LOOP", "SLOW"]:
                            # Para steering asistido, SLOW no es fallo crítico
                            if status == "LOOP":
                                failed_transitions += 1
                        
                        if transition_time:
                            transition_times.append(transition_time)
                        
                        transitions.append({
                            "client": client_mac,
                            "type": "assisted",  # Steering asistido (802.11k/v/r)
                            "deauth_time": None,
                            "reassoc_time": reassoc_time,
                            "transition_time": transition_time,
                            "from_bssid": current_bssid,
                            "to_bssid": new_bssid,
                            "from_band": old_band,
                            "to_band": new_band,
                            "is_band_change": is_band_change,
                            "reason_code": None,
                            "status": status,
                            "returned_to_original": returned_to_original
                        })
                    
                    # Actualizar estado del cliente
                    if new_bssid:
                        current_bssid = new_bssid
                        last_reassoc_time = reassoc_time
                
                # Actualizar BSSID actual para Association inicial
                elif event_subtype in [0, 1] and event["bssid"]:
                    if not current_bssid:  # Primera asociación
                        current_bssid = event["bssid"]
                        last_reassoc_time = event["timestamp"]
        
        # Calcular métricas
        avg_transition_time = sum(transition_times) / len(transition_times) if transition_times else 0
        max_transition_time = max(transition_times) if transition_times else 0
        
        # Determinar veredicto general
        if preventive_detected and total_steering_attempts == 0:
            verdict = "PREVENTIVE_SUCCESS"
        else:
            verdict = self._determine_verdict(
                total_steering_attempts, successful_transitions, 
                failed_transitions, loop_detected, avg_transition_time
            )
        
        return {
            "transitions": transitions,
            "steering_attempts": total_steering_attempts,
            "successful_transitions": successful_transitions,
            "failed_transitions": failed_transitions,
            "loop_detected": loop_detected,
            "avg_transition_time": round(avg_transition_time, 3),
            "max_transition_time": round(max_transition_time, 3),
            "transition_times": transition_times,
            "verdict": verdict,
            "clients_analyzed": len(client_events),
            "preventive_steering": preventive_detected
        }

    def _detect_preventive_steering(self, diag: dict) -> bool:
        """
        Detecta Steering Preventivo (Client Steering) o Selección de Banda Exitosa.
        
        Criterio (más flexible):
        1. La red 2.4GHz está disponible (Beacons > 0).
        2. El cliente genera tráfico de datos.
        3. La inmensa mayoría del tráfico (>90%) ocurre en 5GHz.
        
        Esto indica que el cliente (o la red) prefirió 5GHz sobre 2.4GHz,
        lo cual es el objetivo final del Band Steering.
        """
        beacon_24 = diag.get("beacon_24", 0)
        data_24 = diag.get("data_24", 0)
        data_5 = diag.get("data_5", 0)
        
        total_data = data_24 + data_5
        
        if total_data < 10:  # Necesitamos un mínimo de tráfico para decidir
            return False
            
        # Verificar cobertura 2.4GHz (si no hay 2.4, no hay steering que hacer)
        has_network_24 = beacon_24 > 0
        
        # Calcular ratio de preferencia por 5GHz
        ratio_5ghz = data_5 / total_data
        
        # Si hay red 2.4 pero el cliente prefiere 5GHz (>90%), es éxito
        # (Se asume que "Client Steering" o configuración de AP funcionó)
        is_steering_success = has_network_24 and ratio_5ghz > 0.90
        
        return is_steering_success
    
    def _classify_transition(self, reassoc_found: bool, transition_time: float, 
                            is_band_change: bool, is_bssid_change: bool, 
                            returned_to_original: bool) -> str:
        """Clasifica una transición de steering según su calidad."""
        if not reassoc_found:
            return "NO_REASSOC"
        
        if returned_to_original:
            return "LOOP"
        
        if not (is_band_change or is_bssid_change):
            return "NO_CHANGE"
        
        if transition_time is None:
            return "SUCCESS"  # Steering asistido sin tiempo previo
        
        if transition_time < 1.0:
            return "SUCCESS"
        elif transition_time < 3.0:
            return "SLOW"
        else:
            return "TIMEOUT"
    
    def _determine_verdict(self, attempts: int, successful: int, failed: int,
                          loop_detected: bool, avg_time: float) -> str:
        """Determina el veredicto general del análisis de steering."""
        if attempts == 0:
            return "NO_STEERING_DETECTED"
        
        if loop_detected or failed > successful:
            return "FAILED"
        
        if successful > 0:
            if avg_time < 1.0:
                return "EXCELLENT"
            elif avg_time < 2.0:
                return "GOOD"
            else:
                return "ACCEPTABLE"
        
        return "NEEDS_REVIEW"

    def _evaluate_capture_quality(self, steering_analysis: dict, events: list) -> str:
        """
        Evalúa si la captura contiene suficiente información para análisis de band steering.
        Compatible con steering asistido (802.11k/v/r) y agresivo (Deauth-based).
        
        IMPORTANTE: NO exige Deauth. El steering moderno usa Reassociation directa.
        """
        if not events:
            return "INSUFICIENTE - No hay eventos 802.11"
        
        if steering_analysis.get("preventive_steering"):
            return "VALIDA - Steering Preventivo (Client Steering) detectado"

        if steering_analysis["steering_attempts"] == 0:
            return "INSUFICIENTE - No se detectaron intentos de steering"
        
        # Si hubo transiciones exitosas, la captura es válida
        if steering_analysis["successful_transitions"] > 0:
            return "VALIDA - Steering detectado y analizado"
        
        # Steering detectado pero con problemas (aún es analizable)
        if steering_analysis["failed_transitions"] > 0:
            return "VALIDA - Steering fallido pero analizable"
        
        # Hay intentos pero sin conclusión clara
        return "INSUFICIENTE - Eventos inconclusos"

    def _build_technical_summary(self, stats: Dict[str, Any], file_name: str) -> str:
        """
        Construye un resumen técnico detallado con métricas específicas de band steering.
        """
        d = stats["diagnostics"]
        sa = stats["steering_analysis"]
        
        # Información de BSSIDs detectados
        bssid_summary = ""
        if d["bssid_info"]:
            bssid_summary = "BSSID DETECTADOS:\n"
            for bssid, info in d["bssid_info"].items():
                bssid_summary += f"- {bssid}: {info['band']} ({info['ssid']})\n"
            bssid_summary += "\n"
        
        # Resumen de Steering Preventivo (si aplica)
        preventive_summary = ""
        if sa.get("preventive_steering"):
            bc = d.get("band_counters", {})
            preventive_summary = (
                "🛡️ STEERING PREVENTIVO DETECTADO (CLIENT STEERING):\n"
                f"- Beacons 2.4GHz: {bc.get('beacon_24', 0)} (Red disponible)\n"
                f"- Probe Req Cliente: {bc.get('probe_req', 0)} (Cliente buscando)\n"
                f"- Probe Resp 2.4GHz: {bc.get('probe_resp_24', 0)} (AP ignorando en 2.4)\n"
                f"- Probe Resp 5GHz: {bc.get('probe_resp_5', 0)} (AP respondiendo en 5)\n"
                f"- Data 5GHz: {bc.get('data_5', 0)} (Trafico en 5GHz)\n"
                f"- Data 2.4GHz: {bc.get('data_24', 0)} (Sin tráfico en 2.4GHz)\n\n"
            )
        
        # Resumen BTM (802.11v)
        btm_summary = ""
        bc = d.get("band_counters", {})
        if "btm_stats" in bc:
            btm = bc["btm_stats"]
            reqs = btm.get("requests", 0)
            resps = btm.get("responses", 0)
            
            # Interpretar status codes
            status_desc = []
            for code in btm.get("status_codes", []):
                try:
                    c = int(code) if code.isdigit() else int(code, 16)
                    if c == 0: desc = "0 (Accept)"
                    elif c == 1: desc = "1 (Reject - Unspecified)"
                    elif c == 2: desc = "2 (Reject - Insufficient Beacon)"
                    elif c == 3: desc = "3 (Reject - Insufficient QoS/Capacity)"
                    elif c == 4: desc = "4 (Reject - BSS Undesirable)"
                    elif c == 5: desc = "5 (Reject - Traffic Delay)"
                    elif c == 6: desc = "6 (Reject - Invalid Candidate List)"
                    elif c == 7: desc = "7 (Reject - No Suitable Candidates)"
                    elif c == 8: desc = "8 (Reject - Leaving ESS)"
                    else: desc = f"{c} (Reject/Other)"
                    status_desc.append(desc)
                except:
                    status_desc.append(str(code))
            
            unique_status = list(set(status_desc))
            status_str = ", ".join(unique_status) if unique_status else "N/A"
            
            btm_summary = (
                "📡 BSS TRANSITION MANAGEMENT (802.11v):\n"
                f"- BTM Requests (AP -> Cliente): {reqs}\n"
                f"- BTM Responses (Cliente -> AP): {resps}\n"
                f"- Status Codes: {status_str}\n"
            )
            # Interpretación rápida
            if reqs > 0 and resps == 0:
                 btm_summary += "👉 Cliente ignora BTM (posible falta de soporte 11v)\n\n"
            elif any("Accept" in s for s in unique_status):
                 btm_summary += "✅ Cliente coopera vía 802.11v\n\n"
            elif any("Reject" in s for s in unique_status):
                 btm_summary += "❌ Cliente rechaza propuestas de steering\n\n"
            else:
                 btm_summary += "\n"
        else:
            # Reportar explícitamente que no hubo BTM
            btm_summary = (
                "📡 BSS TRANSITION MANAGEMENT (802.11v):\n"
                "- Estado: NO DETECTADO (Steering vía Probe Suppression o mecanismo legacy)\n"
                "- Eventos BTM: 0\n\n"
            )

        # Resumen de transiciones (sin cambios)
        transitions_summary = ""
        if sa["transitions"]:
            transitions_summary = "TRANSICIONES DETECTADAS:\n"
            for i, trans in enumerate(sa["transitions"][:5], 1):  # Mostrar máximo 5
                status_emoji = {
                    "SUCCESS": "✅",
                    "SLOW": "⚠️",
                    "TIMEOUT": "❌",
                    "LOOP": "🔄",
                    "NO_REASSOC": "❌",
                    "NO_CHANGE": "⚠️"
                }.get(trans["status"], "❓")
                
                # Tipo de steering
                steering_type = "🔴 Agresivo (Deauth)" if trans.get("type") == "aggressive" else "🟢 Asistido (802.11k/v/r)"
                
                time_str = f"{trans['transition_time']:.3f}s" if trans['transition_time'] else "N/A"
                band_change = f"{trans['from_band']} → {trans['to_band']}" if trans['is_band_change'] else "Misma banda"
                
                transitions_summary += (
                    f"{i}. {status_emoji} {steering_type}\n"
                    f"   Cliente: {trans['client'][:17]}...\n"
                    f"   Tiempo: {time_str} | {band_change}\n"
                    f"   BSSID: {trans['from_bssid'][:17] if trans['from_bssid'] else 'N/A'}... → {trans['to_bssid'][:17] if trans['to_bssid'] else 'N/A'}...\n"
                    f"   Estado: {trans['status']}\n"
                )
            
            if len(sa["transitions"]) > 5:
                transitions_summary += f"... y {len(sa['transitions']) - 5} transiciones más\n"
            transitions_summary += "\n"

        return (
            f"# ANÁLISIS DE CAPTURA WIRESHARK - BAND STEERING\n\n"
            f"**Archivo:** {file_name}\n"
            f"**Paquetes analizados:** {stats['total_packets']}\n"
            f"**Eventos 802.11 capturados:** {d['steering_events_count']}\n"
            f"**Calidad de captura:** {d['capture_quality']}\n\n"
            f"---\n\n"
            f"{bssid_summary}"
            f"## MÉTRICAS DE BAND STEERING\n\n"
            f"**Veredicto preliminar:** {sa['verdict']}\n"
            f"**Clientes analizados:** {sa['clients_analyzed']}\n"
            f"**Intentos de steering:** {sa['steering_attempts']}\n"
            f"**Transiciones exitosas:** {sa['successful_transitions']}\n"
            f"**Transiciones fallidas:** {sa['failed_transitions']}\n"
            f"**Bucles detectados:** {'SÍ ❌' if sa['loop_detected'] else 'NO ✅'}\n"
            f"**Tiempo promedio de transición:** {sa['avg_transition_time']}s\n"
            f"**Tiempo máximo de transición:** {sa['max_transition_time']}s\n\n"
            f"---\n\n"
            f"{preventive_summary}"
            f"{btm_summary}"
            f"{transitions_summary}"
            f"## INDICADORES DE RED\n\n"
            f"- **TCP Retransmissions:** {d['tcp_retransmissions']}\n"
            f"- **WLAN Retries:** {d['wlan_retries']}\n"
            f"- **DNS Errors:** {d['dns_errors']}\n"
        )

    def _ask_llm_for_analysis(self, technical_summary: str) -> str:
        """
        Solicita al LLM un análisis interpretativo basado en las métricas extraídas.
        """
        system_message = (
            "Eres un Auditor Senior de Redes Wi-Fi especializado en Band Steering (802.11k/v/r).\n\n"
            
            "## TU TAREA\n"
            "Analizar el resumen técnico proporcionado y emitir un veredicto final sobre la calidad del band steering.\n\n"
            
            "## CONTEXTO IMPORTANTE\n"
            "- El resumen ya contiene un 'Veredicto preliminar' basado en análisis automatizado de eventos 802.11\n"
            "- Tu trabajo es INTERPRETAR y VALIDAR ese veredicto con contexto técnico\n"
            "- NO ignores las métricas proporcionadas\n"
            "- NO asumas éxito si el veredicto preliminar indica fallo\n\n"
            
            "## INTERPRETACIÓN DE VEREDICTOS PRELIMINARES\n\n"
            
            "**EXCELLENT / GOOD / ACCEPTABLE / PREVENTIVE_SUCCESS:**\n"
            "- Indica éxito en el Band Steering\n"
            "- PREVENTIVE_SUCCESS: El cliente se conectó directamente a 5GHz (Client Steering) sin necesidad de transiciones forzadas\n"
            "- EXCELLENT/GOOD: Transiciones asistidas rápidas y efectivas\n"
            "- El cliente terminó operando en la banda óptima (5GHz)\n\n"
            
            "**FAILED:**\n"
            "- Se detectaron bucles (cliente vuelve al BSSID original)\n"
            "- Más transiciones fallidas que exitosas\n"
            "- Timeouts en reconexión (>3 segundos)\n"
            "- Cliente no se reasocia después de deauth\n\n"
            
            "**NO_STEERING_DETECTED:**\n"
            "- No hay eventos de deauthentication/disassociation\n"
            "- La captura no contiene evidencia de steering\n"
            "- Posible captura incorrecta o steering no configurado\n\n"
            
            "**NEEDS_REVIEW:**\n"
            "- Casos ambiguos que requieren análisis manual\n"
            "- Mezcla de transiciones exitosas y fallidas\n\n"
            
            "## CRITERIOS DE EVALUACIÓN\n\n"
            
            "### ✅ PRUEBA EXITOSA\n"
            "- Veredicto preliminar: EXCELLENT, GOOD, ACCEPTABLE o PREVENTIVE_SUCCESS\n"
            "- Si es PREVENTIVE_SUCCESS: Tráfico de datos mayoritariamente en 5GHz\n"
            "- Transiciones exitosas > 0 (si hubo intentos)\n"
            "- Sin bucles detectados\n"
            "- Cambio real de BSSID o banda (o uso exclusivo de 5GHz)\n\n"
            
            "### ⚠️ PRUEBA CON OBSERVACIONES\n"
            "- Veredicto preliminar: ACCEPTABLE o NEEDS_REVIEW\n"
            "- Algunas transiciones exitosas pero con latencia\n"
            "- Retransmisiones TCP elevadas después de steering\n"
            "- Tiempo de transición entre 1-3 segundos\n\n"
            
            "### ❌ PRUEBA FALLIDA\n"
            "- Veredicto preliminar: FAILED\n"
            "- Bucles detectados (loop_detected = SÍ)\n"
            "- Transiciones fallidas > exitosas\n"
            "- Cliente no se reasocia (NO_REASSOC)\n"
            "- Timeouts persistentes\n\n"
            
            "## ESTRUCTURA OBLIGATORIA DEL REPORTE\n\n"
            
            "## ESTRUCTURA OBLIGATORIA DEL REPORTE (PERFIL TÉCNICO)\n\n"
            
            "### 1. VEREDICTO FINAL\n"
            "Indica SOLO uno de estos estados:\n"
            "- ✅ **EXITOSA**\n"
            "- ❌ **FALLIDA**\n\n"
            
            "### 2. ANÁLISIS TÉCNICO DETALLADO\n"
            "Provee un diagnóstico profesional basándote en:\n"
            "- Tipo de Steering detectado (Preventivo vs Reactivo/Asistido vs Agresivo)\n"
            "- Eficiencia de las transiciones\n"
            "- Comportamiento del cliente (adhesión a 5GHz)\n"
            "- Estabilidad de la sesión\n\n"
            
            "### 3. ANÁLISIS BTM (802.11v)\n"
            "Detalla el intercambio de gestión BSS Transition Management:\n"
            "- **Estado**: ¿Activo o No detectado?\n"
            "- **Intercambio**: Cantidad de Requests (AP) vs Responses (Cliente)\n"
            "- **Resultados**: Lista EXACTAMENTE los códigos de estado obtenidos y su significado (ej: '0 (Accept)').\n"
            "- **Conclusión BTM**: ¿El cliente coopera o rechaza?\n\n"

            "### 4. EVIDENCIA DE PROTOCOLO ADICIONAL\n"
            "Lista los otros datos técnicos duros:\n"
            "- Frames de Management (Reassoc, Deauth)\n"
            "- Contadores de paquetes por banda (Beacons, Probes, Data)\n"
            "- Tiempos de roaming\n\n"

            "### 5. INDICADORES DE SALUD DE RED\n"
            "- TCP Retransmissions vs WLAN Retries\n"
            "- Errores DNS\n\n"
            
            "## REGLAS ESTRICTAS\n"
            "1. Tono puramente INGENIERIL y PROFESIONAL.\n"
            "2. VEREDICTO BINARIO: Solo EXITOSA o FALLIDA. Si funciona con observaciones leves, es EXITOSA. Si no cumple el objetivo, es FALLIDA.\n"
            "3. En caso de 'PREVENTIVE_SUCCESS', destaca la eficiencia de la selección de banda del cliente.\n"
            "4. NO existen los estados 'No Evaluable' o 'Con Observaciones'. Debes tomar una decisión técnica basada en la evidencia disponible."
        )

        completion = self.client.chat.completions.create(
            model=self.llm_model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": technical_summary},
            ],
            temperature=0.1,
            max_tokens=1000,
        )

        return completion.choices[0].message.content.strip()

    def analyze_capture(self, file_path: str) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"El archivo no existe: {file_path}")

        file_name = os.path.basename(file_path)

        # 1. Extraer estadísticas base vía tshark
        stats = self._extract_basic_stats(file_path=file_path)

        # 2. Obtener análisis de steering
        steering_analysis = stats.get("steering_analysis", {})
        diagnostics = stats.get("diagnostics", {})

        # 3. Determinar si se debe FORZAR evaluación (guardrail lógico)
        # Basado en si hay eventos de steering detectados
        has_steering_events = diagnostics.get("steering_events_count", 0) > 0
        has_steering_attempts = steering_analysis.get("steering_attempts", 0) > 0
        has_transitions = (
            steering_analysis.get("successful_transitions", 0) > 0 or
            steering_analysis.get("failed_transitions", 0) > 0
        )
        has_preventive = steering_analysis.get("preventive_steering", False)

        # Forzar evaluación si hay CUALQUIER evidencia de steering
        force_evaluation = has_steering_events or has_steering_attempts or has_transitions or has_preventive

        # 4. Construir resumen técnico
        technical_summary = self._build_technical_summary(
            stats=stats,
            file_name=file_name
        )

        # 5. Añadir bandera explícita para el LLM (regla dura)
        if force_evaluation:
            technical_summary += (
                "\n\n**Forzar evaluación:** SÍ\n"
                "Regla: La captura contiene eventos 802.11 suficientes. "
                "Está PROHIBIDO emitir el veredicto ❓ NO EVALUABLE."
            )
        else:
            technical_summary += (
                "\n\n**Forzar evaluación:** NO\n"
                "Regla: La captura puede considerarse insuficiente."
            )

        # 6. Ejecutar análisis con LLM
        analysis_text = self._ask_llm_for_analysis(technical_summary)

        # 7. Retorno final
        return {
            "file_name": file_name,
            "analysis": analysis_text,
            "stats": stats,
            "technical_summary": technical_summary,
            "forced_evaluation": force_evaluation,
        }

