"""
Herramienta especializada para análisis de capturas de red (Wireshark / PCAP)
enfocada en auditoría de Band Steering (802.11). Provee métricas y estructuras
de datos que actúan como fuente de verdad para el resto del sistema.
"""

import os
from collections import Counter
from typing import Dict, Any, Optional

from openai import OpenAI
from ..settings import settings
from ..utils.deauth_validator import DeauthValidator, REASSOC_TIMEOUT_SECONDS


class WiresharkTool:

    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            max_retries=2,
        )
        self.llm_model = settings.llm_model

    def _normalize_subtype(self, subtype_str: str) -> int:
        """Normaliza el subtype de tshark a un entero.
        tshark puede devolver: '8', '0x08', '0x0008', o el valor combinado type_subtype.
        wlan.fc.type_subtype viene como: type * 256 + subtype
        - Type 0 (Management): Subtype 8 (Beacon) = 0*256 + 8 = 8
        - Type 0 (Management): Subtype 0 (Assoc Req) = 0*256 + 0 = 0
        """
        if not subtype_str or not subtype_str.strip():
            return -1
        try:
            subtype_clean = subtype_str.strip()
            val = -1
            
            # Si viene como hex (0x...)
            if subtype_clean.startswith('0x'):
                val = int(subtype_clean, 16)
            # Si es un número decimal
            elif subtype_clean.isdigit() or (subtype_clean.startswith('-') and subtype_clean[1:].isdigit()):
                val = int(subtype_clean)
            else:
                # Intentar parsear como hex sin prefijo
                try:
                    val = int(subtype_clean, 16)
                except Exception:
                    return -1
            
            # wlan.fc.type_subtype viene como type * 256 + subtype
            # Extraer solo el subtype (módulo 256)
            # Si el valor es >= 256, es type_subtype combinado, extraer subtype
            if val >= 256:
                subtype_only = val % 256
                return subtype_only
            else:
                # Si es < 256, asumimos que ya es solo el subtype
                return val
        except (ValueError, AttributeError):
            return -1
    
    def _normalize_frequency(self, freq_str: str) -> int:
        """Normaliza la frecuencia de tshark a MHz.
        tshark puede devolver frecuencia en diferentes formatos.
        """
        if not freq_str or not freq_str.strip():
            return 0
        try:
            freq_val = float(freq_str.strip())
            # Si es muy grande, probablemente está en kHz, convertir a MHz
            if freq_val > 10000:
                freq_val = freq_val / 1000.0
            return int(freq_val)
        except (ValueError, AttributeError):
            return 0
    
    def _normalize_status_code(self, status_str: str) -> int:
        """Normaliza un status code (hex o decimal) a entero."""
        if not status_str or not status_str.strip():
            return -1
        try:
            status_clean = status_str.strip()
            if status_clean.startswith('0x'):
                return int(status_clean, 16)
            elif status_clean.isdigit() or (status_clean.startswith('-') and status_clean[1:].isdigit()):
                return int(status_clean)
            else:
                # Intentar como hex sin prefijo
                return int(status_clean, 16)
        except (ValueError, AttributeError):
            return -1
    
    def _determine_frame_direction(self, subtype_int: int, bssid: str, wlan_sa: str, wlan_da: str) -> tuple:
        """Determina correctamente source y destination según el tipo de frame.
        Retorna (source, destination, client_mac, ap_mac)
        """
        # Para Management frames, la dirección puede variar según el tipo
        if subtype_int in [0, 2]:  # Association/Reassociation Request
            # Cliente envía al AP
            return (wlan_sa or 'N/A', wlan_da or 'Broadcast', wlan_sa, wlan_da)
        elif subtype_int in [1, 3]:  # Association/Reassociation Response
            # AP envía al cliente
            return (wlan_sa or bssid or 'N/A', wlan_da or 'N/A', wlan_da, wlan_sa or bssid)
        elif subtype_int == 8:  # Beacon
            # AP envía, no hay destino específico (broadcast)
            return (bssid or wlan_sa or 'N/A', 'Broadcast', None, bssid or wlan_sa)
        elif subtype_int in [10, 12]:  # Disassociation, Deauthentication
            # Puede venir del AP o del cliente
            if bssid and wlan_sa and wlan_sa.lower() == bssid.lower():
                # AP envía al cliente
                return (wlan_sa, wlan_da or 'N/A', wlan_da, wlan_sa)
            else:
                # Cliente envía
                return (wlan_sa or 'N/A', wlan_da or bssid or 'Broadcast', wlan_sa, wlan_da or bssid)
        elif subtype_int == 13:  # Action Frame (BTM)
            # Necesitamos verificar el action_code para saber dirección
            # Por ahora, usar valores por defecto
            return (wlan_sa or bssid or 'N/A', wlan_da or 'Broadcast', wlan_da, wlan_sa or bssid)
        else:
            # Default: usar valores directos
            return (wlan_sa or 'N/A', wlan_da or 'Broadcast', wlan_sa, wlan_da)

    def _extract_basic_stats(
        self,
        file_path: str,
        max_packets: int = 2000,
        ssid_filter: Optional[str] = None,
        client_mac_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
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
            "-e", "wlan.fixed.bss_transition_status_code",   # BTM Status Code (v1)
            "-e", "wlan.fixed.status_code",       # Status Code de Asociación (0=Success)
            "-e", "wlan_radio.signal_dbm",        # RSSI / Intensidad de Señal
        ]


        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr or "Error ejecutando tshark")

        # Logging de diagnóstico
        lines = result.stdout.splitlines()
        
        # Mostrar primeras 3 líneas para diagnóstico
        if lines:
            for i, line in enumerate(lines[:3], 1):
                pass

        # Contador de paquetes WLAN para diagnóstico
        wlan_packets_with_subtype = 0
        wlan_packets_without_subtype = 0
        subtype_counter = Counter()  # Contador de tipos de frames
        
        # Contadores para detección de Steering Preventivo (Client Steering)
        all_client_macs = []
        band_counters = {
            "beacon_24": 0, "beacon_5": 0,
            "probe_req": 0,
            "probe_resp_24": 0, "probe_resp_5": 0,
            "data_24": 0, "data_5": 0,
        }

        # Lista temporal para muestras de señal (para gráfica continua)
        temp_signal_samples = []
        
        # ========================================================================
        # WIRESHARK RAW: Fuente de verdad - Capturar datos exactos de tshark
        # ========================================================================
        wireshark_raw = {
            "summary": {
                "total_lines": len(lines),
                "total_packets": 0,
                "total_wlan_packets": 0,
                "btm": {
                    "requests": 0,
                    "responses": 0,
                    "responses_accept": 0,  # status_code == 0
                    "responses_reject": 0,   # status_code != 0
                    "status_codes": []
                },
                "assoc": {
                    "requests": 0,
                    "responses": 0,
                    "responses_success": 0,  # status_code == 0
                    "responses_fail": 0      # status_code != 0
                },
                "reassoc": {
                    "requests": 0,
                    "responses": 0,
                    "responses_success": 0,
                    "responses_fail": 0
                },
                "deauth": {
                    "count": 0,
                    "reason_codes": []
                },
                "disassoc": {
                    "count": 0,
                    "reason_codes": []
                },
                "freq_band_map": {}  # frecuencia -> banda detectada
            },
            "sample": [],  # Paquetes importantes para band steering (con filtrado inteligente de Beacons)
            "general_sample": [],  # Muestra general de primeros N paquetes para referencia
            "general_sample_limit": 50,
            "truncated": False,
            # Tracking para filtrado inteligente de Beacons
            "beacon_tracking": {
                "bssids_seen": {},  # BSSID -> {first_seen_time, count, last_saved_time}
                "max_beacons_per_bssid": 3,  # Máximo de Beacons a guardar por BSSID
                "beacon_window_sec": 5.0  # Ventana de tiempo para considerar Beacons "cercanos" a eventos
            }
        }

        for line in lines:
            if not line.strip():
                continue

            fields = line.split("\t")
            # Ajustar para 20 campos (según el comando cmd corregido)
            while len(fields) < 20:
                fields.append("")

            (timestamp, protocols, ip_src, ip_dst, frame_len, tcp_r, wlan_r, 
             dns_r, subtype, bssid, wlan_sa, wlan_da, frequency, reason_code, ssid,
             category_code, action_code, btm_status_code,
             assoc_status_code, signal_strength) = fields[:20] # Tomar solo los campos esperados

            total_packets += 1
            wireshark_raw["summary"]["total_packets"] += 1
            
            # Normalizar campos
            timestamp_float = float(timestamp) if timestamp and timestamp.strip() else 0.0
            subtype_int = self._normalize_subtype(subtype) if subtype else -1
            freq_normalized = self._normalize_frequency(frequency) if frequency else 0
            bssid_clean = bssid.strip() if bssid else ""
            wlan_sa_clean = wlan_sa.strip() if wlan_sa else ""
            wlan_da_clean = wlan_da.strip() if wlan_da else ""
            ssid_clean = ssid.strip() if ssid else ""
            frame_len_int = int(frame_len) if frame_len and frame_len.strip().isdigit() else 0
            
            # Normalizar status codes
            btm_status_normalized = self._normalize_status_code(btm_status_code) if btm_status_code else -1
            assoc_status_normalized = self._normalize_status_code(assoc_status_code) if assoc_status_code else -1
            reason_code_normalized = self._normalize_status_code(reason_code) if reason_code else -1
            
            # Normalizar category y action codes
            category_normalized = self._normalize_status_code(category_code) if category_code else -1
            action_normalized = self._normalize_status_code(action_code) if action_code else -1
            
            # Normalizar RSSI
            rssi_normalized = None
            if signal_strength and signal_strength.strip():
                try:
                    rssi_val = float(signal_strength.strip())
                    if -120 <= rssi_val <= 0:  # Rango válido de RSSI
                        rssi_normalized = int(rssi_val)
                except (ValueError, AttributeError):
                    pass
            
            # Determinar dirección correcta según tipo de frame
            source, destination, client_mac, ap_mac = self._determine_frame_direction(
                subtype_int, bssid_clean, wlan_sa_clean, wlan_da_clean
            )
            
            # Registrar MACs para determinar cliente
            if wlan_sa_clean: all_client_macs.append(wlan_sa_clean)
            if wlan_da_clean: all_client_macs.append(wlan_da_clean)
            
            # Detectar si es paquete WLAN y actualizar contadores
            if protocols and "wlan" in protocols.lower():
                total_wlan_packets += 1
                wireshark_raw["summary"]["total_wlan_packets"] += 1
            
            # Guardar muestra raw: Paquetes importantes con filtrado inteligente de Beacons
            is_important_packet = False
            is_beacon = False
            should_save_beacon = False
            
            # Determinar si es un paquete importante para band steering
            if subtype_int >= 0:
                    
                # Detectar Beacon (subtype 8)
                if subtype_int == 8:
                    is_beacon = True
                    is_important_packet = True  # Temporal, luego decidimos si guardarlo
                # Paquetes críticos: SIEMPRE guardar (BTM, Association, Reassociation, Deauth, Disassoc)
                elif subtype_int in [0, 1, 2, 3, 10, 12, 13]:
                    is_important_packet = True
                    # Para Action frames, verificar si es BTM
                    if subtype_int == 13:
                        if category_normalized == 10:  # WNM (802.11v)
                            is_important_packet = True
                        else:
                            is_important_packet = False  # Solo guardar Action frames de WNM
            
            # Lógica especial para Beacons: filtrado inteligente
            if is_beacon:
                beacon_tracking = wireshark_raw["beacon_tracking"]
                max_per_bssid = beacon_tracking["max_beacons_per_bssid"]
                
                # Usar BSSID o un identificador único si no hay BSSID
                beacon_id = bssid_clean if bssid_clean else f"no_bssid_{freq_normalized}" if freq_normalized else "unknown"
                
                if beacon_id not in beacon_tracking["bssids_seen"]:
                    # Nuevo BSSID: guardar el primer Beacon
                    beacon_tracking["bssids_seen"][beacon_id] = {
                        "first_seen_time": timestamp_float,
                        "saved_count": 0,  # Contador de Beacons guardados (no totales)
                        "last_saved_time": timestamp_float
                    }
                    should_save_beacon = True
                    beacon_tracking["bssids_seen"][beacon_id]["saved_count"] = 1
                else:
                    bssid_info = beacon_tracking["bssids_seen"][beacon_id]
                    
                    # Guardar solo los primeros N Beacons por BSSID
                    if bssid_info["saved_count"] < max_per_bssid:
                        should_save_beacon = True
                        bssid_info["saved_count"] += 1
                        bssid_info["last_saved_time"] = timestamp_float
                    else:
                        # Ya guardamos suficientes Beacons de este BSSID
                        should_save_beacon = False
            
            # Guardar paquetes importantes (no-Beacons siempre, Beacons solo si pasan el filtro)
            if is_important_packet and (not is_beacon or should_save_beacon):
                raw_row = {
                    "timestamp": str(timestamp_float),  # Mantener como string para preservar precisión
                    "protocols": protocols.strip() if protocols else "",
                    "subtype": str(subtype_int) if subtype_int >= 0 else subtype if subtype else "",
                    "bssid": bssid_clean,
                    "wlan_sa": wlan_sa_clean,
                    "wlan_da": wlan_da_clean,
                    "source": source,  # Dirección corregida según tipo de frame
                    "destination": destination,  # Dirección corregida según tipo de frame
                    "frequency": str(freq_normalized) if freq_normalized > 0 else frequency if frequency else "",
                    "reason_code": str(reason_code_normalized) if reason_code_normalized >= 0 else reason_code if reason_code else "",
                    "ssid": ssid_clean,
                    "category_code": str(category_normalized) if category_normalized >= 0 else category_code if category_code else "",
                    "action_code": str(action_normalized) if action_normalized >= 0 else action_code if action_code else "",
                    "btm_status_code": str(btm_status_normalized) if btm_status_normalized >= 0 else btm_status_code if btm_status_code else "",
                    "assoc_status_code": str(assoc_status_normalized) if assoc_status_normalized >= 0 else assoc_status_code if assoc_status_code else "",
                    "signal_strength": str(rssi_normalized) if rssi_normalized is not None else signal_strength if signal_strength else "",
                    "frame_len": str(frame_len_int) if frame_len_int > 0 else frame_len if frame_len else "",
                    "ip_src": ip_src.strip() if ip_src else "",
                    "ip_dst": ip_dst.strip() if ip_dst else "",
                    "client_mac": client_mac if client_mac else "",
                    "ap_mac": ap_mac if ap_mac else ""
                }
                wireshark_raw["sample"].append(raw_row)
            
            # También guardar una muestra general (primeras N filas) para referencia
            if len(wireshark_raw.get("general_sample", [])) < 50:
                if "general_sample" not in wireshark_raw:
                    wireshark_raw["general_sample"] = []
                wireshark_raw["general_sample"].append({
                    "timestamp": timestamp,
                    "protocols": protocols,
                    "subtype": subtype,
                    "bssid": bssid,
                    "wlan_sa": wlan_sa,
                    "wlan_da": wlan_da,
                    "frequency": frequency
                })
            
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
                    try:
                        if category_code:
                            cat_val = int(category_code) if category_code.isdigit() else int(category_code, 16)
                    except Exception:
                        pass

                    if subtype_int == 13 and cat_val == 10: # Category 10 = WNM
                        # Normalizar action_code (dec/hex)
                        ac_val = None
                        try:
                            if action_code:
                                ac_val = int(action_code) if action_code.isdigit() else int(action_code, 16)
                        except Exception:
                            pass

                        if "btm_stats" not in band_counters:
                            band_counters["btm_stats"] = {"requests": 0, "responses": 0, "status_codes": []}

                        if ac_val == 7: # BTM Request
                             band_counters["btm_stats"]["requests"] += 1
                             # Capturar en raw summary
                             wireshark_raw["summary"]["btm"]["requests"] += 1
                             # Mapear frecuencia a banda
                             if frequency:
                                 try:
                                     freq_val = int(frequency) if isinstance(frequency, str) and frequency.isdigit() else float(frequency)
                                     freq_key = str(freq_val)
                                     if freq_key not in wireshark_raw["summary"]["freq_band_map"]:
                                         if 2400 <= freq_val <= 2500:
                                             wireshark_raw["summary"]["freq_band_map"][freq_key] = "2.4GHz"
                                         elif 5000 <= freq_val <= 6000:
                                             wireshark_raw["summary"]["freq_band_map"][freq_key] = "5GHz"
                                 except (ValueError, TypeError):
                                     pass
                             
                             # Calcular banda desde frecuencia si está disponible (corregir inconsistencia)
                             btm_band = current_band
                             if frequency:
                                 try:
                                     freq_val = int(frequency) if isinstance(frequency, str) and frequency.isdigit() else float(frequency)
                                     if 2400 <= freq_val <= 2500:
                                         btm_band = "2.4GHz"
                                     elif 5000 <= freq_val <= 6000:
                                         btm_band = "5GHz"
                                 except (ValueError, TypeError):
                                     pass
                             
                             # Registrar evento para gráfica
                             steering_events.append({
                                 "timestamp": float(timestamp) if timestamp else 0,
                                 "type": "btm",
                                 "event_type": "request",
                                 "subtype": subtype_int,
                                 "bssid": bssid, # Source BSSID (usualmente wlan_sa)
                                 "client_mac": wlan_da, # En Request, el cliente es el destino
                                 "ap_bssid": wlan_sa,   # En Request, el AP es el origen
                                 "wlan_sa": wlan_sa,
                                 "wlan_da": wlan_da,
                                 "band": btm_band,
                                 "frequency": int(frequency) if frequency else 0,
                                 "rssi": int(signal_strength) if signal_strength else None,
                                 "status_code": None
                             })
                             
                        elif ac_val == 8: # BTM Response
                            band_counters["btm_stats"]["responses"] += 1
                            # Capturar en raw summary
                            wireshark_raw["summary"]["btm"]["responses"] += 1
                            # Procesar status code
                            if btm_status_code:
                                try:
                                    status_int = int(btm_status_code) if str(btm_status_code).isdigit() else int(btm_status_code, 16)
                                    if str(status_int) not in wireshark_raw["summary"]["btm"]["status_codes"]:
                                        wireshark_raw["summary"]["btm"]["status_codes"].append(str(status_int))
                                    if status_int == 0:
                                        wireshark_raw["summary"]["btm"]["responses_accept"] += 1
                                    else:
                                        wireshark_raw["summary"]["btm"]["responses_reject"] += 1
                                except (ValueError, TypeError):
                                    pass
                            
                            # Calcular banda desde frecuencia si está disponible (corregir inconsistencia)
                            btm_response_band = current_band
                            if frequency:
                                try:
                                    freq_val = int(frequency) if isinstance(frequency, str) and frequency.isdigit() else float(frequency)
                                    if 2400 <= freq_val <= 2500:
                                        btm_response_band = "2.4GHz"
                                    elif 5000 <= freq_val <= 6000:
                                        btm_response_band = "5GHz"
                                except (ValueError, TypeError):
                                    pass
                            
                            # Registrar evento para gráfica
                            steering_events.append({
                                 "timestamp": float(timestamp) if timestamp else 0,
                                 "type": "btm",
                                 "event_type": "response",
                                 "subtype": subtype_int,
                                 "bssid": bssid,
                                 "client_mac": wlan_sa, # En Response, el cliente es el origen
                                 "ap_bssid": wlan_da,   # En Response, el AP es el destino
                                 "wlan_sa": wlan_sa,
                                 "wlan_da": wlan_da,
                                 "band": btm_response_band,
                                 "frequency": int(frequency) if frequency else 0,
                                 "rssi": int(signal_strength) if signal_strength else None,
                                 "status_code": int(btm_status_code) if btm_status_code and btm_status_code.isdigit() else None
                             })
                        
                        # Captura universal de status code
                        if btm_status_code and btm_status_code != "":
                            if btm_status_code not in band_counters["btm_stats"]["status_codes"]:
                                band_counters["btm_stats"]["status_codes"].append(btm_status_code)

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

                    # --- RECOLECCIÓN DE MUESTRAS DE SEÑAL ---
                    # Guardar una muestra si tenemos RSSI y banda válida
                    if signal_strength and current_band:
                         try:
                             rssi_val = int(signal_strength)
                             # Solo guardar si el valor es realista y tenemos MACs
                             if -120 < rssi_val < 0 and (wlan_sa or wlan_da):
                                 temp_signal_samples.append({
                                     "timestamp": float(timestamp) if timestamp else 0,
                                     "rssi": rssi_val,
                                     "band": current_band,
                                     "frequency": int(frequency) if frequency else 0,
                                     "sa": wlan_sa,
                                     "da": wlan_da
                                 })
                         except Exception:
                             pass

                    # --- DETECCIÓN DE SOPORTE KVR (802.11k/v/r) ---
                    # 11v (WNM) y 11k (Radio Measurement) operan sobre Action Frames (Subtype 13)
                    if subtype_int == 13:
                        if "kvr_stats" not in band_counters:
                             band_counters["kvr_stats"] = {"11k": False, "11v": False, "11r": False}
                        
                        # 11k: Category 5 (Radio Measurement)
                        if cat_val == 5:
                            band_counters["kvr_stats"]["11k"] = True

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
                                # Registrar fallo explícito en contadores de diagnóstico si es necesario
                                if "association_failures" not in band_counters:
                                    band_counters["association_failures"] = []
                                band_counters["association_failures"].append({
                                    "status": s_code,
                                    "time": timestamp,
                                    "bssid": bssid
                                })
                        except Exception:
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
                        # Capturar datos raw para eventos importantes
                        if subtype_int == 0:  # Association Request
                            wireshark_raw["summary"]["assoc"]["requests"] += 1
                        elif subtype_int == 1:  # Association Response
                            wireshark_raw["summary"]["assoc"]["responses"] += 1
                            if assoc_status_code:
                                try:
                                    s_code = int(assoc_status_code) if assoc_status_code.isdigit() else int(assoc_status_code, 16)
                                    if s_code == 0:
                                        wireshark_raw["summary"]["assoc"]["responses_success"] += 1
                                    else:
                                        wireshark_raw["summary"]["assoc"]["responses_fail"] += 1
                                except (ValueError, TypeError):
                                    pass
                        elif subtype_int == 2:  # Reassociation Request
                            wireshark_raw["summary"]["reassoc"]["requests"] += 1
                        elif subtype_int == 3:  # Reassociation Response
                            wireshark_raw["summary"]["reassoc"]["responses"] += 1
                            if assoc_status_code:
                                try:
                                    s_code = int(assoc_status_code) if assoc_status_code.isdigit() else int(assoc_status_code, 16)
                                    if s_code == 0:
                                        wireshark_raw["summary"]["reassoc"]["responses_success"] += 1
                                    else:
                                        wireshark_raw["summary"]["reassoc"]["responses_fail"] += 1
                                except (ValueError, TypeError):
                                    pass
                        elif subtype_int == 10:  # Disassociation
                            wireshark_raw["summary"]["disassoc"]["count"] += 1
                            if reason_code:
                                if reason_code not in wireshark_raw["summary"]["disassoc"]["reason_codes"]:
                                    wireshark_raw["summary"]["disassoc"]["reason_codes"].append(reason_code)
                        elif subtype_int == 12:  # Deauthentication
                            wireshark_raw["summary"]["deauth"]["count"] += 1
                            if reason_code:
                                if reason_code not in wireshark_raw["summary"]["deauth"]["reason_codes"]:
                                    wireshark_raw["summary"]["deauth"]["reason_codes"].append(reason_code)
                        
                        # Determinar banda
                        band = None
                        if frequency:
                            try:
                                freq_mhz = float(frequency)
                                if 2400 <= freq_mhz <= 2500:
                                    band = "2.4GHz"
                                elif 5000 <= freq_mhz <= 6000:
                                    band = "5GHz"
                                # Mapear frecuencia a banda en raw
                                freq_key = str(int(freq_mhz))
                                if freq_key not in wireshark_raw["summary"]["freq_band_map"]:
                                    wireshark_raw["summary"]["freq_band_map"][freq_key] = band
                            except ValueError:
                                pass
                        
                        # Determinar client_mac correctamente: el cliente es el que NO es el BSSID
                        # En Deauth/Disassoc: si viene del AP (SA=BSSID), el cliente es DA
                        # Si viene del cliente (SA=cliente), el cliente es SA
                        client_mac_value = None
                        if bssid:
                            if wlan_sa and wlan_sa.lower() == bssid.lower():
                                client_mac_value = wlan_da  # AP envía, cliente recibe
                            elif wlan_da and wlan_da.lower() == bssid.lower():
                                client_mac_value = wlan_sa  # Cliente envía, AP recibe
                            else:
                                # Fallback: usar el que no sea broadcast/multicast
                                client_mac_value = wlan_da if wlan_da and wlan_da != "ff:ff:ff:ff:ff:ff" else wlan_sa
                        else:
                            # Sin BSSID, usar el que no sea broadcast
                            client_mac_value = wlan_da if wlan_da and wlan_da != "ff:ff:ff:ff:ff:ff" else wlan_sa
                        
                        event = {
                            "timestamp": float(timestamp) if timestamp else 0,
                            "type": event_type,
                            "subtype": subtype_int,
                            "sa": wlan_sa,
                            "da": wlan_da,
                            "client_mac": client_mac_value or wlan_sa or wlan_da,
                            "bssid": bssid,
                            "ssid": ssid,
                            "band": band,
                            "frequency": frequency,
                            "reason_code": reason_code,
                            "assoc_status_code": assoc_status_code,
                            "signal_strength": signal_strength
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
        
        # Mostrar tipos de frames más comunes
        if subtype_counter:
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
        
        # 1. Determinar MAC de Cliente (preciso y robusto)
        client_mac = self._select_primary_client_mac(
            steering_events=steering_events,
            temp_signal_samples=temp_signal_samples,
            all_client_macs=all_client_macs,
            bssid_info=bssid_info,
            client_mac_hint=client_mac_hint,
        )

        # 2. Análisis de sesiones de clientes y transiciones
        steering_analysis = self._analyze_steering_patterns(steering_events, bssid_info, band_counters, client_mac)
        
        # 3. Evaluación de calidad de captura para band steering
        capture_quality = self._evaluate_capture_quality(steering_analysis, steering_events)

        # 3. Construir bloque de diagnósticos (fuente de verdad numérica)
        diagnostics = self._build_diagnostics_block(
            tcp_retransmissions=tcp_retransmissions,
            wlan_retries=wlan_retries,
            dns_errors=dns_errors,
            steering_events=steering_events,
            bssid_info=bssid_info,
            client_mac=client_mac,
            capture_quality=capture_quality,
            band_counters=band_counters,
            wireshark_raw=wireshark_raw,
        )

        # 4. Filtrar muestras de señal para gráfica continua
        final_signal_samples = []
        if client_mac and client_mac != "Desconocido":
            # Usar paquetes donde el cliente es el emisor (SA) para ver su RSSI
            client_samples = [s for s in temp_signal_samples if s["sa"] == client_mac]
            
            # Muestreo simple para no saturar UI (max ~500 puntos)
            if len(client_samples) > 500:
                 step = len(client_samples) // 500
                 if step < 1: step = 1
                 final_signal_samples = client_samples[::step]
            else:
                 final_signal_samples = client_samples

        return {
            "total_packets": total_packets,
            "total_tcp_packets": total_tcp_packets,
            "total_wlan_packets": total_wlan_packets,
            "approx_total_bytes": total_bytes,
            "diagnostics": diagnostics,
            "steering_analysis": steering_analysis,
            "steering_events": steering_events,
            "signal_samples": final_signal_samples, # NUEVO
            "top_protocols": protocol_counter.most_common(10),
            "top_sources": src_counter.most_common(10),
            "top_destinations": dst_counter.most_common(10),
        }

    def _select_primary_client_mac(
        self,
        steering_events,
        temp_signal_samples,
        all_client_macs,
        bssid_info,
        client_mac_hint: Optional[str],
    ) -> str:
        """
        Determina la MAC principal del cliente usando múltiples fuentes de evidencia.
        
        Prioriza:
        - Hint explícito del usuario (si es válido y no es BSSID).
        - Eventos 802.11 (Assoc/Reassoc Request, BTM Response).
        - Muestras de RSSI (emisor real).
        - Frecuencia de aparición global como último recurso.
        """
        client_mac = "Desconocido"

        def is_valid_client_mac(mac: str) -> bool:
            if not mac or mac in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"):
                return False
            try:
                first_octet = int(mac.split(":")[0], 16)
                # Filtrar direcciones multicast / group
                if first_octet & 1:
                    return False
            except Exception:
                return False
            return True

        def _normalize_mac(mac: str) -> str:
            return (mac or "").lower().replace("-", ":").strip()

        known_bssids = set(
            _normalize_mac(b) for b in (bssid_info or {}).keys() if b
        )

        # 1) Hint explícito del usuario
        if client_mac_hint:
            hint_norm = _normalize_mac(client_mac_hint)
            if is_valid_client_mac(hint_norm) and hint_norm not in known_bssids:
                return hint_norm

        mac_score = Counter()

        # 2) Evidencia fuerte desde eventos 802.11
        for ev in steering_events:
            subtype = ev.get("subtype")
            ev_type = ev.get("type")
            ev_event_type = ev.get("event_type")

            # Candidate via client_mac calculado (cuando exista)
            cand = _normalize_mac(ev.get("client_mac"))
            if cand and is_valid_client_mac(cand) and cand not in known_bssids:
                mac_score[cand] += 1

            # Association/Reassociation Request -> SA del evento
            if subtype in [0, 2]:
                cand_sa = _normalize_mac(ev.get("sa") or ev.get("wlan_sa"))
                if cand_sa and is_valid_client_mac(cand_sa) and cand_sa not in known_bssids:
                    mac_score[cand_sa] += 5

            # BTM Response explícito (formato WiresharkTool)
            if ev_type == "btm" and ev_event_type == "response":
                cand_cli = _normalize_mac(ev.get("client_mac"))
                if cand_cli and is_valid_client_mac(cand_cli) and cand_cli not in known_bssids:
                    mac_score[cand_cli] += 8

        # 3) Evidencia desde RSSI samples: el cliente es el emisor real de frames con RSSI
        for s in temp_signal_samples:
            cand_sa = _normalize_mac(s.get("sa"))
            if cand_sa and is_valid_client_mac(cand_sa) and cand_sa not in known_bssids:
                mac_score[cand_sa] += 2

        # 4) Fallback: frecuencia de aparición global en all_client_macs (menos confiable)
        fallback_clients = [
            _normalize_mac(m)
            for m in all_client_macs
            if is_valid_client_mac(_normalize_mac(m))
            and _normalize_mac(m) not in known_bssids
        ]
        if fallback_clients:
            mac_score.update(Counter(fallback_clients))

        if mac_score:
            client_mac = mac_score.most_common(1)[0][0]

        return client_mac

    def _compute_bssid_roles(self, bssid_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calcula roles sugeridos para BSSIDs (maestro/esclavo) según banda.
        
        Convención:
        - 5GHz -> maestro (objetivo principal).
        - 2.4GHz -> esclavo/fallback (o maestro si es la única banda).
        """
        bssid_roles: Dict[str, Any] = {}
        try:
            bssids_5 = [
                b
                for b, v in (bssid_info or {}).items()
                if isinstance(v, dict)
                and str(v.get("band", "")).lower().startswith("5")
            ]
            bssids_24 = [
                b
                for b, v in (bssid_info or {}).items()
                if isinstance(v, dict)
                and (
                    "2.4" in str(v.get("band", "")).lower()
                    or "2,4" in str(v.get("band", "")).lower()
                )
            ]

            if bssids_5 and bssids_24:
                for b in bssids_5:
                    bssid_roles[b] = {"role": "maestro", "band": "5GHz"}
                for b in bssids_24:
                    bssid_roles[b] = {"role": "esclavo", "band": "2.4GHz"}
            elif bssids_5:
                for b in bssids_5:
                    bssid_roles[b] = {"role": "maestro", "band": "5GHz"}
            elif bssids_24:
                for b in bssids_24:
                    bssid_roles[b] = {"role": "maestro", "band": "2.4GHz"}
        except Exception:
            # En caso de cualquier incoherencia, devolvemos sin roles adicionales
            bssid_roles = {}

        return bssid_roles

    def _build_diagnostics_block(
        self,
        tcp_retransmissions: int,
        wlan_retries: int,
        dns_errors: int,
        steering_events,
        bssid_info: Dict[str, Any],
        client_mac: str,
        capture_quality: Dict[str, Any],
        band_counters: Dict[str, Any],
        wireshark_raw: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Construye el bloque `diagnostics`, fuente de verdad numérica.
        
        Centraliza la estructura que consumen otros servicios (`BTMAnalyzer`,
        `BandSteeringService`, etc.) sin recalcular métricas en múltiples sitios.
        """
        bssid_roles = self._compute_bssid_roles(bssid_info)

        return {
            "tcp_retransmissions": tcp_retransmissions,
            "wlan_retries": wlan_retries,
            "dns_errors": dns_errors,
            "steering_events_count": len(steering_events),
            "unique_bssid_count": len(bssid_info),
            "bssid_info": bssid_info,
            "bssid_roles": bssid_roles,
            "client_mac": client_mac,
            "capture_quality": capture_quality,
            "band_counters": band_counters,  # Contadores para steering preventivo
            "wireshark_raw": wireshark_raw,  # Datos exactos de tshark
        }

    def _analyze_steering_patterns(
        self,
        events: list,
        bssid_info: dict,
        band_counters: dict = None,
        primary_client_mac: str = None,
    ) -> Dict[str, Any]:
        """
        Analiza patrones de band steering en los eventos capturados.
        
        Soporta:
        1. Steering agresivo (Deauth → Reassoc).
        2. Steering asistido (Reassoc directa).
        3. Steering preventivo (client steering silenciando 2.4GHz).
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
        
        (
            sorted_events,
            client_events,
        ) = self._group_events_by_client(events=events, bssid_info=bssid_info)

        (
            total_steering_attempts,
            successful_transitions,
        ) = self._count_btm_attempts_and_successes(
            sorted_events=sorted_events,
            band_counters=band_counters,
            primary_client_mac=primary_client_mac,
        )

        (
            transitions,
            client_attempts,
            client_successes,
            failed_transitions,
            loop_detected,
            transition_times,
        ) = self._analyze_client_transitions(
            client_events=client_events,
            bssid_info=bssid_info,
        )

        total_steering_attempts += client_attempts
        successful_transitions += client_successes
        
        avg_transition_time, max_transition_time = self._compute_transition_metrics(
            transition_times=transition_times,
        )

        verdict = self._determine_overall_steering_verdict(
            preventive_detected=preventive_detected,
            total_steering_attempts=total_steering_attempts,
            band_counters=band_counters or {},
            successful_transitions=successful_transitions,
            failed_transitions=failed_transitions,
            loop_detected=loop_detected,
            avg_transition_time=avg_transition_time,
            events=events,
            primary_client_mac=primary_client_mac,
        )

        total_attempts_final = max(total_steering_attempts, len(transitions))

        return {
            "transitions": transitions,
            "steering_attempts": total_attempts_final,
            "successful_transitions": successful_transitions,
            "failed_transitions": max(
                0, total_attempts_final - successful_transitions
            ),
            "loop_detected": loop_detected or len(transitions) > 3,
            "avg_transition_time": round(avg_transition_time, 3),
            "max_transition_time": round(max_transition_time, 3),
            "transition_times": transition_times,
            "verdict": verdict,
            "clients_analyzed": len(client_events),
            "preventive_steering": preventive_detected,
        }

    def _detect_preventive_steering(self, diag: dict) -> bool:
        """
        Detecta Steering Preventivo (Client Steering) o Selección de Banda Exitosa.
        
        Criterio (más flexible):
        1. La red 2.4GHz está disponible (beacons > 0).
        2. El cliente genera tráfico de datos.
        3. La mayoría del tráfico (>90%) ocurre en 5GHz.
        
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

    def _group_events_by_client(
        self,
        events: list,
        bssid_info: dict,
    ) -> (list, Dict[str, list]):
        """
        Ordena eventos por tiempo y los agrupa por cliente, filtrando BSSIDs conocidos.
        """
        sorted_events = sorted(events, key=lambda x: x["timestamp"])

        known_bssids_set = set(bssid_info.keys()) if bssid_info else set()

        def is_bssid(mac: str) -> bool:
            if not mac:
                return True
            mac_normalized = mac.lower().replace("-", ":")
            for bssid in known_bssids_set:
                if bssid.lower().replace("-", ":") == mac_normalized:
                    return True
            return False

        client_events: Dict[str, list] = {}
        for event in sorted_events:
            client = event.get("client_mac")
            if client and client != "" and not is_bssid(client):
                client_events.setdefault(client, []).append(event)

        return sorted_events, client_events

    def _count_btm_attempts_and_successes(
        self,
        sorted_events: list,
        band_counters: Optional[dict],
        primary_client_mac: Optional[str],
    ) -> (int, int):
        """
        Cuenta intentos y éxitos de steering basados en BTM (requests/responses).
        """
        total_steering_attempts = 0
        successful_transitions = 0

        if not band_counters or "btm_stats" not in band_counters:
            return total_steering_attempts, successful_transitions

        btm_stats = band_counters["btm_stats"]

        if primary_client_mac:
            btm_requests_count = sum(
                1
                for event in sorted_events
                if event.get("type") == "btm"
                and event.get("event_type") == "request"
                and event.get("client_mac") == primary_client_mac
            )
        else:
            btm_requests_count = btm_stats.get("requests", 0)

        if btm_requests_count > 0:
            total_steering_attempts += btm_requests_count

        btm_successful_responses = sum(
            1
            for event in sorted_events
            if event.get("type") == "btm"
            and event.get("event_type") == "response"
            and (
                event.get("status_code") == 0
                or str(event.get("status_code")) == "0"
            )
            and (not primary_client_mac or event.get("client_mac") == primary_client_mac)
        )

        if btm_successful_responses > 0:
            successful_transitions += btm_successful_responses

        return total_steering_attempts, successful_transitions

    def _analyze_client_transitions(
        self,
        client_events: Dict[str, list],
        bssid_info: dict,
    ) -> (list, int, int, int, bool, list):
        """
        Analiza, por cliente, transiciones agresivas y asistidas.
        """
        transitions = []
        total_steering_attempts = 0
        successful_transitions = 0
        failed_transitions = 0
        loop_detected = False
        transition_times: list = []

        def normalize_band(band):
            if not band:
                return None
            band_str = str(band).lower()
            if "5" in band_str:
                return "5GHz"
            if "2.4" in band_str or "2,4" in band_str:
                return "2.4GHz"
            return band

        for client_mac, client_event_list in client_events.items():
            if len(client_event_list) < 2:
                continue

            current_bssid = None
            last_reassoc_time = None

            for i, event in enumerate(client_event_list):
                event_subtype = event["subtype"]

                # Caso 1: Steering agresivo (Deauth/Disassoc → Reassoc)
                if event_subtype in [10, 12]:
                    (
                        new_transitions,
                        attempts_inc,
                        success_inc,
                        fail_inc,
                        loop_flag,
                        new_times,
                        current_bssid,
                    ) = self._process_aggressive_steering_event(
                        client_mac=client_mac,
                        event=event,
                        client_event_list=client_event_list,
                        start_index=i,
                        current_bssid=current_bssid,
                        normalize_band=normalize_band,
                    )

                    transitions.extend(new_transitions)
                    total_steering_attempts += attempts_inc
                    successful_transitions += success_inc
                    failed_transitions += fail_inc
                    if loop_flag:
                        loop_detected = True
                    transition_times.extend(new_times)

                # Caso 2: Steering asistido (Reassociation directa)
                elif event_subtype in [2, 3]:
                    (
                        new_transitions,
                        attempts_inc,
                        success_inc,
                        fail_inc,
                        loop_flag,
                        new_times,
                        current_bssid,
                        last_reassoc_time,
                    ) = self._process_assisted_steering_event(
                        client_mac=client_mac,
                        event=event,
                        client_event_list=client_event_list,
                        start_index=i,
                        current_bssid=current_bssid,
                        last_reassoc_time=last_reassoc_time,
                        bssid_info=bssid_info,
                        normalize_band=normalize_band,
                    )

                    transitions.extend(new_transitions)
                    total_steering_attempts += attempts_inc
                    successful_transitions += success_inc
                    failed_transitions += fail_inc
                    if loop_flag:
                        loop_detected = True
                    transition_times.extend(new_times)

                # Actualizar BSSID actual para Association inicial
                elif event_subtype in [0, 1] and event.get("bssid"):
                    if not current_bssid:
                        current_bssid = event["bssid"]
                        last_reassoc_time = event["timestamp"]

        return (
            transitions,
            total_steering_attempts,
            successful_transitions,
            failed_transitions,
            loop_detected,
            transition_times,
        )

    def _process_aggressive_steering_event(
        self,
        client_mac: str,
        event: dict,
        client_event_list: list,
        start_index: int,
        current_bssid: Optional[str],
        normalize_band,
    ):
        """Procesa un evento de steering agresivo (Deauth/Disassoc)."""
        transitions = []
        attempts_inc = 0
        success_inc = 0
        fail_inc = 0
        loop_flag = False
        new_times = []

        deauth_band = event["band"]
        deauth_time = event["timestamp"]
        reason_code = event["reason_code"]
        deauth_bssid = event.get("bssid")

        is_forced, classification, desc = DeauthValidator.validate_and_classify(
            event, client_mac
        )
        if not is_forced:
            return transitions, attempts_inc, success_inc, fail_inc, loop_flag, new_times, current_bssid

        attempts_inc += 1

        reassoc_found = False
        reassoc_time = None
        new_bssid = None
        new_band = None

        reassoc_limit = REASSOC_TIMEOUT_SECONDS
        for next_event in client_event_list[start_index + 1 :]:
            if (next_event["timestamp"] - deauth_time) > reassoc_limit:
                break

            if next_event["subtype"] in [1, 3]:
                current_status_code = next_event.get("assoc_status_code", "0")
                try:
                    s_val = (
                        int(current_status_code)
                        if str(current_status_code).isdigit()
                        else 0
                    )
                except Exception:
                    s_val = 0

                if s_val == 0:
                    reassoc_found = True
                    reassoc_time = next_event["timestamp"]
                    new_bssid = next_event["bssid"]
                    new_band = next_event["band"]
                    break
                else:
                    reassoc_found = False
                    break

        transition_time = (
            reassoc_time - deauth_time if reassoc_time is not None else None
        )

        deauth_band_norm = normalize_band(deauth_band)
        new_band_norm = normalize_band(new_band)
        is_band_change = (
            deauth_band_norm
            and new_band_norm
            and deauth_band_norm != new_band_norm
        )
        is_bssid_change = (
            deauth_bssid and new_bssid and deauth_bssid != new_bssid
        )

        returned_to_original = False
        if reassoc_found and new_bssid and current_bssid:
            if new_bssid == current_bssid:
                returned_to_original = True
                loop_flag = True

        status = self._classify_transition(
            reassoc_found,
            transition_time,
            is_band_change,
            is_bssid_change,
            returned_to_original,
        )

        if status == "SUCCESS":
            success_inc += 1
        elif status in ["LOOP", "TIMEOUT", "NO_REASSOC"]:
            fail_inc += 1

        if transition_time is not None:
            new_times.append(transition_time)

        transitions.append(
            {
                "client": client_mac,
                "type": "aggressive",
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
                "returned_to_original": returned_to_original,
            }
        )

        if reassoc_found and new_bssid:
            current_bssid = new_bssid

        return transitions, attempts_inc, success_inc, fail_inc, loop_flag, new_times, current_bssid

    def _process_assisted_steering_event(
        self,
        client_mac: str,
        event: dict,
        client_event_list: list,
        start_index: int,
        current_bssid: Optional[str],
        last_reassoc_time: Optional[float],
        bssid_info: dict,
        normalize_band,
    ):
        """Procesa un evento de steering asistido (reassociation directa)."""
        transitions = []
        attempts_inc = 0
        success_inc = 0
        fail_inc = 0
        loop_flag = False
        new_times = []

        new_bssid = event["bssid"]
        new_band = event["band"]
        reassoc_time = event["timestamp"]

        if current_bssid and new_bssid and current_bssid != new_bssid:
            attempts_inc += 1

            transition_time = None
            if last_reassoc_time:
                transition_time = reassoc_time - last_reassoc_time

            old_band = None
            if current_bssid in bssid_info:
                old_band = bssid_info[current_bssid].get("band")

            old_band_norm = normalize_band(old_band)
            new_band_norm = normalize_band(new_band)
            is_band_change = (
                old_band_norm
                and new_band_norm
                and old_band_norm != new_band_norm
            )
            is_bssid_change = True

            returned_to_original = False
            for next_event in client_event_list[
                start_index + 1 : min(start_index + 5, len(client_event_list))
            ]:
                if next_event.get("bssid") == current_bssid:
                    returned_to_original = True
                    loop_flag = True
                    break

            status = self._classify_transition(
                True,
                transition_time,
                is_band_change,
                is_bssid_change,
                returned_to_original,
            )

            if status == "SUCCESS":
                success_inc += 1
            elif status in ["LOOP", "SLOW"]:
                if status == "LOOP":
                    fail_inc += 1

            if transition_time is not None:
                new_times.append(transition_time)

            transitions.append(
                {
                    "client": client_mac,
                    "type": "assisted",
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
                    "returned_to_original": returned_to_original,
                }
            )

        if new_bssid:
            current_bssid = new_bssid
            last_reassoc_time = reassoc_time

        return (
            transitions,
            attempts_inc,
            success_inc,
            fail_inc,
            loop_flag,
            new_times,
            current_bssid,
            last_reassoc_time,
        )

    def _compute_transition_metrics(self, transition_times: list) -> (float, float):
        """Calcula métricas agregadas de tiempos de transición."""
        if not transition_times:
            return 0.0, 0.0

        avg_transition_time = sum(transition_times) / len(transition_times)
        max_transition_time = max(transition_times)
        return avg_transition_time, max_transition_time

    def _determine_overall_steering_verdict(
        self,
        preventive_detected: bool,
        total_steering_attempts: int,
        band_counters: dict,
        successful_transitions: int,
        failed_transitions: int,
        loop_detected: bool,
        avg_transition_time: float,
        events: list,
        primary_client_mac: Optional[str],
    ) -> str:
        """
        Determina el veredicto global de steering combinando BTM, transiciones y steering preventivo.
        """
        if preventive_detected and total_steering_attempts == 0:
            btm_accept = False
            if band_counters.get("btm_stats", {}):
                for code in band_counters["btm_stats"].get("status_codes", []):
                    try:
                        if int(code) == 0:
                            btm_accept = True
                    except Exception:
                        pass

            if btm_accept:
                return "EXCELLENT"
            return "PREVENTIVE_SUCCESS"

        return self._determine_verdict(
            total_steering_attempts,
            successful_transitions,
            failed_transitions,
            loop_detected,
            avg_transition_time,
            band_counters,
            events,
            primary_client_mac,
        )
    
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
        
        if transition_time < 2.0: # Aumentado de 1.0 a 2.0 para SUCCESS
            return "SUCCESS"
        elif transition_time < 8.0: # Aumentado de 3.0 a 8.0 para SLOW
            return "SLOW"
        else:
            return "TIMEOUT"
    
    def _determine_verdict(self, attempts: int, successful: int, failed: int,
                          loop_detected: bool, avg_time: float, band_counters: dict = None,
                          steering_events: list = None, client_mac: str = None) -> str:
        """
        Determina el veredicto general con granularidad de calidad.
        """
        
        # PRIORIDAD 1: Detectar desconexiones forzadas (Deauth/Disassoc)
        # Solo fallar si el evento es DIRIGIDO al cliente y no es una salida normal
        forced_disconnects = 0
        if steering_events and client_mac:
            for e in steering_events:
                # Subtype 12 (Deauth) o 10 (Disassoc)
                if e.get("subtype") in [10, 12]:
                    # ¿Va dirigido a nuestro cliente?
                    is_targeted = (e.get("da") == client_mac)
                    # ¿Qué motivo tiene? (Ignorar 3=STA leaving, 8=STA leaving BSS)
                    reason = str(e.get("reason_code", "0"))
                    is_graceful = reason in ["3", "8"]
                    
                    if is_targeted and not is_graceful:
                        forced_disconnects += 1

        if forced_disconnects > 0:
            return "FAILED"  # Fallo automático por inestabilidad real
        
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
                except Exception:
                    pass

            # Si hubo aceptación BTM
            if has_accepted_btm:
                if has_issues:
                    return "ACCEPTABLE" # Pasó por BTM, pero tuvo problemas operativos
                return "EXCELLENT" # Pasó limpio

        # 2. Análisis de transiciones exitosas
        if successful > 0:
            if loop_detected or failed > 0:
                # Si hubo éxito pero con "ruido", es GOOD o ACCEPTABLE, no FALLIDO automáticamente
                return "GOOD" if successful > failed else "ACCEPTABLE"
            
            # Si es limpio, calificar por tiempo
            if avg_time < 3.0: 
                return "EXCELLENT" 
            elif avg_time < 10.0:
                return "GOOD"
            else:
                return "ACCEPTABLE" # Lento pero exitoso
        
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
                # Validar que info sea un diccionario (puede ser float en algunos casos)
                if isinstance(info, dict):
                    band = info.get('band', 'Unknown')
                    ssid = info.get('ssid', 'N/A')
                    bssid_summary += f"- {bssid}: {band} ({ssid})\n"
                else:
                    # Si info no es un dict, solo mostrar el BSSID
                    bssid_summary += f"- {bssid}: (info no disponible)\n"
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
                except Exception:
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
            f"**⚠️ IMPORTANTE: Todos los valores numéricos en este resumen provienen directamente de la captura de Wireshark/tshark. "
            f"No se deben estimar, redondear o inventar números que no aparezcan explícitamente aquí.**\n\n"
            f"{btm_success_note}"
            f"**Archivo:** {file_name}\n"
            f"**Paquetes WLAN analizados:** {stats['total_wlan_packets']}\n"
            f"**Eventos 802.11 capturados:** {d['steering_events_count']}\n"
            f"**Calidad de captura:** {d['capture_quality']}\n\n"
            f"---\n\n"
            f"{bssid_summary}"
            f"## MÉTRICAS DE BAND STEERING\n\n"
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
            
            "## TU MISIÓN\n"
            "Redactar un informe técnico profesional, completo y adaptativo sobre la auditoría de Band Steering.\n"
            "Debes analizar los datos de la captura de Wireshark y la tabla de cumplimiento para generar un reporte que sea:\n"
            "- **Preciso**: Basado en evidencia real de la captura\n"
            "- **Coherente**: Respetando el veredicto de la tabla de cumplimiento\n"
            "- **Completo**: Cubriendo todos los aspectos técnicos relevantes\n"
            "- **Profesional**: Con estructura lógica y conclusiones claras\n\n"
            
            "## REGLA DE ORO: FIDELIDAD A LA TABLA DE CUMPLIMIENTO Y A LA TABLA DE MÉTRICAS\n"
            "El resumen técnico incluye una sección '❌ CHECKS QUE FALLARON' y '✅ CHECKS QUE PASARON'.\n\n"
            
            "**PARA EL VEREDICTO:**\n"
            "- **SOLO** menciona como causas de fallo los checks que aparezcan en '❌ CHECKS QUE FALLARON'\n"
            "- Si un check dice 'PASÓ', NO lo uses como causa de fallo, incluso si las métricas parecen subóptimas\n\n"
            
            "**PARA EL ANÁLISIS TÉCNICO:**\n"
            "- USA todos los datos disponibles: BTM, transiciones, tiempos, bucles, códigos de estado, etc.\n"
            "- Explica el CONTEXTO de por qué algo falló usando métricas detalladas\n"
            "- Proporciona insights técnicos profundos sobre el comportamiento del cliente\n\n"
            
            "## EJEMPLO DE ANÁLISIS CORRECTO:\n"
            "❌ INCORRECTO: 'El veredicto es FAILED porque solo 1 de 12 transiciones fue exitosa'\n\n"
            
            "✅ CORRECTO:\n"
            "'El veredicto es FAILED debido a:\n\n"
            "**Asociación y Reasociación: FALLÓ**\n"
            "Se detectaron 5 desconexiones forzadas (Deauthentication) y 3 desasociaciones durante la captura.\n"
            "Esto indica que el AP está expulsando activamente al cliente en lugar de usar mecanismos de steering\n"
            "cooperativos. El análisis de las transiciones muestra que de 12 intentos de steering, 9 fallaron\n"
            "precisamente por estas desconexiones abruptas, generando bucles entre bandas 2.4GHz y 5GHz.\n\n"
            
            "**Estándares KVR: FALLÓ**\n"
            "El dispositivo solo soporta 802.11v (BTM), pero carece de 802.11k (Neighbor Reports) y 802.11r\n"
            "(Fast Transition). Aunque se detectaron 2 BTM Requests con Status Code 0 (Accept), la ausencia\n"
            "de 11k/11r limita la capacidad del cliente para tomar decisiones informadas de roaming.\n\n"
            
            "**NOTA IMPORTANTE:** Aunque hubo 1 transición exitosa, la prueba es FALLIDA debido a los checks\n"
            "críticos que no se cumplieron. Las transiciones exitosas se mencionan como contexto técnico,\n"
            "pero no cambian el veredicto.'\n\n"

            "## ESTRUCTURA DEL REPORTE (ADAPTATIVA)\n\n"
            
            "Debes crear un reporte con las secciones que sean relevantes según los datos encontrados.\n"
            "No uses una estructura rígida; adapta las secciones al contenido de la captura.\n\n"
            
            "**SECCIONES OBLIGATORIAS:**\n\n"
            
            "### 1. RESUMEN EJECUTIVO\n"
            "- Declara el veredicto (EXITOSA/FALLIDA/PARCIAL) basándote en 'CAUSA RAÍZ DEL VEREDICTO'\n"
            "- Menciona SOLO los checks fallidos como causa del veredicto\n"
            "- Proporciona un overview de alto nivel de los hallazgos clave\n"
            "- Usa datos concretos (ej: '5 Deauth detectados', 'BTM Status Code 0', etc.)\n\n"
            
            "### [SECCIONES TÉCNICAS DINÁMICAS]\n"
            "Crea las secciones que necesites para cubrir los aspectos técnicos relevantes. Ejemplos:\n\n"
            
            "- **Análisis de Protocolos de Roaming (802.11k/v/r)**: Si hay datos de BTM, KVR, etc.\n"
            "  * Qué protocolos se detectaron\n"
            "  * Cómo se comportó el cliente (cooperativo, ignoró, rechazó)\n"
            "  * Códigos de estado BTM y su significado\n\n"
            
            "- **Análisis de Transiciones de Banda**: Si hay transiciones detectadas\n"
            "  * Cantidad de intentos vs éxitos\n"
            "  * Tiempos de transición (promedio, máximo)\n"
            "  * Tipo de steering (agresivo con Deauth, asistido con BTM, preventivo)\n"
            "  * Detección de bucles o patrones problemáticos\n\n"
            
            "- **Estabilidad de Asociación**: Si hay eventos de Deauth/Disassoc\n"
            "  * Cantidad de desconexiones forzadas\n"
            "  * Impacto en la experiencia del usuario\n"
            "  * Relación con fallos de steering\n\n"
            
            "- **Calidad de Red**: Si hay métricas de rendimiento\n"
            "  * Retransmisiones TCP/WLAN\n"
            "  * Errores DNS\n"
            "  * Latencia observada\n\n"
            
            "- **Comportamiento del Cliente**: Insights sobre el dispositivo\n"
            "  * Capacidades detectadas\n"
            "  * Preferencias de banda observadas\n"
            "  * Nivel de cooperación con el AP\n\n"
            
            "## REGLA DE ORO: FIDELIDAD TOTAL AL VEREDICTO FINAL\n"
            "El resumen técnico tiene una sección llamada '**VEREDICTO FINAL**'.\n"
            "- Si el veredicto es **SUCCESS** o **EXITOSA**, el reporte **DEBE** concluir que la prueba fue exitosa.\n"
            "- Si el veredicto es **SUCCESS**, puedes mencionar bucles o tiempos altos como 'puntos de mejora' o 'observaciones técnicas', pero **NUNCA** usarlos para decir que la prueba falló.\n"
            "- Un veredicto de **SUCCESS** significa que los criterios mínimos se cumplieron; tu análisis debe validar ese éxito.\n\n"
            
            "**PARA EL VEREDICTO:**\n"
            "- **SOLO** menciona como causas de fallo los checks que aparezcan en '❌ CHECKS QUE FALLARON'\n"
            "- Si un check dice 'PASÓ', NO lo uses como causa de fallo ni de veredicto negativo.\n\n"
            
            "## ESTRUCTURA DEL REPORTE (ADAPTATIVA)\n\n"
            "1. **RESUMEN EJECUTIVO**: Declara el veredicto basándote estrictamente en el 'VEREDICTO FINAL'.\n"
            "2. **ANÁLISIS TÉCNICO**: Usa las métricas para explicar el proceso.\n"
            "3. **CONCLUSIÓN FINAL**: Debe ser 100% coherente con el veredicto de la tabla.\n\n"
            
            "## REGLAS ESTRICTAS\n"
            "1. **CONSISTENCIA**: Si la tabla dice SUCCESS, tu conclusión es EXITOSA.\n"
            "2. **TONO**: Si es SUCCESS, el tono debe ser positivo, reconociendo el cumplimiento de los estándares.\n"
            "3. **NÚMEROS - CRÍTICO**: \n"
            "   - TODOS los números que uses DEBEN aparecer explícitamente en el resumen técnico.\n"
            "   - Estos valores provienen DIRECTAMENTE de la captura de Wireshark/tshark.\n"
            "   - ESTÁ TERMINANTEMENTE PROHIBIDO:\n"
            "     * Estimar o aproximar valores\n"
            "     * Redondear números (excepto si ya vienen redondeados en el resumen)\n"
            "     * Inventar cantidades que no aparezcan en el resumen\n"
            "     * Calcular promedios o estadísticas que no estén en el resumen\n"
            "     * Usar valores 'típicos' o 'esperados' en lugar de los valores reales\n"
            "   - Si un número no aparece en el resumen técnico, NO lo menciones.\n"
            "   - Ejemplo: Si el resumen dice '3 transiciones exitosas', usa exactamente '3', no 'aproximadamente 3' ni 'alrededor de 3'.\n"
            "4. **CAMBIOS DE BANDA - REGLA CRÍTICA**:\n"
            "   - El resumen técnico incluye una sección '📊 RESUMEN DE STEERING EFECTIVO (VALORES CORREGIDOS)' que muestra el número CORRECTO de cambios de banda.\n"
            "   - SIEMPRE usa el número de cambios de banda que aparece en esa sección, NO el que pueda aparecer en otras partes del resumen.\n"
            "   - Si la sección dice 'Cambios de banda físicos detectados: X', usa exactamente ese valor X en tu análisis.\n"
            "   - NO uses el número de transiciones individuales que puedan tener 'is_band_change' marcado, ya que ese cálculo puede ser incorrecto.\n"
            "   - El valor corregido se calculó comparando transiciones consecutivas y es el único valor confiable.\n"
            "5. **IDIOMA**: ESPAÑOL.\n"
        )

        completion = self.client.chat.completions.create(
            model=self.llm_model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": technical_summary},
            ],
            temperature=0.1,
            max_tokens=2000,
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