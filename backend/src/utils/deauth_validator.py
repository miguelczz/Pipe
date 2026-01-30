"""
Validador centralizado para frames Deauthentication y Disassociation.
Asegura que solo se cuenten como steering forzado los deauth dirigidos específicamente al cliente.

Este módulo es crítico para:
    pass
1. Evitar contar deauth broadcast como steering
2. Distinguir entre destierro forzado vs salidas normales (inactividad, client-initiated)
3. Unificar la lógica entre wireshark_tool.py y btm_analyzer.py
"""
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)

# Reason codes IEEE 802.11 que indican salida GRACEFUL (normal/voluntaria)
GRACEFUL_DEAUTH_REASONS = {
    3: "STA is leaving (client-initiated)",
    4: "Disassociated due to inactivity",
    8: "Deauthenticated because of inactivity",
    32: "Disassociated due to inactivity",
}

# Reason codes que indican destierro FORZADO del AP (trigger para steering)
FORCED_DEAUTH_REASONS = {
    1: "Unspecified reason (likely AP-initiated)",
    2: "Previous authentication no longer valid",
    5: "AP unable to handle all currently associated STAs (AP full)",
    6: "Class 2 frame received from nonauthenticated STA",
    7: "Class 3 frame received from nonassociated STA",
    15: "4-Way Handshake timeout",
    16: "Group Key Handshake timeout",
    17: "IE in 4-Way Handshake differs",
    24: "Invalid PMKID",
    25: "Invalid MDE",
    26: "Invalid FTE",
    33: "Disassociated due to lack of QoS resources",
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
        Valida si un deauth/disassoc frame involucra al cliente específico.
        
        Criterios:
            pass
        1. DA (Destination) == client_mac (el cliente recibe el deauth del AP) O
        2. SA (Source) == client_mac (el cliente envía el deauth al AP)
        3. No es broadcast o multicast
        
        Args:
            deauth_event: Dict con campos "da", "sa", "bssid", etc.
            client_mac: MAC del cliente a validar (ej: "11:22:33:44:55:66")
            ap_bssid: MAC del AP (opcional, para validación adicional)
        
        Returns:
            bool: True si el frame involucra al cliente (como receptor o emisor)
        """
        da = DeauthValidator.normalize_mac(deauth_event.get("da", ""))
        sa = DeauthValidator.normalize_mac(deauth_event.get("sa", ""))
        client_check = DeauthValidator.normalize_mac(client_mac)
        
        if not client_check:
            return False
        
        # Rechazar broadcast y multicast
        if da and DeauthValidator.is_broadcast(da):
            return False
        
        # Caso 1: AP envía deauth al cliente (DA == client_mac)
        if da == client_check:
            return True
        
        # Caso 2: Cliente envía deauth al AP (SA == client_mac)
        if sa == client_check:
            return True
        
        return False

    @staticmethod
    def is_forced_deauth(reason_code: int) -> bool:
        """
        Clasifica si un reason_code indica destierro FORZADO del AP.
        
        Args:
            reason_code: Código de razón (0-65535)
        
        Returns:
            bool: True si es destierro forzado, False si es graceful
        
        Lógica:
            pass
        - Si está en GRACEFUL_DEAUTH_REASONS → False (salida normal)
        - Si está en FORCED_DEAUTH_REASONS → True (destierro AP)
        - Si está fuera de ambas listas → True (ser conservador y asumir forzado)
        """
        try:
            code_int = int(reason_code)
        except (ValueError, TypeError):
            # Código inválido, asumir forzado por seguridad
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
                pass
            - "broadcast": Deauth dirigido a broadcast/multicast
            - "directed_to_other": No involucra al cliente (ni como receptor ni emisor)
            - "graceful": Involucra al cliente pero con reason code graceful (salida voluntaria)
            - "forced_to_client": AP destierra al cliente (reason code forzado)
            - "unknown": No se puede clasificar (campos faltantes)
        """
        da = event.get("da", "").strip().lower()
        sa = event.get("sa", "").strip().lower()
        
        # Verificar broadcast primero
        if da and DeauthValidator.is_broadcast(da):
            return "broadcast"
        
        if not da and not sa:
            return "unknown"
        
        # Verificar si involucra al cliente (como receptor o emisor)
        client_norm = DeauthValidator.normalize_mac(client_mac)
        da_norm = DeauthValidator.normalize_mac(da) if da else ""
        sa_norm = DeauthValidator.normalize_mac(sa) if sa else ""
        
        # Verificar si el cliente está involucrado
        client_is_receiver = da_norm == client_norm  # AP → Cliente
        client_is_sender = sa_norm == client_norm     # Cliente → AP
        
        if not client_is_receiver and not client_is_sender:
            return "directed_to_other"
        
        # El cliente está involucrado, verificar reason code
        reason_raw = event.get("reason_code", 0)
        try:
            if isinstance(reason_raw, str) and reason_raw.startswith("0x"):
                reason = int(reason_raw, 16)
            else:
                reason = int(reason_raw) if reason_raw else 0
        except (ValueError, TypeError):
            reason = 0
        
        # Si el cliente es el emisor (SA == client_mac), generalmente es graceful
        # Si el AP es el emisor (DA == client_mac), verificar reason code
        if client_is_sender:
            # Cliente envía deauth: generalmente es graceful (salida voluntaria)
            if DeauthValidator.is_forced_deauth(reason):
                # Aunque tenga reason code "forzado", si el cliente lo envía, es voluntario
                return "graceful"
            else:
                return "graceful"
        else:
            # AP envía deauth al cliente: verificar si es forzado o graceful
            if DeauthValidator.is_forced_deauth(reason):
                return "forced_to_client"
            else:
                return "graceful"

    @staticmethod
    def get_reason_description(reason_code: int) -> str:
        """Retorna descripción textual de un reason_code."""
        try:
            # Asegurar que sea int incluso si viene como hex string
            if isinstance(reason_code, str) and reason_code.startswith("0x"):
                code_int = int(reason_code, 16)
            else:
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
        
        reason_raw = event.get("reason_code", 0)
        try:
            if isinstance(reason_raw, str) and reason_raw.startswith("0x"):
                reason_code = int(reason_raw, 16)
            else:
                reason_code = int(reason_raw) if reason_raw else 0
        except (ValueError, TypeError):
            reason_code = 0
            
        reason_desc = DeauthValidator.get_reason_description(reason_code)
        
        da = event.get("da", "").strip().lower() if event.get("da") else "unknown"
        sa = event.get("sa", "").strip().lower() if event.get("sa") else "unknown"
        
        description = f"{classification} (DA={da}, reason={reason_code}: {reason_desc})"
        
        return is_forced, classification, description


# Configuración
REASSOC_TIMEOUT_SECONDS = 15.0  # Ventana temporal para buscar reassoc después de deauth
