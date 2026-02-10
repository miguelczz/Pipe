# 🔌 AIDLC - Fase 4: Especificación de APIs y Contratos

## 🎯 Definición de Contratos de API

### Principios de Diseño de API
1. **RESTful**: Seguir principios REST para operaciones CRUD
2. **Versionado**: APIs versionadas para compatibilidad
3. **Consistencia**: Estructura uniforme de respuestas
4. **Documentación**: OpenAPI/Swagger para documentación automática
5. **Validación**: Validación estricta de entrada y salida
6. **Manejo de Errores**: Códigos de error consistentes y descriptivos

## 📋 Esquemas de Datos (Pydantic Models)

### Modelos Base
```python
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime

class BTMStatusCode(str, Enum):
    """Códigos de estado BTM según 802.11v"""
    ACCEPT = "0"
    ACCEPT_PREFERRED = "1"
    REJECT_UNSPECIFIED = "2"
    REJECT_INSUFFICIENT_BEACON = "3"
    REJECT_INSUFFICIENT_CAPINFO = "4"
    REJECT_UNACCEPTABLE_DELAY = "5"
    REJECT_DESTINATION_UNREACHABLE = "6"
    REJECT_INVALID_CANDIDATE = "7"
    REJECT_LEAVING_ESS = "8"

class SteeringType(str, Enum):
    """Tipos de steering detectados"""
    AGGRESSIVE = "aggressive"
    ASSISTED = "assisted"
    PREVENTIVE = "preventive"
    UNKNOWN = "unknown"

class AnalysisStatus(str, Enum):
    """Estados de análisis"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class DeviceCategory(str, Enum):
    """Categorías de dispositivos"""
    MOBILE = "mobile_device"
    COMPUTER = "computer_laptop"
    NETWORK_EQUIPMENT = "network_equipment"
    VIRTUAL_MACHINE = "virtual_machine"
    IOT_DEVICE = "iot_device"
    UNKNOWN = "unknown_device"
```

### Modelos de Entrada (Request)
```python
class CaptureUploadRequest(BaseModel):
    """Request para subir captura"""
    filename: str = Field(..., description="Nombre del archivo de captura")
    file_size: int = Field(..., gt=0, description="Tamaño del archivo en bytes")
    file_hash: Optional[str] = Field(None, description="Hash SHA-256 del archivo")
    
    # Metadatos opcionales
    device_brand: Optional[str] = Field(None, description="Marca del dispositivo (manual)")
    device_model: Optional[str] = Field(None, description="Modelo del dispositivo (manual)")
    test_scenario: Optional[str] = Field(None, description="Escenario de prueba")
    notes: Optional[str] = Field(None, max_length=1000, description="Notas adicionales")
    
    @validator('filename')
    def validate_filename(cls, v):
        if not v.endswith(('.pcap', '.pcapng')):
            raise ValueError('Archivo debe ser .pcap o .pcapng')
        return v

class AnalysisConfigRequest(BaseModel):
    """Configuración para análisis"""
    include_fragments: bool = Field(True, description="Incluir extracción de fragmentos")
    generate_pdf_report: bool = Field(False, description="Generar reporte en PDF")
    detailed_analysis: bool = Field(True, description="Análisis detallado vs básico")
    max_devices: Optional[int] = Field(None, gt=0, le=100, description="Máximo dispositivos a analizar")
    
    # Filtros de análisis
    focus_on_failures: bool = Field(False, description="Enfocarse en fallos detectados")
    include_virtual_devices: bool = Field(True, description="Incluir dispositivos virtuales")
    min_transition_time: Optional[float] = Field(None, ge=0.0, description="Tiempo mínimo de transición (segundos)")

class ComparisonRequest(BaseModel):
    """Request para comparación entre análisis"""
    analysis_ids: List[str] = Field(..., min_items=2, max_items=20, description="IDs de análisis a comparar")
    group_by: str = Field("vendor", description="Agrupar por: vendor, device_category, test_scenario")
    include_statistical_analysis: bool = Field(True, description="Incluir análisis estadístico")
    
    @validator('group_by')
    def validate_group_by(cls, v):
        allowed = ['vendor', 'device_category', 'test_scenario', 'analysis_date']
        if v not in allowed:
            raise ValueError(f'group_by debe ser uno de: {allowed}')
        return v

class RAGQueryRequest(BaseModel):
    """Request para consulta RAG especializada"""
    query: str = Field(..., min_length=10, max_length=500, description="Consulta del usuario")
    analysis_id: Optional[str] = Field(None, description="ID de análisis para contexto")
    include_technical_details: bool = Field(True, description="Incluir detalles técnicos")
    max_results: int = Field(5, ge=1, le=20, description="Máximo resultados de búsqueda")
    
    # Filtros de búsqueda
    document_types: Optional[List[str]] = Field(None, description="Tipos de documento a buscar")
    standards_filter: Optional[List[str]] = Field(None, description="Filtrar por estándares (802.11k/v/r)")
```

### Modelos de Salida (Response)
```python
class DeviceInfo(BaseModel):
    """Información de dispositivo"""
    mac_address: str = Field(..., description="MAC address del dispositivo")
    oui: str = Field(..., description="OUI (primeros 6 caracteres)")
    vendor: str = Field(..., description="Fabricante del dispositivo")
    device_model: Optional[str] = Field(None, description="Modelo del dispositivo")
    device_category: DeviceCategory = Field(..., description="Categoría del dispositivo")
    is_virtual: bool = Field(False, description="Es dispositivo virtual")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confianza en la identificación")

class BTMEvent(BaseModel):
    """Evento BTM individual"""
    timestamp: float = Field(..., description="Timestamp del evento")
    event_type: str = Field(..., description="Tipo: request o response")
    client_mac: str = Field(..., description="MAC del cliente")
    ap_bssid: str = Field(..., description="BSSID del AP")
    status_code: Optional[int] = Field(None, description="Código de estado BTM")
    band: Optional[str] = Field(None, description="Banda: 2.4GHz o 5GHz")
    frequency: Optional[int] = Field(None, description="Frecuencia en MHz")

class SteeringTransition(BaseModel):
    """Transición de steering"""
    client_mac: str = Field(..., description="MAC del cliente")
    steering_type: SteeringType = Field(..., description="Tipo de steering")
    start_time: float = Field(..., description="Tiempo de inicio")
    end_time: Optional[float] = Field(None, description="Tiempo de fin")
    duration: Optional[float] = Field(None, description="Duración en segundos")
    
    # Origen y destino
    from_bssid: Optional[str] = Field(None, description="BSSID origen")
    to_bssid: Optional[str] = Field(None, description="BSSID destino")
    from_band: Optional[str] = Field(None, description="Banda origen")
    to_band: Optional[str] = Field(None, description="Banda destino")
    
    # Estado
    is_successful: bool = Field(..., description="Transición exitosa")
    is_band_change: bool = Field(False, description="Cambio de banda")
    returned_to_original: bool = Field(False, description="Volvió al BSSID original")

class ComplianceCheck(BaseModel):
    """Verificación de cumplimiento"""
    check_name: str = Field(..., description="Nombre de la verificación")
    description: str = Field(..., description="Descripción de la verificación")
    category: str = Field(..., description="Categoría: btm, kvr, association, performance")
    passed: bool = Field(..., description="Verificación pasada")
    severity: str = Field(..., description="Severidad: low, medium, high, critical")
    score: float = Field(..., ge=0.0, le=1.0, description="Puntuación (0-1)")
    details: Optional[str] = Field(None, description="Detalles adicionales")
    recommendation: Optional[str] = Field(None, description="Recomendación de mejora")

class KVRSupport(BaseModel):
    """Soporte de estándares KVR"""
    k_support: bool = Field(False, description="Soporte 802.11k")
    v_support: bool = Field(False, description="Soporte 802.11v")
    r_support: bool = Field(False, description="Soporte 802.11r")
    compliance_score: float = Field(..., ge=0.0, le=1.0, description="Puntuación de cumplimiento")

class CaptureFragment(BaseModel):
    """Fragmento de captura extraído"""
    fragment_id: str = Field(..., description="ID único del fragmento")
    fragment_type: str = Field(..., description="Tipo: btm_sequence, transition, channel_change")
    description: str = Field(..., description="Descripción del fragmento")
    start_time: float = Field(..., description="Tiempo de inicio")
    end_time: float = Field(..., description="Tiempo de fin")
    packet_count: int = Field(..., description="Número de paquetes")
    file_size: int = Field(..., description="Tamaño del archivo en bytes")
    download_url: str = Field(..., description="URL para descargar el fragmento")

class BandSteeringAnalysis(BaseModel):
    """Análisis completo de Band Steering"""
    analysis_id: str = Field(..., description="ID único del análisis")
    filename: str = Field(..., description="Nombre del archivo analizado")
    analysis_timestamp: datetime = Field(..., description="Timestamp del análisis")
    
    # Métricas básicas
    total_packets: int = Field(..., description="Total de paquetes")
    wlan_packets: int = Field(..., description="Paquetes WLAN")
    analysis_duration_ms: int = Field(..., description="Duración del análisis en ms")
    
    # Dispositivos
    devices: List[DeviceInfo] = Field(..., description="Dispositivos analizados")
    
    # Eventos BTM
    btm_events: List[BTMEvent] = Field(..., description="Eventos BTM detectados")
    btm_requests: int = Field(0, description="Número de BTM requests")
    btm_responses: int = Field(0, description="Número de BTM responses")
    btm_success_rate: float = Field(0.0, ge=0.0, le=1.0, description="Tasa de éxito BTM")
    
    # Transiciones
    transitions: List[SteeringTransition] = Field(..., description="Transiciones detectadas")
    successful_transitions: int = Field(0, description="Transiciones exitosas")
    failed_transitions: int = Field(0, description="Transiciones fallidas")
    
    # Soporte de estándares
    kvr_support: KVRSupport = Field(..., description="Soporte KVR")
    
    # Cumplimiento
    compliance_checks: List[ComplianceCheck] = Field(..., description="Verificaciones de cumplimiento")
    overall_compliance_score: float = Field(..., ge=0.0, le=1.0, description="Puntuación general")
    
    # Métricas de rendimiento
    avg_transition_time: float = Field(0.0, description="Tiempo promedio de transición")
    max_transition_time: float = Field(0.0, description="Tiempo máximo de transición")
    
    # Problemas detectados
    loops_detected: bool = Field(False, description="Bucles detectados")
    timeouts_detected: bool = Field(False, description="Timeouts detectados")
    
    # Veredicto final
    verdict: str = Field(..., description="Veredicto: SUCCESS, PARTIAL_SUCCESS, FAILED, NO_DATA")
    
    # Fragmentos (opcional)
    fragments: Optional[List[CaptureFragment]] = Field(None, description="Fragmentos extraídos")

class AnalysisResponse(BaseModel):
    """Respuesta de análisis"""
    analysis: BandSteeringAnalysis = Field(..., description="Análisis completo")
    executive_summary: str = Field(..., description="Resumen ejecutivo")
    recommendations: List[str] = Field(..., description="Recomendaciones")
    
    # URLs de descarga
    html_report_url: Optional[str] = Field(None, description="URL del reporte HTML")
    pdf_report_url: Optional[str] = Field(None, description="URL del reporte PDF")
    
    # Metadatos
    processing_time_ms: int = Field(..., description="Tiempo de procesamiento")
    api_version: str = Field("1.0", description="Versión de la API")

class ComparisonResponse(BaseModel):
    """Respuesta de comparación"""
    comparison_id: str = Field(..., description="ID único de la comparación")
    analyses_compared: int = Field(..., description="Número de análisis comparados")
    group_by: str = Field(..., description="Criterio de agrupación")
    
    # Estadísticas por grupo
    group_statistics: Dict[str, Any] = Field(..., description="Estadísticas por grupo")
    
    # Métricas comparativas
    best_performers: List[str] = Field(..., description="Mejores performers")
    worst_performers: List[str] = Field(..., description="Peores performers")
    
    # Insights
    key_insights: List[str] = Field(..., description="Insights clave")
    recommendations: List[str] = Field(..., description="Recomendaciones")
    
    # Reporte
    comparison_report_url: str = Field(..., description="URL del reporte de comparación")

class RAGResponse(BaseModel):
    """Respuesta de consulta RAG"""
    query: str = Field(..., description="Consulta original")
    answer: str = Field(..., description="Respuesta generada")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confianza en la respuesta")
    
    # Fuentes utilizadas
    sources: List[Dict[str, Any]] = Field(..., description="Fuentes consultadas")
    
    # Contexto de análisis (si aplica)
    related_analysis: Optional[str] = Field(None, description="ID de análisis relacionado")
    
    # Metadatos
    response_time_ms: int = Field(..., description="Tiempo de respuesta")
    tokens_used: int = Field(..., description="Tokens utilizados")

class ErrorResponse(BaseModel):
    """Respuesta de error estándar"""
    error_code: str = Field(..., description="Código de error")
    error_message: str = Field(..., description="Mensaje de error")
    error_details: Optional[Dict[str, Any]] = Field(None, description="Detalles adicionales")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp del error")
    request_id: Optional[str] = Field(None, description="ID de la request para trazabilidad")
```

## 🛣️ Endpoints de API

### 1. Gestión de Capturas
```python
@router.post("/captures/upload", response_model=Dict[str, str])
async def upload_capture(
    file: UploadFile = File(...),
    metadata: CaptureUploadRequest = Depends()
) -> Dict[str, str]:
    """
    Sube archivo de captura para análisis
    
    Returns:
        - upload_id: ID único para el archivo subido
        - status: Estado inicial (pending)
        - estimated_processing_time: Tiempo estimado en segundos
    """

@router.post("/captures/{upload_id}/analyze", response_model=Dict[str, str])
async def start_analysis(
    upload_id: str,
    config: AnalysisConfigRequest = Body(...)
) -> Dict[str, str]:
    """
    Inicia análisis de captura subida
    
    Returns:
        - analysis_id: ID único del análisis
        - status: Estado inicial (processing)
        - estimated_completion: Timestamp estimado de finalización
    """

@router.get("/analyses/{analysis_id}/status", response_model=Dict[str, Any])
async def get_analysis_status(analysis_id: str) -> Dict[str, Any]:
    """
    Obtiene estado actual del análisis
    
    Returns:
        - status: Estado actual
        - progress_percentage: Progreso (0-100)
        - current_step: Paso actual del análisis
        - estimated_remaining_time: Tiempo restante estimado
    """

@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis_result(
    analysis_id: str,
    include_fragments: bool = Query(False)
) -> AnalysisResponse:
    """
    Obtiene resultado completo del análisis
    
    Args:
        analysis_id: ID del análisis
        include_fragments: Incluir fragmentos extraídos
        
    Returns:
        AnalysisResponse: Análisis completo con reportes
    """

@router.delete("/analyses/{analysis_id}")
async def delete_analysis(analysis_id: str) -> Dict[str, str]:
    """
    Elimina análisis y archivos asociados
    
    Returns:
        - message: Confirmación de eliminación
        - deleted_files: Lista de archivos eliminados
    """
```

### 2. Comparación y Estadísticas
```python
@router.post("/analyses/compare", response_model=ComparisonResponse)
async def compare_analyses(
    request: ComparisonRequest = Body(...)
) -> ComparisonResponse:
    """
    Compara múltiples análisis
    
    Returns:
        ComparisonResponse: Comparación detallada con estadísticas
    """

@router.get("/statistics/vendors", response_model=Dict[str, Any])
async def get_vendor_statistics(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None)
) -> Dict[str, Any]:
    """
    Obtiene estadísticas por fabricante
    
    Returns:
        - vendor_stats: Estadísticas por fabricante
        - total_devices: Total de dispositivos analizados
        - top_performers: Mejores fabricantes
        - compliance_trends: Tendencias de cumplimiento
    """

@router.get("/statistics/btm-codes", response_model=Dict[str, Any])
async def get_btm_code_statistics() -> Dict[str, Any]:
    """
    Obtiene estadísticas de códigos BTM
    
    Returns:
        - code_distribution: Distribución de códigos BTM
        - success_rates: Tasas de éxito por código
        - trend_analysis: Análisis de tendencias
    """
```

### 3. RAG y Consultas Especializadas
```python
@router.post("/rag/query", response_model=RAGResponse)
async def rag_query(
    request: RAGQueryRequest = Body(...)
) -> RAGResponse:
    """
    Consulta especializada usando RAG
    
    Returns:
        RAGResponse: Respuesta contextualizada con fuentes
    """

@router.get("/rag/documents", response_model=List[Dict[str, Any]])
async def list_indexed_documents() -> List[Dict[str, Any]]:
    """
    Lista documentos indexados para RAG
    
    Returns:
        - Lista de documentos con metadatos
        - Estadísticas de indexación
        - Cobertura por estándares
    """

@router.post("/rag/documents/reindex")
async def reindex_documents() -> Dict[str, str]:
    """
    Re-indexa documentos técnicos
    
    Returns:
        - message: Estado de la re-indexación
        - documents_processed: Número de documentos procesados
    """
```

### 4. Gestión de Fragmentos
```python
@router.get("/analyses/{analysis_id}/fragments", response_model=List[CaptureFragment])
async def get_analysis_fragments(analysis_id: str) -> List[CaptureFragment]:
    """
    Obtiene fragmentos extraídos de un análisis
    
    Returns:
        Lista de fragmentos con URLs de descarga
    """

@router.get("/fragments/{fragment_id}/download")
async def download_fragment(fragment_id: str) -> FileResponse:
    """
    Descarga fragmento específico
    
    Returns:
        Archivo pcap del fragmento
    """

@router.post("/fragments/extract", response_model=List[CaptureFragment])
async def extract_custom_fragments(
    analysis_id: str,
    criteria: Dict[str, Any] = Body(...)
) -> List[CaptureFragment]:
    """
    Extrae fragmentos personalizados
    
    Args:
        analysis_id: ID del análisis
        criteria: Criterios de extracción personalizados
        
    Returns:
        Lista de fragmentos extraídos
    """
```

### 5. Reportes y Exportación
```python
@router.get("/analyses/{analysis_id}/reports/html")
async def get_html_report(analysis_id: str) -> HTMLResponse:
    """
    Obtiene reporte HTML
    
    Returns:
        Reporte HTML renderizado
    """

@router.get("/analyses/{analysis_id}/reports/pdf")
async def get_pdf_report(analysis_id: str) -> FileResponse:
    """
    Obtiene reporte PDF
    
    Returns:
        Archivo PDF del reporte
    """

@router.post("/analyses/{analysis_id}/reports/custom", response_model=Dict[str, str])
async def generate_custom_report(
    analysis_id: str,
    template: str = Body(...),
    format: str = Body("html")
) -> Dict[str, str]:
    """
    Genera reporte personalizado
    
    Args:
        analysis_id: ID del análisis
        template: Plantilla personalizada
        format: Formato de salida (html, pdf, json)
        
    Returns:
        - report_url: URL del reporte generado
        - generation_time: Tiempo de generación
    """
```

## 🔒 Autenticación y Autorización

### Esquema de Autenticación
```python
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends, HTTPException, status

security = HTTPBearer()

class AuthService:
    def verify_token(self, credentials: HTTPAuthorizationCredentials = Depends(security)):
        """
        Verifica token JWT
        
        Returns:
            UserInfo: Información del usuario autenticado
            
        Raises:
            HTTPException: Token inválido o expirado
        """
        
    def check_permissions(self, user: UserInfo, required_permission: str):
        """
        Verifica permisos del usuario
        
        Args:
            user: Usuario autenticado
            required_permission: Permiso requerido
            
        Raises:
            HTTPException: Permisos insuficientes
        """

# Permisos definidos
class Permissions:
    UPLOAD_CAPTURES = "upload:captures"
    VIEW_ANALYSES = "view:analyses"
    DELETE_ANALYSES = "delete:analyses"
    COMPARE_ANALYSES = "compare:analyses"
    ADMIN_SYSTEM = "admin:system"
    EXPORT_DATA = "export:data"
```

### Middleware de Rate Limiting
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

# Rate limits por endpoint
@limiter.limit("10/minute")  # Máximo 10 uploads por minuto
async def upload_capture(...):
    pass

@limiter.limit("100/minute")  # Máximo 100 consultas por minuto
async def get_analysis_result(...):
    pass

@limiter.limit("5/minute")  # Máximo 5 comparaciones por minuto
async def compare_analyses(...):
    pass
```

## 📊 Códigos de Error Estándar

### Códigos de Error HTTP
```python
class ErrorCodes:
    # Errores de validación (400)
    INVALID_FILE_FORMAT = "INVALID_FILE_FORMAT"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_PARAMETER_VALUE = "INVALID_PARAMETER_VALUE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    
    # Errores de autenticación (401)
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    
    # Errores de autorización (403)
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    RESOURCE_ACCESS_DENIED = "RESOURCE_ACCESS_DENIED"
    
    # Errores de recursos (404)
    ANALYSIS_NOT_FOUND = "ANALYSIS_NOT_FOUND"
    CAPTURE_NOT_FOUND = "CAPTURE_NOT_FOUND"
    FRAGMENT_NOT_FOUND = "FRAGMENT_NOT_FOUND"
    
    # Errores de estado (409)
    ANALYSIS_ALREADY_RUNNING = "ANALYSIS_ALREADY_RUNNING"
    DUPLICATE_UPLOAD = "DUPLICATE_UPLOAD"
    
    # Errores de procesamiento (422)
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    UNSUPPORTED_CAPTURE_FORMAT = "UNSUPPORTED_CAPTURE_FORMAT"
    CORRUPTED_CAPTURE_FILE = "CORRUPTED_CAPTURE_FILE"
    
    # Errores de servidor (500)
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    DATABASE_CONNECTION_ERROR = "DATABASE_CONNECTION_ERROR"
    EXTERNAL_SERVICE_UNAVAILABLE = "EXTERNAL_SERVICE_UNAVAILABLE"
    
    # Errores de servicio (503)
    SERVICE_TEMPORARILY_UNAVAILABLE = "SERVICE_TEMPORARILY_UNAVAILABLE"
    MAINTENANCE_MODE = "MAINTENANCE_MODE"
```

### Manejo de Errores
```python
@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            error_code="VALIDATION_ERROR",
            error_message="Error de validación en los datos de entrada",
            error_details={"validation_errors": exc.errors()},
            request_id=request.headers.get("X-Request-ID")
        ).dict()
    )

@app.exception_handler(AnalysisError)
async def analysis_exception_handler(request: Request, exc: AnalysisError):
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error_code="ANALYSIS_FAILED",
            error_message=str(exc),
            error_details={"analysis_step": exc.step, "capture_file": exc.filename},
            request_id=request.headers.get("X-Request-ID")
        ).dict()
    )
```

## 📚 Documentación OpenAPI

### Configuración de OpenAPI
```python
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="Band Steering Analysis API",
        version="1.0.0",
        description="""
        API para análisis automatizado de Band Steering en capturas Wireshark.
        
        ## Características principales:
        - Análisis automático de códigos BTM (802.11v)
        - Evaluación de cumplimiento KVR (802.11k/v/r)
        - Clasificación automática de dispositivos
        - Extracción de fragmentos relevantes
        - Comparación entre marcas y modelos
        - Consultas RAG especializadas
        
        ## Flujo típico:
        1. Subir captura con `/captures/upload`
        2. Iniciar análisis con `/captures/{id}/analyze`
        3. Monitorear progreso con `/analyses/{id}/status`
        4. Obtener resultados con `/analyses/{id}`
        5. Descargar reportes y fragmentos
        """,
        routes=app.routes,
    )
    
    # Agregar información de seguridad
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    
    # Agregar ejemplos de respuesta
    openapi_schema["components"]["examples"] = {
        "SuccessfulAnalysis": {
            "summary": "Análisis exitoso",
            "value": {
                "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
                "verdict": "SUCCESS",
                "compliance_score": 0.95,
                "btm_success_rate": 1.0,
                "devices_analyzed": 2
            }
        },
        "FailedAnalysis": {
            "summary": "Análisis con fallos",
            "value": {
                "analysis_id": "550e8400-e29b-41d4-a716-446655440001",
                "verdict": "FAILED",
                "compliance_score": 0.3,
                "btm_success_rate": 0.0,
                "loops_detected": True
            }
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
```

---

**Próximo paso**: Proceder a la fase de Planificación de Testing y Validación