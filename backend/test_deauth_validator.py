"""
Tests unitarios para el validador de Deauthentication.
Valida que la lógica de clasificación de deauth sea correcta en todos los casos edge.
"""
import pytest
from backend.src.utils.deauth_validator import (
    DeauthValidator,
    GRACEFUL_DEAUTH_REASONS,
    FORCED_DEAUTH_REASONS,
)


class TestDeauthValidatorBasics:
    """Tests de funcionalidad básica del validador."""

    def test_normalize_mac(self):
        """Test de normalización de MAC addresses."""
        assert DeauthValidator.normalize_mac("AA:BB:CC:DD:EE:FF") == "aa:bb:cc:dd:ee:ff"
        assert DeauthValidator.normalize_mac("  11:22:33:44:55:66  ") == "11:22:33:44:55:66"
        assert DeauthValidator.normalize_mac("") == ""
        assert DeauthValidator.normalize_mac(None) == ""

    def test_is_broadcast(self):
        """Test de detección de broadcast y multicast."""
        # Broadcast
        assert DeauthValidator.is_broadcast("ff:ff:ff:ff:ff:ff") is True
        assert DeauthValidator.is_broadcast("FF:FF:FF:FF:FF:FF") is True
        
        # IPv4 Multicast
        assert DeauthValidator.is_broadcast("01:00:5e:00:00:01") is True
        assert DeauthValidator.is_broadcast("01:00:5e:7f:ff:fa") is True
        
        # IPv6 Multicast
        assert DeauthValidator.is_broadcast("33:33:00:00:00:01") is True
        assert DeauthValidator.is_broadcast("33:33:ff:12:34:56") is True
        
        # Unicast (no broadcast)
        assert DeauthValidator.is_broadcast("aa:bb:cc:dd:ee:ff") is False
        assert DeauthValidator.is_broadcast("11:22:33:44:55:66") is False
        assert DeauthValidator.is_broadcast("") is False


class TestIsDirectedToClient:
    """Tests para validación de direccionamiento de deauth."""

    def test_deauth_broadcast_ignored(self):
        """Deauth broadcast debe ser ignorado."""
        event = {
            "da": "ff:ff:ff:ff:ff:ff",
            "sa": "aa:bb:cc:dd:ee:ff",
            "reason_code": 1,
        }
        client_mac = "11:22:33:44:55:66"
        
        assert DeauthValidator.is_directed_to_client(event, client_mac) is False

    def test_deauth_multicast_ipv4_ignored(self):
        """Deauth multicast IPv4 debe ser ignorado."""
        event = {
            "da": "01:00:5e:00:00:01",
            "sa": "aa:bb:cc:dd:ee:ff",
        }
        client_mac = "11:22:33:44:55:66"
        
        assert DeauthValidator.is_directed_to_client(event, client_mac) is False

    def test_deauth_to_specific_client(self):
        """Deauth dirigido específicamente al cliente debe ser detectado."""
        event = {
            "da": "11:22:33:44:55:66",
            "sa": "aa:bb:cc:dd:ee:ff",
            "reason_code": 1,
        }
        client_mac = "11:22:33:44:55:66"
        
        assert DeauthValidator.is_directed_to_client(event, client_mac) is True

    def test_deauth_to_other_client_ignored(self):
        """Deauth dirigido a otro cliente debe ser ignorado."""
        event = {
            "da": "99:99:99:99:99:99",
            "sa": "aa:bb:cc:dd:ee:ff",
        }
        client_mac = "11:22:33:44:55:66"
        
        assert DeauthValidator.is_directed_to_client(event, client_mac) is False

    def test_case_insensitive_comparison(self):
        """Comparación debe ser case-insensitive."""
        event = {
            "da": "AA:BB:CC:DD:EE:FF",
            "sa": "11:22:33:44:55:66",
        }
        client_mac = "aa:bb:cc:dd:ee:ff"
        
        assert DeauthValidator.is_directed_to_client(event, client_mac) is True


class TestIsForcedDeauth:
    """Tests para clasificación de reason codes."""

    def test_graceful_reason_codes(self):
        """Códigos graceful deben retornar False."""
        for code in GRACEFUL_DEAUTH_REASONS.keys():
            assert DeauthValidator.is_forced_deauth(code) is False, f"Code {code} debería ser graceful"

    def test_forced_reason_codes(self):
        """Códigos forced deben retornar True."""
        for code in FORCED_DEAUTH_REASONS.keys():
            assert DeauthValidator.is_forced_deauth(code) is True, f"Code {code} debería ser forced"

    def test_unknown_reason_code_assumed_forced(self):
        """Códigos desconocidos deben asumir forced (conservador)."""
        assert DeauthValidator.is_forced_deauth(99) is True
        assert DeauthValidator.is_forced_deauth(255) is True

    def test_specific_graceful_codes(self):
        """Test específico de códigos graceful conocidos."""
        assert DeauthValidator.is_forced_deauth(3) is False  # Client leaving
        assert DeauthValidator.is_forced_deauth(8) is False   # Inactivity
        assert DeauthValidator.is_forced_deauth(32) is False  # Disassoc inactivity

    def test_specific_forced_codes(self):
        """Test específico de códigos forced conocidos."""
        assert DeauthValidator.is_forced_deauth(1) is True   # Unspecified
        assert DeauthValidator.is_forced_deauth(2) is True   # Previous auth invalid
        assert DeauthValidator.is_forced_deauth(5) is True   # Unable to handle STAs
        assert DeauthValidator.is_forced_deauth(15) is True  # 4-way timeout

    def test_invalid_reason_code(self):
        """Códigos inválidos deben asumir forced."""
        assert DeauthValidator.is_forced_deauth("invalid") is True
        assert DeauthValidator.is_forced_deauth(None) is True


class TestClassifyDeauthEvent:
    """Tests para clasificación completa de eventos deauth."""

    def test_broadcast_classification(self):
        """Evento deauth broadcast."""
        event = {
            "da": "ff:ff:ff:ff:ff:ff",
            "sa": "aa:bb:cc:dd:ee:ff",
            "reason_code": 1,
        }
        classification = DeauthValidator.classify_deauth_event(event, "11:22:33:44:55:66")
        assert classification == "broadcast"

    def test_directed_to_other_client(self):
        """Evento dirigido a otro cliente."""
        event = {
            "da": "99:99:99:99:99:99",
            "sa": "aa:bb:cc:dd:ee:ff",
            "reason_code": 1,
        }
        classification = DeauthValidator.classify_deauth_event(event, "11:22:33:44:55:66")
        assert classification == "directed_to_other"

    def test_graceful_to_client(self):
        """Evento graceful dirigido al cliente."""
        event = {
            "da": "11:22:33:44:55:66",
            "sa": "aa:bb:cc:dd:ee:ff",
            "reason_code": 3,  # Client leaving
        }
        classification = DeauthValidator.classify_deauth_event(event, "11:22:33:44:55:66")
        assert classification == "graceful"

    def test_forced_to_client(self):
        """Evento forced dirigido al cliente."""
        event = {
            "da": "11:22:33:44:55:66",
            "sa": "aa:bb:cc:dd:ee:ff",
            "reason_code": 1,  # Unspecified (forced)
        }
        classification = DeauthValidator.classify_deauth_event(event, "11:22:33:44:55:66")
        assert classification == "forced_to_client"

    def test_unknown_classification(self):
        """Evento sin campos necesarios."""
        event = {}
        classification = DeauthValidator.classify_deauth_event(event, "11:22:33:44:55:66")
        assert classification == "unknown"

    def test_inactivity_reason_graceful(self):
        """Reason code 8 (inactividad) debe ser graceful."""
        event = {
            "da": "11:22:33:44:55:66",
            "sa": "aa:bb:cc:dd:ee:ff",
            "reason_code": 8,
        }
        classification = DeauthValidator.classify_deauth_event(event, "11:22:33:44:55:66")
        assert classification == "graceful"

    def test_poor_channel_conditions_forced(self):
        """Reason code 34 (poor channel) debe ser forced."""
        event = {
            "da": "11:22:33:44:55:66",
            "sa": "aa:bb:cc:dd:ee:ff",
            "reason_code": 34,
        }
        classification = DeauthValidator.classify_deauth_event(event, "11:22:33:44:55:66")
        assert classification == "forced_to_client"


class TestRealWorldScenarios:
    """Tests con escenarios realistas de capturas."""

    def test_steering_aggressive_with_valid_deauth(self):
        """Scenario: Steering agresivo con deauth válido dirigido al cliente."""
        # AP destierro del cliente de 2.4GHz → cliente se reassocia en 5GHz
        deauth_event = {
            "da": "11:22:33:44:55:66",  # Cliente específico
            "sa": "aa:bb:cc:dd:ee:ff",  # AP
            "reason_code": 5,           # AP unable to handle
            "timestamp": 100.0,
            "bssid": "aa:bb:cc:dd:ee:ff",
            "band": "2.4GHz",
        }
        client_mac = "11:22:33:44:55:66"
        
        is_directed = DeauthValidator.is_directed_to_client(deauth_event, client_mac)
        classification = DeauthValidator.classify_deauth_event(deauth_event, client_mac)
        
        assert is_directed is True
        assert classification == "forced_to_client"

    def test_steering_broadcast_false_positive(self):
        """Scenario: Deauth broadcast seguido de reassoc (FALSO POSITIVO)."""
        # AP envía deauth broadcast (reload, cambio config, etc)
        # Luego un cliente se reassocia → NO debe contarse como steering
        deauth_event = {
            "da": "ff:ff:ff:ff:ff:ff",  # Broadcast
            "sa": "aa:bb:cc:dd:ee:ff",  # AP
            "reason_code": 1,
        }
        client_mac = "11:22:33:44:55:66"
        
        is_directed = DeauthValidator.is_directed_to_client(deauth_event, client_mac)
        assert is_directed is False  # NO debe contar

    def test_client_initiated_leave(self):
        """Scenario: Cliente se va voluntariamente (disconnected)."""
        # Cliente inicia disconnection
        deauth_event = {
            "da": "aa:bb:cc:dd:ee:ff",  # Dirigido al AP (SA del cliente)
            "sa": "11:22:33:44:55:66",  # Cliente
            "reason_code": 3,           # STA leaving
        }
        client_mac = "11:22:33:44:55:66"
        
        # NO está dirigido AL cliente (está dirigido al AP)
        is_directed = DeauthValidator.is_directed_to_client(deauth_event, client_mac)
        assert is_directed is False

    def test_inactivity_timeout_no_steering(self):
        """Scenario: Cliente desconectado por inactividad, no es steering."""
        deauth_event = {
            "da": "11:22:33:44:55:66",
            "sa": "aa:bb:cc:dd:ee:ff",
            "reason_code": 8,  # Inactivity timeout
        }
        client_mac = "11:22:33:44:55:66"
        
        classification = DeauthValidator.classify_deauth_event(deauth_event, client_mac)
        assert classification == "graceful"


class TestValidateAndClassify:
    """Tests para la función todo-en-uno."""

    def test_complete_validation_forced_deauth(self):
        """Test completo de validación para deauth forzado."""
        event = {
            "da": "11:22:33:44:55:66",
            "sa": "aa:bb:cc:dd:ee:ff",
            "reason_code": 1,
        }
        
        is_forced, classification, description = DeauthValidator.validate_and_classify(
            event, "11:22:33:44:55:66"
        )
        
        assert is_forced is True
        assert classification == "forced_to_client"
        assert "forced_to_client" in description
        assert "reason=1" in description

    def test_complete_validation_graceful(self):
        """Test completo de validación para deauth graceful."""
        event = {
            "da": "11:22:33:44:55:66",
            "sa": "aa:bb:cc:dd:ee:ff",
            "reason_code": 8,
        }
        
        is_forced, classification, description = DeauthValidator.validate_and_classify(
            event, "11:22:33:44:55:66"
        )
        
        assert is_forced is False
        assert classification == "graceful"
        assert "graceful" in description

    def test_complete_validation_broadcast(self):
        """Test completo de validación para broadcast."""
        event = {
            "da": "ff:ff:ff:ff:ff:ff",
            "sa": "aa:bb:cc:dd:ee:ff",
            "reason_code": 1,
        }
        
        is_forced, classification, description = DeauthValidator.validate_and_classify(
            event, "11:22:33:44:55:66"
        )
        
        assert is_forced is False
        assert classification == "broadcast"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
