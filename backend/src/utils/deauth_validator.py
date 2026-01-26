"""
Validador centralizado para frames Deauthentication y Disassociation.
Asegura que solo se cuenten como steering forzado los deauth dirigidos específicamente al cliente.

Este módulo es crítico para:
1. Evitar contar deauth broadcast como steering
2. Distinguir entre destierro forzado vs salidas normales (inactividad, client-initiated)
3. Unificar la lógica entre wireshark_tool.py y btm_analyzer.py
"""
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)

# Reason codes IEEE 802.11 que indican salida GRACEFUL (no forzada)
GRACEFUL_DEAUTH_REASONS = {
    3: "STA is leaving (client-initiated)",
    8: "Deauthenticated because of inactivity",
    32: "Disassociated due to inactivity",
    33: "Unable to handle another STA",
    34: "Class 2 frame received from nonauthenticated STA",
    35: "Class 3 frame received from nonassociated STA",
}

# Reason codes que indican destierro FORZADO del AP
FORCED_DEAUTH_REASONS = {
    1: "Unspecified reason (likely AP-initiated)",
    2: "Previous authentication no longer valid",
    5: "Disassociated because AP unable to handle all currently associated STAs",
    7: "Class 2 frame received from an unauthenticated STA",
    15: "4-Way Handshake timeout",
    16: "Group Key Handshake timeout",
    17: "IE in 4-Way Handshake differs from (Re)Association Request/Probe Response/Beacon",
    24: "Invalid PMKID",
    25: "Invalid MDE",
    26: "Invalid FTE",
    34: "Disassociated due to poor channel conditions",
}


class DeauthValidator:
    """
    Valida si un frame Deauthentication o Disassociation está dirigido a un cliente específico
    y clasifica el tipo de destierro (forzado vs graceful).
    """

    @staticmethod
    def normalize_mac(mac: str) -> str:
        """Normaliza dirección MAC a formato lowercase sin validación estricta."""
        if not mac:
            return ""
        return mac.strip().lower()

    @staticmethod
    def is_broadcast(da: str) -> bool:
        """
        Retorna True si la dirección de destino es broadcast o multicast.
        
        - Broadcast: ff:ff:ff:ff:ff:ff
        - Multicast IPv4: 01:00:5e:xx:xx:xx
        - Multicast IPv6: 33:33:xx:xx:xx:xx
        """
        da_norm = DeauthValidator.normalize_mac(da)
        return (
            da_norm == "ff:ff:ff:ff:ff:ff"
            or da_norm.startswith("01:00:5e")
            or da_norm.startswith("33:33")
        )

    @staticmethod
    def is_directed_to_client(
        deauth_event: Dict,
        client_mac: str,
        ap_bssid: str = None
    ) -> bool:
        """
        Valida si un deauth/disassoc frame está dirigido AL cliente específico.
        
        Criterios:
        1. DA (Destination) == client_mac (el cliente recibe el deauth)
        2. No es broadcast o multicast
        3. Opcionalmente: SA (Source) debe ser coherente con un AP
        
        Args:
            deauth_event: Dict con campos "da", "sa", "bssid", etc.
            client_mac: MAC del cliente a validar (ej: "11:22:33:44:55:66")
            ap_bssid: MAC del AP (opcional, para validación adicional)
        
        Returns:
            bool: True si está dirigido al cliente específico
        """
        da = DeauthValidator.normalize_mac(deauth_event.get("da", ""))
        sa = DeauthValidator.normalize_mac(deauth_event.get("sa", ""))
        client_check = DeauthValidator.normalize_mac(client_mac)
        
        if not da or not client_check:
            return False
        
        # Rechazar broadcast y multicast
        if DeauthValidator.is_broadcast(da):
            logger.debug(f"Deauth broadcast detectado (DA={da}), ignorado")
            return False
        
        # Debe estar dirigido específicamente al cliente
        if da != client_check:
            logger.debug(f"Deauth dirigido a {da}, no al cliente {client_check}")
            return False
        
        return True

    @staticmethod
    def is_forced_deauth(reason_code: int) -> bool:
        """
        Clasifica si un reason_code indica destierro FORZADO del AP.
        
        Args:
            reason_code: Código de razón (0-65535)
        
        Returns:
            bool: True si es destierro forzado, False si es graceful
        
        Lógica:
        - Si está en GRACEFUL_DEAUTH_REASONS → False (salida normal)
        - Si está en FORCED_DEAUTH_REASONS → True (destierro AP)
        - Si está fuera de ambas listas → True (ser conservador y asumir forzado)
        """
        try:
            code_int = int(reason_code)
        except (ValueError, TypeError):
            # Código inválido, asumir forzado por seguridad
            logger.warning(f"Reason code inválido: {reason_code}, asumiendo forzado")
            return True
        
        if code_int in GRACEFUL_DEAUTH_REASONS:
            return False
        
        # Cualquier otro código: asumir forzado (mejor falso positivo que falso negativo)
        return True

    @staticmethod
    def classify_deauth_event(
        event: Dict,
        client_mac: str,
        ap_bssid: str = None
    ) -> str:
        """
        Clasifica un evento deauth en una de varias categorías.
        
        Args:
            event: Dict con campos "da", "sa", "reason_code", etc.
            client_mac: MAC del cliente siendo analizado
            ap_bssid: MAC del AP (opcional)
        
        Returns:
            str: Una de:
            - "broadcast": Deauth dirigido a broadcast/multicast
            - "directed_to_other": Dirigido a otro cliente (no al nuestro)
            - "graceful": Dirigido al cliente pero con reason code graceful
            - "forced_to_client": Dirigido al cliente con destierro forzado
            - "unknown": No se puede clasificar (campos faltantes)
        """
        da = event.get("da", "").strip().lower()
        
        # Verificar broadcast primero
        if not da:
            return "unknown"
        
        if DeauthValidator.is_broadcast(da):
            return "broadcast"
        
        # Verificar si está dirigido al cliente
        client_norm = DeauthValidator.normalize_mac(client_mac)
        da_norm = DeauthValidator.normalize_mac(da)
        
        if da_norm != client_norm:
            return "directed_to_other"
        
        # Está dirigido al cliente, verificar reason code
        reason = int(event.get("reason_code", 0)) if event.get("reason_code") else 0
        
        if DeauthValidator.is_forced_deauth(reason):
            return "forced_to_client"
        else:
            return "graceful"

    @staticmethod
    def get_reason_description(reason_code: int) -> str:
        """Retorna descripción textual de un reason_code."""
        try:
            code_int = int(reason_code)
        except (ValueError, TypeError):
            return f"Unknown reason code: {reason_code}"
        
        if code_int in GRACEFUL_DEAUTH_REASONS:
            return GRACEFUL_DEAUTH_REASONS[code_int]
        
        if code_int in FORCED_DEAUTH_REASONS:
            return FORCED_DEAUTH_REASONS[code_int]
        
        return f"Reserved/Unknown (0x{code_int:04x})"

    @staticmethod
    def validate_and_classify(
        event: Dict,
        client_mac: str,
        ap_bssid: str = None
    ) -> Tuple[bool, str, str]:
        """
        Validación y clasificación en una llamada.
        
        Args:
            event: Dict del evento deauth
            client_mac: MAC del cliente
            ap_bssid: MAC del AP (opcional)
        
        Returns:
            Tuple[is_forced, classification, description]
            - is_forced (bool): True si es destierro forzado al cliente
            - classification (str): Categoría ("broadcast", "graceful", "forced_to_client", etc)
            - description (str): Descripción textual para logging
        """
        classification = DeauthValidator.classify_deauth_event(event, client_mac, ap_bssid)
        is_forced = classification == "forced_to_client"
        
        reason_code = int(event.get("reason_code", 0)) if event.get("reason_code") else 0
        reason_desc = DeauthValidator.get_reason_description(reason_code)
        
        da = event.get("da", "").strip().lower() if event.get("da") else "unknown"
        sa = event.get("sa", "").strip().lower() if event.get("sa") else "unknown"
        
        description = f"{classification} (DA={da}, reason={reason_code}: {reason_desc})"
        
        return is_forced, classification, description


# Configuración
REASSOC_TIMEOUT_SECONDS = 15.0  # Ventana temporal para buscar reassoc después de deauth
