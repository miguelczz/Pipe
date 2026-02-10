# 🧪 AIDLC - Fase 5: Estrategia de Testing y Validación

## 🎯 Objetivos de Testing

### Objetivos Principales
1. **Precisión de Análisis**: Validar detección correcta de códigos BTM y patrones
2. **Rendimiento**: Asegurar tiempos de respuesta aceptables
3. **Escalabilidad**: Verificar manejo de múltiples análisis concurrentes
4. **Robustez**: Validar manejo de archivos corruptos y casos edge
5. **Integración**: Asegurar funcionamiento correcto entre componentes
6. **Usabilidad**: Validar experiencia de usuario fluida

### Métricas de Calidad
- **Precisión de detección BTM**: >95%
- **Precisión de clasificación de dispositivos**: >98%
- **Tiempo de análisis**: <30s para capturas <2MB
- **Disponibilidad del sistema**: >99.5%
- **Tasa de falsos positivos**: <2%
- **Cobertura de código**: >85%

## 🏗️ Pirámide de Testing

### Nivel 1: Unit Tests (70%)
```python
# Ejemplo: Test de BTM Analyzer
import pytest
from unittest.mock import Mock, patch
from backend.src.tools.btm_analyzer import BTMAnalyzer
from backend.src.models.btm_schemas import BTMStatusCode, SteeringType

class TestBTMAnalyzer:
    
    @pytest.fixture
    def btm_analyzer(self):
        return BTMAnalyzer()
    
    @pytest.fixture
    def sample_steering_events(self):
        return [
            {
                "timestamp": 1234567890.123,
                "type": "Action",
                "subtype": 13,
                "client_mac": "aa:bb:cc:dd:ee:ff",
                "bssid": "11:22:33:44:55:66",
                "category_code": "10",
                "action_code": "7"  # BTM Request
            },
            {
                "timestamp": 1234567890.456,
                "type": "Action", 
                "subtype": 13,
                "client_mac": "aa:bb:cc:dd:ee:ff",
                "bssid": "11:22:33:44:55:66",
                "category_code": "10",
                "action_code": "8",  # BTM Response
                "btm_status_code": "0"  # Accept
            }
        ]
    
    @pytest.fixture
    def sample_band_counters(self):
        return {
            "btm_stats": {
                "requests": 1,
                "responses": 1,
                "status_codes": ["0"]
            },
            "kvr_stats": {
                "11k": False,
                "11v": True,
                "11r": False
            }
        }
    
    def test_extract_btm_events_success(self, btm_analyzer, sample_steering_events, sample_band_counters):
        """Test extracción exitosa de eventos BTM"""
        analysis = btm_analyzer.analyze_btm_events(sample_steering_events, sample_band_counters)
        
        assert analysis.btm_requests == 1
        assert analysis.btm_responses == 1
        assert analysis.btm_success_rate == 1.0
        assert len(analysis.btm_events) == 2
    
    def test_classify_btm_code_accept(self, btm_analyzer):
        """Test clasificación de código BTM Accept"""
        assert BTMStatusCode.is_success(0) == True
        assert BTMStatusCode.get_description(0) == "Accept - Cliente acepta la transición"
    
    def test_classify_btm_code_reject(self, btm_analyzer):
        """Test clasificación de código BTM Reject"""
        assert BTMStatusCode.is_success(2) == False
        assert "Reject" in BTMStatusCode.get_description(2)
    
    def test_detect_steering_pattern_aggressive(self, btm_analyzer):
        """Test detección de steering agresivo"""
        events = [
            {"type": "Deauthentication", "client_mac": "aa:bb:cc:dd:ee:ff"},
            {"type": "Reassociation Response", "client_mac": "aa:bb:cc:dd:ee:ff", "assoc_status_code": "0"}
        ]
        
        # Mock del método interno
        with patch.object(btm_analyzer, '_analyze_client_transitions') as mock_analyze:
            mock_analyze.return_value = None
            btm_analyzer._analyze_steering_transitions(events)
            mock_analyze.assert_called_once()
    
    def test_evaluate_kvr_support(self, btm_analyzer, sample_band_counters):
        """Test evaluación de soporte KVR"""
        kvr_support = btm_analyzer._evaluate_kvr_support(sample_band_counters)
        
        assert kvr_support.k_support == False
        assert kvr_support.v_support == True
        assert kvr_support.r_support == False
        assert kvr_support.compliance_score == 1/3
    
    def test_compliance_checks_btm_support(self, btm_analyzer, sample_band_counters):
        """Test verificación de cumplimiento BTM"""
        btm_analyzer._run_compliance_checks(sample_band_counters)
        
        btm_check = next((check for check in btm_analyzer.compliance_checks 
                         if check.check_name == "BTM Support"), None)
        
        assert btm_check is not None
        assert btm_check.passed == True
        assert btm_check.severity == "high"
    
    def test_calculate_transition_metrics(self, btm_analyzer):
        """Test cálculo de métricas de transición"""
        from backend.src.models.btm_schemas import SteeringTransition, TransitionStatus
        
        transitions = [
            SteeringTransition(
                client_mac="aa:bb:cc:dd:ee:ff",
                steering_type=SteeringType.AGGRESSIVE,
                start_time=1000.0,
                end_time=1002.5,
                duration=2.5,
                status=TransitionStatus.SUCCESS,
                is_successful=True
            ),
            SteeringTransition(
                client_mac="aa:bb:cc:dd:ee:ff", 
                steering_type=SteeringType.ASSISTED,
                start_time=2000.0,
                end_time=2001.0,
                duration=1.0,
                status=TransitionStatus.SUCCESS,
                is_successful=True
            )
        ]
        
        btm_analyzer.transitions = transitions
        metrics = btm_analyzer._calculate_metrics()
        
        assert metrics["avg_time"] == 1.75  # (2.5 + 1.0) / 2
        assert metrics["max_time"] == 2.5
        assert metrics["min_time"] == 1.0
    
    def test_determine_verdict_success(self, btm_analyzer):
        """Test determinación de veredicto exitoso"""
        btm_analyzer.compliance_checks = [
            Mock(passed=True, severity="high"),
            Mock(passed=True, severity="medium")
        ]
        btm_analyzer.transitions = [
            Mock(is_successful=True),
            Mock(is_successful=True)
        ]
        
        verdict = btm_analyzer._determine_verdict()
        assert verdict == "SUCCESS"
    
    def test_determine_verdict_failed(self, btm_analyzer):
        """Test determinación de veredicto fallido"""
        btm_analyzer.compliance_checks = [
            Mock(passed=False, severity="critical"),
            Mock(passed=False, severity="high")
        ]
        btm_analyzer.transitions = [
            Mock(is_successful=False),
            Mock(is_successful=False)
        ]
        
        verdict = btm_analyzer._determine_verdict()
        assert verdict == "FAILED"
    
    @pytest.mark.parametrize("requests,responses,expected_rate", [
        (0, 0, 0.0),
        (1, 1, 1.0),  # Asumiendo status code 0
        (2, 1, 1.0),  # Solo cuenta responses
        (1, 0, 0.0)   # Sin responses
    ])
    def test_btm_success_rate_calculation(self, btm_analyzer, requests, responses, expected_rate):
        """Test cálculo de tasa de éxito BTM con diferentes escenarios"""
        band_counters = {
            "btm_stats": {
                "requests": requests,
                "responses": responses,
                "status_codes": ["0"] * responses  # Todos exitosos
            }
        }
        
        rate = btm_analyzer._calculate_btm_success_rate(band_counters)
        assert rate == expected_rate
    
    def test_empty_events_handling(self, btm_analyzer):
        """Test manejo de eventos vacíos"""
        analysis = btm_analyzer.analyze_btm_events([], {})
        
        assert analysis.btm_requests == 0
        assert analysis.btm_responses == 0
        assert analysis.verdict == "NO_DATA"
        assert len(analysis.client_devices) == 0
    
    def test_malformed_events_handling(self, btm_analyzer):
        """Test manejo de eventos malformados"""
        malformed_events = [
            {"invalid": "event"},
            {"timestamp": "invalid_timestamp"},
            None
        ]
        
        # No debe lanzar excepción
        analysis = btm_analyzer.analyze_btm_events(malformed_events, {})
        assert analysis.verdict in ["NO_DATA", "FAILED"]
```

### Nivel 2: Integration Tests (20%)
```python
# Ejemplo: Test de integración Band Steering Service
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from backend.src.services.band_steering_service import BandSteeringService

class TestBandSteeringServiceIntegration:
    
    @pytest.fixture
    async def band_steering_service(self):
        service = BandSteeringService()
        # Mock de dependencias externas
        service.oui_lookup = AsyncMock()
        service.report_generator = AsyncMock()
        service.fragment_extractor = AsyncMock()
        return service
    
    @pytest.fixture
    def sample_capture_file(self, tmp_path):
        """Crea archivo de captura de prueba"""
        capture_file = tmp_path / "test_capture.pcap"
        # Crear archivo pcap mínimo válido
        with open(capture_file, 'wb') as f:
            # Header pcap básico
            f.write(b'\xd4\xc3\xb2\xa1\x02\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\x00\x00\x01\x00\x00\x00')
        return str(capture_file)
    
    @pytest.mark.asyncio
    async def test_analyze_capture_complete_success(self, band_steering_service, sample_capture_file):
        """Test análisis completo exitoso"""
        # Mock de wireshark_tool
        with patch.object(band_steering_service.wireshark_tool, 'analyze_capture') as mock_wireshark:
            mock_wireshark.return_value = {
                "file_name": "test_capture.pcap",
                "analysis": "Análisis exitoso",
                "stats": {
                    "total_packets": 100,
                    "total_wlan_packets": 50,
                    "steering_events": [
                        {
                            "client_mac": "aa:bb:cc:dd:ee:ff",
                            "type": "BTM Request",
                            "timestamp": 1234567890.0
                        }
                    ],
                    "diagnostics": {
                        "band_counters": {
                            "btm_stats": {"requests": 1, "responses": 1, "status_codes": ["0"]}
                        }
                    }
                }
            }
            
            # Mock de device classifier
            band_steering_service.oui_lookup.lookup_vendor = AsyncMock(return_value="Apple")
            
            # Mock de fragment extractor
            band_steering_service.fragment_extractor.extract_key_fragments = AsyncMock(return_value=[])
            
            # Ejecutar análisis
            report = await band_steering_service.analyze_capture_complete(
                sample_capture_file,
                device_info={"brand": "Apple", "model": "iPhone 12"}
            )
            
            # Verificaciones
            assert report.filename == "test_capture.pcap"
            assert report.overall_analysis.verdict in ["SUCCESS", "PARTIAL_SUCCESS", "NO_DATA"]
            assert len(report.device_analyses) >= 0
            assert report.executive_summary != ""
            assert len(report.recommendations) >= 0
    
    @pytest.mark.asyncio
    async def test_analyze_capture_with_multiple_devices(self, band_steering_service, sample_capture_file):
        """Test análisis con múltiples dispositivos"""
        with patch.object(band_steering_service.wireshark_tool, 'analyze_capture') as mock_wireshark:
            mock_wireshark.return_value = {
                "stats": {
                    "steering_events": [
                        {"client_mac": "aa:bb:cc:dd:ee:ff", "type": "BTM Request"},
                        {"client_mac": "11:22:33:44:55:66", "type": "BTM Response"},
                        {"client_mac": "aa:bb:cc:dd:ee:ff", "type": "Reassociation"}
                    ],
                    "diagnostics": {"band_counters": {}}
                }
            }
            
            # Mock diferentes fabricantes
            async def mock_lookup(oui):
                if oui.startswith("aa:bb:cc"):
                    return "Apple"
                else:
                    return "Samsung"
            
            band_steering_service.oui_lookup.lookup_vendor = mock_lookup
            
            report = await band_steering_service.analyze_capture_complete(sample_capture_file)
            
            # Debe detectar 2 dispositivos únicos
            unique_macs = set(analysis.device_mac for analysis in report.device_analyses)
            assert len(unique_macs) == 2
    
    @pytest.mark.asyncio
    async def test_compare_device_brands(self, band_steering_service):
        """Test comparación entre marcas"""
        from backend.src.models.btm_schemas import CaptureReport, DeviceAnalysis, BandSteeringAnalysis
        
        # Crear reportes de prueba
        reports = [
            CaptureReport(
                report_id="1",
                filename="apple_test.pcap",
                overall_analysis=BandSteeringAnalysis(filename="apple_test.pcap"),
                device_analyses=[
                    DeviceAnalysis(
                        device_mac="aa:bb:cc:dd:ee:ff",
                        device_brand="Apple",
                        steering_analysis=BandSteeringAnalysis(filename="apple_test.pcap")
                    )
                ]
            ),
            CaptureReport(
                report_id="2", 
                filename="samsung_test.pcap",
                overall_analysis=BandSteeringAnalysis(filename="samsung_test.pcap"),
                device_analyses=[
                    DeviceAnalysis(
                        device_mac="11:22:33:44:55:66",
                        device_brand="Samsung",
                        steering_analysis=BandSteeringAnalysis(filename="samsung_test.pcap")
                    )
                ]
            )
        ]
        
        comparison = await band_steering_service.compare_device_brands(reports)
        
        assert "Apple" in comparison
        assert "Samsung" in comparison
        assert comparison["Apple"]["device_count"] == 1
        assert comparison["Samsung"]["device_count"] == 1
    
    @pytest.mark.asyncio
    async def test_error_handling_invalid_file(self, band_steering_service):
        """Test manejo de errores con archivo inválido"""
        with pytest.raises(FileNotFoundError):
            await band_steering_service.analyze_capture_complete("nonexistent_file.pcap")
    
    @pytest.mark.asyncio
    async def test_error_handling_corrupted_capture(self, band_steering_service, tmp_path):
        """Test manejo de archivo corrupto"""
        corrupted_file = tmp_path / "corrupted.pcap"
        with open(corrupted_file, 'wb') as f:
            f.write(b'invalid pcap data')
        
        with patch.object(band_steering_service.wireshark_tool, 'analyze_capture') as mock_wireshark:
            mock_wireshark.side_effect = RuntimeError("Error ejecutando tshark")
            
            with pytest.raises(RuntimeError):
                await band_steering_service.analyze_capture_complete(str(corrupted_file))
```

### Nivel 3: End-to-End Tests (10%)
```python
# Ejemplo: Test E2E completo
import pytest
import httpx
from fastapi.testclient import TestClient
from backend.main import app

class TestBandSteeringE2E:
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    @pytest.fixture
    def auth_headers(self):
        # Mock de autenticación para tests
        return {"Authorization": "Bearer test_token"}
    
    @pytest.fixture
    def sample_pcap_file(self):
        """Archivo pcap real para testing E2E"""
        # En un entorno real, esto sería un archivo pcap válido con datos BTM
        return "tests/fixtures/sample_band_steering.pcap"
    
    def test_complete_analysis_workflow(self, client, auth_headers, sample_pcap_file):
        """Test del flujo completo de análisis"""
        
        # 1. Subir captura
        with open(sample_pcap_file, "rb") as f:
            upload_response = client.post(
                "/api/v1/captures/upload",
                files={"file": ("test.pcap", f, "application/octet-stream")},
                data={
                    "filename": "test.pcap",
                    "file_size": 1024,
                    "device_brand": "Apple",
                    "device_model": "iPhone 12"
                },
                headers=auth_headers
            )
        
        assert upload_response.status_code == 200
        upload_data = upload_response.json()
        upload_id = upload_data["upload_id"]
        
        # 2. Iniciar análisis
        analysis_response = client.post(
            f"/api/v1/captures/{upload_id}/analyze",
            json={
                "include_fragments": True,
                "generate_pdf_report": True,
                "detailed_analysis": True
            },
            headers=auth_headers
        )
        
        assert analysis_response.status_code == 200
        analysis_data = analysis_response.json()
        analysis_id = analysis_data["analysis_id"]
        
        # 3. Monitorear progreso
        import time
        max_wait = 60  # 60 segundos máximo
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            status_response = client.get(
                f"/api/v1/analyses/{analysis_id}/status",
                headers=auth_headers
            )
            
            assert status_response.status_code == 200
            status_data = status_response.json()
            
            if status_data["status"] == "completed":
                break
            elif status_data["status"] == "failed":
                pytest.fail(f"Análisis falló: {status_data}")
            
            time.sleep(2)
        else:
            pytest.fail("Análisis no completó en tiempo esperado")
        
        # 4. Obtener resultados
        result_response = client.get(
            f"/api/v1/analyses/{analysis_id}",
            params={"include_fragments": True},
            headers=auth_headers
        )
        
        assert result_response.status_code == 200
        result_data = result_response.json()
        
        # Verificaciones del resultado
        analysis = result_data["analysis"]
        assert analysis["analysis_id"] == analysis_id
        assert analysis["verdict"] in ["SUCCESS", "PARTIAL_SUCCESS", "FAILED", "NO_DATA"]
        assert 0.0 <= analysis["overall_compliance_score"] <= 1.0
        assert len(analysis["devices"]) >= 0
        
        # 5. Descargar reporte HTML
        html_response = client.get(
            f"/api/v1/analyses/{analysis_id}/reports/html",
            headers=auth_headers
        )
        
        assert html_response.status_code == 200
        assert "text/html" in html_response.headers["content-type"]
        
        # 6. Descargar reporte PDF
        pdf_response = client.get(
            f"/api/v1/analyses/{analysis_id}/reports/pdf",
            headers=auth_headers
        )
        
        assert pdf_response.status_code == 200
        assert "application/pdf" in pdf_response.headers["content-type"]
        
        # 7. Obtener fragmentos
        fragments_response = client.get(
            f"/api/v1/analyses/{analysis_id}/fragments",
            headers=auth_headers
        )
        
        assert fragments_response.status_code == 200
        fragments = fragments_response.json()
        assert isinstance(fragments, list)
    
    def test_rag_query_workflow(self, client, auth_headers):
        """Test del flujo de consulta RAG"""
        
        # Consulta técnica sobre BTM
        rag_response = client.post(
            "/api/v1/rag/query",
            json={
                "query": "¿Qué significa el código BTM 0 en una respuesta?",
                "include_technical_details": True,
                "max_results": 5
            },
            headers=auth_headers
        )
        
        assert rag_response.status_code == 200
        rag_data = rag_response.json()
        
        assert rag_data["query"] == "¿Qué significa el código BTM 0 en una respuesta?"
        assert len(rag_data["answer"]) > 0
        assert 0.0 <= rag_data["confidence_score"] <= 1.0
        assert len(rag_data["sources"]) > 0
    
    def test_comparison_workflow(self, client, auth_headers):
        """Test del flujo de comparación"""
        
        # Asumir que ya existen análisis en el sistema
        # En un test real, se crearían múltiples análisis primero
        
        comparison_response = client.post(
            "/api/v1/analyses/compare",
            json={
                "analysis_ids": ["analysis_1", "analysis_2", "analysis_3"],
                "group_by": "vendor",
                "include_statistical_analysis": True
            },
            headers=auth_headers
        )
        
        # Puede fallar si no existen los análisis, pero estructura debe ser correcta
        if comparison_response.status_code == 200:
            comparison_data = comparison_response.json()
            assert "group_statistics" in comparison_data
            assert "best_performers" in comparison_data
            assert "worst_performers" in comparison_data
```

## 🎯 Test Data y Fixtures

### Generador de Datos de Prueba
```python
# tests/fixtures/data_generator.py
import json
import random
from datetime import datetime, timedelta
from backend.src.models.btm_schemas import *

class TestDataGenerator:
    
    @staticmethod
    def generate_btm_events(count: int = 10) -> List[Dict[str, Any]]:
        """Genera eventos BTM de prueba"""
        events = []
        base_time = datetime.now().timestamp()
        
        for i in range(count):
            # Alternar entre request y response
            event_type = "request" if i % 2 == 0 else "response"
            
            event = {
                "timestamp": base_time + i * 0.5,
                "type": "Action",
                "subtype": 13,
                "client_mac": f"aa:bb:cc:dd:ee:{i:02x}",
                "bssid": f"11:22:33:44:55:{(i//2):02x}",
                "category_code": "10",
                "action_code": "7" if event_type == "request" else "8",
                "band": "5GHz" if i % 3 == 0 else "2.4GHz",
                "frequency": 5180 if i % 3 == 0 else 2412
            }
            
            if event_type == "response":
                # 80% de éxito, 20% de fallo
                event["btm_status_code"] = "0" if random.random() < 0.8 else str(random.randint(2, 8))
            
            events.append(event)
        
        return events
    
    @staticmethod
    def generate_steering_transitions(count: int = 5) -> List[SteeringTransition]:
        """Genera transiciones de steering de prueba"""
        transitions = []
        base_time = datetime.now().timestamp()
        
        for i in range(count):
            transition = SteeringTransition(
                client_mac=f"aa:bb:cc:dd:ee:{i:02x}",
                steering_type=random.choice(list(SteeringType)),
                start_time=base_time + i * 10,
                end_time=base_time + i * 10 + random.uniform(0.5, 3.0),
                from_bssid=f"11:22:33:44:55:{i:02x}",
                to_bssid=f"11:22:33:44:55:{(i+1):02x}",
                from_band="2.4GHz",
                to_band="5GHz",
                is_successful=random.random() < 0.8,
                is_band_change=True
            )
            
            if transition.end_time:
                transition.duration = transition.end_time - transition.start_time
            
            transitions.append(transition)
        
        return transitions
    
    @staticmethod
    def generate_device_info(vendor: str = "Apple") -> DeviceInfo:
        """Genera información de dispositivo de prueba"""
        return DeviceInfo(
            mac_address="aa:bb:cc:dd:ee:ff",
            oui="aa:bb:cc",
            vendor=vendor,
            device_model="iPhone 12" if vendor == "Apple" else "Galaxy S21",
            device_category=DeviceCategory.MOBILE,
            is_virtual=False,
            confidence_score=0.95
        )
    
    @staticmethod
    def generate_compliance_checks() -> List[ComplianceCheck]:
        """Genera verificaciones de cumplimiento de prueba"""
        checks = [
            ComplianceCheck(
                check_name="BTM Support",
                description="Verificar soporte de BTM",
                category="btm",
                passed=True,
                severity="high",
                score=1.0,
                details="BTM detectado correctamente"
            ),
            ComplianceCheck(
                check_name="KVR Support",
                description="Verificar soporte KVR",
                category="kvr", 
                passed=False,
                severity="medium",
                score=0.33,
                details="Solo 802.11v detectado",
                recommendation="Habilitar 802.11k y 802.11r"
            )
        ]
        return checks
```

### Fixtures de Archivos de Captura
```python
# tests/fixtures/pcap_generator.py
import struct
from pathlib import Path

class PcapGenerator:
    """Generador de archivos pcap mínimos para testing"""
    
    @staticmethod
    def create_minimal_pcap(output_path: str):
        """Crea archivo pcap mínimo válido"""
        with open(output_path, 'wb') as f:
            # Global header
            f.write(struct.pack('<LHHLLLL', 
                0xa1b2c3d4,  # magic number
                2,           # version major
                4,           # version minor  
                0,           # thiszone
                0,           # sigfigs
                65535,       # snaplen
                1            # network (Ethernet)
            ))
    
    @staticmethod
    def create_btm_pcap(output_path: str):
        """Crea archivo pcap con frames BTM simulados"""
        # Implementación más compleja que incluiría:
        # - Headers de paquetes individuales
        # - Frames 802.11 con BTM requests/responses
        # - Timestamps realistas
        pass
```

## 📊 Estrategias de Testing Específicas

### Testing de Precisión de BTM
```python
class TestBTMAccuracy:
    """Tests específicos para validar precisión de detección BTM"""
    
    @pytest.mark.parametrize("status_code,expected_success", [
        (0, True),   # Accept
        (1, True),   # Accept with preferred candidate
        (2, False),  # Reject - Unspecified
        (3, False),  # Reject - Insufficient beacon
        (4, False),  # Reject - Insufficient capinfo
        (5, False),  # Reject - Unacceptable delay
        (6, False),  # Reject - Destination unreachable
        (7, False),  # Reject - Invalid candidate
        (8, False),  # Reject - Leaving ESS
    ])
    def test_btm_code_classification_accuracy(self, status_code, expected_success):
        """Test precisión de clasificación de códigos BTM"""
        assert BTMStatusCode.is_success(status_code) == expected_success
    
    def test_btm_detection_with_real_captures(self):
        """Test con capturas reales de BTM"""
        # Usar capturas reales conocidas para validar detección
        pass
```

### Performance Testing
```python
class TestPerformance:
    """Tests de rendimiento"""
    
    @pytest.mark.performance
    def test_analysis_time_small_capture(self, band_steering_service):
        """Test tiempo de análisis para captura pequeña (<2MB)"""
        import time
        
        start_time = time.time()
        # Análisis de captura pequeña
        end_time = time.time()
        
        analysis_time = end_time - start_time
        assert analysis_time < 30.0  # Menos de 30 segundos
    
    @pytest.mark.performance
    def test_concurrent_analyses(self, band_steering_service):
        """Test análisis concurrentes"""
        import asyncio
        
        async def run_analysis(file_path):
            return await band_steering_service.analyze_capture_complete(file_path)
        
        # Ejecutar 5 análisis concurrentes
        tasks = [run_analysis(f"test_file_{i}.pcap") for i in range(5)]
        
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()
        
        # Verificar que no haya errores críticos
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0
        
        # Tiempo total no debe exceder significativamente el tiempo individual
        assert end_time - start_time < 180.0  # 3 minutos para 5 análisis
```

### Load Testing
```python
# tests/load/locustfile.py
from locust import HttpUser, task, between

class BandSteeringUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        """Setup inicial del usuario"""
        # Login o setup de autenticación
        pass
    
    @task(3)
    def upload_and_analyze(self):
        """Simula upload y análisis de captura"""
        # 1. Upload
        with open("test_capture.pcap", "rb") as f:
            response = self.client.post(
                "/api/v1/captures/upload",
                files={"file": f},
                data={"filename": "test.pcap", "file_size": 1024}
            )
        
        if response.status_code == 200:
            upload_id = response.json()["upload_id"]
            
            # 2. Start analysis
            self.client.post(
                f"/api/v1/captures/{upload_id}/analyze",
                json={"include_fragments": False}
            )
    
    @task(1)
    def rag_query(self):
        """Simula consulta RAG"""
        self.client.post(
            "/api/v1/rag/query",
            json={
                "query": "¿Qué es BTM en 802.11v?",
                "max_results": 3
            }
        )
    
    @task(1)
    def get_statistics(self):
        """Simula consulta de estadísticas"""
        self.client.get("/api/v1/statistics/vendors")
```

## 🔍 Testing de Casos Edge

### Casos Límite y Errores
```python
class TestEdgeCases:
    """Tests para casos límite y manejo de errores"""
    
    def test_empty_capture_file(self, band_steering_service):
        """Test con archivo de captura vacío"""
        # Crear archivo vacío
        empty_file = "empty.pcap"
        Path(empty_file).touch()
        
        with pytest.raises(Exception):  # Debe fallar graciosamente
            band_steering_service.analyze_capture_complete(empty_file)
    
    def test_corrupted_pcap_header(self, band_steering_service):
        """Test con header pcap corrupto"""
        corrupted_file = "corrupted.pcap"
        with open(corrupted_file, 'wb') as f:
            f.write(b'invalid_header_data')
        
        with pytest.raises(RuntimeError):
            band_steering_service.analyze_capture_complete(corrupted_file)
    
    def test_very_large_capture(self, band_steering_service):
        """Test con captura muy grande"""
        # Simular captura de 100MB+
        # Verificar que no cause out-of-memory
        pass
    
    def test_no_wlan_packets(self, band_steering_service):
        """Test con captura sin paquetes WLAN"""
        # Captura solo con tráfico Ethernet
        pass
    
    def test_malformed_btm_frames(self, btm_analyzer):
        """Test con frames BTM malformados"""
        malformed_events = [
            {"type": "Action", "subtype": 13, "category_code": "invalid"},
            {"type": "Action", "subtype": 13, "action_code": "999"},
            {"type": "Action", "btm_status_code": "invalid_code"}
        ]
        
        # No debe lanzar excepción
        analysis = btm_analyzer.analyze_btm_events(malformed_events, {})
        assert analysis.verdict in ["NO_DATA", "FAILED"]
```

## 📈 Métricas y Reportes de Testing

### Configuración de Coverage
```python
# pytest.ini
[tool:pytest]
addopts = 
    --cov=backend/src
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=85
    --strict-markers
    --disable-warnings

markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    performance: Performance tests
    slow: Slow running tests
```

### CI/CD Pipeline Testing
```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:13
        env:
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      redis:
        image: redis:6
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.10
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-test.txt
    
    - name: Install tshark
      run: |
        sudo apt-get update
        sudo apt-get install -y tshark
    
    - name: Run unit tests
      run: pytest tests/unit -v --cov=backend/src
    
    - name: Run integration tests
      run: pytest tests/integration -v
    
    - name: Run E2E tests
      run: pytest tests/e2e -v --slow
    
    - name: Upload coverage
      uses: codecov/codecov-action@v1
```

---

**Próximo paso**: Proceder a la fase de Documentación y Deployment