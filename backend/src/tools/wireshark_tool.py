"""
Specialized tool for network capture analysis (Wireshark / PCAP)
focused on Band Steering (802.11) auditing. Provides metrics and data
structures that act as the source of truth for the rest of the system.
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
        """Normalizes the tshark subtype to an integer.
        tshark can return: '8', '0x08', '0x0008', or the combined type_subtype value.
        wlan.fc.type_subtype comes as: type * 256 + subtype
        - Type 0 (Management): Subtype 8 (Beacon) = 0*256 + 8 = 8
        - Type 0 (Management): Subtype 0 (Assoc Req) = 0*256 + 0 = 0
        """
        if not subtype_str or not subtype_str.strip():
            return -1
        try:
            subtype_clean = subtype_str.strip()
            val = -1
            
            # If it comes as hex (0x...)
            if subtype_clean.startswith('0x'):
                val = int(subtype_clean, 16)
            # If it's a decimal number
            elif subtype_clean.isdigit() or (subtype_clean.startswith('-') and subtype_clean[1:].isdigit()):
                val = int(subtype_clean)
            else:
                # Try parsing as hex without prefix
                try:
                    val = int(subtype_clean, 16)
                except Exception:
                    return -1
            
            # wlan.fc.type_subtype comes as type * 256 + subtype
            # Extract only the subtype (modulo 256)
            # If the value is >= 256, it's combined type_subtype, extract subtype
            if val >= 256:
                subtype_only = val % 256
                return subtype_only
            else:
                # If it's < 256, we assume it's already just the subtype
                return val
        except (ValueError, AttributeError):
            return -1
    
    def _normalize_frequency(self, freq_str: str) -> int:
        """Normalizes the tshark frequency to MHz.
        tshark can return frequency in different formats.
        """
        if not freq_str or not freq_str.strip():
            return 0
        try:
            freq_val = float(freq_str.strip())
            # If it's very large, it's probably in kHz, convert to MHz
            if freq_val > 10000:
                freq_val = freq_val / 1000.0
            return int(freq_val)
        except (ValueError, AttributeError):
            return 0
    
    def _normalize_status_code(self, status_str: str) -> int:
        """Normalizes a status code (hex or decimal) to an integer."""
        if not status_str or not status_str.strip():
            return -1
        try:
            status_clean = status_str.strip()
            if status_clean.startswith('0x'):
                return int(status_clean, 16)
            elif status_clean.isdigit() or (status_clean.startswith('-') and status_clean[1:].isdigit()):
                return int(status_clean)
            else:
                # Try as hex without prefix
                return int(status_clean, 16)
        except (ValueError, AttributeError):
            return -1
    
    def _determine_frame_direction(self, subtype_int: int, bssid: str, wlan_sa: str, wlan_da: str) -> tuple:
        """Correctly determines source and destination according to frame type.
        Returns (source, destination, client_mac, ap_mac)
        """
        # For Management frames, direction may vary by type
        if subtype_int in [0, 2]:  # Association/Reassociation Request
            # Client sends to AP
            return (wlan_sa or 'N/A', wlan_da or 'Broadcast', wlan_sa, wlan_da)
        elif subtype_int in [1, 3]:  # Association/Reassociation Response
            # AP sends to client
            return (wlan_sa or bssid or 'N/A', wlan_da or 'N/A', wlan_da, wlan_sa or bssid)
        elif subtype_int == 8:  # Beacon
            # AP sends, no specific destination (broadcast)
            return (bssid or wlan_sa or 'N/A', 'Broadcast', None, bssid or wlan_sa)
        elif subtype_int in [10, 12]:  # Disassociation, Deauthentication
            # Can come from AP or client
            if bssid and wlan_sa and wlan_sa.lower() == bssid.lower():
                # AP sends to client
                return (wlan_sa, wlan_da or 'N/A', wlan_da, wlan_sa)
            else:
                # Client sends
                return (wlan_sa or 'N/A', wlan_da or bssid or 'Broadcast', wlan_sa, wlan_da or bssid)
        elif subtype_int == 13:  # Action Frame (BTM)
            # We need to check action_code for direction
            # For now, use default values
            return (wlan_sa or bssid or 'N/A', wlan_da or 'Broadcast', wlan_da, wlan_sa or bssid)
        else:
            # Default: use direct values
            return (wlan_sa or 'N/A', wlan_da or 'Broadcast', wlan_sa, wlan_da)

    def _extract_basic_stats(
        self,
        file_path: str,
        max_packets: int = 2000,
        ssid_filter: Optional[str] = None,
        client_mac_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Extracts detailed capture statistics with a focus on band steering.
        Analyzes time sequences, BSSID transitions, and quality metrics.
        """
        import subprocess
        import shutil
        from datetime import datetime

        tshark_path = shutil.which("tshark")
        if not tshark_path:
            raise RuntimeError("tshark is not available in PATH.")

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

        # Structures for band steering analysis
        steering_events = []  # List of events ordered chronologically
        client_sessions = {}  # Sessions by client MAC
        bssid_info = {}  # Information for each BSSID (band, channel)
        
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
            "-e", "wlan.fixed.reason_code",  # Reason code for deauth/disassoc
            "-e", "wlan.ssid",  # SSID
            # Campos BTM (802.11v) - Campos reales de Wireshark 4.6.2
            "-e", "wlan.fixed.category_code",                # Category (10 = WNM)
            "-e", "wlan.fixed.action_code",                  # Action (7=Req, 8=Resp)
            "-e", "wlan.fixed.bss_transition_status_code",   # BTM Status Code (v1)
            "-e", "wlan.fixed.status_code",       # Association Status Code (0=Success)
            "-e", "wlan_radio.signal_dbm",        # RSSI / Signal Strength
        ]


        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr or "Error executing tshark")

        # Diagnostic logging
        lines = result.stdout.splitlines()
        
        # Show first 3 lines for diagnosis
        if lines:
            for i, line in enumerate(lines[:3], 1):
                pass

        # WLAN packet counter for diagnosis
        wlan_packets_with_subtype = 0
        wlan_packets_without_subtype = 0
        subtype_counter = Counter()  # Frame types counter
        
        # Counters for Preventive Steering (Client Steering) detection
        all_client_macs = []
        band_counters = {
            "beacon_24": 0, "beacon_5": 0,
            "probe_req": 0,
            "probe_resp_24": 0, "probe_resp_5": 0,
            "data_24": 0, "data_5": 0,
        }

        # Temporary list for signal samples (for continuous chart)
        temp_signal_samples = []
        
        # ========================================================================
        # WIRESHARK RAW: Source of truth - Capture exact tshark data
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
                "freq_band_map": {}  # frequency -> detected band
            },
            "sample": [],  # Important packets for band steering (with smart Beacon filtering)
            "general_sample": [],  # General sample of first N packets for reference
            "general_sample_limit": 50,
            "truncated": False,
            # Tracking for smart Beacon filtering
            "beacon_tracking": {
                "bssids_seen": {},  # BSSID -> {first_seen_time, count, last_saved_time}
                "max_beacons_per_bssid": 3,  # Max Beacons to save per BSSID
                "beacon_window_sec": 5.0  # Time window to consider Beacons "close" to events
            }
        }

        for line in lines:
            if not line.strip():
                continue

            fields = line.split("\t")
            # Adjust for 20 fields (per corrected cmd command)
            while len(fields) < 20:
                fields.append("")

            (timestamp, protocols, ip_src, ip_dst, frame_len, tcp_r, wlan_r, 
             dns_r, subtype, bssid, wlan_sa, wlan_da, frequency, reason_code, ssid,
             category_code, action_code, btm_status_code,
             assoc_status_code, signal_strength) = fields[:20] # Take only expected fields

            total_packets += 1
            wireshark_raw["summary"]["total_packets"] += 1
            
            # Normalize fields
            timestamp_float = float(timestamp) if timestamp and timestamp.strip() else 0.0
            subtype_int = self._normalize_subtype(subtype) if subtype else -1
            freq_normalized = self._normalize_frequency(frequency) if frequency else 0
            bssid_clean = bssid.strip() if bssid else ""
            wlan_sa_clean = wlan_sa.strip() if wlan_sa else ""
            wlan_da_clean = wlan_da.strip() if wlan_da else ""
            ssid_clean = ssid.strip() if ssid else ""
            frame_len_int = int(frame_len) if frame_len and frame_len.strip().isdigit() else 0
            
            # Normalize status codes
            btm_status_normalized = self._normalize_status_code(btm_status_code) if btm_status_code else -1
            assoc_status_normalized = self._normalize_status_code(assoc_status_code) if assoc_status_code else -1
            reason_code_normalized = self._normalize_status_code(reason_code) if reason_code else -1
            
            # Normalize category and action codes
            category_normalized = self._normalize_status_code(category_code) if category_code else -1
            action_normalized = self._normalize_status_code(action_code) if action_code else -1
            
            # Normalize RSSI
            rssi_normalized = None
            if signal_strength and signal_strength.strip():
                try:
                    rssi_val = float(signal_strength.strip())
                    if -120 <= rssi_val <= 0:  # Valid RSSI range
                        rssi_normalized = int(rssi_val)
                except (ValueError, AttributeError):
                    pass
            
            # Determine correct direction based on frame type
            source, destination, client_mac, ap_mac = self._determine_frame_direction(
                subtype_int, bssid_clean, wlan_sa_clean, wlan_da_clean
            )
            
            # Record MACs to determine client
            if wlan_sa_clean: all_client_macs.append(wlan_sa_clean)
            if wlan_da_clean: all_client_macs.append(wlan_da_clean)
            
            # Detect if it's a WLAN packet and update counters
            if protocols and "wlan" in protocols.lower():
                total_wlan_packets += 1
                wireshark_raw["summary"]["total_wlan_packets"] += 1
            
            # Save raw sample: Important packets with smart Beacon filtering
            is_important_packet = False
            is_beacon = False
            should_save_beacon = False
            
            # Determine if it's an important packet for band steering
            if subtype_int >= 0:
                    
                # Detectar Beacon (subtype 8)
                if subtype_int == 8:
                    is_beacon = True
                    is_important_packet = True  # Temporary, then we decide whether to save it
                # Critical packets: ALWAYS save (BTM, Association, Reassociation, Deauth, Disassoc)
                elif subtype_int in [0, 1, 2, 3, 10, 12, 13]:
                    is_important_packet = True
                    # For Action frames, check if it's BTM
                    if subtype_int == 13:
                        if category_normalized == 10:  # WNM (802.11v)
                            is_important_packet = True
                        else:
                            is_important_packet = False  # Only save WNM Action frames
            
            # Special logic for Beacons: smart filtering
            if is_beacon:
                beacon_tracking = wireshark_raw["beacon_tracking"]
                max_per_bssid = beacon_tracking["max_beacons_per_bssid"]
                
                # Use BSSID or a unique identifier if no BSSID
                beacon_id = bssid_clean if bssid_clean else f"no_bssid_{freq_normalized}" if freq_normalized else "unknown"
                
                if beacon_id not in beacon_tracking["bssids_seen"]:
                    # New BSSID: save the first Beacon
                    beacon_tracking["bssids_seen"][beacon_id] = {
                        "first_seen_time": timestamp_float,
                        "saved_count": 0,  # Saved Beacons counter (not total)
                        "last_saved_time": timestamp_float
                    }
                    should_save_beacon = True
                    beacon_tracking["bssids_seen"][beacon_id]["saved_count"] = 1
                else:
                    bssid_info = beacon_tracking["bssids_seen"][beacon_id]
                    
                    # Save only the first N Beacons per BSSID
                    if bssid_info["saved_count"] < max_per_bssid:
                        should_save_beacon = True
                        bssid_info["saved_count"] += 1
                        bssid_info["last_saved_time"] = timestamp_float
                    else:
                        # We already saved enough Beacons from this BSSID
                        should_save_beacon = False
            
            # Save important packets (non-Beacons always, Beacons only if they pass the filter)
            if is_important_packet and (not is_beacon or should_save_beacon):
                raw_row = {
                    "timestamp": str(timestamp_float),  # Keep as string to preserve precision
                    "protocols": protocols.strip() if protocols else "",
                    "subtype": str(subtype_int) if subtype_int >= 0 else subtype if subtype else "",
                    "bssid": bssid_clean,
                    "wlan_sa": wlan_sa_clean,
                    "wlan_da": wlan_da_clean,
                    "source": source,  # Corrected address per frame type
                    "destination": destination,  # Corrected address per frame type
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
            
            # Also save a general sample (first N rows) for reference
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

            # Detailed analysis of 802.11 events
            if subtype:
                try:
                    # Conversion subtype (igual)
                    if subtype.startswith('0x'):
                        subtype_int = int(subtype, 16)
                    else:
                        subtype_int = int(subtype)
                    
                    wlan_packets_with_subtype += 1
                    subtype_counter[subtype_int] += 1  # Contar este tipo de frame
                    
                    # --- BTM DETECTION (802.11v) ---
                    # Subtype 13 = Action Frame, Category 10 = WNM
                    
                    # Normalizar category_code (dec/hex)
                    cat_val = -1
                    try:
                        if category_code:
                            cat_val = int(category_code) if category_code.isdigit() else int(category_code, 16)
                    except Exception:
                        pass

                    if subtype_int == 13 and cat_val == 10: # Category 10 = WNM
                        # Normalize action_code (dec/hex)
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
                             # Capture in raw summary
                             wireshark_raw["summary"]["btm"]["requests"] += 1
                             # Map frequency to band
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
                             
                             # Calculate band from frequency if available (correct inconsistency)
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
                             
                             # Register event for chart
                             steering_events.append({
                                 "timestamp": float(timestamp) if timestamp else 0,
                                 "type": "btm",
                                 "event_type": "request",
                                 "subtype": subtype_int,
                                 "bssid": bssid, # Source BSSID (usually wlan_sa)
                                 "client_mac": wlan_da, # In Request, the client is the destination
                                 "ap_bssid": wlan_sa,   # In Request, the AP is the source
                                 "wlan_sa": wlan_sa,
                                 "wlan_da": wlan_da,
                                 "band": btm_band,
                                 "frequency": int(frequency) if frequency else 0,
                                 "rssi": int(signal_strength) if signal_strength else None,
                                 "status_code": None
                             })
                             
                        elif ac_val == 8: # BTM Response
                            band_counters["btm_stats"]["responses"] += 1
                            # Capture in raw summary
                            wireshark_raw["summary"]["btm"]["responses"] += 1
                            # Process status code
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
                            
                            # Calculate band from frequency if available (correct inconsistency)
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
                            
                            # Register event for chart
                            steering_events.append({
                                 "timestamp": float(timestamp) if timestamp else 0,
                                 "type": "btm",
                                 "event_type": "response",
                                 "subtype": subtype_int,
                                 "bssid": bssid,
                                 "client_mac": wlan_sa, # In Response, the client is the source
                                 "ap_bssid": wlan_da,   # In Response, the AP is the destination
                                 "wlan_sa": wlan_sa,
                                 "wlan_da": wlan_da,
                                 "band": btm_response_band,
                                 "frequency": int(frequency) if frequency else 0,
                                 "rssi": int(signal_strength) if signal_strength else None,
                                 "status_code": int(btm_status_code) if btm_status_code and btm_status_code.isdigit() else None
                             })
                        
                        # Universal status code capture
                        if btm_status_code and btm_status_code != "":
                            if btm_status_code not in band_counters["btm_stats"]["status_codes"]:
                                band_counters["btm_stats"]["status_codes"].append(btm_status_code)

                    # --- PREVENTIVE STEERING LOGIC ---
                    # Determine current packet band
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

                    # Count key frames by band
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

                    # --- SIGNAL SAMPLE COLLECTION ---
                    # Save a sample if we have RSSI and valid band
                    if signal_strength and current_band:
                         try:
                             rssi_val = int(signal_strength)
                             # Only save if value is realistic and we have MACs
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

                    # --- KVR SUPPORT DETECTION (802.11k/v/r) ---
                    # 11v (WNM) and 11k (Radio Measurement) operate over Action Frames (Subtype 13)
                    if subtype_int == 13:
                        if "kvr_stats" not in band_counters:
                             band_counters["kvr_stats"] = {"11k": False, "11v": False, "11r": False}
                        
                        # 11k: Category 5 (Radio Measurement)
                        if cat_val == 5:
                            band_counters["kvr_stats"]["11k"] = True

                        # 11v: Category 10 (WNM)
                        if cat_val == 10:
                            band_counters["kvr_stats"]["11v"] = True
                            # Note: 11v BTM log is already done above in the BTM section
                    
                    # 11r: Detected in Authentication Frames (Subtype 11) with Auth Alg = 2
                    # (Logic commented temporarily due to failure in tshark wlan.fixed.auth_alg)
                    
                    # Mark 11v also if we detect explicit BTM activity
                    if band_counters.get("btm_stats", {}).get("requests", 0) > 0 or band_counters.get("btm_stats", {}).get("responses", 0) > 0:
                        if "kvr_stats" not in band_counters:
                             band_counters["kvr_stats"] = {"11k": False, "11v": False, "11r": False}
                        band_counters["kvr_stats"]["11v"] = True
                    
                    # --- NEW ASSOCIATION VALIDATION LOGIC (Status Code) ---
                    # (KVR Capabilities detection disabled temporarily due to failure in tshark)
                    
                    # 1. Association Status Validation (Assoc/Reassoc Response)
                    # Subtype 1=Assoc Resp, 3=Reassoc Resp
                    if subtype_int in [1, 3] and assoc_status_code:
                        try:
                            s_code = int(assoc_status_code) if assoc_status_code.isdigit() else int(assoc_status_code, 16)
                            if s_code != 0:
                                # Record explicit failure in diagnostic counters if necessary
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
                        # Capture raw data for important events
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
                        
                        # Determine band
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
                        
                        # Determine client_mac correctly: the client is the one that is NOT the BSSID
                        # In Deauth/Disassoc: if it comes from AP (SA=BSSID), the client is DA
                        # If it comes from client (SA=client), the client is SA
                        client_mac_value = None
                        if bssid:
                            if wlan_sa and wlan_sa.lower() == bssid.lower():
                                client_mac_value = wlan_da  # AP sends, client receives
                            elif wlan_da and wlan_da.lower() == bssid.lower():
                                client_mac_value = wlan_sa  # Client sends, AP receives
                            else:
                                # Fallback: use the one that is not broadcast/multicast
                                client_mac_value = wlan_da if wlan_da and wlan_da != "ff:ff:ff:ff:ff:ff" else wlan_sa
                        else:
                            # Without BSSID, use the one that is not broadcast
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
                        
                        # Register BSSID information (even without band)
                        if bssid:
                            if bssid not in bssid_info:
                                bssid_info[bssid] = {
                                    "band": band,  # Can be None
                                    "ssid": ssid,
                                    "frequency": frequency
                                }
                            # Update band if we now have info and didn't before
                            elif band and not bssid_info[bssid].get("band"):
                                bssid_info[bssid]["band"] = band
                                bssid_info[bssid]["frequency"] = frequency
                except (ValueError, AttributeError):
                    # If it cannot be parsed, ignore this packet
                    wlan_packets_without_subtype += 1

        # Results logging
        
        # Show most common frame types
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
        
        # 1. Determine primary Client MAC (precise and robust)
        client_mac = self._select_primary_client_mac(
            steering_events=steering_events,
            temp_signal_samples=temp_signal_samples,
            all_client_macs=all_client_macs,
            bssid_info=bssid_info,
            client_mac_hint=client_mac_hint,
        )

        # 2. Client sessions and transitions analysis
        steering_analysis = self._analyze_steering_patterns(steering_events, bssid_info, band_counters, client_mac)
        
        # 3. Capture quality evaluation for band steering
        capture_quality = self._evaluate_capture_quality(steering_analysis, steering_events)

        # 4. Build diagnostics block (numerical source of truth)
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

        # 5. Filter signal samples for continuous chart
        final_signal_samples = []
        if client_mac and client_mac != "Unknown":
            # Use packets where the client is the source (SA) to see its RSSI
            client_samples = [s for s in temp_signal_samples if s["sa"] == client_mac]
            
            # Simple sampling to not saturate UI (max ~500 points)
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
            "signal_samples": final_signal_samples, # NEW
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
        Determines the primary client MAC using multiple evidence sources.
        
        Prioritizes:
        - Explicit user hint (if valid and not a BSSID).
        - 802.11 events (Assoc/Reassoc Request, BTM Response).
        - RSSI samples (actual source).
        - Global occurrence frequency as a last resort.
        """
        client_mac = "Unknown"

        def is_valid_client_mac(mac: str) -> bool:
            if not mac or mac in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"):
                return False
            try:
                first_octet = int(mac.split(":")[0], 16)
                # Filter multicast / group addresses
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

        # 1) Explicit user hint
        if client_mac_hint:
            hint_norm = _normalize_mac(client_mac_hint)
            if is_valid_client_mac(hint_norm) and hint_norm not in known_bssids:
                return hint_norm

        mac_score = Counter()

        # 2) Strong evidence from 802.11 events
        for ev in steering_events:
            subtype = ev.get("subtype")
            ev_type = ev.get("type")
            ev_event_type = ev.get("event_type")

            # Candidate via calculated client_mac (when it exists)
            cand = _normalize_mac(ev.get("client_mac"))
            if cand and is_valid_client_mac(cand) and cand not in known_bssids:
                mac_score[cand] += 1

            # Association/Reassociation Request -> SA del evento
            if subtype in [0, 2]:
                cand_sa = _normalize_mac(ev.get("sa") or ev.get("wlan_sa"))
                if cand_sa and is_valid_client_mac(cand_sa) and cand_sa not in known_bssids:
                    mac_score[cand_sa] += 5

            # Explicit BTM Response (WiresharkTool format)
            if ev_type == "btm" and ev_event_type == "response":
                cand_cli = _normalize_mac(ev.get("client_mac"))
                if cand_cli and is_valid_client_mac(cand_cli) and cand_cli not in known_bssids:
                    mac_score[cand_cli] += 8

        # 3) Evidence from RSSI samples: the client is the actual sender of frames with RSSI
        for s in temp_signal_samples:
            cand_sa = _normalize_mac(s.get("sa"))
            if cand_sa and is_valid_client_mac(cand_sa) and cand_sa not in known_bssids:
                mac_score[cand_sa] += 2

        # 4) Fallback: global occurrence frequency in all_client_macs (less reliable)
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
        Calculates suggested roles for BSSIDs (master/slave) by band.
        
        Convention:
        - 5GHz -> master (primary objective).
        - 2.4GHz -> slave/fallback (or master if only band).
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
                    bssid_roles[b] = {"role": "master", "band": "5GHz"}
                for b in bssids_24:
                    bssid_roles[b] = {"role": "slave", "band": "2.4GHz"}
            elif bssids_5:
                for b in bssids_5:
                    bssid_roles[b] = {"role": "master", "band": "5GHz"}
            elif bssids_24:
                for b in bssids_24:
                    bssid_roles[b] = {"role": "master", "band": "2.4GHz"}
        except Exception:
            # In case of any inconsistency, return without additional roles
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
        Builds the `diagnostics` block, the numerical source of truth.
        
        Centralizes the structure consumed by other services (`BTMAnalyzer`,
        `BandSteeringService`, etc.) without recalculating metrics in multiple places.
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
            "band_counters": band_counters,  # Counters for preventive steering
            "wireshark_raw": wireshark_raw,  # Exact tshark data
        }

    def _analyze_steering_patterns(
        self,
        events: list,
        bssid_info: dict,
        band_counters: dict = None,
        primary_client_mac: str = None,
    ) -> Dict[str, Any]:
        """
        Analyzes band steering patterns in captured events.
        
        Supports:
        1. Aggressive steering (Deauth → Reassoc).
        2. Assisted steering (Direct Reassoc).
        3. Preventive steering (client steering by silencing 2.4GHz).
        """
        
        # Detect Preventive Steering (always checked, even without transition events)
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
        Detects Preventive Steering (Client Steering) or Successful Band Selection.
        
        Criterion (more flexible):
        1. 2.4GHz network is available (beacons > 0).
        2. Client generates data traffic.
        3. Most traffic (>90%) occurs on 5GHz.
        
        This indicates that the client (or network) preferred 5GHz over 2.4GHz,
        which is the final goal of Band Steering.
        """
        beacon_24 = diag.get("beacon_24", 0)
        data_24 = diag.get("data_24", 0)
        data_5 = diag.get("data_5", 0)
        
        total_data = data_24 + data_5
        
        if total_data < 10:  # Need minimum traffic to decide
            return False
            
        # Check 2.4GHz coverage (if no 2.4, no steering to do)
        has_network_24 = beacon_24 > 0
        
        # Calculate preference ratio for 5GHz
        ratio_5ghz = data_5 / total_data
        
        # If there is 2.4 network but client prefers 5GHz (>90%), it's a success
        # (Assumes "Client Steering" or AP config worked)
        if has_network_24 and ratio_5ghz > 0.90:
             return True
        
        return False

    def _group_events_by_client(
        self,
        events: list,
        bssid_info: dict,
    ) -> (list, Dict[str, list]):
        """
        Sorts events by time and groups them by client, filtering known BSSIDs.
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
        Counts steering attempts and successes based on BTM (requests/responses).
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
        Analyzes aggressive and assisted transitions by client.
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

                # Case 1: Aggressive steering (Deauth/Disassoc → Reassoc)
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

                # Case 2: Assisted steering (Direct Reassociation)
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

                # Update current BSSID for initial Association
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
        """Processes an aggressive steering event (Deauth/Disassoc)."""
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
        """Processes an assisted steering event (direct reassociation)."""
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
        """Calculates aggregate transition time metrics."""
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
        Determines overall steering verdict by combining BTM, transitions, and preventive steering.
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
        """Classifies a steering transition based on its quality."""
        if not reassoc_found:
            return "NO_REASSOC"
        
        if returned_to_original:
            return "LOOP"
        
        if not (is_band_change or is_bssid_change):
            return "NO_CHANGE"
        
        if transition_time < 2.0: # Increased from 1.0 to 2.0 for SUCCESS
            return "SUCCESS"
        elif transition_time < 8.0: # Increased from 3.0 to 8.0 for SLOW
            return "SLOW"
        else:
            return "TIMEOUT"
    
    def _determine_verdict(self, attempts: int, successful: int, failed: int,
                          loop_detected: bool, avg_time: float, band_counters: dict = None,
                          steering_events: list = None, client_mac: str = None) -> str:
        """
        Determines the overall verdict with quality granularity.
        """
        
        # PRIORITY 1: Detect forced disconnections (Deauth/Disassoc)
        # Only fail if the event is DIRECTED at the client and is not a normal exit
        forced_disconnects = 0
        if steering_events and client_mac:
            for e in steering_events:
                # Subtype 12 (Deauth) or 10 (Disassoc)
                if e.get("subtype") in [10, 12]:
                    # Is it directed to our client?
                    is_targeted = (e.get("da") == client_mac)
                    # What is the reason? (Ignore 3=STA leaving, 8=STA leaving BSS)
                    reason = str(e.get("reason_code", "0"))
                    is_graceful = reason in ["3", "8"]
                    
                    if is_targeted and not is_graceful:
                        forced_disconnects += 1

        if forced_disconnects > 0:
            return "FAILED"  # Automatic failure due to real instability
        
        # Detect "noise" in the test (previous failures or loops)
        has_issues = loop_detected or (failed > 0)
        
        # 1. BTM Analysis (802.11v)
        if band_counters and "btm_stats" in band_counters:
            btm = band_counters["btm_stats"]
            status_codes = btm.get("status_codes", [])
            
            # Check if there was any explicit acceptance (Status 0)
            has_accepted_btm = False
            for code in status_codes:
                try:
                    c = int(code) if code.isdigit() else int(code, 16)
                    if c == 0:
                        has_accepted_btm = True
                        break
                except Exception:
                    pass

            # If there was BTM acceptance
            if has_accepted_btm:
                if has_issues:
                    return "ACCEPTABLE" # Passed via BTM, but had operational issues
                return "EXCELLENT" # Passed clean

        # 2. Successful transitions analysis
        if successful > 0:
            if loop_detected or failed > 0:
                # If success but with "noise", it's GOOD or ACCEPTABLE, not automatically FAILED
                return "GOOD" if successful > failed else "ACCEPTABLE"
            
            # If clean, rate by time
            if avg_time < 3.0: 
                return "EXCELLENT" 
            elif avg_time < 10.0:
                return "GOOD"
            else:
                return "ACCEPTABLE" # Slow but successful
        
        # 3. Failures (If we get here, it's because NO success was confirmed)
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
        Evaluates if the capture contains enough info for band steering analysis.
        Compatible with assisted (802.11k/v/r) and aggressive (Deauth-based) steering.
        
        IMPORTANT: Does NOT require Deauth. Modern steering uses direct Reassociation.
        """
        if not events:
            return "INSUFFICIENT - No 802.11 events"
        
        if steering_analysis.get("preventive_steering"):
            return "VALID - Preventive Steering (Client Steering) detected"

        if steering_analysis["steering_attempts"] == 0:
            return "INSUFFICIENT - No steering attempts detected"
        
        # If there were successful transitions, the capture is valid
        if steering_analysis["successful_transitions"] > 0:
            return "VALID - Steering detected and analyzed"
        
        # Steering detected but with issues (still analyzable)
        if steering_analysis["failed_transitions"] > 0:
            return "VALID - Failed steering but analyzable"
        
        # Attempts made but without clear conclusion
        return "INSUFFICIENT - Inconclusive events"

    def _build_bssid_summary(self, bssid_info: dict) -> str:
        """Helper to build BSSID summary string."""
        bssid_summary = ""
        if bssid_info:
            bssid_summary = "BSSIDs DETECTED:\n"
            for bssid, info in bssid_info.items():
                # Validate that info is a dictionary (it can be float in some cases)
                if isinstance(info, dict):
                    band = info.get('band', 'Unknown')
                    ssid = info.get('ssid', 'N/A')
                    bssid_summary += f"- {bssid}: {band} ({ssid})\n"
                else:
                    # If info is not a dict, just show the BSSID
                    bssid_summary += f"- {bssid}: (info not available)\n"
            bssid_summary += "\n"
        return bssid_summary
    
    def _build_preventive_summary(self, band_counters: dict) -> str:
        """Helper to build Preventive Steering summary string."""
        preventive_summary = ""
        if band_counters.get("preventive_steering"): # This flag is set in _analyze_steering_patterns
            bc = band_counters
            preventive_summary = (
                "🛡️ PREVENTIVE STEERING DETECTED (CLIENT STEERING):\n"
                f"- Beacons 2.4GHz: {bc.get('beacon_24', 0)} (Network available)\n"
                f"- Client Probe Req: {bc.get('probe_req', 0)} (Client searching)\n"
                f"- Probe Resp 2.4GHz: {bc.get('probe_resp_24', 0)} (AP ignoring on 2.4)\n"
                f"- Probe Resp 5GHz: {bc.get('probe_resp_5', 0)} (AP responding on 5)\n"
                f"- Data 5GHz: {bc.get('data_5', 0)} (Traffic on 5GHz)\n"
                f"- Data 2.4GHz: {bc.get('data_24', 0)} (No traffic on 2.4GHz)\n\n"
            )
        return preventive_summary

    def _build_technical_summary(self, stats: Dict[str, Any], file_name: str) -> str:
        """
        Builds a detailed technical summary with specific band steering metrics.
        """
        d = stats["diagnostics"]
        sa = stats["steering_analysis"]
        
        # Information of detected BSSIDs
        bssid_summary = self._build_bssid_summary(d.get("bssid_info", {}))
        
        # Preventive Steering Summary (if applicable)
        preventive_summary = self._build_preventive_summary(d.get("band_counters", {}))
        
        # --- IMPROVEMENT: Immediate Success Header for the LLM ---
        btm_success_note = ""
        if sa["verdict"] == "EXCELLENT" or sa["verdict"] == "GOOD":
             # Check if it was via BTM
             has_btm_success = False
             btm_stats = d.get("band_counters", {}).get("btm_stats", {})
             if any(str(c) == "0" or str(c) == "0x00" for c in btm_stats.get("status_codes", [])):
                 has_btm_success = True
            
             if has_btm_success:
                btm_success_note = "⭐ **CRITICAL EVIDENCE:** A SUCCESSFUL BTM (802.11v) exchange has been confirmed with Status Code 0 (Accept).\n\n"
             elif sa["verdict"] == "EXCELLENT": # If excellent by FT
                btm_success_note = "⭐ **CRITICAL EVIDENCE:** SUCCESSFUL Advanced Roaming has been confirmed.\n\n"

        # BTM Summary (802.11v)
        btm_summary = ""
        bc = d.get("band_counters", {})
        if "btm_stats" in bc:
            btm = bc["btm_stats"]
            reqs = btm.get("requests", 0)
            resps = btm.get("responses", 0)
            
            # Interpret status codes
            status_desc = []
            for code in btm.get("status_codes", []):
                try:
                    c = int(code) if code.isdigit() else int(code, 16)
                    # BTM Status Codes (802.11v Table 9-365)
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
                f"- BTM Requests (AP -> Client): {reqs}\n"
                f"- BTM Responses (Client -> AP): {resps}\n"
                f"- Status Codes: {status_str}\n"
            )
            # Quick interpretation
            if reqs > 0 and resps == 0:
                 btm_summary += "👉 Client ignores BTM (possible lack of 11v support)\n\n"
            elif any("Accept" in s for s in unique_status):
                 btm_summary += "✅ Client cooperates via 802.11v\n\n"
            elif any("Reject" in s for s in unique_status):
                 btm_summary += "❌ Client rejects steering proposals\n\n"
            else:
                 btm_summary += "\n"
        else:
            # Explicitly report that no BTM was found
            btm_summary = (
                "📡 BSS TRANSITION MANAGEMENT (802.11v):\n"
                "- Status: NOT DETECTED (Steering via Probe Suppression or legacy mechanism)\n"
                "- BTM Events: 0\n\n"
            )

        # KVR Summary
        kvr_summary = ""
        kvr = d.get("band_counters", {}).get("kvr_stats", {})
        if kvr:
             kvr_list = []
             if kvr.get("11k"): kvr_list.append("802.11k (Neighbor Reports)")
             if kvr.get("11v"): kvr_list.append("802.11v (BTM/WNM)")
             if kvr.get("11r"): kvr_list.append("802.11r (Fast Transition)")
             
             if kvr_list:
                  kvr_summary = f"📶 ROAMING STANDARDS DETECTED (KVR):\n" + "\n".join([f"- ✅ {s}" for s in kvr_list]) + "\n\n"
             else:
                  kvr_summary = "📶 ROAMING STANDARDS: No explicit KVR flags detected in the capture.\n\n"

        # Association Failures Summary
        assoc_failures_summary = ""
        assoc_failures = d.get("band_counters", {}).get("association_failures", [])
        if assoc_failures:
            assoc_failures_summary = "❌ ASSOCIATION FAILURES DETECTED:\n"
            for f in assoc_failures[:10]:  # Max 10 to not saturate
                assoc_failures_summary += f"- BSSID: {f.get('bssid', 'N/A')} | Status: {f.get('status', 'N/A')} (Rejected by AP)\n"
            assoc_failures_summary += "\n"


        # Transitions summary
        transitions_summary = ""
        if sa["transitions"]:
            transitions_summary = "🔄 TRANSITION DETAILS:\n"
            for i, trans in enumerate(sa["transitions"][:5], 1):  # Show max 5
                status_emoji = {
                    "SUCCESS": "✅",
                    "SLOW": "⚠️",
                    "TIMEOUT": "❌",
                    "LOOP": "🔄",
                    "NO_REASSOC": "❌",
                    "NO_CHANGE": "⚠️"
                }.get(trans["status"], "❓")
                
                # Steering type
                steering_type = "🔴 Aggressive (Deauth)" if trans.get("type") == "aggressive" else "🟢 Assisted (802.11k/v/r)"
                
                time_str = f"{trans['transition_time']:.3f}s" if trans['transition_time'] else "N/A"
                band_change = f"{trans['from_band']} → {trans['to_band']}" if trans['is_band_change'] else "Same band"
                
                transitions_summary += (
                    f"{i}. {status_emoji} {steering_type}\n"
                    f"   Client: {trans['client'][:17]}...\n"
                    f"   Time: {time_str} | {band_change}\n"
                    f"   BSSID: {trans['from_bssid'][:17] if trans['from_bssid'] else 'N/A'}... → {trans['to_bssid'][:17] if trans['to_bssid'] else 'N/A'}...\n"
                    f"   Status: {trans['status']}\n"
                )
            
            if len(sa["transitions"]) > 5:
                transitions_summary += f"... and {len(sa['transitions']) - 5} more transitions\n"
            transitions_summary += "\n"
        
        return (
            f"# WIRESHARK CAPTURE ANALYSIS - BAND STEERING\n\n"
            f"**⚠️ IMPORTANT: All numerical values in this summary come directly from the Wireshark/tshark capture. "
            f"Do not estimate, round, or invent numbers that do not explicitly appear here.**\n\n"
            f"{btm_success_note}"
            f"**File:** {file_name}\n"
            f"**WLAN packets analyzed:** {stats['total_wlan_packets']}\n"
            f"**802.11 events captured:** {d['steering_events_count']}\n"
            f"**Capture quality:** {d['capture_quality']}\n\n"
            f"---\n\n"
            f"{bssid_summary}"
            f"## BAND STEERING METRICS\n\n"
            f"**Clients analyzed:** {sa['clients_analyzed']}\n"
            f"**Steering attempts:** {sa['steering_attempts']}\n"
            f"**Successful transitions:** {sa['successful_transitions']}\n"
            f"**Failed transitions:** {sa['failed_transitions']}\n"
            f"**Loops detected:** {'YES ❌' if sa['loop_detected'] else 'NO ✅'}\n"
            f"**Average transition time:** {sa['avg_transition_time']}s\n"
            f"**Max transition time:** {sa['max_transition_time']}s\n\n"
            f"---\n\n"
            f"{preventive_summary}"
            f"{kvr_summary}"
            f"{btm_summary}"
            f"{assoc_failures_summary}"
            f"{transitions_summary}"
            f"## NETWORK INDICATORS\n\n"
            f"- **TCP Retransmissions:** {d['tcp_retransmissions']}\n"
            f"- **WLAN Retries:** {d['wlan_retries']}\n"
            f"- **DNS Errors:** {d['dns_errors']}\n"
        )

    def _ask_llm_for_analysis(self, technical_summary: str) -> str:
        """
        Requests an interpretative analysis from the LLM based on extracted metrics.
        """
        system_message = (
            "You are a Senior Wi-Fi Network Auditor specialized in Band Steering (802.11k/v/r).\n\n"
            
            "## YOUR MISSION\n"
            "Write a professional, complete, and adaptive technical report on the Band Steering audit.\n"
            "You must analyze the Wireshark capture data and the compliance table to generate a report that is:\n"
            "- **Precise**: Based on real evidence from the capture\n"
            "- **Coherent**: Respecting the verdict of the compliance table\n"
            "- **Complete**: Covering all relevant technical aspects\n"
            "- **Professional**: With logical structure and clear conclusions\n\n"
            
            "## GOLDEN RULE: FIDELITY TO COMPLIANCE TABLE AND METRICS TABLE\n"
            "The technical summary includes a section '❌ FAILED CHECKS' and '✅ PASSED CHECKS'.\n\n"
            
            "**FOR THE VERDICT:**\n"
            "- **ONLY** mention as causes of failure the checks that appear in '❌ FAILED CHECKS'\n"
            "- If a check says 'PASSED', DO NOT use it as a cause of failure, even if the metrics seem suboptimal\n\n"
            
            "**FOR THE TECHNICAL ANALYSIS:**\n"
            "- USE all available data: BTM, transitions, times, loops, status codes, etc.\n"
            "- Explain the CONTEXT of why something failed using detailed metrics\n"
            "- Provide deep technical insights into the client's behavior\n\n"
            
            "## EXAMPLE OF CORRECT ANALYSIS:\n"
            "❌ INCORRECT: 'The verdict is FAILED because only 1 out of 12 transitions was successful'\n\n"
            
            "✅ CORRECT:\n"
            "'The verdict is FAILED due to:\n\n"
            "**Association and Reassociation: FAILED**\n"
            "5 forced disconnections (Deauthentication) and 3 disassociations were detected during the capture.\n"
            "This indicates that the AP is actively kicking the client instead of using cooperative\n"
            "steering mechanisms. Analysis of the transitions shows that out of 12 steering attempts, 9 failed\n"
            "precisely because of these abrupt disconnections, generating loops between 2.4GHz and 5GHz bands.\n\n"
            
            "**KVR Standards: FAILED**\n"
            "The device only supports 802.11v (BTM), but lacks 802.11k (Neighbor Reports) and 802.11r\n"
            "(Fast Transition). Although 2 BTM Requests with Status Code 0 (Accept) were detected, the absence\n"
            "of 11k/11r limits the client's ability to make informed roaming decisions.\n\n"
            
            "**IMPORTANT NOTE:** Although there was 1 successful transition, the test is FAILED due to the\n"
            "critical checks that were not met. Successful transitions are mentioned as technical context,\n"
            "but do not change the verdict.'\n\n"
 
            "## REPORT STRUCTURE (ADAPTIVE)\n\n"
            
            "You must create a report with sections that are relevant based on the data found.\n"
            "Do not use a rigid structure; adapt the sections to the capture content.\n\n"
            
            "**MANDATORY SECTIONS:**\n\n"
            
            "### 1. EXECUTIVE SUMMARY\n"
            "- Declare the verdict (SUCCESSFUL/FAILED/PARTIAL) based on 'ROOT CAUSE OF VERDICT'\n"
            "- Mention ONLY the failed checks as the cause of the verdict\n"
            "- Provide a high-level overview of key findings\n"
            "- Use concrete data (e.g., '5 Deauth detected', 'BTM Status Code 0', etc.)\n\n"
            
            "### [DYNAMIC TECHNICAL SECTIONS]\n"
            "Create the sections you need to cover relevant technical aspects. Examples:\n\n"
            
            "- **Roaming Protocol Analysis (802.11k/v/r)**: If there is BTM, KVR data, etc.\n"
            "  * What protocols were detected\n"
            "  * How the client behaved (cooperative, ignored, rejected)\n"
            "  * BTM status codes and their meaning\n\n"
            
            "- **Band Transition Analysis**: If transitions were detected\n"
            "  * Number of attempts vs successes\n"
            "  * Transition times (average, maximum)\n"
            "  * Steering type (aggressive with Deauth, assisted with BTM, preventive)\n"
            "  * Detection of loops or problematic patterns\n\n"
            
            "- **Association Stability**: If there are Deauth/Disassoc events\n"
            "  * Number of forced disconnections\n"
            "  * Impact on user experience\n"
            "  * Relationship with steering failures\n\n"
            
            "- **Network Quality**: If there are performance metrics\n"
            "  * TCP/WLAN retransmissions\n"
            "  * DNS errors\n"
            "  * Observed latency\n\n"
            
            "- **Client Behavior**: Insights about the device\n"
            "  * Detected capabilities\n"
            "  * Observed band preferences\n"
            "  * Cooperation level with the AP\n\n"
            
            "## GOLDEN RULE: TOTAL FIDELITY TO FINAL VERDICT\n"
            "The technical summary has a section called '**FINAL VERDICT**'.\n"
            "- If the verdict is **SUCCESS**, the report **MUST** conclude that the test was successful.\n"
            "- If the verdict is **SUCCESS**, you can mention loops or high times as 'points for improvement' or 'technical observations', but **NEVER** use them to say the test failed.\n"
            "- A **SUCCESS** verdict means minimum criteria were met; your analysis must validate that success.\n\n"
            
            "**FOR THE VERDICT:**\n"
            "- **ONLY** mention as causes of failure the checks that appear in '❌ FAILED CHECKS'\n"
            "- If a check says 'PASSED', DO NOT use it as a cause of failure or negative verdict.\n\n"
            
            "**REPORT STRUCTURE (ADAPTIVE):**\n\n"
            "1. **EXECUTIVE SUMMARY**: Declare the verdict based strictly on the 'FINAL VERDICT'.\n"
            "2. **TECHNICAL ANALYSIS**: Use metrics to explain the process.\n"
            "3. **FINAL CONCLUSION**: Must be 100% consistent with the table's verdict.\n\n"
            
            "## STRICT RULES\n"
            "1. **CONSISTENCY**: If the table says SUCCESS, your conclusion is SUCCESSFUL.\n"
            "2. **TONE**: If it is SUCCESS, the tone must be positive, acknowledging compliance with standards.\n"
            "3. **NUMBERS - CRITICAL**:\n"
            "   - ALL numbers you use MUST explicitly appear in the technical summary.\n"
            "   - These values come DIRECTLY from the Wireshark/tshark capture.\n"
            "   - IT IS STRICTLY FORBIDDEN TO:\n"
            "     * Estimate or approximate values\n"
            "     * Round numbers (unless already rounded in the summary)\n"
            "     * Invent quantities that do not appear in the summary\n"
            "     * Calculate averages or statistics not in the summary\n"
            "     * Use 'typical' or 'expected' values instead of real ones\n"
            "   - If a number does not appear in the technical summary, DO NOT mention it.\n"
            "   - Example: If the summary says '3 successful transitions', use exactly '3', not 'approximately 3' or 'around 3'.\n"
            "4. **BAND CHANGES - CRITICAL RULE**:\n"
            "   - The technical summary includes a section '📊 EFFECTIVE STEERING SUMMARY (CORRECTED VALUES)' showing the CORRECT number of band changes.\n"
            "   - ALWAYS use the number of band changes from that section, NOT from other parts of the summary.\n"
            "   - If the section says 'Physical band changes detected: X', use exactly that value X in your analysis.\n"
            "   - DO NOT use individual transitions with 'is_band_change' marked, as that calculation may be incorrect.\n"
            "   - The corrected value was calculated by comparing consecutive transitions and is the only reliable value.\n"
            "5. **LANGUAGE**: ENGLISH.\n"
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
            raise FileNotFoundError(f"File not found: {file_path}")

        file_name = os.path.basename(file_path)

        # 1. Extract base stats via tshark
        stats = self._extract_basic_stats(file_path=file_path)

        # 2. Get steering analysis
        steering_analysis = stats.get("steering_analysis", {})
        diagnostics = stats.get("diagnostics", {})

        # 3. Determine if evaluation should be FORCED (logic guardrail)
        # Based on whether there are detected steering events
        has_steering_events = diagnostics.get("steering_events_count", 0) > 0
        has_steering_attempts = steering_analysis.get("steering_attempts", 0) > 0
        has_transitions = (
            steering_analysis.get("successful_transitions", 0) > 0 or
            steering_analysis.get("failed_transitions", 0) > 0
        )
        has_preventive = steering_analysis.get("preventive_steering", False)

        # Force evaluation if there is ANY steering evidence
        force_evaluation = has_steering_events or has_steering_attempts or has_transitions or has_preventive

        # 4. Build technical summary
        technical_summary = self._build_technical_summary(
            stats=stats,
            file_name=file_name
        )

        # 5. Add explicit flag for the LLM (hard rule)
        if force_evaluation:
            technical_summary += (
                "\n\n**Force evaluation:** YES\n"
                "Rule: The capture contains sufficient 802.11 events. "
                "It is FORBIDDEN to issue the verdict ❓ NOT EVALUABLE."
            )
        else:
            technical_summary += (
                "\n\n**Force evaluation:** NO\n"
                "Rule: The capture may be considered insufficient."
            )

        # 6. Execute analysis with LLM
        analysis_text = self._ask_llm_for_analysis(technical_summary)

        # 7. Final return
        return {
            "file_name": file_name,
            "analysis": analysis_text,
            "stats": stats,
            "technical_summary": technical_summary,
            "forced_evaluation": force_evaluation,
        }