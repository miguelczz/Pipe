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
    Director de orquesta para el proceso AIDLC de Band Steering.
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
        Realiza el ciclo completo de análisis AIDLC:
        Extracción -> Clasificación -> Análisis BTM -> Fragmentación -> Reporte IA -> Persistencia -> Indexación.
        """
        logger.info(f"Iniciando análisis integral de: {file_path}")
        file_name = original_filename or os.path.basename(file_path)
        
        # 1. Extracción de datos crudos (WiresharkTool)
        raw_data = self.wireshark_tool._extract_basic_stats(file_path)
        
        # 2. Identificación y Clasificación del Dispositivo
        steering_events = raw_data.get("steering_events", [])
        
        def is_valid_client_mac(mac: str) -> bool:
            if not mac or mac == "ff:ff:ff:ff:ff:ff" or mac == "00:00:00:00:00:00":
                return False
            try:
                first_octet = int(mac.split(':')[0], 16)
                if first_octet & 1: return False # Multicast
            except: return False
            return True

        primary_mac = "unknown"
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
        # Sincronizar: Pasar los resultados de WiresharkTool como base para BTMAnalyzer
        combined_stats = raw_data.get("diagnostics", {}).get("band_counters", {}).copy()
        if "steering_analysis" in raw_data:
            combined_stats.update(raw_data["steering_analysis"])

        analysis = self.btm_analyzer.analyze_btm_events(
            steering_events=steering_events,
            band_counters=combined_stats,
            filename=file_name,
            device_info=device_info
        )
        
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
        technical_summary += f"\n\n## AUDITORÍA DE CUMPLIMIENTO (AIDLC)\n\n"
        technical_summary += f"**Veredicto Final AIDLC:** {analysis.verdict}\n\n"
        
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
