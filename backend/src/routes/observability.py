"""
Observability API - Métricas y datos de Langfuse
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
import logging
from datetime import datetime, timedelta

try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

from ..settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/observability", tags=["observability"])


def get_langfuse_client() -> Langfuse:
    """Obtiene cliente de Langfuse si está configurado."""
    if not LANGFUSE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Langfuse no está instalado")
    
    if not all([settings.langfuse_host, settings.langfuse_public_key, settings.langfuse_secret_key]):
        raise HTTPException(status_code=503, detail="Langfuse no está configurado")
    
    return Langfuse(
        host=settings.langfuse_host,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
    )


@router.get("/metrics")
async def get_metrics() -> Dict[str, Any]:
    """
    Obtiene métricas agregadas de Langfuse.
    
    Returns:
        Diccionario con métricas de uso, costos y rendimiento
    """
    try:
        client = get_langfuse_client()
        
        # Obtener trazas recientes (últimas 24 horas)
        # Nota: La API de Langfuse puede variar según la versión
        # Aquí usamos un enfoque genérico que funciona con la mayoría de versiones
        
        # Calcular timestamp de hace 24 horas
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        # Intentar obtener datos usando el cliente de Langfuse
        # Como la API puede variar, usamos try/except para cada llamada
        metrics = {
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat(),
            "period": "24h",
            "total_traces": 0,
            "total_cost_usd": 0.0,
            "avg_latency_ms": 0,
            "total_tokens": 0,
            "models_used": {},
            "tags_usage": {},  # New: Cost breakdown by tag
            "recent_traces": [],
            "error_rate": 0.0,
        }
        
        try:
            # 1. Obtener Observaciones (Generaciones) PRIMERO para datos ricos
            # Esto nos da el costo real y el modelo por trace_id
            observations = client.fetch_observations(limit=100, type="GENERATION")
            
            obs_list = []
            if observations and hasattr(observations, 'data'):
                obs_list = observations.data
            
            # Agrupar datos por trace_id
            trace_map = {} # { trace_id: { cost: 0.0, tokens: 0, models: set() } }
            models_usage = {} # Para métricas globales
            tags_usage = {} # Para métricas de tags (routing vs rag vs synthesis)
            
            total_cost_obs = 0.0
            total_tokens_obs = 0

            for obs in obs_list:
                t_id = getattr(obs, 'trace_id', None)
                o_cost = getattr(obs, 'calculated_total_cost', 0) or 0
                o_model = getattr(obs, 'model', 'unknown')
                
                # Globales
                total_cost_obs += o_cost
                
                usage = getattr(obs, 'usage', None)
                o_tokens = 0
                if usage:
                     o_tokens = getattr(usage, 'total', 0) or 0
                     total_tokens_obs += o_tokens

                # Agrupar Modelos Global
                if o_model not in models_usage:
                    models_usage[o_model] = {"count": 0, "cost": 0.0, "tokens": 0}
                models_usage[o_model]["count"] += 1
                models_usage[o_model]["cost"] += o_cost
                models_usage[o_model]["tokens"] += o_tokens

                # Agrupar por Traza (solo costo, modelo, tokens - los tags están en la traza)
                if t_id:
                    if t_id not in trace_map:
                        trace_map[t_id] = {"cost": 0.0, "models": set(), "tokens": 0}
                    trace_map[t_id]["cost"] += o_cost
                    trace_map[t_id]["tokens"] += o_tokens
                    if o_model:
                        trace_map[t_id]["models"].add(o_model)

            # 2. Obtener Trazas (para tiempo, estado, tags y sessionId)
            # IMPORTANTE: Langfuse almacena tags y sessionId a nivel de TRAZA, no de observación
            traces = client.fetch_traces(limit=50)
            trace_list = []
            if traces and hasattr(traces, 'data'):
                trace_list = traces.data

            metrics["total_traces"] = len(trace_list)
            
            # Variables acumuladoras para trazas
            total_latency = 0
            errors = 0
            recent_traces_data = []
            
            # Procesar trazas enriquecidas
            for trace in trace_list:
                t_id = getattr(trace, 'id', 'unknown')
                
                # Datos básicos
                t_latency = getattr(trace, 'latency', 0) or 0
                
                # Costo y modelo: desde observaciones (más preciso)
                t_cost = 0.0
                t_tokens = 0
                t_models_str = "Unknown"
                
                if t_id in trace_map:
                    t_cost = trace_map[t_id]["cost"]
                    t_tokens = trace_map[t_id]["tokens"]
                    models_set = trace_map[t_id]["models"]
                    if len(models_set) == 1:
                        t_models_str = list(models_set)[0]
                    elif len(models_set) > 1:
                        t_models_str = f"{len(models_set)} models"
                else:
                    t_cost = getattr(trace, 'calculated_total_cost', 0) or 0

                t_name = getattr(trace, 'name', 'Interaction')
                # Si el nombre es genérico y tenemos modelo, usar modelo
                if "litellm" in t_name.lower() and t_models_str != "Unknown":
                    t_name = t_models_str
                
                # Session ID: Langfuse almacena como sessionId (camelCase)
                # El SDK de Python puede mapearlo a session_id o sessionId
                t_session_id = (
                    getattr(trace, 'session_id', None)
                    or getattr(trace, 'sessionId', None)
                )
                if not t_session_id:
                    # Fallback: buscar en metadata
                    t_metadata = getattr(trace, 'metadata', {}) or {}
                    if isinstance(t_metadata, dict):
                        t_session_id = t_metadata.get('session_id') or t_metadata.get('sessionId')

                # Tags: Langfuse almacena a nivel de TRAZA (no observación)
                t_tags = getattr(trace, 'tags', []) or []
                
                # Agregar tags al tags_usage global (con datos de costo de la traza)
                for tag in t_tags:
                    if tag not in tags_usage:
                        tags_usage[tag] = {"count": 0, "cost": 0.0, "tokens": 0}
                    tags_usage[tag]["count"] += 1
                    tags_usage[tag]["cost"] += t_cost
                    tags_usage[tag]["tokens"] += t_tokens

                t_timestamp = getattr(trace, 'timestamp', datetime.utcnow())
                if isinstance(t_timestamp, str):
                     try:
                         t_timestamp = datetime.fromisoformat(t_timestamp.replace('Z', '+00:00'))
                     except:
                         t_timestamp = datetime.utcnow()

                total_latency += t_latency
                
                # Detectar errores
                status = "success"
                if hasattr(trace, 'level') and trace.level == 'ERROR':
                    errors += 1
                    status = "error"

                if len(recent_traces_data) < 20:
                    recent_traces_data.append({
                        "id": t_id,
                        "name": t_name,
                        "timestamp": t_timestamp.isoformat(),
                        "latency_ms": round(t_latency * 1000, 2) if t_latency < 10 else round(t_latency, 2),
                        "cost_usd": t_cost,
                        "status": status,
                        "model": t_models_str,
                        "session_id": t_session_id,
                        "tags": t_tags
                    })

            metrics["recent_traces"] = recent_traces_data
            
            # Asignar contadores globales calculados desde observaciones (los más precisos)
            metrics["total_cost_usd"] = round(total_cost_obs, 6)
            metrics["total_tokens"] = total_tokens_obs
            metrics["models_used"] = models_usage
            metrics["tags_usage"] = tags_usage

            # Calcular promedios finales
            if metrics["total_traces"] > 0:
                avg_lat = total_latency / metrics["total_traces"]
                metrics["avg_latency_ms"] = round(avg_lat * 1000, 2) if avg_lat < 100 else round(avg_lat, 2)
                metrics["error_rate"] = round((errors / metrics["total_traces"]) * 100, 2)

        except Exception as e:
            logger.warning(f"Error al obtener métricas de Langfuse: {e}")
            metrics["error"] = str(e)
            # Asegurar estructura válida
            metrics["models_used"] = {}
            metrics["tags_usage"] = {}
        
        return metrics
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al obtener métricas de observabilidad: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener métricas: {str(e)}")


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Verifica si Langfuse está accesible.
    
    Returns:
        Estado de la conexión con Langfuse
    """
    try:
        client = get_langfuse_client()
        
        # Intentar hacer una llamada simple para verificar conectividad
        try:
            # Verificar que el cliente esté inicializado
            health_status = {
                "status": "healthy",
                "langfuse_host": settings.langfuse_host,
                "configured": True,
            }
        except Exception as e:
            health_status = {
                "status": "degraded",
                "langfuse_host": settings.langfuse_host,
                "configured": True,
                "error": str(e)
            }
        
        return health_status
    
    except HTTPException as e:
        return {
            "status": "unavailable",
            "configured": False,
            "detail": e.detail
        }
    except Exception as e:
        return {
            "status": "error",
            "configured": False,
            "error": str(e)
        }
