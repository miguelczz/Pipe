"""
Observability API - Langfuse metrics and data
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
    """Gets Langfuse client if configured."""
    if not LANGFUSE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Langfuse is not installed")
    
    if not all([settings.langfuse_host, settings.langfuse_public_key, settings.langfuse_secret_key]):
        raise HTTPException(status_code=503, detail="Langfuse is not configured")
    
    return Langfuse(
        host=settings.langfuse_host,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
    )


@router.get("/metrics")
async def get_metrics() -> Dict[str, Any]:
    """
    Gets aggregated metrics from Langfuse.
    
    Returns:
        Dictionary with usage, cost and performance metrics
    """
    try:
        client = get_langfuse_client()
        
        # Get recent traces (last 24 hours)
        # Note: Langfuse API may vary depending on the version
        # Here we use a generic approach that works with most versions
        
        # Calculate timestamp from 24 hours ago
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        # Try to get data using Langfuse client
        # Since the API can vary, we use try/except for each call
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
            # 1. Get Observations (Generations) FIRST for rich data
            # This gives us the actual cost and model per trace_id
            observations = client.fetch_observations(limit=100, type="GENERATION")
            
            obs_list = []
            if observations and hasattr(observations, 'data'):
                obs_list = observations.data
            
            # Group data by trace_id
            trace_map = {} # { trace_id: { cost: 0.0, tokens: 0, models: set() } }
            models_usage = {} # For global metrics
            tags_usage = {} # For tag metrics (routing vs rag vs synthesis)
            
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

                # Group Models Global
                if o_model not in models_usage:
                    models_usage[o_model] = {"count": 0, "cost": 0.0, "tokens": 0}
                models_usage[o_model]["count"] += 1
                models_usage[o_model]["cost"] += o_cost
                models_usage[o_model]["tokens"] += o_tokens

                # Group by Trace (only cost, model, tokens - tags are in the trace)
                if t_id:
                    if t_id not in trace_map:
                        trace_map[t_id] = {"cost": 0.0, "models": set(), "tokens": 0}
                    trace_map[t_id]["cost"] += o_cost
                    trace_map[t_id]["tokens"] += o_tokens
                    if o_model:
                        trace_map[t_id]["models"].add(o_model)

            # 2. Get Traces (for time, status, tags and sessionId)
            # IMPORTANT: Langfuse stores tags and sessionId at TRACE level, not observation
            traces = client.fetch_traces(limit=50)
            trace_list = []
            if traces and hasattr(traces, 'data'):
                trace_list = traces.data

            metrics["total_traces"] = len(trace_list)
            
            # Accumulator variables for traces
            total_latency = 0
            errors = 0
            recent_traces_data = []
            
            # Process enriched traces
            for trace in trace_list:
                t_id = getattr(trace, 'id', 'unknown')
                
                # Basic data
                t_latency = getattr(trace, 'latency', 0) or 0
                
                # Cost and model: from observations (more precise)
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
                # If the name is generic and we have a model, use the model
                if "litellm" in t_name.lower() and t_models_str != "Unknown":
                    t_name = t_models_str
                
                # Session ID: Langfuse stores as sessionId (camelCase)
                # The Python SDK may map it to session_id or sessionId
                t_session_id = (
                    getattr(trace, 'session_id', None)
                    or getattr(trace, 'sessionId', None)
                )
                if not t_session_id:
                    # Fallback: search in metadata
                    t_metadata = getattr(trace, 'metadata', {}) or {}
                    if isinstance(t_metadata, dict):
                        t_session_id = t_metadata.get('session_id') or t_metadata.get('sessionId')

                # Tags: Langfuse stores at TRACE level (not observation)
                t_tags = getattr(trace, 'tags', []) or []
                
                # Add tags to global tags_usage (with trace cost data)
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
                
                # Detect errors
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
            
            # Assign global counters calculated from observations (most precise)
            metrics["total_cost_usd"] = round(total_cost_obs, 6)
            metrics["total_tokens"] = total_tokens_obs
            metrics["models_used"] = models_usage
            metrics["tags_usage"] = tags_usage

            # Calculate final averages
            if metrics["total_traces"] > 0:
                avg_lat = total_latency / metrics["total_traces"]
                metrics["avg_latency_ms"] = round(avg_lat * 1000, 2) if avg_lat < 100 else round(avg_lat, 2)
                metrics["error_rate"] = round((errors / metrics["total_traces"]) * 100, 2)

        except Exception as e:
            logger.warning(f"Error fetching Langfuse metrics: {e}")
            metrics["error"] = str(e)
            # Ensure valid structure
            metrics["models_used"] = {}
            metrics["tags_usage"] = {}
        
        return metrics
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching observability metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching metrics: {str(e)}")


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Checks if Langfuse is accessible.
    
    Returns:
        Connection status with Langfuse
    """
    try:
        client = get_langfuse_client()
        
        # Try to make a simple call to verify connectivity
        try:
            # Check that the client is initialized
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
