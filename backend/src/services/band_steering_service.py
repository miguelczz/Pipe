"""
Servicio orquestador principal para el análisis de Band Steering.
Coordina la extracción de datos, análisis BTM, clasificación de dispositivos y generación de fragmentos.
"""
import logging
import json
import os
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
        self.base_dir = Path(base_data_dir)
        self.wireshark_tool = wireshark_tool or WiresharkTool()
        self.btm_analyzer = btm_analyzer or BTMAnalyzer()
        self.device_classifier = device_classifier or DeviceClassifier()
        self.fragment_extractor = fragment_extractor or FragmentExtractor()
        
        # Crear directorio base si no existe
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def process_capture(
        self, 
        file_path: str, 
        user_metadata: Optional[Dict[str, str]] = None,
        original_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Realiza el ciclo completo de análisis de Band Steering:
        Extracción -> Clasificación -> Análisis BTM -> Fragmentación -> Reporte IA -> Persistencia -> Indexación.
        """ 
        logger.info(f"Iniciando análisis integral de: {file_path}")
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
                logger.warning(f"⚠️ {client_mac_warning}")
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
            
        device_info = self.device_classifier.classify_device(
            primary_mac, 
            user_metadata,
            filename=file_name
        )
        logger.info(f"Dispositivo identificado: {device_info.vendor} ({device_info.mac_address})")

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
            logger.info(f"📊 Métricas sincronizadas: {synchronized_metrics.get('successful_transitions', 0)}/{synchronized_metrics.get('steering_attempts', 0)} exitosos")
        
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
        
        # Añadir información de cumplimiento al summary para el LLM
        technical_summary += f"\n\n## AUDITORÍA DE CUMPLIMIENTO (BAND STEERING)\n\n"
        technical_summary += f"**Veredicto Final:** {analysis.verdict}\n\n"
        
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
        
        analysis.analysis_text = self.wireshark_tool._ask_llm_for_analysis(technical_summary)

        # 6. Guardar raw_stats en el objeto de análisis para persistencia
        analysis.raw_stats = raw_data

        # 7. Organización y Persistencia por Marca
        save_path = self._save_analysis_result(analysis, device_info)
        logger.info(f"Análisis guardado exitosamente en: {save_path}")

        # 8. Indexar en RAG (Qdrant) para que el chat tenga acceso
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
        steering_effective_count = max(band_change_transitions, bssid_change_transitions)
        
        # Si hay BTM Accept PERO también hay cambio de banda/BSSID, es steering efectivo
        # Si solo hay BTM Accept sin cambios físicos, NO es steering efectivo
        if btm_successful_responses > 0 and steering_effective_count == 0:
            # BTM Accept sin cambio físico: no es steering efectivo
            total_successful = 0
        else:
            # Si hay steering efectivo, usar el máximo entre efectivo y BTM (si hay cambio físico)
            total_successful = max(steering_effective_count, btm_successful_responses if steering_effective_count > 0 else 0)
        
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
            logger.info(f"Análisis {analysis.analysis_id} indexado en Qdrant para RAG.")
            
        except Exception as e:
            logger.error(f"Error al indexar análisis para RAG: {e}")

    def _save_analysis_result(self, analysis: BandSteeringAnalysis, device: DeviceInfo) -> str:
        """
        Organiza los archivos en carpetas por Marca/Modelo.
        Estructura: data/analyses/{Vendor}/{Model_or_MAC}/{analysis_id}.json
        """
        vendor_name = device.vendor.replace(" ", "_")
        device_id = device.device_model.replace(" ", "_") if device.device_model else device.mac_address.replace(":", "")
        
        target_dir = self.base_dir / vendor_name / device_id
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Guardar JSON de análisis
        file_path = target_dir / f"{analysis.analysis_id}.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            # Usamos el método .model_dump_json() de Pydantic v2 (o .json() en v1)
            # Como estamos bajo Software Engineering Constitution (Pydantic 2), usamos model_dump
            f.write(analysis.model_dump_json(indent=4))
            
        return str(file_path)

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
