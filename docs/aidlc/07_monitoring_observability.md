# 📊 AIDLC - Fase 7: Monitoreo y Observabilidad

## 🎯 Estrategia de Observabilidad

### Pilares de Observabilidad
1. **Métricas**: Datos cuantitativos sobre rendimiento del sistema
2. **Logs**: Registros detallados de eventos y operaciones
3. **Trazas**: Seguimiento de requests a través de componentes
4. **Alertas**: Notificaciones proactivas de problemas
5. **Dashboards**: Visualización en tiempo real del estado del sistema

### Objetivos de Monitoreo
- **Disponibilidad**: Uptime del sistema >99.5%
- **Rendimiento**: Tiempos de respuesta dentro de SLAs
- **Calidad**: Precisión de análisis >95%
- **Recursos**: Utilización eficiente de CPU/memoria/storage
- **Experiencia de Usuario**: Satisfacción y usabilidad

## 📈 Métricas del Sistema

### Métricas de Aplicación
```python
from prometheus_client import Counter, Histogram, Gauge, Summary
import time
from functools import wraps

# Contadores de eventos
analysis_requests_total = Counter(
    'band_steering_analysis_requests_total',
    'Total number of analysis requests',
    ['endpoint', 'method', 'status']
)

analysis_duration_seconds = Histogram(
    'band_steering_analysis_duration_seconds',
    'Time spent processing analysis',
    ['analysis_type', 'file_size_category'],
    buckets=[1, 5, 10, 30, 60, 120, 300]
)

active_analyses = Gauge(
    'band_steering_active_analyses',
    'Number of currently active analyses'
)

btm_detection_accuracy = Gauge(
    'band_steering_btm_detection_accuracy',
    'Accuracy of BTM code detection',
    ['device_vendor']
)

# Métricas de calidad de datos
data_quality_score = Gauge(
    'band_steering_data_quality_score',
    'Overall data quality score',
    ['metric_type']
)

# Métricas de recursos
memory_usage_bytes = Gauge(
    'band_steering_memory_usage_bytes',
    'Memory usage in bytes',
    ['component']
)

# Decorator para métricas automáticas
def monitor_performance(operation_name: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                analysis_requests_total.labels(
                    endpoint=operation_name,
                    method='async',
                    status='success'
                ).inc()
                return result
            except Exception as e:
                analysis_requests_total.labels(
                    endpoint=operation_name,
                    method='async', 
                    status='error'
                ).inc()
                raise
            finally:
                duration = time.time() - start_time
                analysis_duration_seconds.labels(
                    analysis_type=operation_name,
                    file_size_category='unknown'
                ).observe(duration)
        
        return wrapper
    return decorator
```

### Métricas de Negocio
```python
# Métricas específicas del dominio
btm_success_rate = Gauge(
    'band_steering_btm_success_rate',
    'BTM success rate by vendor',
    ['device_vendor', 'time_period']
)

compliance_score_distribution = Histogram(
    'band_steering_compliance_score_distribution',
    'Distribution of compliance scores',
    ['vendor_category'],
    buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 0.95, 1.0]
)

steering_pattern_frequency = Counter(
    'band_steering_pattern_frequency',
    'Frequency of different steering patterns',
    ['pattern_type', 'success_status']
)

device_analysis_count = Counter(
    'band_steering_device_analysis_count',
    'Number of devices analyzed',
    ['vendor', 'category', 'analysis_result']
)

user_satisfaction_score = Gauge(
    'band_steering_user_satisfaction_score',
    'User satisfaction rating',
    ['feature', 'user_type']
)
```

## 📝 Logging Estructurado

### Configuración de Logging
```python
import logging
import json
from datetime import datetime
from typing import Dict, Any

class StructuredLogger:
    """Logger estructurado para observabilidad"""
    
    def __init__(self, component_name: str):
        self.component_name = component_name
        self.logger = logging.getLogger(component_name)
        
        # Configurar handler con formato JSON
        handler = logging.StreamHandler()
        handler.setFormatter(self.JsonFormatter())
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    class JsonFormatter(logging.Formatter):
        def format(self, record):
            log_entry = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': record.levelname,
                'component': record.name,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno
            }
            
            # Agregar contexto adicional si existe
            if hasattr(record, 'analysis_id'):
                log_entry['analysis_id'] = record.analysis_id
            if hasattr(record, 'user_id'):
                log_entry['user_id'] = record.user_id
            if hasattr(record, 'request_id'):
                log_entry['request_id'] = record.request_id
            if hasattr(record, 'duration_ms'):
                log_entry['duration_ms'] = record.duration_ms
            
            return json.dumps(log_entry)
    
    def info(self, message: str, **context):
        """Log info con contexto"""
        extra = {k: v for k, v in context.items()}
        self.logger.info(message, extra=extra)
    
    def error(self, message: str, error: Exception = None, **context):
        """Log error con contexto y stack trace"""
        extra = {k: v for k, v in context.items()}
        if error:
            extra['error_type'] = type(error).__name__
            extra['error_message'] = str(error)
        self.logger.error(message, extra=extra, exc_info=error is not None)
    
    def warning(self, message: str, **context):
        """Log warning con contexto"""
        extra = {k: v for k, v in context.items()}
        self.logger.warning(message, extra=extra)

# Uso en componentes
btm_logger = StructuredLogger('btm_analyzer')
service_logger = StructuredLogger('band_steering_service')
api_logger = StructuredLogger('api_gateway')
```

### Eventos de Log Importantes
```python
class LogEvents:
    """Eventos de log estandarizados"""
    
    # Eventos de análisis
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETED = "analysis_completed"
    ANALYSIS_FAILED = "analysis_failed"
    
    # Eventos de BTM
    BTM_DETECTED = "btm_detected"
    BTM_CLASSIFICATION_COMPLETED = "btm_classification_completed"
    STEERING_PATTERN_IDENTIFIED = "steering_pattern_identified"
    
    # Eventos de calidad
    DATA_QUALITY_CHECK = "data_quality_check"
    COMPLIANCE_EVALUATION = "compliance_evaluation"
    ACCURACY_VALIDATION = "accuracy_validation"
    
    # Eventos de sistema
    COMPONENT_HEALTH_CHECK = "component_health_check"
    RESOURCE_THRESHOLD_EXCEEDED = "resource_threshold_exceeded"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    
    # Eventos de usuario
    USER_FEEDBACK_RECEIVED = "user_feedback_received"
    REPORT_GENERATED = "report_generated"
    FRAGMENT_DOWNLOADED = "fragment_downloaded"

# Ejemplo de uso
def log_analysis_event(logger: StructuredLogger, event: str, **context):
    """Helper para logging de eventos de análisis"""
    logger.info(f"Analysis event: {event}", event_type=event, **context)

# En BTM Analyzer
btm_logger.info(
    "BTM analysis completed successfully",
    event_type=LogEvents.BTM_CLASSIFICATION_COMPLETED,
    analysis_id="12345",
    btm_requests=5,
    btm_responses=4,
    success_rate=0.8,
    duration_ms=1250
)
```

## 🔍 Distributed Tracing

### Configuración de Tracing
```python
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

# Configurar tracer
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)

# Configurar exportador Jaeger
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",
    agent_port=6831,
)

span_processor = BatchSpanProcessor(jaeger_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

# Instrumentar FastAPI automáticamente
FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument()

# Tracing manual para operaciones críticas
class TracedBTMAnalyzer:
    """BTM Analyzer con tracing distribuido"""
    
    def __init__(self):
        self.tracer = trace.get_tracer("btm_analyzer")
    
    async def analyze_btm_events(self, steering_events, band_counters):
        with self.tracer.start_as_current_span("btm_analysis") as span:
            span.set_attribute("events.count", len(steering_events))
            span.set_attribute("analysis.type", "btm")
            
            try:
                # Extracción de eventos BTM
                with self.tracer.start_as_current_span("extract_btm_events") as extract_span:
                    btm_events = self._extract_btm_events(steering_events, band_counters)
                    extract_span.set_attribute("btm_events.extracted", len(btm_events))
                
                # Análisis de transiciones
                with self.tracer.start_as_current_span("analyze_transitions") as transition_span:
                    transitions = self._analyze_steering_transitions(steering_events)
                    transition_span.set_attribute("transitions.count", len(transitions))
                
                # Evaluación de cumplimiento
                with self.tracer.start_as_current_span("compliance_evaluation") as compliance_span:
                    compliance_checks = self._run_compliance_checks(band_counters)
                    compliance_span.set_attribute("checks.total", len(compliance_checks))
                    compliance_span.set_attribute("checks.passed", 
                                                sum(1 for c in compliance_checks if c.passed))
                
                span.set_attribute("analysis.verdict", "success")
                span.set_status(trace.Status(trace.StatusCode.OK))
                
                return self._build_analysis_result(btm_events, transitions, compliance_checks)
                
            except Exception as e:
                span.set_attribute("analysis.verdict", "failed")
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise
```

## 🚨 Sistema de Alertas

### Configuración de Alertas
```yaml
# alerting_rules.yml
groups:
  - name: band_steering_system
    rules:
      # Alertas críticas
      - alert: AnalysisFailureRateHigh
        expr: rate(band_steering_analysis_requests_total{status="error"}[5m]) > 0.05
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "High analysis failure rate detected"
          description: "Analysis failure rate is {{ $value | humanizePercentage }} over the last 5 minutes"
      
      - alert: SystemMemoryHigh
        expr: band_steering_memory_usage_bytes / (1024^3) > 8
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High memory usage detected"
          description: "Memory usage is {{ $value }}GB, exceeding 8GB threshold"
      
      - alert: BTMDetectionAccuracyLow
        expr: band_steering_btm_detection_accuracy < 0.90
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "BTM detection accuracy below threshold"
          description: "BTM detection accuracy is {{ $value | humanizePercentage }} for vendor {{ $labels.device_vendor }}"
      
      # Alertas de negocio
      - alert: ComplianceScoreDrop
        expr: avg_over_time(band_steering_compliance_score_distribution[1h]) < 0.70
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Average compliance score dropping"
          description: "Average compliance score over last hour is {{ $value | humanizePercentage }}"
      
      - alert: UserSatisfactionLow
        expr: band_steering_user_satisfaction_score < 3.5
        for: 30m
        labels:
          severity: info
        annotations:
          summary: "User satisfaction score low"
          description: "User satisfaction for {{ $labels.feature }} is {{ $value }}/5"

  - name: band_steering_data_quality
    rules:
      - alert: DataQualityScoreLow
        expr: band_steering_data_quality_score{metric_type="completeness"} < 0.85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Data quality score below threshold"
          description: "{{ $labels.metric_type }} quality score is {{ $value | humanizePercentage }}"
      
      - alert: ProcessingQueueBacklog
        expr: band_steering_active_analyses > 50
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Processing queue backlog detected"
          description: "{{ $value }} analyses are currently queued/processing"
```

### Canales de Notificación
```python
from abc import ABC, abstractmethod
from typing import Dict, Any
import smtplib
import requests
import json

class AlertChannel(ABC):
    """Interfaz base para canales de alerta"""
    
    @abstractmethod
    async def send_alert(self, alert: Dict[str, Any]) -> bool:
        pass

class EmailAlertChannel(AlertChannel):
    """Canal de alertas por email"""
    
    def __init__(self, smtp_config: Dict[str, str]):
        self.smtp_config = smtp_config
    
    async def send_alert(self, alert: Dict[str, Any]) -> bool:
        try:
            subject = f"[{alert['severity'].upper()}] {alert['summary']}"
            body = f"""
            Alert: {alert['alert_name']}
            Severity: {alert['severity']}
            Description: {alert['description']}
            Timestamp: {alert['timestamp']}
            Labels: {json.dumps(alert['labels'], indent=2)}
            """
            
            # Enviar email (implementación simplificada)
            # En producción usar librerías como sendgrid, ses, etc.
            return True
        except Exception as e:
            print(f"Error sending email alert: {e}")
            return False

class SlackAlertChannel(AlertChannel):
    """Canal de alertas por Slack"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def send_alert(self, alert: Dict[str, Any]) -> bool:
        try:
            color = {
                'critical': '#FF0000',
                'warning': '#FFA500', 
                'info': '#0000FF'
            }.get(alert['severity'], '#808080')
            
            payload = {
                "attachments": [{
                    "color": color,
                    "title": f"{alert['severity'].upper()}: {alert['summary']}",
                    "text": alert['description'],
                    "fields": [
                        {"title": "Alert", "value": alert['alert_name'], "short": True},
                        {"title": "Timestamp", "value": alert['timestamp'], "short": True}
                    ]
                }]
            }
            
            response = requests.post(self.webhook_url, json=payload)
            return response.status_code == 200
        except Exception as e:
            print(f"Error sending Slack alert: {e}")
            return False

class AlertManager:
    """Gestor de alertas"""
    
    def __init__(self):
        self.channels = []
        self.alert_history = []
    
    def add_channel(self, channel: AlertChannel):
        self.channels.append(channel)
    
    async def send_alert(self, alert: Dict[str, Any]):
        """Envía alerta a todos los canales configurados"""
        self.alert_history.append(alert)
        
        for channel in self.channels:
            try:
                await channel.send_alert(alert)
            except Exception as e:
                print(f"Error in alert channel: {e}")
    
    def get_alert_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Obtiene historial de alertas"""
        # Filtrar por tiempo (implementación simplificada)
        return self.alert_history[-100:]  # Últimas 100 alertas
```

## 📊 Dashboards y Visualización

### Dashboard Principal
```yaml
# grafana_dashboard.json (estructura simplificada)
Dashboard: "Band Steering System Overview"
Panels:
  - Title: "System Health"
    Type: "stat"
    Metrics:
      - "up{job='band-steering-api'}"
      - "rate(band_steering_analysis_requests_total[5m])"
      - "band_steering_active_analyses"
    
  - Title: "Analysis Performance"
    Type: "graph"
    Metrics:
      - "histogram_quantile(0.95, band_steering_analysis_duration_seconds)"
      - "histogram_quantile(0.50, band_steering_analysis_duration_seconds)"
    
  - Title: "BTM Detection Accuracy"
    Type: "gauge"
    Metrics:
      - "band_steering_btm_detection_accuracy"
    Thresholds:
      - Green: "> 0.95"
      - Yellow: "0.90 - 0.95"
      - Red: "< 0.90"
    
  - Title: "Compliance Score Distribution"
    Type: "heatmap"
    Metrics:
      - "band_steering_compliance_score_distribution"
    
  - Title: "Error Rate by Component"
    Type: "table"
    Metrics:
      - "rate(band_steering_analysis_requests_total{status='error'}[1h]) by (component)"
    
  - Title: "Resource Utilization"
    Type: "graph"
    Metrics:
      - "band_steering_memory_usage_bytes"
      - "rate(process_cpu_seconds_total[5m])"
      - "process_open_fds"
```

### Dashboard de Calidad de Datos
```yaml
Dashboard: "Data Quality Monitoring"
Panels:
  - Title: "Data Completeness Score"
    Type: "stat"
    Metrics:
      - "band_steering_data_quality_score{metric_type='completeness'}"
    
  - Title: "Analysis Accuracy Trend"
    Type: "graph"
    Metrics:
      - "band_steering_btm_detection_accuracy"
      - "avg_over_time(band_steering_user_satisfaction_score[1h])"
    
  - Title: "Device Vendor Distribution"
    Type: "pie"
    Metrics:
      - "sum by (vendor) (band_steering_device_analysis_count)"
    
  - Title: "Steering Pattern Success Rates"
    Type: "bar"
    Metrics:
      - "rate(band_steering_pattern_frequency{success_status='success'}[1h]) by (pattern_type)"
    
  - Title: "Processing Queue Status"
    Type: "graph"
    Metrics:
      - "band_steering_active_analyses"
      - "rate(band_steering_analysis_requests_total[5m])"
```

## 🔧 Health Checks y SLIs/SLOs

### Health Checks
```python
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import asyncio
import time

health_router = APIRouter(prefix="/health", tags=["health"])

class HealthChecker:
    """Sistema de health checks"""
    
    def __init__(self):
        self.checks = {}
    
    def register_check(self, name: str, check_func):
        """Registra un health check"""
        self.checks[name] = check_func
    
    async def run_all_checks(self) -> Dict[str, Any]:
        """Ejecuta todos los health checks"""
        results = {}
        overall_healthy = True
        
        for name, check_func in self.checks.items():
            try:
                start_time = time.time()
                result = await check_func()
                duration = time.time() - start_time
                
                results[name] = {
                    "status": "healthy" if result else "unhealthy",
                    "duration_ms": round(duration * 1000, 2),
                    "timestamp": time.time()
                }
                
                if not result:
                    overall_healthy = False
                    
            except Exception as e:
                results[name] = {
                    "status": "error",
                    "error": str(e),
                    "timestamp": time.time()
                }
                overall_healthy = False
        
        return {
            "status": "healthy" if overall_healthy else "unhealthy",
            "checks": results,
            "timestamp": time.time()
        }

# Instancia global
health_checker = HealthChecker()

# Health checks específicos
async def database_health_check() -> bool:
    """Verifica conectividad a base de datos"""
    try:
        # Ejecutar query simple
        # result = await database.execute("SELECT 1")
        return True
    except:
        return False

async def qdrant_health_check() -> bool:
    """Verifica conectividad a Qdrant"""
    try:
        # Verificar conexión a Qdrant
        # client.get_collections()
        return True
    except:
        return False

async def analysis_pipeline_health_check() -> bool:
    """Verifica que el pipeline de análisis funcione"""
    try:
        # Verificar que los componentes críticos respondan
        return True
    except:
        return False

# Registrar health checks
health_checker.register_check("database", database_health_check)
health_checker.register_check("qdrant", qdrant_health_check)
health_checker.register_check("analysis_pipeline", analysis_pipeline_health_check)

@health_router.get("/")
async def health_check():
    """Health check general"""
    results = await health_checker.run_all_checks()
    
    if results["status"] == "healthy":
        return results
    else:
        raise HTTPException(status_code=503, detail=results)

@health_router.get("/ready")
async def readiness_check():
    """Readiness / health check (platform-neutral)"""
    # Verificar que el sistema esté listo para recibir tráfico
    return {"status": "ready", "timestamp": time.time()}

@health_router.get("/live")
async def liveness_check():
    """Liveness / health check (platform-neutral)"""
    # Verificar que el proceso esté vivo
    return {"status": "alive", "timestamp": time.time()}
```

### SLIs y SLOs
```yaml
Service Level Indicators (SLIs):
  Availability:
    - Metric: "up{job='band-steering-api'}"
    - Measurement: "Percentage of time service responds to health checks"
    
  Latency:
    - Metric: "histogram_quantile(0.95, band_steering_analysis_duration_seconds)"
    - Measurement: "95th percentile of analysis completion time"
    
  Error Rate:
    - Metric: "rate(band_steering_analysis_requests_total{status='error'}[5m])"
    - Measurement: "Percentage of failed analysis requests"
    
  Accuracy:
    - Metric: "band_steering_btm_detection_accuracy"
    - Measurement: "Percentage of correctly detected BTM codes"

Service Level Objectives (SLOs):
  Availability SLO:
    - Target: 99.5% uptime
    - Measurement Window: 30 days
    - Error Budget: 0.5% (3.6 hours/month)
    
  Latency SLO:
    - Target: 95% of analyses complete within 30 seconds
    - Measurement Window: 7 days
    - Error Budget: 5% of requests can exceed 30 seconds
    
  Error Rate SLO:
    - Target: <2% error rate
    - Measurement Window: 24 hours
    - Error Budget: 2% of requests can fail
    
  Accuracy SLO:
    - Target: >95% BTM detection accuracy
    - Measurement Window: 7 days
    - Error Budget: 5% margin for accuracy degradation
```

---

**Próxima fase**: Seguridad y Cumplimiento Normativo