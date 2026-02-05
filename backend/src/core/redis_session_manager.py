"""
Gestor de sesiones con persistencia en Redis.
Permite que las sesiones sobrevivan reinicios del servidor y funcionen con múltiples instancias.
"""
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from ..models.schemas import AgentState, Message
import redis
import ssl
from ..settings import settings


class RedisSessionManager:
    """
    Gestor de sesiones que usa Redis para persistencia.
    Thread-safe y permite persistencia entre reinicios del servidor.
    """
    
    def __init__(self, redis_url: Optional[str] = None, ttl_seconds: int = 86400):
        """
        Inicializa el gestor de sesiones con Redis.
        
        Args:
            redis_url: URL de conexión a Redis (por defecto: settings.redis_url)
            ttl_seconds: Tiempo de vida de las sesiones en segundos (por defecto: 24 horas)
        """
        self.redis_url = redis_url or settings.redis_url
        self.ttl_seconds = ttl_seconds
        
        # Construir URL de Redis (soporta formato Upstash)
        redis_connection_url = self._build_redis_url(self.redis_url, settings.redis_token)
        
        # Si no hay URL de Redis, usar fallback en memoria directamente
        if not redis_connection_url:
            self.redis_available = False
            self.redis_client = None
            self._fallback_sessions: Dict[str, AgentState] = {}
            return
        
        try:
            # Intentar conectar a Redis
            
            # Configurar SSL si es rediss:// (Redis con SSL)
            # Para Heroku Redis y otros servicios con certificados autofirmados
            ssl_params = {}
            if redis_connection_url.startswith('rediss://'):
                # Deshabilitar verificación de certificados para certificados autofirmados
                ssl_params = {
                    'ssl_cert_reqs': ssl.CERT_NONE,
                    'ssl_check_hostname': False
                }
            
            self.redis_client = redis.from_url(
                redis_connection_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                **ssl_params
            )
            # Probar conexión
            self.redis_client.ping()
            self.redis_available = True
        except Exception as e:
            self.redis_available = False
            self.redis_client = None
            # Fallback: usar diccionario en memoria
            self._fallback_sessions: Dict[str, AgentState] = {}
    
    def _build_redis_url(self, redis_url: Optional[str], redis_token: Optional[str]) -> Optional[str]:
        """
        Construye la URL de conexión a Redis.
        Soporta formato estándar y formato Upstash (REST URL + Token).
        
        Upstash proporciona:
            pass
        - REST URL: https://xxx.upstash.io (para REST API)
        - Redis URL: redis://xxx.upstash.io:6379 (para Redis protocol)
        - Token: para autenticación
        """
        if not redis_url:
            return None
        
        # Si ya es una URL de Redis válida (redis:// o rediss://), usarla directamente
        if redis_url.startswith('redis://') or redis_url.startswith('rediss://'):
            return redis_url
        
        # Si es una URL HTTPS (formato Upstash REST), construir URL de Redis
        if redis_url.startswith('https://') and redis_token:
            # Extraer el host de la URL REST
            from urllib.parse import urlparse
            parsed = urlparse(redis_url)
            host = parsed.hostname
            
            # Upstash requiere SSL para Redis protocol
            # Construir URL: rediss://default:TOKEN@HOST:6379
            redis_protocol_url = f"rediss://default:{redis_token}@{host}:6379"
            return redis_protocol_url
        
        # Si no se puede determinar el formato, retornar None
        return None
    
    def _mask_redis_url(self, url: str) -> str:
        """Enmascara la contraseña en la URL de Redis para logging seguro."""
        try:
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(url)
            if parsed.password:
                # Reemplazar contraseña con asteriscos
                masked_netloc = f"{parsed.username}:{'*' * len(parsed.password)}@{parsed.hostname}"
                if parsed.port:
                    masked_netloc += f":{parsed.port}"
                masked_parsed = parsed._replace(netloc=masked_netloc)
                return urlunparse(masked_parsed)
            return url
        except Exception:
            # Si hay error al parsear, retornar URL parcialmente enmascarada
            if "@" in url:
                parts = url.split("@")
                if len(parts) == 2:
                    return f"{parts[0].split(':')[0]}:****@{parts[1]}"
            return url
    
    def _serialize_state(self, state: AgentState) -> str:
        """Serializa un AgentState a JSON."""
        return json.dumps({
            "session_id": state.session_id,
            "user_id": state.user_id,
            "context_window": [
                {"role": msg.role, "content": msg.content}
                for msg in state.context_window
            ],
            "variables": state.variables,
            "results": state.results,
        })
    
    def _deserialize_state(self, data: str, session_id: str) -> AgentState:
        """Deserializa JSON a AgentState."""
        obj = json.loads(data)
        return AgentState(
            session_id=obj.get("session_id", session_id),
            user_id=obj.get("user_id"),
            context_window=[
                Message(role=msg["role"], content=msg["content"])
                for msg in obj.get("context_window", [])
            ],
            variables=obj.get("variables", {}),
            results=obj.get("results", {}),
        )
    
    def get_session(self, session_id: str, user_id: Optional[str] = None) -> AgentState:
        """
        Obtiene o crea una sesión. Si la sesión no existe, se crea una nueva.
        """
        if self.redis_available and self.redis_client:
            try:
                # Intentar obtener de Redis
                cached_data = self.redis_client.get(f"session:{session_id}")
                if cached_data:
                    state = self._deserialize_state(cached_data, session_id)
                    # Actualizar user_id si se proporciona
                    if user_id:
                        state.user_id = user_id
                        self.update_session(session_id, state)
                    return state
            except Exception as e:
                pass
        
        # Crear nueva sesión (Redis no disponible o sesión no existe)
        new_state = AgentState(session_id=session_id, user_id=user_id)
        
        # Guardar en Redis si está disponible
        if self.redis_available and self.redis_client:
            try:
                self.update_session(session_id, new_state)
            except Exception as e:
                pass
        else:
            # Fallback: guardar en memoria
            self._fallback_sessions[session_id] = new_state
        
        return new_state
    
    def update_session(self, session_id: str, state: AgentState):
        """
        Actualiza el estado de una sesión existente.
        """
        if self.redis_available and self.redis_client:
            try:
                serialized = self._serialize_state(state)
                # Guardar en Redis con TTL
                self.redis_client.setex(
                    f"session:{session_id}",
                    self.ttl_seconds,
                    serialized
                )
            except Exception as e:
                # Fallback: guardar en memoria
                self._fallback_sessions[session_id] = state
        else:
            # Fallback: guardar en memoria
            self._fallback_sessions[session_id] = state
    
    def clear_session(self, session_id: str):
        """Limpia una sesión específica."""
        if self.redis_available and self.redis_client:
            try:
                self.redis_client.delete(f"session:{session_id}")
            except Exception as e:
                # Fallback: limpiar de memoria
                if session_id in self._fallback_sessions:
                    self._fallback_sessions[session_id].context_window = []
        else:
            # Fallback: limpiar de memoria
            if session_id in self._fallback_sessions:
                self._fallback_sessions[session_id].context_window = []
    
    def delete_session(self, session_id: str):
        """Elimina completamente una sesión."""
        if self.redis_available and self.redis_client:
            try:
                self.redis_client.delete(f"session:{session_id}")
            except Exception as e:
                # Fallback: eliminar de memoria
                self._fallback_sessions.pop(session_id, None)
        else:
            # Fallback: eliminar de memoria
            self._fallback_sessions.pop(session_id, None)
    
    def get_all_sessions(self) -> Dict[str, AgentState]:
        """
        Obtiene todas las sesiones (útil para debugging).
        Solo funciona con fallback en memoria, Redis requiere scan.
        """
        if not self.redis_available:
            return self._fallback_sessions.copy()
        
        # Para Redis, sería necesario hacer SCAN, pero no es crítico
        return {}

