"""
Centralized validator for Deauthentication and Disassociation frames.
Ensures that only deauths specifically directed to the client are counted as forced steering.

This module is critical for:
1. Avoiding counting broadcast deauths as steering
2. Distinguishing between forced exile vs. normal departures (inactivity, client-initiated)
3. Unifying logic between wireshark_tool.py and btm_analyzer.py
"""
from typing import Dict, Tuple

# IEEE 802.11 reason codes indicating GRACEFUL departure (normal/voluntary)
GRACEFUL_DEAUTH_REASONS = {
    3: "STA is leaving (client-initiated)",
    4: "Disassociated due to inactivity",
    8: "Deauthenticated because of inactivity",
    32: "Disassociated due to inactivity",
}

# Reason codes indicating FORCED exile from AP (trigger for steering)
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
    Validates if a Deauthentication or Disassociation frame is directed to a specific client
    and classifies the type of exile (forced vs graceful).
    """

    @staticmethod
    def normalize_mac(mac: str) -> str:
        """Normalizes MAC address to lowercase format without strict validation."""
        if not mac:
            return ""
        return mac.strip().lower()

    @staticmethod
    def is_broadcast(da: str) -> bool:
        """
        Returns True if the destination address is broadcast or multicast.
        
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
        Validates if a deauth/disassoc frame involves the specific client.
        
        Criteria:
        1. DA (Destination) == client_mac (the client receives the deauth from the AP) OR
        2. SA (Source) == client_mac (the client sends the deauth to the AP)
        3. Not broadcast or multicast
        
        Args:
            deauth_event: Dict with fields "da", "sa", "bssid", etc.
            client_mac: Client MAC to validate (e.g., "11:22:33:44:55:66")
            ap_bssid: AP MAC (optional, for additional validation)
        
        Returns:
            bool: True if the frame involves the client (as receiver or sender)
        """
        da = DeauthValidator.normalize_mac(deauth_event.get("da", ""))
        sa = DeauthValidator.normalize_mac(deauth_event.get("sa", ""))
        client_check = DeauthValidator.normalize_mac(client_mac)
        
        if not client_check:
            return False
        
        # Reject broadcast and multicast
        if da and DeauthValidator.is_broadcast(da):
            return False
        
        # Case 1: AP sends deauth to client (DA == client_mac)
        if da == client_check:
            return True
        
        # Case 2: Client sends deauth to AP (SA == client_mac)
        if sa == client_check:
            return True
        
        return False

    @staticmethod
    def is_forced_deauth(reason_code: int) -> bool:
        """
        Classifies if a reason_code indicates FORCED exile from the AP.
        
        Args:
            reason_code: Reason code (0-65535)
        
        Returns:
            bool: True if it is forced exile, False if it is graceful
        
        Logic:
        - If it is in GRACEFUL_DEAUTH_REASONS → False (normal departure)
        - If it is in FORCED_DEAUTH_REASONS → True (AP exile)
        - If it is outside both lists → True (be conservative and assume forced)
        """
        try:
            code_int = int(reason_code)
        except (ValueError, TypeError):
            # Invalid code, assume forced for safety
            return True
        
        if code_int in GRACEFUL_DEAUTH_REASONS:
            return False
        
        # Any other code: assume forced (better false positive than false negative)
        return True

    @staticmethod
    def classify_deauth_event(
        event: Dict,
        client_mac: str,
        ap_bssid: str = None
    ) -> str:
        """
        Classifies a deauth event into one of several categories.
        
        Args:
            event: Dict with fields "da", "sa", "reason_code", etc.
            client_mac: MAC of the client being analyzed
            ap_bssid: AP MAC (optional)
        
        Returns:
            str: One of:
            - "broadcast": Deauth directed to broadcast/multicast
            - "directed_to_other": Does not involve the client (neither as receiver nor sender)
            - "graceful": Involves the client but with a graceful reason code (voluntary departure)
            - "forced_to_client": AP exiles the client (forced reason code)
            - "unknown": Cannot be classified (missing fields)
        """
        da = event.get("da", "").strip().lower()
        sa = event.get("sa", "").strip().lower()
        
        # Check broadcast first
        if da and DeauthValidator.is_broadcast(da):
            return "broadcast"
        
        if not da and not sa:
            return "unknown"
        
        # Check if it involves the client (as receiver or sender)
        client_norm = DeauthValidator.normalize_mac(client_mac)
        da_norm = DeauthValidator.normalize_mac(da) if da else ""
        sa_norm = DeauthValidator.normalize_mac(sa) if sa else ""
        
        # Check if the client is involved
        client_is_receiver = da_norm == client_norm  # AP → Client
        client_is_sender = sa_norm == client_norm     # Client → AP
        
        if not client_is_receiver and not client_is_sender:
            return "directed_to_other"
        
        # The client is involved, check reason code
        reason_raw = event.get("reason_code", 0)
        try:
            if isinstance(reason_raw, str) and reason_raw.startswith("0x"):
                reason = int(reason_raw, 16)
            else:
                reason = int(reason_raw) if reason_raw else 0
        except (ValueError, TypeError):
            reason = 0
        
        # If the client is the sender (SA == client_mac), it is generally graceful
        # If the AP is the sender (DA == client_mac), check reason code
        if client_is_sender:
            # Client sends deauth: generally graceful (voluntary departure)
            if DeauthValidator.is_forced_deauth(reason):
                # Even if it has a "forced" reason code, if the client sends it, it is voluntary
                return "graceful"
            else:
                return "graceful"
        else:
            # AP sends deauth to client: check if it is forced or graceful
            if DeauthValidator.is_forced_deauth(reason):
                return "forced_to_client"
            else:
                return "graceful"

    @staticmethod
    def get_reason_description(reason_code: int) -> str:
        """Returns textual description of a reason_code."""
        try:
            # Ensure it is int even if it comes as hex string
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
        Validation and classification in one call.
        
        Args:
            event: Deauth event dict
            client_mac: Client MAC
            ap_bssid: AP MAC (optional)
        
        Returns:
            Tuple[is_forced, classification, description]
            - is_forced (bool): True if it is forced exile to client
            - classification (str): Category ("broadcast", "graceful", "forced_to_client", etc)
            - description (str): Textual description for logging
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


# Configuration
REASSOC_TIMEOUT_SECONDS = 15.0  # Time window to search for reassoc after deauth
