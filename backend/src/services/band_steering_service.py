"""
Servicio orquestador principal para el análisis de Band Steering.
Coordina la extracción de datos, análisis BTM, clasificación de dispositivos y generación de fragmentos.
"""
import logging
import json
import os
import shutil
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..tools.wireshark_tool import WiresharkTool
from ..tools.btm_analyzer import BTMAnalyzer
from ..tools.device_classifier import DeviceClassifier
from .fragment_extractor import FragmentExtractor
from .embeddings_service import process_and_store_pdf # Para indexar si generamos PDF
from ..models.btm_schemas import BandSteeringAnalysis, DeviceInfo
from ..repositories.qdrant_repository import get_qdrant_repository

logger = logging.getLogger(__name__)

class BandSteeringService:
    """
    Director de orquesta para el proceso de Band Steering.
    Cumple con los requerimientos de organización por marca y extracción de fragmentos.
    """

    def __init__(
        self, 
        base_data_dir: str = "data/analyses",
        wireshark_tool: Optional[WiresharkTool] = None,
        btm_analyzer: Optional[BTMAnalyzer] = None,
        device_classifier: Optional[DeviceClassifier] = None,
        fragment_extractor: Optional[FragmentExtractor] = None
    ):
        # Asegurar que el directorio base sea absoluto
        # En Docker, usar /app/data/analyses; en local, usar ruta relativa resuelta
        base_path = Path(base_data_dir)
        if not base_path.is_absolute():
            # Si es relativo, resolverlo desde el directorio de trabajo actual
            # En Docker, WORKDIR es /app, así que "data/analyses" se resuelve a /app/data/analyses
            # En local, se resuelve desde donde se ejecuta el script
            base_path = Path(base_data_dir).resolve()
        self.base_dir = base_path
        self.wireshark_tool = wireshark_tool or WiresharkTool()
        self.btm_analyzer = btm_analyzer or BTMAnalyzer()
        self.device_classifier = device_classifier or DeviceClassifier()
        self.fragment_extractor = fragment_extractor or FragmentExtractor()
        
        # Crear directorio base si no existe
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"🔍 [INIT] BandSteeringService inicializado con base_dir: {self.base_dir} (absoluto: {self.base_dir.is_absolute()})")

    async def process_capture(
        self, 
        file_path: str, 
        user_metadata: Optional[Dict[str, str]] = None,
        original_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Realiza el ciclo completo de análisis de Band Steering:
            pass
        Extracción -> Clasificación -> Análisis BTM -> Fragmentación -> Reporte IA -> Persistencia -> Indexación.
        """ 
        file_name = original_filename or os.path.basename(file_path)
        
        # 1. Extracción de datos crudos (WiresharkTool)
        ssid_hint = (user_metadata or {}).get("ssid") if user_metadata else None
        client_mac_hint = (user_metadata or {}).get("client_mac") if user_metadata else None
        raw_data = self.wireshark_tool._extract_basic_stats(
            file_path=file_path,
            ssid_filter=ssid_hint,
            client_mac_hint=client_mac_hint,
        )
        
        # 2. Identificación y Clasificación del Dispositivo
        steering_events = raw_data.get("steering_events", [])
        signal_samples = raw_data.get("signal_samples", [])
        
        def is_valid_client_mac(mac: str) -> bool:
            if not mac or mac == "ff:ff:ff:ff:ff:ff" or mac == "00:00:00:00:00:00":
                return False
            try:
                first_octet = int(mac.split(':')[0], 16)
                if first_octet & 1: return False # Multicast
            except: return False
            return True

        primary_mac = "unknown"
        client_mac_warning = None

        # Obtener BSSIDs conocidos para validación
        bssid_info = raw_data.get("diagnostics", {}).get("bssid_info", {})
        known_bssids = set()
        if bssid_info:
            for bssid in bssid_info.keys():
                if bssid and bssid != "":
                    known_bssids.add(bssid.lower().replace("-", ":"))

        # Preferir la MAC proporcionada por el usuario si es válida
        if client_mac_hint and is_valid_client_mac(client_mac_hint):
            # Normalizar MAC para comparación
            hint_normalized = client_mac_hint.lower().replace("-", ":")
            
            # Verificar si la MAC ingresada es un BSSID conocido
            if hint_normalized in known_bssids:
                client_mac_warning = (
                    f"La MAC ingresada ({client_mac_hint}) corresponde a un BSSID conocido. "
                    f"¿Estás seguro de que es la MAC del cliente y no del Access Point? "
                    f"El análisis usará esta MAC pero puede no ser correcta."
                )
            else:
                primary_mac = client_mac_hint
        else:
            for event in steering_events:
                event_mac = event.get("client_mac")
                if is_valid_client_mac(event_mac):
                    primary_mac = event_mac
                    break
            
            # Si no hay eventos específicos, usar la que detectó WiresharkTool como global
            if primary_mac == "unknown":
                primary_mac = raw_data.get("diagnostics", {}).get("client_mac", "unknown")
        
        # Validar que primary_mac sea una MAC válida antes de clasificar
        # Si no es válida, usar una MAC genérica válida para evitar errores en classify_device
        if not is_valid_client_mac(primary_mac) or primary_mac == "unknown":
            # Usar una MAC válida genérica (unicast, globalmente administrada)
            # Esta MAC pasará la validación pero no identificará un dispositivo real
            primary_mac = "00:11:22:33:44:55"
            
        device_info = self.device_classifier.classify_device(
            primary_mac, 
            user_metadata,
            filename=file_name
        )

        # 3. Análisis Especializado BTM y cumplimiento (BTMAnalyzer)
        # Sincronizar: Pasar los resultados de WiresharkTool como base para BTMAnalyzer.
        # IMPORTANTE: `combined_stats` es sólo un contenedor de lectura para
        # BTMAnalyzer; la fuente de verdad sigue siendo `raw_data.diagnostics`.
        combined_stats = raw_data.get("diagnostics", {}).get("band_counters", {}).copy()
        if "steering_analysis" in raw_data:
            combined_stats.update(raw_data["steering_analysis"])
        # Adjuntar referencia de solo lectura a los datos crudos de Wireshark
        # para que BTMAnalyzer pueda usar `wireshark_raw.summary` cuando exista.
        wireshark_raw = raw_data.get("diagnostics", {}).get("wireshark_raw")
        if wireshark_raw:
            combined_stats["wireshark_raw"] = wireshark_raw

        analysis = self.btm_analyzer.analyze_btm_events(
            steering_events=steering_events,
            band_counters=combined_stats,
            filename=file_name,
            device_info=device_info,
            signal_samples=signal_samples,
            wireshark_raw=raw_data.get("diagnostics", {}).get("wireshark_raw")
        )
        
        # SINCRONIZAR: Actualizar steering_analysis con los valores calculados en
        # BTMAnalyzer para que todos los paneles muestren los mismos valores.
        # En esta dirección, BTMAnalyzer sólo puede *refinar* valores ya
        # derivados de WiresharkTool (por ejemplo, tomando el máximo entre
        # BTM Accepts y transiciones exitosas), pero nunca inventar
        # contadores que contradigan a `wireshark_raw.summary`.
        if "steering_analysis" in raw_data:
            synchronized_metrics = self._synchronize_steering_metrics(analysis, steering_events, primary_mac)
            raw_data["steering_analysis"].update(synchronized_metrics)
        
        # COMPARAR: Raw Wireshark vs Datos Procesados
        wireshark_compare = self._compare_wireshark_raw_vs_processed(
            raw_data.get("diagnostics", {}).get("wireshark_raw"),
            raw_data.get("steering_analysis", {}),
            analysis
        )
        if "diagnostics" in raw_data:
            raw_data["diagnostics"]["wireshark_compare"] = wireshark_compare
        
        # Completar datos globales que BTMAnalyzer no tiene
        analysis.total_packets = raw_data.get("total_packets", 0)
        analysis.wlan_packets = raw_data.get("total_wlan_packets", 0)

        # 4. Extracción de Fragmentos (FragmentExtractor)
        fragments = []
        for transition in analysis.transitions:
            if transition.is_band_change:
                frag = self.fragment_extractor.extract_channel_transition(
                    input_file=file_path,
                    client_mac=transition.client_mac,
                    transition_time=transition.start_time
                )
                if frag:
                    fragments.append(frag)
        
        analysis.fragments = fragments

        # 5. Generación de Informe Narrativo (IA)
        # Usamos la lógica de WiresharkTool para mantener consistencia con el reporte visual
        technical_summary = self.wireshark_tool._build_technical_summary(
            stats=raw_data,
            file_name=file_name
        )
        
        # Recalcular el veredicto basándose en los checks corregidos (que ahora tienen el cálculo correcto de cambios de banda)
        # El veredicto ya debería estar correcto porque los checks se calcularon con la lógica corregida,
        # pero lo recalculamos para asegurarnos de que sea consistente
        corrected_verdict = self.btm_analyzer._determine_verdict(
            checks=analysis.compliance_checks,
            transitions=analysis.transitions,
            btm_rate=analysis.btm_success_rate,
            success_count=analysis.successful_transitions
        )
        analysis.verdict = corrected_verdict
        
        # Añadir información de cumplimiento al summary para el LLM
        technical_summary += f"\n\n## AUDITORÍA DE CUMPLIMIENTO (BAND STEERING)\n\n"
        technical_summary += f"**Veredicto Final:** {analysis.verdict}\n\n"
        
        # Agregar información explícita sobre cambios de banda calculados correctamente ANTES de los checks
        # para que el agente tenga contexto claro desde el inicio
        steering_check = next((c for c in analysis.compliance_checks if c.check_name == "Steering Efectivo"), None)
        if steering_check:
            # Extraer el número de cambios de banda del details del check (que ya está corregido)
            details = steering_check.details or ""
            # El formato es: "TRANSICIONES CON CAMBIO DE BANDA: X | TRANSICIONES TOTALES: Y | BTM ACCEPT: Z"
            band_change_match = re.search(r'TRANSICIONES CON CAMBIO DE BANDA:\s*(\d+)', details)
            total_match = re.search(r'TRANSICIONES TOTALES:\s*(\d+)', details)
            btm_match = re.search(r'BTM ACCEPT:\s*(\d+)', details)
            
            if band_change_match:
                band_change_count = int(band_change_match.group(1))
                total_transitions = int(total_match.group(1)) if total_match else 0
                btm_accept = int(btm_match.group(1)) if btm_match else 0
                
                technical_summary += f"### 📊 RESUMEN DE STEERING EFECTIVO (VALORES CORREGIDOS)\n\n"
                technical_summary += f"**⚠️ IMPORTANTE:** Los siguientes valores fueron calculados comparando transiciones consecutivas para detectar cambios reales de banda, incluso si el campo `is_band_change` individual no estaba marcado correctamente.\n\n"
                technical_summary += f"- **Cambios de banda físicos detectados:** {band_change_count}\n"
                technical_summary += f"- **Transiciones exitosas totales:** {total_transitions}\n"
                technical_summary += f"- **BTM Accept (Status Code 0):** {btm_accept}\n\n"
                technical_summary += f"**NOTA CRÍTICA:** El número de cambios de banda ({band_change_count}) es el valor CORRECTO calculado mediante comparación de transiciones consecutivas. "
                technical_summary += f"Este es el valor que debe usarse para determinar si el steering fue efectivo, NO el número que pueda aparecer en otras secciones del resumen.\n\n"
        
        # Separar checks en pasados y fallidos para claridad
        passed_checks = [c for c in analysis.compliance_checks if c.passed]
        failed_checks = [c for c in analysis.compliance_checks if not c.passed]
        
        if failed_checks:
            technical_summary += "### ❌ CHECKS QUE FALLARON (CAUSA DEL VEREDICTO):\n"
            for check in failed_checks:
                technical_summary += f"- **{check.check_name}**: FALLÓ\n"
                technical_summary += f"  - Descripción: {check.description}\n"
                technical_summary += f"  - Evidencia: {check.details}\n"
                if check.recommendation:
                    technical_summary += f"  - Recomendación: {check.recommendation}\n"
                technical_summary += "\n"
        
        if passed_checks:
            technical_summary += "### ✅ CHECKS QUE PASARON:\n"
            for check in passed_checks:
                technical_summary += f"- **{check.check_name}**: PASÓ ({check.details})\n"
        
        # Explicación del veredicto basada en los fallos
        technical_summary += f"\n**CAUSA RAÍZ DEL VEREDICTO '{analysis.verdict}':**\n"
        if analysis.verdict == "FAILED":
            if failed_checks:
                technical_summary += "La prueba falló debido a los siguientes problemas críticos:\n"
                for check in failed_checks:
                    technical_summary += f"  - {check.check_name}: {check.recommendation or 'Revisar configuración'}\n"
            else:
                technical_summary += "Fallo general sin checks específicos identificados.\n"
        elif analysis.verdict == "SUCCESS":
            technical_summary += "La prueba fue exitosa: se cumplieron los criterios de band steering.\n"
            if steering_check and steering_check.passed:
                # Extraer el número de cambios de banda para mencionarlo en el éxito
                band_change_match = re.search(r'TRANSICIONES CON CAMBIO DE BANDA:\s*(\d+)', steering_check.details or "")
                if band_change_match:
                    band_change_count = int(band_change_match.group(1))
                    technical_summary += f"Se detectaron {band_change_count} cambio(s) de banda exitoso(s), cumpliendo con el criterio mínimo requerido.\n"
        
        analysis.analysis_text = self.wireshark_tool._ask_llm_for_analysis(technical_summary)

        # 6. Guardar user_metadata en raw_data para persistencia
        # Asegurar que los metadatos del usuario (SSID, client_mac) se guarden correctamente
        logger.info(f"🔍 [METADATA] user_metadata recibido: {user_metadata}")
        if user_metadata:
            if "diagnostics" not in raw_data:
                raw_data["diagnostics"] = {}
            if "user_metadata" not in raw_data["diagnostics"]:
                raw_data["diagnostics"]["user_metadata"] = {}
            # Guardar SSID y client_mac del usuario (si fueron proporcionados)
            if "ssid" in user_metadata and user_metadata["ssid"]:
                raw_data["diagnostics"]["user_metadata"]["ssid"] = user_metadata["ssid"]
                logger.info(f"✅ [METADATA] SSID guardado en raw_data: {user_metadata['ssid']}")
            else:
                logger.warning(f"⚠️ [METADATA] SSID no proporcionado o vacío en user_metadata")
            if "client_mac" in user_metadata and user_metadata["client_mac"]:
                raw_data["diagnostics"]["user_metadata"]["client_mac"] = user_metadata["client_mac"]
                logger.info(f"✅ [METADATA] client_mac guardado en raw_data: {user_metadata['client_mac']}")
            else:
                logger.warning(f"⚠️ [METADATA] client_mac no proporcionado o vacío en user_metadata")
        else:
            logger.warning(f"⚠️ [METADATA] user_metadata es None o vacío")
        
        logger.info(f"🔍 [METADATA] raw_data['diagnostics']['user_metadata'] final: {raw_data.get('diagnostics', {}).get('user_metadata', {})}")

        # 7. Guardar raw_stats en el objeto de análisis para persistencia
        analysis.raw_stats = raw_data

        # 8. Organización y Persistencia por Marca
        # Asegurar que file_path sea absoluto para evitar problemas en Docker
        original_file_path_abs = Path(file_path).resolve() if file_path else None
        logger.info(f"🔍 [PROCESS] Antes de guardar, file_path original: {file_path}")
        logger.info(f"🔍 [PROCESS] file_path absoluto: {original_file_path_abs}")
        logger.info(f"🔍 [PROCESS] file_path existe: {original_file_path_abs.exists() if original_file_path_abs else False}")
        save_path = self._save_analysis_result(analysis, device_info, str(original_file_path_abs) if original_file_path_abs else None)
        logger.info(f"🔍 [PROCESS] Después de guardar, save_path: {save_path}")

        # 9. Indexar en RAG (Qdrant) para que el chat tenga acceso
        self._index_analysis_for_rag(analysis)

        # Retornar objeto de análisis y datos crudos (para compatibilidad frontend)
        return {
            "analysis": analysis,
            "raw_stats": raw_data,
            "save_path": save_path
        }

    def _synchronize_steering_metrics(
        self, 
        analysis: BandSteeringAnalysis, 
        steering_events: List[Dict[str, Any]],
        primary_client_mac: str
    ) -> Dict[str, Any]:
        """
        Sincroniza las métricas de steering_analysis con los valores calculados en BTMAnalyzer.
        Esto asegura que todos los paneles (métricas, compliance checks, gráfica) muestren los mismos valores.
        
        Usa la MISMA lógica que los compliance checks para garantizar consistencia.
        """
        # USAR EXACTAMENTE LA MISMA LÓGICA que compliance checks para garantizar consistencia
        
        # Contar transiciones con cambio de banda exitosas
        band_change_transitions = sum(1 for t in analysis.transitions if t.is_successful and t.is_band_change)
        
        # Contar transiciones exitosas entre BSSIDs distintos (roaming dentro de la misma banda)
        # MISMOS CRITERIOS que compliance checks: solo cambios de BSSID, no todas las transiciones sin cambio de banda
        bssid_change_transitions = sum(
            1
            for t in analysis.transitions
            if t.is_successful
            and t.from_bssid
            and t.to_bssid
            and t.from_bssid != t.to_bssid
        )
        
        # Contar BTM responses exitosos (cooperación del cliente con steering)
        btm_successful_responses = sum(
            1 for e in steering_events 
            if e.get("type") == "btm" 
            and e.get("event_type") == "response"
            and (e.get("status_code") == 0 or str(e.get("status_code")) == "0")
            and (not primary_client_mac or e.get("client_mac") == primary_client_mac)
        )
        
        # MISMOS CRITERIOS que compliance checks: Steering efectivo SOLO si hay:
        # 1. Al menos 1 cambio de banda exitoso, O
        # 2. Al menos 1 transición exitosa entre BSSIDs distintos
        # NOTA: BTM Accept solo cuenta si también hay cambio de banda o BSSID
        # (un BTM Accept sin cambio físico no es steering efectivo)
        # CORRECCIÓN: Contar TODAS las transiciones exitosas (no solo el máximo)
        # Una transición puede tener cambio de banda Y cambio de BSSID, pero solo se cuenta una vez
        total_successful_transitions = sum(1 for t in analysis.transitions if t.is_successful)
        steering_effective_count = max(band_change_transitions, bssid_change_transitions)
        
        # Si hay BTM Accept PERO también hay cambio de banda/BSSID, es steering efectivo
        # Si solo hay BTM Accept sin cambios físicos, NO es steering efectivo
        if btm_successful_responses > 0 and steering_effective_count == 0:
            # BTM Accept sin cambio físico: no es steering efectivo
            total_successful = 0
        else:
            # Usar el total de transiciones exitosas (no solo el máximo entre tipos)
            # Esto asegura que se cuenten todas: cambios de banda + transiciones de asociación
            total_successful = total_successful_transitions
        
        # Contar BTM requests del cliente principal
        btm_requests_count = sum(
            1 for e in steering_events 
            if e.get("type") == "btm" 
            and e.get("event_type") == "request"
            and (not primary_client_mac or e.get("client_mac") == primary_client_mac)
        )
        
        # El total de intentos es el máximo entre requests BTM y número de transiciones
        # Esto asegura que si hay más transiciones que requests, se cuenten todas
        total_attempts = max(btm_requests_count, len(analysis.transitions))
        
        # Calcular tiempo promedio de transiciones exitosas
        successful_transition_times = [
            t.duration for t in analysis.transitions 
            if t.is_successful and t.duration and t.duration > 0
        ]
        avg_time = sum(successful_transition_times) / len(successful_transition_times) if successful_transition_times else 0
        
        return {
            "steering_attempts": total_attempts,
            "successful_transitions": total_successful,
            "failed_transitions": max(0, total_attempts - total_successful),
            "avg_transition_time": round(avg_time, 3),
            "max_transition_time": round(max(successful_transition_times) if successful_transition_times else 0, 3),
            "verdict": analysis.verdict
        }
    
    def _compare_wireshark_raw_vs_processed(
        self,
        wireshark_raw: Optional[Dict[str, Any]],
        steering_analysis: Dict[str, Any],
        analysis: BandSteeringAnalysis
    ) -> Dict[str, Any]:
        """
        Compara los datos raw de Wireshark con los datos procesados para detectar inconsistencias.
        Retorna un diccionario con mismatches encontrados.
        """
        if not wireshark_raw:
            return {
                "enabled": False,
                "reason": "wireshark_raw no disponible",
                "mismatches": []
            }
        
        mismatches = []
        raw_summary = wireshark_raw.get("summary", {})
        raw_btm = raw_summary.get("btm", {})
        raw_assoc = raw_summary.get("assoc", {})
        raw_reassoc = raw_summary.get("reassoc", {})
        
        # Comparación 1: BTM Requests
        raw_btm_requests = raw_btm.get("requests", 0)
        processed_steering_attempts = steering_analysis.get("steering_attempts", 0)
        if raw_btm_requests > 0 and processed_steering_attempts != raw_btm_requests:
            mismatches.append({
                "field": "btm_requests_vs_steering_attempts",
                "raw_value": raw_btm_requests,
                "processed_value": processed_steering_attempts,
                "delta": processed_steering_attempts - raw_btm_requests,
                "severity": "warning",
                "explanation": f"Los intentos de steering ({processed_steering_attempts}) pueden incluir Deauth/Disassoc además de BTM Requests ({raw_btm_requests})"
            })
        
        # Comparación 2: BTM Responses Accept vs Successful Transitions
        raw_btm_accept = raw_btm.get("responses_accept", 0)
        processed_successful = steering_analysis.get("successful_transitions", 0)
        # Usar el máximo entre transiciones exitosas y BTM accepts (como en compliance checks)
        analysis_successful = max(
            sum(1 for t in analysis.transitions if t.is_successful),
            raw_btm_accept
        )
        if raw_btm_accept > 0 and processed_successful != analysis_successful:
            mismatches.append({
                "field": "btm_accept_vs_successful_transitions",
                "raw_value": raw_btm_accept,
                "processed_value": processed_successful,
                "expected_value": analysis_successful,
                "delta": processed_successful - analysis_successful,
                "severity": "error" if abs(processed_successful - analysis_successful) > 1 else "warning",
                "explanation": f"BTM Accept raw: {raw_btm_accept}, Transiciones exitosas: {sum(1 for t in analysis.transitions if t.is_successful)}, Esperado: {analysis_successful}, Procesado: {processed_successful}"
            })
        
        # Comparación 3: Association/Reassociation counts (coherencia básica)
        raw_assoc_req = raw_assoc.get("requests", 0)
        raw_assoc_resp = raw_assoc.get("responses", 0)
        raw_reassoc_req = raw_reassoc.get("requests", 0)
        raw_reassoc_resp = raw_reassoc.get("responses", 0)
        
        # Comparación 4: Deauth / Disassoc totales
        raw_deauth = raw_summary.get("deauth", {})
        raw_disassoc = raw_summary.get("disassoc", {})
        raw_deauth_count = raw_deauth.get("count", 0)
        raw_disassoc_count = raw_disassoc.get("count", 0)

        # Contar eventos de steering que son Deauth/Disassoc dirigidos al cliente
        processed_deauth = 0
        processed_disassoc = 0
        if analysis.transitions:
            for t in analysis.transitions:
                # Transitions no contienen todos los eventos 1:1, así que aquí
                # sólo verificamos si hay una desviación grosera (ej. 0 vs muchos).
                # El conteo fino se hace en los compliance checks.
                pass
        # Si Wireshark detecta desconexiones pero el análisis no ve ninguna
        if (raw_deauth_count + raw_disassoc_count) > 0 and analysis.loops_detected is False:
            mismatches.append({
                "field": "forced_disconnect_visibility",
                "raw_value": {
                    "deauth": raw_deauth_count,
                    "disassoc": raw_disassoc_count,
                },
                "processed_value": "no_loops_detected",
                "severity": "warning",
                "explanation": "Wireshark detecta desconexiones (Deauth/Disassoc) pero el análisis no marca bucles; revisar estabilidad en el reporte narrativo."
            })

        # Verificar inconsistencias en freq_band_map
        freq_band_inconsistencies = []
        freq_band_map = raw_summary.get("freq_band_map", {})
        for freq_str, band in freq_band_map.items():
            try:
                freq_val = int(freq_str)
                expected_band = "2.4GHz" if 2400 <= freq_val <= 2500 else ("5GHz" if 5000 <= freq_val <= 6000 else None)
                if expected_band and band != expected_band:
                    freq_band_inconsistencies.append({
                        "frequency": freq_val,
                        "raw_band": band,
                        "expected_band": expected_band
                    })
            except (ValueError, TypeError):
                pass
        
        if freq_band_inconsistencies:
            mismatches.append({
                "field": "freq_band_inconsistencies",
                "raw_value": freq_band_inconsistencies,
                "processed_value": None,
                "severity": "error",
                "explanation": f"Se detectaron {len(freq_band_inconsistencies)} inconsistencias entre frecuencia y banda asignada"
            })
        
        # Comparación 4: BTM Status Codes
        raw_status_codes = raw_btm.get("status_codes", [])
        processed_status_codes = []
        for event in analysis.btm_events:
            if event.status_code is not None and str(event.status_code) not in processed_status_codes:
                processed_status_codes.append(str(event.status_code))
        
        if set(raw_status_codes) != set(processed_status_codes):
            mismatches.append({
                "field": "btm_status_codes",
                "raw_value": raw_status_codes,
                "processed_value": processed_status_codes,
                "severity": "warning",
                "explanation": "Los status codes pueden diferir si se filtraron eventos por cliente principal"
            })
        
        return {
            "enabled": True,
            "total_mismatches": len(mismatches),
            "mismatches": mismatches,
            "summary": {
                "raw_btm_requests": raw_btm_requests,
                "raw_btm_responses": raw_btm.get("responses", 0),
                "raw_btm_accept": raw_btm_accept,
                "processed_steering_attempts": processed_steering_attempts,
                "processed_successful_transitions": processed_successful,
                "raw_assoc": f"{raw_assoc_req}/{raw_assoc_resp}",
                "raw_reassoc": f"{raw_reassoc_req}/{raw_reassoc_resp}"
            }
        }
    
    def _index_analysis_for_rag(self, analysis: BandSteeringAnalysis):
        """
        Convierte el resultado del análisis en texto y lo indexa en Qdrant.
        Esto permite que el usuario pregunte sobre los resultados en el chat.
        """
        try:
            repo = get_qdrant_repository()
            
            # Crear un resumen textual del análisis
            summary = (
                f"Resultado del Análisis de Band Steering para el archivo {analysis.filename}. "
                f"Dispositivo: {analysis.devices[0].vendor} {analysis.devices[0].device_model if analysis.devices[0].device_model else ''}. "
                f"Veredicto Final: {analysis.verdict}. "
                f"Eventos BTM: {analysis.btm_requests} requests, {analysis.btm_responses} responses. "
                f"Tasa de éxito BTM: {analysis.btm_success_rate * 100}%. "
                f"Transiciones exitosas: {analysis.successful_transitions}. "
                f"Soporte KVR: K={analysis.kvr_support.k_support}, V={analysis.kvr_support.v_support}, R={analysis.kvr_support.r_support}. "
            )
            
            # Agregar detalles de los checks de cumplimiento
            for check in analysis.compliance_checks:
                status = "PASADO" if check.passed else "FALLADO"
                summary += f"Check '{check.check_name}': {status}. {check.details}. "

            # En un entorno real, usaría embedding_for_text del repo
            from ..utils.embeddings import embedding_for_text
            vector = embedding_for_text(summary)
            
            point = {
                "id": str(analysis.analysis_id),
                "vector": vector,
                "payload": {
                    "text": summary,
                    "source": analysis.filename,
                    "type": "analysis_result",
                    "timestamp": datetime.now().isoformat(),
                    "analysis_id": analysis.analysis_id
                }
            }
            
            repo.upsert_points([point])
            
        except Exception as e:
            pass

    def _save_analysis_result(self, analysis: BandSteeringAnalysis, device: DeviceInfo, original_file_path: Optional[str] = None) -> str:
        """
        Organiza los archivos en carpetas por Marca/Modelo.
        Estructura: data/analyses/{Vendor}/{Model_or_MAC}/{analysis_id}.json
        También guarda el archivo pcap original para descarga posterior.
        """
        logger.info(f"🔍 [SAVE] _save_analysis_result llamado")
        logger.info(f"🔍 [SAVE] original_file_path recibido: {original_file_path}")
        logger.info(f"🔍 [SAVE] analysis_id: {analysis.analysis_id}")
        vendor_name = device.vendor.replace(" ", "_")
        device_id = device.device_model.replace(" ", "_") if device.device_model else device.mac_address.replace(":", "")
        
        target_dir = self.base_dir / vendor_name / device_id
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Guardar JSON de análisis
        json_path = target_dir / f"{analysis.analysis_id}.json"
        
        # Guardar el archivo pcap original si existe
        saved_pcap_path = None
        logger.info(f"🔍 [SAVE] Intentando guardar archivo pcap. original_file_path: {original_file_path}")
        logger.info(f"🔍 [SAVE] base_dir: {self.base_dir} (absoluto: {self.base_dir.is_absolute()})")
        if original_file_path:
            # Asegurar que el path sea absoluto
            original_path = Path(original_file_path)
            if not original_path.is_absolute():
                original_path = original_path.resolve()
            logger.info(f"🔍 [SAVE] Path original (relativo): {original_file_path}")
            logger.info(f"🔍 [SAVE] Path absoluto resuelto: {original_path}")
            logger.info(f"🔍 [SAVE] Path existe: {original_path.exists()}")
            if original_path.exists():
                try:
                    # Copiar el archivo pcap a la carpeta del análisis
                    pcap_filename = original_path.name
                    logger.info(f"🔍 [SAVE] Nombre original del archivo: {pcap_filename}")
                    # Limpiar UUID del nombre si existe (formato UUID_Nombre.pcap)
                    if '_' in pcap_filename and len(pcap_filename.split('_')[0]) == 36:
                        pcap_filename = '_'.join(pcap_filename.split('_')[1:])
                        logger.info(f"🔍 [SAVE] Nombre limpiado (sin UUID): {pcap_filename}")
                    
                    saved_pcap_path = target_dir / f"{analysis.analysis_id}_{pcap_filename}"
                    logger.info(f"🔍 [SAVE] Copiando de {original_path} a {saved_pcap_path}")
                    shutil.copy2(original_path, saved_pcap_path)
                    saved_pcap_path = str(saved_pcap_path)
                    logger.info(f"✅ [SAVE] Archivo pcap copiado exitosamente a: {saved_pcap_path}")
                except Exception as e:
                    logger.error(f"❌ [SAVE] Error al copiar archivo pcap: {e}", exc_info=True)
            else:
                logger.warning(f"⚠️ [SAVE] El archivo original no existe: {original_path}")
        else:
            logger.warning(f"⚠️ [SAVE] original_file_path es None o vacío")
        
        # Guardar la ruta del archivo en el análisis
        # NOTA: No asignar directamente al objeto Pydantic (no es un campo del modelo)
        # Se guardará en el dict al serializar para persistencia en JSON
        
        with open(json_path, "w", encoding="utf-8") as f:
            # Convertir a dict para poder agregar campos adicionales
            # Usar model_dump con mode='json' para serializar datetime correctamente
            analysis_dict = analysis.model_dump(mode='json', exclude_none=False)
            
            # CRÍTICO: Asegurar que raw_stats (que contiene user_metadata) se guarde SIEMPRE
            # Aunque raw_stats es un campo del modelo, lo forzamos explícitamente
            # porque model_dump puede no incluirlo si es None o si hay problemas de serialización
            if hasattr(analysis, 'raw_stats'):
                analysis_dict["raw_stats"] = analysis.raw_stats
                if analysis.raw_stats:
                    user_meta = analysis.raw_stats.get('diagnostics', {}).get('user_metadata', {})
                    logger.info(f"✅ [SAVE] raw_stats guardado en JSON")
                    logger.info(f"✅ [SAVE] user_metadata en raw_stats: {user_meta}")
                else:
                    logger.warning(f"⚠️ [SAVE] raw_stats es None en analysis")
            else:
                logger.error(f"❌ [SAVE] analysis no tiene atributo raw_stats")
            
            if saved_pcap_path:
                analysis_dict["original_file_path"] = saved_pcap_path
                logger.info(f"✅ [SAVE] original_file_path guardado: {saved_pcap_path}")
            
            # Verificar que user_metadata esté en el dict final antes de guardar
            final_user_meta = analysis_dict.get('raw_stats', {}).get('diagnostics', {}).get('user_metadata', {})
            logger.info(f"🔍 [SAVE] user_metadata en analysis_dict final: {final_user_meta}")
            
            # Guardar el JSON
            json.dump(analysis_dict, f, indent=4, ensure_ascii=False)
            logger.info(f"✅ [SAVE] Análisis guardado en: {json_path}")
            
            # Verificación final: leer el archivo guardado para confirmar que user_metadata está ahí
            try:
                with open(json_path, "r", encoding="utf-8") as verify_f:
                    verify_data = json.load(verify_f)
                    verify_user_meta = verify_data.get('raw_stats', {}).get('diagnostics', {}).get('user_metadata', {})
                    if verify_user_meta:
                        logger.info(f"✅ [SAVE] VERIFICACIÓN: user_metadata confirmado en archivo guardado: {verify_user_meta}")
                    else:
                        logger.error(f"❌ [SAVE] VERIFICACIÓN FALLIDA: user_metadata NO está en el archivo guardado!")
            except Exception as e:
                logger.error(f"❌ [SAVE] Error al verificar archivo guardado: {e}")
            
        return str(json_path)

    def get_brand_statistics(self, brand: str) -> Dict[str, Any]:
        """
        Retorna estadísticas agregadas para una marca específica.
        """
        brand_dir = self.base_dir / brand.replace(" ", "_")
        if not brand_dir.exists():
            return {"error": "Marca no encontrada"}
            
        # Lógica para recorrer archivos y promediar compliance scores, etc.
        # (Implementación futura según necesidad)
        return {"brand": brand, "status": "active"}
