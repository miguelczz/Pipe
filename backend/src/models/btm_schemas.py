"""
Schemas Pydantic para el análisis de Band Steering (AIDLC).
Definiciones de estructuras de datos para eventos 802.11, BTM, métricas y reportes.
"""
from enum import Enum
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field


# ============================================================================
# Enums y Constantes
# ============================================================================

class BTMStatusCode(str, Enum):
    """
    Códigos de estado BTM según estándar 802.11v.
    Define la respuesta del cliente a una solicitud de transición.
    """
    ACCEPT = "0"
    ACCEPT_PREFERRED = "1"
    REJECT_UNSPECIFIED = "2"
    REJECT_INSUFFICIENT_BEACON = "3"
    REJECT_INSUFFICIENT_CAPINFO = "4"
    REJECT_UNACCEPTABLE_DELAY = "5"
    REJECT_DESTINATION_UNREACHABLE = "6"
    REJECT_INVALID_CANDIDATE = "7"
    REJECT_LEAVING_ESS = "8"
    UNKNOWN = "unknown"

    @classmethod
    def is_success(cls, code: Union[str, int]) -> bool:
        """Determina si un código representa una transición exitosa (0 o 1)."""
        str_code = str(code)
        return str_code in [cls.ACCEPT.value, cls.ACCEPT_PREFERRED.value]

    @classmethod
    def get_description(cls, code: Union[str, int]) -> str:
        """Obtiene la descripción legible del código."""
        descriptions = {
            "0": "Accept",
            "1": "Accept with Candidate List",
            "2": "Reject - Unspecified",
            "3": "Reject - Insufficient Beacon",
            "4": "Reject - Insufficient Capacity",
            "5": "Reject - Unacceptable Termination Delay",
            "6": "Reject - Destination Unreachable",
            "7": "Reject - Invalid Candidate",
            "8": "Reject - Leaving ESS",
        }
        return descriptions.get(str(code), "Unknown Code")


class SteeringType(str, Enum):
    """
    Tipos de patrones de steering detectados.
    """
    AGGRESSIVE = "aggressive"  # Deauth/Disassoc forzada
    ASSISTED = "assisted"      # BTM, 802.11v
    PREVENTIVE = "preventive"  # Steering preventivo antes de degradación
    UNKNOWN = "unknown"


class DeviceCategory(str, Enum):
    """
    Categorías de dispositivos basadas en OUI y comportamiento.
    """
    MOBILE = "mobile_device"
    COMPUTER = "computer_laptop"
    NETWORK_EQUIPMENT = "network_equipment"
    VIRTUAL_MACHINE = "virtual_machine"
    IOT_DEVICE = "iot_device"
    UNKNOWN = "unknown_device"


# ============================================================================
# Modelos de Componentes
# ============================================================================

class DeviceInfo(BaseModel):
    """Información detallada de un dispositivo analizado."""
    mac_address: str = Field(..., description="MAC address del dispositivo")
    oui: str = Field(..., description="OUI (primeros 6 caracteres)")
    vendor: str = Field(..., description="Fabricante identificado")
    device_model: Optional[str] = Field(None, description="Modelo del dispositivo (si es detectable)")
    device_category: DeviceCategory = Field(default=DeviceCategory.UNKNOWN, description="Categoría del dispositivo")
    is_virtual: bool = Field(False, description="Indica si es una máquina virtual o MAC aleatoria")
    confidence_score: float = Field(0.0, ge=0.0, le=1.0, description="Confianza en la identificación (0-1)")


class BTMEvent(BaseModel):
    """Evento individual relacionado con BSS Transition Management (802.11v)."""
    timestamp: float = Field(..., description="Timestamp del evento en la captura")
    event_type: str = Field(..., description="Tipo de evento: 'request' o 'response'")
    client_mac: str = Field(..., description="MAC del cliente involucrado")
    ap_bssid: str = Field(..., description="BSSID del AP involucrado")
    status_code: Optional[int] = Field(None, description="Código de estado BTM (solo para responses)")
    band: Optional[str] = Field(None, description="Banda de frecuencia (2.4GHz/5GHz)")
    frequency: Optional[int] = Field(None, description="Frecuencia en MHz")
    # Campos adicionales para contexto
    frame_number: Optional[int] = Field(None, description="Número de frame en Wireshark")


class SteeringTransition(BaseModel):
    """
    Representa una transición de roaming/steering completa.
    """
    client_mac: str = Field(..., description="MAC del cliente")
    steering_type: SteeringType = Field(default=SteeringType.UNKNOWN, description="Tipo de mecanismo de steering usado")
    
    # Tiempos
    start_time: float = Field(..., description="Inicio de la transición (ej. primer BTM Request o Deauth)")
    end_time: Optional[float] = Field(None, description="Fin de la transición (ej. Reassociation Complete)")
    duration: Optional[float] = Field(None, description="Duración en segundos")
    
    # Origen y Destino
    from_bssid: Optional[str] = Field(None, description="BSSID de origen")
    to_bssid: Optional[str] = Field(None, description="BSSID de destino")
    from_band: Optional[str] = Field(None, description="Banda de origen")
    to_band: Optional[str] = Field(None, description="Banda de destino")
    
    # Estado de la transición
    is_successful: bool = Field(..., description="¿La transición se completó exitosamente?")
    is_band_change: bool = Field(False, description="¿Hubo cambio de banda (ej. 2.4 -> 5)?")
    returned_to_original: bool = Field(False, description="¿El cliente volvió al AP original (ping-pong)?")
    
    # Detalles técnicos
    btm_status_code: Optional[int] = Field(None, description="Código BTM asociado si aplica")
    failure_reason: Optional[str] = Field(None, description="Razón del fallo si no fue exitosa")


class KVRSupport(BaseModel):
    """Evaluación de soporte de estándares 802.11k/v/r."""
    k_support: bool = Field(False, description="Soporte 802.11k (Radio Measurement)")
    v_support: bool = Field(False, description="Soporte 802.11v (BTM/WNM)")
    r_support: bool = Field(False, description="Soporte 802.11r (Fast Transition)")
    compliance_score: float = Field(0.0, ge=0.0, le=1.0, description="Score de cumplimiento de estándares (0-1)")


class ComplianceCheck(BaseModel):
    """
    Un chequeo individual de cumplimiento (ej. 'Soporte BTM', 'Sin Bucles').
    Usado para generar la tabla de resumen.
    """
    check_name: str = Field(..., description="Nombre corto de la verificación")
    description: str = Field(..., description="Descripción detallada")
    category: str = Field(..., description="Categoría: 'btm', 'kvr', 'association', 'performance'")
    passed: bool = Field(..., description="¿Pasó la prueba?")
    severity: str = Field(..., description="Severidad: 'low', 'medium', 'high', 'critical'")
    score: float = Field(..., ge=0.0, le=1.0, description="Puntuación (0-1)")
    details: Optional[str] = Field(None, description="Detalles técnicos (ej. 'Requests: 5, Resp: 0')")
    recommendation: Optional[str] = Field(None, description="Acción sugerida si falló")


class CaptureFragment(BaseModel):
    """
    Metadatos de un fragmento de captura extraído (ej. el pcap del roaming).
    """
    fragment_id: str = Field(..., description="Identificador único del fragmento")
    fragment_type: str = Field(..., description="Tipo: 'btm_sequence', 'transition', 'channel_change'")
    description: str = Field(..., description="Descripción humana del fragmento")
    start_time: float = Field(..., description="Timestamp inicio")
    end_time: float = Field(..., description="Timestamp fin")
    packet_count: int = Field(0, description="Cantidad de paquetes en el fragmento")
    file_path: Optional[str] = Field(None, description="Ruta absoluta al archivo generado")
    download_url: Optional[str] = Field(None, description="URL relativa para descarga")


# ============================================================================
# Modelo Principal de Análisis
# ============================================================================

class BandSteeringAnalysis(BaseModel):
    """
    Objeto raiz que contiene TODO el resultado del análisis de una captura.
    """
    analysis_id: str = Field(..., description="UUID del análisis")
    filename: str = Field(..., description="Nombre del archivo pcap original")
    analysis_timestamp: datetime = Field(default_factory=datetime.now, description="Fecha de análisis")
    
    # Métricas Globales
    total_packets: int = Field(0, description="Total paquetes analizados")
    wlan_packets: int = Field(0, description="Total paquetes WiFi")
    analysis_duration_ms: int = Field(0, description="Tiempo que tomó el análisis (ms)")
    
    # Dispositivos Identificados
    devices: List[DeviceInfo] = Field(default_factory=list, description="Lista de dispositivos únicos analizados")
    
    # Eventos y Transiciones
    btm_events: List[BTMEvent] = Field(default_factory=list, description="Lista plana de eventos BTM")
    transitions: List[SteeringTransition] = Field(default_factory=list, description="Lista de transiciones detectadas")
    
    # Métricas Agregadas
    btm_requests: int = Field(0, description="Total Requests")
    btm_responses: int = Field(0, description="Total Responses")
    btm_success_rate: float = Field(0.0, ge=0.0, le=1.0, description="Tasa de éxito (Responses 0/1 sobre Total)")
    
    successful_transitions: int = Field(0, description="Total transiciones exitosas")
    failed_transitions: int = Field(0, description="Total transiciones fallidas")
    
    loops_detected: bool = Field(False, description="¿Se detectó ping-pong entre bandas?")
    
    # Cumplimiento y Soporte
    kvr_support: KVRSupport = Field(default_factory=KVRSupport, description="Resumen de soporte KVR")
    compliance_checks: List[ComplianceCheck] = Field(default_factory=list, description="Lista de chequeos para tabla de resumen")
    overall_compliance_score: float = Field(0.0, ge=0.0, le=1.0, description="Score global (0-1)")
    
    # Resultado Final
    verdict: str = Field(..., description="Veredicto final: 'SUCCESS', 'PARTIAL', 'FAILED', 'NO_DATA'")
    analysis_text: Optional[str] = Field(None, description="Informe narrativo generado por la IA")
    
    # Fragmentos
    fragments: List[CaptureFragment] = Field(default_factory=list, description="Fragmentos de pcap extraídos")

    class Config:
        use_enum_values = True
