# 🚀 Roadmap de Implementación - Mejoras AIDLC Band Steering

## 📋 Resumen Ejecutivo

Este documento detalla **qué cambiar**, **qué mejorar** y **qué integrar** en el proyecto NetMind para implementar las mejoras del ciclo de vida de IA (AIDLC) enfocadas en análisis de Band Steering.

### Estado Actual vs Estado Objetivo
- **Estado Actual**: Sistema básico de análisis Wireshark con chat RAG
- **Estado Objetivo**: Sistema inteligente completo con análisis BTM, clasificación automática, reportes de cumplimiento y organización por marcas

---

## 🔄 CAMBIOS REQUERIDOS EN COMPONENTES EXISTENTES

### 1. Modificaciones al WiresharkTool Existente
**Archivo**: `backend/src/tools/wireshark_tool.py`

#### Cambios Necesarios:
```python
# ANTES: Análisis básico de steering
def _analyze_steering_patterns(self, events, bssid_info):
    # Lógica básica existente
    
# DESPUÉS: Integración con BTM Analyzer especializado
def _analyze_steering_patterns(self, events, bssid_info, band_counters):
    # Delegar análisis especializado al BTMAnalyzer
    btm_analyzer = BTMAnalyzer()
    detailed_analysis = btm_analyzer.analyze_btm_events(events, band_counters)
    
    # Mantener compatibilidad con análisis existente
    legacy_analysis = self._legacy_steering_analysis(events, bssid_info)
    
    # Combinar resultados
    return self._merge_analysis_results(detailed_analysis, legacy_analysis)
```

#### Mejoras Específicas:
- ✅ **Mantener**: Lógica de extracción de eventos 802.11 existente
- 🔄 **Modificar**: Método `_analyze_steering_patterns()` para usar BTMAnalyzer
- ➕ **Agregar**: Detección mejorada de códigos BTM (0-8)
- ➕ **Agregar**: Clasificación de patrones agresivo/asistido/preventivo
- 🔄 **Mejorar**: Método `_build_technical_summary()` con nuevas métricas

### 2. Mejoras al Sistema RAG Existente
**Archivos**: `backend/src/tools/rag_tool.py`, `backend/src/services/embeddings_service.py`

#### Cambios Necesarios:
```python
# ANTES: RAG genérico
class RAGTool:
    def query(self, user_prompt, conversation_context):
        # Búsqueda genérica en documentos
        
# DESPUÉS: RAG especializado en Band Steering
class RAGTool:
    def query(self, user_prompt, conversation_context, analysis_context=None):
        # Búsqueda contextualizada con análisis específico
        if self._is_btm_related_query(user_prompt):
            return self._query_btm_specialized(user_prompt, analysis_context)
        
        # Mantener funcionalidad existente para otras consultas
        return self._query_generic(user_prompt, conversation_context)
```

#### Mejoras Específicas:
- ➕ **Agregar**: Indexación de documentos AIDLC y Wireshark Band Steering
- ➕ **Agregar**: Consultas especializadas sobre códigos BTM
- ➕ **Agregar**: Explicación contextual de fallos detectados
- 🔄 **Mejorar**: Embeddings con términos técnicos específicos (802.11k/v/r)

### 3. Extensión del API Gateway
**Archivo**: `backend/src/api/agent.py`

#### Cambios Necesarios:
```python
# ANTES: Endpoint básico de análisis
@router.post("/query")
async def agent_query(query: AgentQuery):
    # Análisis genérico
    
# DESPUÉS: Endpoints especializados
@router.post("/query")
async def agent_query(query: AgentQuery):
    # Mantener compatibilidad existente
    
@router.post("/analyze-capture")  # NUEVO
async def analyze_capture_advanced(request: CaptureAnalysisRequest):
    # Análisis especializado de Band Steering
    
@router.get("/btm-codes")  # NUEVO
async def get_btm_codes_reference():
    # Referencia de códigos BTM
```

---

## ➕ COMPONENTES COMPLETAMENTE NUEVOS

### 1. BTM Analyzer (Nuevo)
**Archivo**: `backend/src/tools/btm_analyzer.py`
```python
class BTMAnalyzer:
    """Analizador especializado para eventos BTM (802.11v)"""
    
    def analyze_btm_events(self, steering_events, band_counters):
        # Análisis completo de BTM con clasificación automática
        
    def classify_btm_code(self, status_code):
        # Clasificación según estándar 802.11v
        
    def detect_steering_pattern(self, client_events):
        # Detección de patrones agresivo/asistido/preventivo
```

**Funcionalidades**:
- ✨ Detección automática de códigos BTM (0-8)
- ✨ Clasificación de éxito/fallo por situación
- ✨ Análisis de patrones de steering
- ✨ Evaluación de cumplimiento KVR (802.11k/v/r)

### 2. Device Classifier (Nuevo)
**Archivo**: `backend/src/tools/device_classifier.py`
```python
class DeviceClassifier:
    """Clasificador automático de dispositivos por MAC"""
    
    def classify_device(self, mac_address, device_info=None):
        # Identificación automática de marca/modelo
        
    def batch_classify(self, mac_addresses):
        # Clasificación en lote
        
    def get_vendor_statistics(self, device_list):
        # Estadísticas por fabricante
```

**Funcionalidades**:
- ✨ Lookup automático de fabricantes por OUI
- ✨ Categorización por tipo de dispositivo
- ✨ Organización automática en carpetas por marca
- ✨ Estadísticas comparativas entre fabricantes

### 3. Band Steering Service (Nuevo)
**Archivo**: `backend/src/services/band_steering_service.py`
```python
class BandSteeringService:
    """Servicio orquestador para análisis completo"""
    
    async def analyze_capture_complete(self, file_path, device_info=None):
        # Análisis completo con todas las mejoras
        
    async def compare_device_brands(self, reports):
        # Comparación entre marcas
        
    def generate_compliance_report(self, analysis):
        # Reporte de cumplimiento automático
```

**Funcionalidades**:
- ✨ Orquestación de análisis completo
- ✨ Integración de todos los componentes especializados
- ✨ Generación de reportes ejecutivos
- ✨ Comparación automática entre marcas

### 4. Report Generator (Nuevo)
**Archivo**: `backend/src/services/report_generator.py`
```python
class ReportGenerator:
    """Generador de reportes especializados"""
    
    def generate_executive_report(self, analysis):
        # Reporte ejecutivo con métricas clave
        
    def generate_technical_report(self, analysis):
        # Reporte técnico detallado
        
    def generate_comparison_report(self, analyses):
        # Reporte comparativo entre dispositivos/marcas
```

**Funcionalidades**:
- ✨ Reportes HTML/PDF automáticos
- ✨ Plantillas personalizables
- ✨ Visualizaciones de datos
- ✨ Exportación en múltiples formatos

### 5. Fragment Extractor (Nuevo)
**Archivo**: `backend/src/services/fragment_extractor.py`
```python
class FragmentExtractor:
    """Extractor de fragmentos relevantes de capturas"""
    
    def extract_key_fragments(self, capture_file, analysis):
        # Extracción de secuencias importantes
        
    def extract_btm_sequence(self, capture_file, btm_events):
        # Secuencias BTM específicas
        
    def extract_channel_changes(self, capture_file, transitions):
        # Cambios de canal detectados
```

**Funcionalidades**:
- ✨ Extracción automática de fragmentos relevantes
- ✨ Secuencias de cambio de canal
- ✨ Eventos BTM completos (Request → Response)
- ✨ Filtrado inteligente de paquetes

### 6. OUI Lookup Service (Nuevo)
**Archivo**: `backend/src/utils/oui_lookup.py`
```python
class OUILookup:
    """Servicio de lookup de fabricantes"""
    
    async def lookup_vendor(self, mac_address):
        # Identificación de fabricante por MAC
        
    def categorize_device(self, vendor, mac_address):
        # Categorización automática
        
    def is_mobile_device(self, mac_address):
        # Detección de dispositivos móviles
```

**Funcionalidades**:
- ✨ Base de datos de OUIs actualizada
- ✨ Caché local para rendimiento
- ✨ API externa como fallback
- ✨ Categorización automática de dispositivos

---

## 🗄️ NUEVOS MODELOS DE DATOS

### 1. Esquemas BTM (Nuevo)
**Archivo**: `backend/src/models/btm_schemas.py`
```python
class BTMStatusCode(Enum):
    ACCEPT = 0
    ACCEPT_PREFERRED = 1
    REJECT_UNSPECIFIED = 2
    # ... más códigos

class SteeringTransition(BaseModel):
    client_mac: str
    steering_type: SteeringType
    start_time: float
    end_time: Optional[float]
    # ... más campos

class BandSteeringAnalysis(BaseModel):
    # Modelo completo de análisis
```

### 2. Nuevas Tablas de Base de Datos
```sql
-- Tabla principal de análisis (NUEVA)
CREATE TABLE capture_analyses (
    id UUID PRIMARY KEY,
    filename VARCHAR(255),
    overall_verdict VARCHAR(50),
    compliance_score DECIMAL(3,2),
    btm_requests INTEGER,
    btm_responses INTEGER,
    -- ... más campos
);

-- Tabla de dispositivos analizados (NUEVA)
CREATE TABLE analyzed_devices (
    id UUID PRIMARY KEY,
    analysis_id UUID REFERENCES capture_analyses(id),
    mac_address VARCHAR(17),
    vendor VARCHAR(100),
    device_category VARCHAR(50),
    -- ... más campos
);

-- Tabla de eventos BTM (NUEVA)
CREATE TABLE btm_events (
    id UUID PRIMARY KEY,
    analysis_id UUID REFERENCES capture_analyses(id),
    timestamp_ms BIGINT,
    event_type VARCHAR(20),
    status_code INTEGER,
    -- ... más campos
);
```

---

## 🔧 MEJORAS A FUNCIONALIDADES EXISTENTES

### 1. Chat RAG Mejorado
**Cambios en**: `backend/src/agent/router.py`

#### Antes:
```python
def decide(self, user_prompt, context):
    # Decisión básica entre RAG/IP/DNS
```

#### Después:
```python
def decide(self, user_prompt, context, analysis_context=None):
    # Decisión contextualizada con análisis de Band Steering
    if self._is_btm_query(user_prompt):
        return self._handle_btm_query(user_prompt, analysis_context)
    
    # Mantener lógica existente para otras consultas
    return self._handle_generic_query(user_prompt, context)
```

**Mejoras**:
- ➕ Consultas sobre códigos BTM específicos
- ➕ Explicación de fallos detectados en análisis
- ➕ Recomendaciones basadas en resultados
- ➕ Acceso contextual a documentación técnica

### 2. Sistema de Archivos Mejorado
**Cambios en**: `backend/src/api/files.py`

#### Nuevas Funcionalidades:
```python
@router.post("/upload-for-analysis")  # NUEVO
async def upload_capture_for_analysis(
    file: UploadFile,
    device_brand: Optional[str] = None,
    device_model: Optional[str] = None
):
    # Upload especializado para análisis de Band Steering

@router.get("/analyses/{analysis_id}/fragments")  # NUEVO
async def get_analysis_fragments(analysis_id: str):
    # Obtener fragmentos extraídos
```

### 3. Frontend Mejorado
**Cambios en**: `frontend/src/`

#### Nuevos Componentes:
- ➕ `BTMAnalysisView.jsx` - Vista especializada de análisis BTM
- ➕ `ComplianceTable.jsx` - Tabla de cumplimiento KVR
- ➕ `DeviceComparison.jsx` - Comparación entre marcas
- ➕ `FragmentViewer.jsx` - Visualizador de fragmentos
- 🔄 `ChatContainer.jsx` - Mejorado con consultas especializadas

---

## 📊 NUEVAS FUNCIONALIDADES DE SISTEMA

### 1. Sistema de Carpetas por Marca
```
/data/analyses/
├── Apple/
│   ├── iPhone_12/
│   │   ├── analysis_001.json
│   │   ├── fragments/
│   │   └── reports/
│   └── iPhone_13/
├── Samsung/
│   ├── Galaxy_S21/
│   └── Galaxy_S22/
└── Unknown/
    └── unidentified_devices/
```

### 2. Tabla de Cumplimiento Automática
```yaml
Compliance Checks:
  BTM Support (802.11v):
    Status: ✅ PASSED
    Details: "BTM Requests: 5, Responses: 4"
    Score: 100%
    
  KVR Standards:
    802.11k: ❌ NOT DETECTED
    802.11v: ✅ DETECTED  
    802.11r: ⚠️ PARTIAL
    Score: 66%
    
  Steering Performance:
    Success Rate: 80%
    Avg Transition Time: 1.2s
    Loops Detected: NO
    Score: 85%
```

### 3. Fragmentos de Captura Automáticos
- 🎯 **BTM Sequences**: Request → Response completas
- 🎯 **Channel Changes**: Transiciones de banda detectadas
- 🎯 **Steering Events**: Deauth → Reassoc sequences
- 🎯 **Failure Cases**: Fallos de asociación y timeouts

---

## 📅 CRONOGRAMA DE IMPLEMENTACIÓN

### Fase 1: Fundamentos (Semana 1-2)
- ✅ Crear modelos de datos BTM (`btm_schemas.py`)
- ✅ Implementar BTM Analyzer básico
- ✅ Configurar nuevas tablas de base de datos
- ✅ Crear OUI Lookup service

### Fase 2: Análisis Especializado (Semana 3-4)
- ✅ Integrar BTM Analyzer con WiresharkTool existente
- ✅ Implementar Device Classifier
- ✅ Crear Band Steering Service orquestador
- ✅ Desarrollar Fragment Extractor

### Fase 3: Reportes y Visualización (Semana 5-6)
- ✅ Implementar Report Generator
- ✅ Crear plantillas de reportes HTML/PDF
- ✅ Desarrollar sistema de carpetas por marca
- ✅ Integrar tabla de cumplimiento automática

### Fase 4: Mejoras RAG y Frontend (Semana 7-8)
- ✅ Mejorar RAG con documentos especializados
- ✅ Implementar consultas BTM contextuales
- ✅ Crear componentes frontend especializados
- ✅ Integrar visualizador de fragmentos

### Fase 5: Testing y Optimización (Semana 9-10)
- ✅ Implementar suite de tests completa
- ✅ Optimizar rendimiento de análisis
- ✅ Validar precisión con casos reales
- ✅ Documentar APIs y funcionalidades

---

## 🎯 CRITERIOS DE ÉXITO

### Métricas Técnicas
- ✅ **Detección BTM**: >95% precisión en códigos 0-8
- ✅ **Clasificación de dispositivos**: >98% precisión en fabricantes
- ✅ **Tiempo de análisis**: <30s para capturas <2MB
- ✅ **Cobertura de tests**: >85% del código

### Métricas de Usuario
- ✅ **Reducción de tiempo**: 80% menos tiempo vs análisis manual
- ✅ **Satisfacción**: >4.5/5 en encuestas de usuario
- ✅ **Adopción**: 90% de usuarios usan nuevas funcionalidades
- ✅ **Precisión percibida**: >90% de análisis considerados correctos

### Métricas de Negocio
- ✅ **Productividad**: 5x más análisis por día
- ✅ **Consistencia**: 95% concordancia entre análisis
- ✅ **Trazabilidad**: 100% de análisis documentados
- ✅ **Escalabilidad**: Soporte para 100+ análisis concurrentes

---

## 🚨 RIESGOS Y MITIGACIONES

### Riesgos Técnicos
1. **Complejidad de integración**: Muchos componentes nuevos
   - **Mitigación**: Implementación incremental, tests exhaustivos
   
2. **Rendimiento con archivos grandes**: Capturas >10MB
   - **Mitigación**: Procesamiento asíncrono, optimización de memoria
   
3. **Precisión de detección BTM**: Variabilidad en implementaciones
   - **Mitigación**: Dataset de validación extenso, ajuste continuo

### Riesgos de Proyecto
1. **Tiempo de desarrollo**: Scope amplio
   - **Mitigación**: Priorización clara, MVP funcional temprano
   
2. **Compatibilidad hacia atrás**: Cambios en APIs existentes
   - **Mitigación**: Versionado de APIs, período de transición
   
3. **Adopción de usuarios**: Curva de aprendizaje
   - **Mitigación**: Documentación clara, training, soporte

---

## 📋 CHECKLIST DE IMPLEMENTACIÓN

### Preparación
- [ ] Backup completo del sistema actual
- [ ] Configuración de entorno de desarrollo
- [ ] Creación de branch de desarrollo
- [ ] Setup de base de datos de testing

### Desarrollo
- [ ] Implementar modelos de datos BTM
- [ ] Crear BTM Analyzer con tests
- [ ] Desarrollar Device Classifier
- [ ] Integrar con WiresharkTool existente
- [ ] Implementar Report Generator
- [ ] Crear Fragment Extractor
- [ ] Mejorar sistema RAG
- [ ] Desarrollar componentes frontend

### Testing
- [ ] Tests unitarios (>85% cobertura)
- [ ] Tests de integración
- [ ] Tests end-to-end
- [ ] Validación con capturas reales
- [ ] Performance testing
- [ ] User acceptance testing

### Deployment
Deployment-related tasks and infrastructure configuration have been removed from the repository and from these documents. The project documentation now focuses on development, testing and internal operations. See the repository root README for local development instructions.

---

**🎯 Objetivo Final**: Transformar NetMind de un analizador básico a una plataforma completa de análisis inteligente de Band Steering con capacidades de IA avanzadas, organización automática y reportes de cumplimiento profesionales.