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
            # --- NUEVOS CAMPOS PRECISION STEERING (Solicitados por usuario) ---
            "-e", "wlan.fixed.status_code",       # Status Code de Asociación (0=Success)
            # COMENTADO: Campos de capabilities fallan en versión local de tshark
            # "-e", "wlan.rm.enabled_capabilities", 
            # "-e", "wlan.extcap.b31",              
            # "-e", "wlan.mdie.mobility_domain",    
            
            # "-c", str(max_packets)   # COMENTADO: Analizar archivo completo para no perder eventos
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
            # Ajustar para 20 campos (19 anteriores + 1 nuevo)
            while len(fields) < 20:
                fields.append("")

            (timestamp, protocols, ip_src, ip_dst, frame_len, tcp_r, wlan_r, 
             dns_r, subtype, bssid, wlan_sa, wlan_da, frequency, reason_code, ssid,
             category_code, action_code, btm_status_code, public_action_code,
             assoc_status_code) = fields

            total_packets += 1
            
            # Detectar si es paquete WLAN y actualizar contadores
            if protocols and "wlan" in protocols.lower():
                total_wlan_packets += 1
            
            # Contadores de protocolos
            if protocols:
                for proto in protocols.split(":"):
                    proto = proto.strip()
                    if proto:
                        protocol_counter[proto] += 1

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
                    
                    # Normalizar category_code (dec/hex)
                    cat_val = -1
                    # cat_str = category_code if category_code else category_backup # Eliminado backup
                    
                    try:
                        if category_code:
                            cat_val = int(category_code) if category_code.isdigit() else int(category_code, 16)
                    except:
                        pass

                    if subtype_int == 13:
                        # Debug explícito para ver qué está llegando
                        # logger.debug(f"Action Frame detectado: Cat={cat_str}, Act={action_code}")
                        pass
                    
                    if subtype_int == 13 and cat_val == 10: # Category 10 = WNM
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

                    # --- DETECCIÓN DE SOPORTE KVR (802.11k/v/r) ---
                    # 11v (WNM) y 11k (Radio Measurement) operan sobre Action Frames (Subtype 13)
                    if subtype_int == 13:
                        if "kvr_stats" not in band_counters:
                             band_counters["kvr_stats"] = {"11k": False, "11v": False, "11r": False}
                        
                        # 11k: Category 5 (Radio Measurement)
                        if cat_val == 5:
                            band_counters["kvr_stats"]["11k"] = True
                            logger.info(f"✅ 802.11k (Radio Measurement) detectado.")

                        # 11v: Category 10 (WNM)
                        if cat_val == 10:
                            band_counters["kvr_stats"]["11v"] = True
                            # Nota: El log de 11v BTM ya se hace arriba en la sección BTM
                    
                    # 11r: Detectado en Authentication Frames (Subtype 11) con Auth Alg = 2
                    # (Lógica comentada temporalmente por fallo en tshark wlan.fixed.auth_alg)
                    
                    # Marcar 11v también si detectamos actividad BTM explícita
                    if band_counters.get("btm_stats", {}).get("requests", 0) > 0 or band_counters.get("btm_stats", {}).get("responses", 0) > 0:
                        if "kvr_stats" not in band_counters:
                             band_counters["kvr_stats"] = {"11k": False, "11v": False, "11r": False}
                        band_counters["kvr_stats"]["11v"] = True
                    
                    # --- NUEVA LÓGICA DE VALIDACION ASOCIACIÓN (Status Code) ---
                    # (KVR Capabilities detección desactivada temporalmente por fallo en tshark)
                    
                    # 1. Validación de Estado de Asociación (Assoc/Reassoc Response)
                    # Subtype 1=Assoc Resp, 3=Reassoc Resp
                    if subtype_int in [1, 3] and assoc_status_code:
                        try:
                            s_code = int(assoc_status_code) if assoc_status_code.isdigit() else int(assoc_status_code, 16)
                            if s_code != 0:
                                logger.warning(f"❌ Fallo de asociación detectado: MAC {wlan_da} -> Status {s_code}")
                                # Registrar fallo explícito en contadores de diagnóstico si es necesario
                                if "association_failures" not in band_counters:
                                    band_counters["association_failures"] = []
                                band_counters["association_failures"].append({
                                    "status": s_code,
                                    "time": timestamp,
                                    "bssid": bssid
                                })
                        except:
                            pass

                    
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
                            "reason_code": reason_code,
                            "assoc_status_code": assoc_status_code  # NUEVO: Para validar éxito
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
        
        # --- CORRECCIÓN LÓGICA: Contar éxito BTM como transición exitosa ---
        # Si hubo BTM Accept, el cliente cooperó exitosamente, aunque no hayamos visto el paquete Reassoc
        if band_counters and "btm_stats" in band_counters:
            btm_stats = band_counters["btm_stats"]
            status_codes = btm_stats.get("status_codes", [])
            requests = btm_stats.get("requests", 0)
            
            # Si hubo BTM Requests, contar como intentos de steering
            if requests > 0:
                total_steering_attempts += requests
                logger.info(f"✅ Contando {requests} BTM Request(s) como intento(s) de steering")
            
            # Si hubo Status 0 (Accept), contar como éxito
            if any(str(c) == "0" or str(c) == "0x00" for c in status_codes):
                successful_transitions += 1
                logger.info("✅ Contando BTM Accept como transición exitosa inicial")

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
                    
                    for j in range(i + 1, min(i + 15, len(client_event_list))):  # Aumentado a 15
                        next_event = client_event_list[j]
                        
                        # Buscar RESPONSE (1=Assoc Resp, 3=Reassoc Resp)
                        if next_event["subtype"] in [1, 3]:
                            # VALIDAR STATUS CODE
                            current_status_code = next_event.get("assoc_status_code", "0")
                            try:
                                s_val = int(current_status_code) if str(current_status_code).isdigit() else 0
                            except:
                                s_val = 0
                            
                            if s_val == 0:
                                # Éxito: AP aceptó la asociación
                                reassoc_found = True
                                reassoc_time = next_event["timestamp"]
                                new_bssid = next_event["bssid"]
                                new_band = next_event["band"]
                                break
                            else:
                                # Fallo: AP rechazó (Status != 0)
                                reassoc_found = False
                                logger.warning(f"❌ Transición fallida por Status Code: {s_val} en BSSID {next_event.get('bssid')}")
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
            # Verificar si hay BTM aunque no haya habido Reassoc (raro, pero posible)
            btm_accept = False
            if band_counters.get("btm_stats", {}):
                for code in band_counters["btm_stats"].get("status_codes", []):
                    try:
                        if int(code) == 0: btm_accept = True
                    except: pass
            
            if btm_accept:
                 verdict = "EXCELLENT" # BTM accept es superior a preventive
            else:
                 verdict = "PREVENTIVE_SUCCESS"
        else:
            verdict = self._determine_verdict(
                total_steering_attempts, successful_transitions, 
                failed_transitions, loop_detected, avg_transition_time,
                band_counters # Pasamos band_counters para ver BTM
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
        if has_network_24 and ratio_5ghz > 0.90:
             return True
        
        return False
    
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
                          loop_detected: bool, avg_time: float, band_counters: dict = None) -> str:
        """
        Determina el veredicto general con granularidad de calidad.
        
        NIVELES:
        - EXCELLENT: Éxito limpio (BTM o Transición rápida) SIN fallos ni bucles.
        - GOOD: Éxito estándar sin fallos graves.
        - ACCEPTABLE: Éxito (logró pasar) PERO con bucles o intentos fallidos previos ("Pasó raspando").
        - FAILED: Sin éxito de transición ni BTM Accept.
        """
        
        # Detectar "suciedad" en la prueba (fallos previos o bucles)
        has_issues = loop_detected or (failed > 0)
        
        # 1. Análisis BTM (802.11v)
        if band_counters and "btm_stats" in band_counters:
            btm = band_counters["btm_stats"]
            status_codes = btm.get("status_codes", [])
            
            # Chequear si hubo alguna aceptación explícita (Status 0)
            has_accepted_btm = False
            for code in status_codes:
                try:
                    c = int(code) if code.isdigit() else int(code, 16)
                    if c == 0:
                        has_accepted_btm = True
                        break
                except: pass
            
            # Si hubo aceptación BTM
            if has_accepted_btm:
                if has_issues:
                    return "ACCEPTABLE" # Pasó por BTM, pero tuvo problemas operativos
                return "EXCELLENT" # Pasó limpio

        # 2. Análisis de transiciones exitosas
        if successful > 0:
            if has_issues:
                return "ACCEPTABLE" # Logró pasar, pero con intentos fallidos o bucles previos
            
            # Si es limpio, calificar por tiempo
            if avg_time < 1.0: 
                return "EXCELLENT" 
            elif avg_time < 4.0:
                return "GOOD"
            else:
                return "ACCEPTABLE" # Lento
        
        # 3. Fallos (Si llegamos aquí, es porque NO hubo éxito confirmed)
        if loop_detected:
            return "FAILED_LOOP"
            
        if failed > 0:
            return "FAILED"
            
        if band_counters and "btm_stats" in band_counters and band_counters["btm_stats"].get("requests", 0) > 0:
             return "FAILED"

        if attempts > 0:
            return "FAILED"
            
        return "NO_STEERING_EVENTS"

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

    def _build_bssid_summary(self, bssid_info: dict) -> str:
        """Helper to build BSSID summary string."""
        bssid_summary = ""
        if bssid_info:
            bssid_summary = "BSSID DETECTADOS:\n"
            for bssid, info in bssid_info.items():
                bssid_summary += f"- {bssid}: {info['band']} ({info['ssid']})\n"
            bssid_summary += "\n"
        return bssid_summary

    def _build_preventive_summary(self, band_counters: dict) -> str:
        """Helper to build Preventive Steering summary string."""
        preventive_summary = ""
        if band_counters.get("preventive_steering"): # This flag is set in _analyze_steering_patterns
            bc = band_counters
            preventive_summary = (
                "🛡️ STEERING PREVENTIVO DETECTADO (CLIENT STEERING):\n"
                f"- Beacons 2.4GHz: {bc.get('beacon_24', 0)} (Red disponible)\n"
                f"- Probe Req Cliente: {bc.get('probe_req', 0)} (Cliente buscando)\n"
                f"- Probe Resp 2.4GHz: {bc.get('probe_resp_24', 0)} (AP ignorando en 2.4)\n"
                f"- Probe Resp 5GHz: {bc.get('probe_resp_5', 0)} (AP respondiendo en 5)\n"
                f"- Data 5GHz: {bc.get('data_5', 0)} (Trafico en 5GHz)\n"
                f"- Data 2.4GHz: {bc.get('data_24', 0)} (Sin tráfico en 2.4GHz)\n\n"
            )
        return preventive_summary

    def _build_technical_summary(self, stats: Dict[str, Any], file_name: str) -> str:
        """
        Construye un resumen técnico detallado con métricas específicas de band steering.
        """
        d = stats["diagnostics"]
        sa = stats["steering_analysis"]
        
        # Información de BSSIDs detectados
        bssid_summary = self._build_bssid_summary(d.get("bssid_info", {}))
        
        # Resumen de Steering Preventivo (si aplica)
        preventive_summary = self._build_preventive_summary(d.get("band_counters", {}))
        
        # --- MEJORA: Encabezado de Éxito Inmediato para el LLM ---
        btm_success_note = ""
        if sa["verdict"] == "EXCELLENT" or sa["verdict"] == "GOOD":
             # Verificar si fue por BTM
             has_btm_success = False
             btm_stats = d.get("band_counters", {}).get("btm_stats", {})
             if any(str(c) == "0" or str(c) == "0x00" for c in btm_stats.get("status_codes", [])):
                 has_btm_success = True
            
             if has_btm_success:
                btm_success_note = "⭐ **EVIDENCIA CRÍTICA:** Se ha confirmado un intercambio BTM (802.11v) EXITOSO con Status Code 0 (Accept).\n\n"
             elif sa["verdict"] == "EXCELLENT": # Si es excellent por FT
                btm_success_note = "⭐ **EVIDENCIA CRÍTICA:** Se ha confirmado Roaming Avanzado EXITOSO.\n\n"

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
                    # Códigos de estado BTM (802.11v Table 9-365)
                    desc = ""
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

        # Resumen KVR (NUEVO)
        kvr_summary = ""
        kvr = d.get("band_counters", {}).get("kvr_stats", {})
        if kvr:
             kvr_list = []
             if kvr.get("11k"): kvr_list.append("802.11k (Neighbor Reports)")
             if kvr.get("11v"): kvr_list.append("802.11v (BTM/WNM)")
             if kvr.get("11r"): kvr_list.append("802.11r (Fast Transition)")
             
             if kvr_list:
                  kvr_summary = f"📶 ESTÁNDARES DE ROAMING DETECTADOS (KVR):\n" + "\n".join([f"- ✅ {s}" for s in kvr_list]) + "\n\n"
             else:
                  kvr_summary = "📶 ESTÁNDARES DE ROAMING: No se detectaron flags explícitos de KVR en la captura.\n\n"

        # Resumen de Fallos de Asociación (NUEVO - Solicitado por usuario)
        assoc_failures_summary = ""
        assoc_failures = d.get("band_counters", {}).get("association_failures", [])
        if assoc_failures:
            assoc_failures_summary = "❌ FALLOS DE ASOCIACIÓN DETECTADOS:\n"
            for f in assoc_failures[:10]:  # Máximo 10 para no saturar
                assoc_failures_summary += f"- BSSID: {f.get('bssid', 'N/A')} | Status: {f.get('status', 'N/A')} (Rechazado por AP)\n"
            assoc_failures_summary += "\n"


        # Resumen de transiciones (sin cambios)
        transitions_summary = ""
        if sa["transitions"]:
            transitions_summary = "🔄 DETALLE DE TRANSICIONES:\n"
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
            f"{btm_success_note}"
            f"**Archivo:** {file_name}\n"
            f"**Paquetes WLAN analizados:** {stats['total_wlan_packets']}\n"
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
            f"{kvr_summary}"
            f"{btm_summary}"
            f"{assoc_failures_summary}"
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
            
            "⭐ **CRITERIO DE EVALUACIÓN:**\n"
            "- **EXCELLENT/GOOD:** Transición exitosa y limpia (sin fallos previos).\n"
            "- **ACCEPTABLE:** Transición exitosa PERO con intentos fallidos o bucles previos. (El cliente pasó, pero le costó).\n"
            "- **FAILED:** No hubo ninguna transición exitosa ni BTM Accept.\n\n"
            
            "**EXCELLENT:**\n"
            "- ✅ **EXITOSA** (Máxima calidad)\n"
            "- Evidencia: BTM Status Code 0 (Accept) O Fast Transition (11r) exitosa.\n"
            "- Interpretación: El cliente soporta y obedece gestión avanzada de red.\n\n"
            
            "**GOOD / ACCEPTABLE:**\n"
            "- ✅ **EXITOSA** (Calidad estándar)\n"
            "- Evidencia: Transiciones exitosas con tiempos razonables.\n"
            "- Interpretación: Steering funcional, aunque no use protocolos avanzados.\n\n"

            "**PREVENTIVE_SUCCESS:**\n"
            "- ✅ **EXITOSA** (Éxito pasivo)\n"
            "- Evidencia: Cliente estable en 5GHz (>90% tráfico).\n"
            "- Interpretación: Preferencia de cliente confirmada, objetivo cumplido.\n\n"
            
            "**FAILED / FAILED_LOOP / FAILED_BTM_REJECT:**\n"
            "- ❌ **FALLIDA**\n"
            "- Evidencia: BTM Reject, bucles, o fallos de asociación.\n\n"
            
            "**NO_STEERING_EVENTS:**\n"
            "- ⚠️ Evaluar caso por caso\n"
            "- Si hay tráfico 5GHz: Considerar PREVENTIVE_SUCCESS.\n"
            "- Si no hay datos: Reportar 'Datos Insuficientes'.\n\n"
            
            "## CRITERIOS DE EVALUACIÓN (JERARQUÍA DE VALIDEZ)\n\n"
            
            "### 🥇 NIVEL 1: GESTIÓN EXPLÍCITA (MÁXIMA CALIDAD)\n"
            "- **Evidencia:** Frames BTM (802.11v) con **Status Code 0 (Accept)**.\n"
            "- **Veredicto:** ✅ EXITOSA (El cliente soporta y obedece al AP).\n"
            "- **Nota:** Esta es la prueba de oro que confirma funcionalidad avanzada.\n\n"
            
            "### 🥈 NIVEL 2: ROAMING ACTIVO\n"
            "- **Evidencia:** Reasociación exitosa (11r FT o Standard) con cambio de BSSID/Banda.\n"
            "- **Veredicto:** ✅ EXITOSA.\n\n"
            
            "### 🥉 NIVEL 3: COMPORTAMIENTO PASIVO (CLIENT STEERING)\n"
            "- **Evidencia:** Sin BTM ni Roaming, pero cliente anclado a 5GHz sólido.\n"
            "- **Veredicto:** ✅ EXITOSA (Por comportamiento).\n"
            "- **IMPORTANTE:** Distinguir en el texto que es éxito por 'Preferencia de Cliente', no por gestión activa.\n\n"
            
            "### ❌ FALLO CONFIRMADO\n"
            "- BTM Reject (Status != 0).\n"
            "- Loop entre APs.\n"
            "- Desconexión sin reconexión.\n\n"
            
            "## ESTRUCTURA OBLIGATORIA DEL REPORTE (Comienza directamente aquí)\n\n"
            
            "### 1. RESUMEN EJECUTIVO (EVIDENCIA CLAVE)\n"
            "Justifica el veredicto con la evidencia de mayor jerarquía encontrada:\n"
            "- ¿Hubo BTM Accept (Code 0)? -> ¡Menciónalo primero! Es un éxito rotundo.\n"
            "- ¿Se detectó Roaming exitoso? -> Detalla el cambio de BSSID.\n"
            "- ¿Se detectó PREVENTIVE_SUCCESS (Cliente estable en 5GHz)? -> Es EXITOSA. Explica que el cliente prefirió la banda óptima.\n"
            "- ¿Hubo fallo explícito? -> Explica el loop o el rechazo.\n"
            "- **NOTA:** No incluyas un encabezado de 'Veredicto Final' por separado, el veredicto debe estar implícito y claro en este resumen.\n\n"
            
            "### 2. ANÁLISIS BTM Y KVR (802.11k/v/r)\n"
            "Detalla el soporte de estándares:\n"
            "- **Protocolos Detectados**: Lista si viste 11k, 11v, 11r.\n"
            "- **Intercambio BTM**: Detalla Requests/Responses y CÓDIGOS DE ESTADO.\n"
            "- **Interpretación**: ¿El cliente es inteligente (Smart Roaming)?\n\n"

            "### 3. DETALLE DE TRANSICIONES\n"
            "- Calidad, tiempos y estabilidad.\n"
            
            "## REGLAS ESTRICTAS\n"
            "1. Si el veredicto detectó al menos una transición exitosa, reporta como EXITOSA.\n"
            "2. USA EXCLUSIVAMENTE EL IDIOMA ESPAÑOL.\n\n"
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