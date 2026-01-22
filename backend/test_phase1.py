"""
Script de validación para Fase 1 del AIDLC.
Prueba los modelos y componentes básicos creados.
"""
import sys
from pathlib import Path

# Agregar el directorio backend al path
import os
sys.path.insert(0, str(Path(__file__).parent))

# Configurar variables de entorno dummy para evitar errores de validación de Settings
os.environ["OPENAI_API_KEY"] = "sk-dummy"
os.environ["QDRANT_URL"] = "http://localhost:6333"
os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost/db"

from src.models.btm_schemas import (
    BTMStatusCode, 
    SteeringType, 
    DeviceCategory,
    BTMEvent,
    DeviceInfo,
    SteeringTransition,
    ComplianceCheck,
    KVRSupport,
    BandSteeringAnalysis
)
from src.utils.oui_lookup import oui_lookup
from src.tools.device_classifier import DeviceClassifier

def test_btm_status_codes():
    """Test 1: Validar clasificación de códigos BTM"""
    print("🧪 Test 1: Códigos BTM...")
    
    # Códigos de éxito
    assert BTMStatusCode.is_success(0) == True, "Code 0 debe ser éxito"
    assert BTMStatusCode.is_success("0") == True, "Code '0' string debe ser éxito"
    assert BTMStatusCode.is_success(1) == True, "Code 1 debe ser éxito"
    
    # Códigos de fallo
    assert BTMStatusCode.is_success(2) == False, "Code 2 debe ser fallo"
    assert BTMStatusCode.is_success(8) == False, "Code 8 debe ser fallo"
    
    # Descripciones
    desc = BTMStatusCode.get_description(0)
    assert "Accept" in desc, "Descripción de code 0 debe contener 'Accept'"
    
    print("   ✅ Códigos BTM funcionan correctamente")

def test_device_info_creation():
    """Test 2: Crear objetos DeviceInfo"""
    print("🧪 Test 2: Creación de DeviceInfo...")
    
    device = DeviceInfo(
        mac_address="aa:bb:cc:dd:ee:ff",
        oui="aa:bb:cc",
        vendor="Apple",
        device_model="iPhone 12",
        device_category=DeviceCategory.MOBILE,
        is_virtual=False,
        confidence_score=0.95
    )
    
    assert device.vendor == "Apple"
    assert device.device_category == DeviceCategory.MOBILE
    assert device.confidence_score == 0.95
    
    print("   ✅ DeviceInfo se crea correctamente")

def test_btm_event_creation():
    """Test 3: Crear eventos BTM"""
    print("🧪 Test 3: Creación de BTMEvent...")
    
    event = BTMEvent(
        timestamp=1234567890.123,
        event_type="request",
        client_mac="aa:bb:cc:dd:ee:ff",
        ap_bssid="11:22:33:44:55:66",
        status_code=None,
        band="5GHz",
        frequency=5180
    )
    
    assert event.event_type == "request"
    assert event.band == "5GHz"
    
    print("   ✅ BTMEvent se crea correctamente")

def test_steering_transition():
    """Test 4: Crear transiciones de steering"""
    print("🧪 Test 4: Creación de SteeringTransition...")
    
    transition = SteeringTransition(
        client_mac="aa:bb:cc:dd:ee:ff",
        steering_type=SteeringType.ASSISTED,
        start_time=1000.0,
        end_time=1002.5,
        duration=2.5,
        from_bssid="11:22:33:44:55:66",
        to_bssid="11:22:33:44:55:77",
        from_band="2.4GHz",
        to_band="5GHz",
        is_successful=True,
        is_band_change=True
    )
    
    assert transition.steering_type == SteeringType.ASSISTED
    assert transition.is_band_change == True
    assert transition.duration == 2.5
    
    print("   ✅ SteeringTransition se crea correctamente")

def test_oui_lookup():
    """Test 5: Lookup de fabricantes"""
    print("🧪 Test 5: OUI Lookup...")
    
    # Apple
    vendor = oui_lookup.lookup_vendor("00:17:f2:aa:bb:cc")
    assert vendor == "Apple", f"Esperaba 'Apple', obtuve '{vendor}'"
    
    # Samsung
    vendor = oui_lookup.lookup_vendor("00:02:78:11:22:33")
    assert vendor == "Samsung", f"Esperaba 'Samsung', obtuve '{vendor}'"
    
    # Unknown
    vendor = oui_lookup.lookup_vendor("ff:ff:ff:aa:bb:cc")
    assert vendor == "Unknown", f"Esperaba 'Unknown', obtuve '{vendor}'"
    
    print("   ✅ OUI Lookup funciona correctamente")

def test_device_classifier():
    """Test 6: Clasificación de dispositivos"""
    print("🧪 Test 6: Device Classifier...")
    
    classifier = DeviceClassifier()
    
    # Clasificar un dispositivo Apple
    device = classifier.classify_device("00:17:f2:aa:bb:cc")
    assert device.vendor == "Apple"
    assert device.device_category == DeviceCategory.MOBILE
    
    # Clasificar con info manual
    device = classifier.classify_device(
        "aa:bb:cc:dd:ee:ff",
        manual_info={"device_brand": "Samsung", "device_model": "Galaxy S21"}
    )
    assert device.vendor == "Samsung"
    assert device.device_model == "Galaxy S21"
    assert device.confidence_score == 1.0  # Manual = máxima confianza
    
    print("   ✅ Device Classifier funciona correctamente")

def test_compliance_check():
    """Test 7: Checks de cumplimiento"""
    print("🧪 Test 7: Compliance Checks...")
    
    check = ComplianceCheck(
        check_name="Soporte BTM",
        description="Verificar soporte de 802.11v",
        category="btm",
        passed=True,
        severity="high",
        score=1.0,
        details="Requests: 5, Responses: 4"
    )
    
    assert check.passed == True
    assert check.score == 1.0
    assert check.severity == "high"
    
    print("   ✅ ComplianceCheck funciona correctamente")

def test_band_steering_analysis():
    """Test 8: Análisis completo (estructura)"""
    print("🧪 Test 8: BandSteeringAnalysis...")
    
    analysis = BandSteeringAnalysis(
        analysis_id="test-001",
        filename="test.pcap",
        total_packets=1000,
        wlan_packets=500,
        analysis_duration_ms=1500,
        btm_requests=5,
        btm_responses=4,
        btm_success_rate=0.8,
        successful_transitions=3,
        failed_transitions=1,
        verdict="SUCCESS"
    )
    
    assert analysis.verdict == "SUCCESS"
    assert analysis.btm_success_rate == 0.8
    assert len(analysis.devices) == 0  # Lista vacía por defecto
    
    print("   ✅ BandSteeringAnalysis se crea correctamente")

def main():
    """Ejecutar todos los tests"""
    print("\n" + "="*60)
    print("🚀 VALIDACIÓN FASE 1 - AIDLC Band Steering")
    print("="*60 + "\n")
    
    try:
        test_btm_status_codes()
        test_device_info_creation()
        test_btm_event_creation()
        test_steering_transition()
        test_oui_lookup()
        test_device_classifier()
        test_compliance_check()
        test_band_steering_analysis()
        
        print("\n" + "="*60)
        print("✅ TODOS LOS TESTS PASARON EXITOSAMENTE")
        print("="*60 + "\n")
        print("📋 Resumen:")
        print("   - Modelos Pydantic: ✅ Funcionando")
        print("   - OUI Lookup: ✅ Funcionando")
        print("   - Device Classifier: ✅ Funcionando")
        print("   - Lógica de negocio: ✅ Validada")
        print("\n🎯 Fase 1 completada. Listo para Fase 2 (Integración).\n")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ ERROR: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
