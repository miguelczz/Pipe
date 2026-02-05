from ..models.schemas import AgentState
from datetime import datetime
from typing import Optional, Dict, Any
import threading
from ..settings import settings


# GlobalState eliminado - no se usaba en ningún lugar del código
# El estado se maneja ahora a través de GraphState en src/core/graph_state.py
# que implementa el patrón State correctamente para compartir estado entre nodos

class SessionManager:
    """
    Gestor de sesiones que mantiene el estado por session_id.
    Thread-safe y permite persistencia de sesiones.
    
    Nota: FastAPI manejará la instancia única mediante Dependency Injection.
    No es necesario usar Singleton - FastAPI crea la instancia una vez y la reutiliza.
    """
    _lock = threading.Lock()
    
    def __init__(self):
        self._sessions: Dict[str, AgentState] = {}
        self._session_locks: Dict[str, threading.Lock] = {}
        self._lock = threading.Lock()
    
    def get_session(self, session_id: str, user_id: Optional[str] = None) -> AgentState:
        """
        Obtiene o crea una sesión. Si la sesión no existe, se crea una nueva.
        """
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = AgentState(session_id=session_id, user_id=user_id)
                self._session_locks[session_id] = threading.Lock()
        
        return self._sessions[session_id]
    
    def update_session(self, session_id: str, state: AgentState):
        """
        Actualiza el estado de una sesión existente.
        """
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = state
                self._session_locks[session_id] = threading.Lock()
            else:
                self._sessions[session_id] = state
    
    def get_session_lock(self, session_id: str) -> threading.Lock:
        """Obtiene el lock de una sesión específica."""
        with self._lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = threading.Lock()
            return self._session_locks[session_id]
    
    def clear_session(self, session_id: str):
        """Limpia una sesión específica."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].context_window = []
    
    def delete_session(self, session_id: str):
        """Elimina completamente una sesión."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
            if session_id in self._session_locks:
                del self._session_locks[session_id]


# ============================================================================
# Instancias únicas para Dependency Injection de FastAPI
# ============================================================================

# Instancias únicas que se reutilizan (equivalente a Singleton pero más explícito)
_session_manager_instance: Optional[SessionManager] = None
_instance_lock = threading.Lock()


def get_session_manager():
    """
    Dependency para FastAPI que proporciona una instancia única de SessionManager.
    Intenta usar RedisSessionManager si Redis está disponible, sino usa SessionManager en memoria.
    
    Ventajas:
        pass
    - Persistencia entre reinicios si Redis está disponible
    - Fallback automático a memoria si Redis no está disponible
    - Thread-safe y testeable
    
    Uso:
        @router.post("/endpoint")
        def endpoint(session_mgr = Depends(get_session_manager)):
            ...
    """
    global _session_manager_instance
    if _session_manager_instance is None:
        with _instance_lock:
            if _session_manager_instance is None:
                # Intentar usar Redis si está configurado
                try:
                    from .redis_session_manager import RedisSessionManager
                    _session_manager_instance = RedisSessionManager()
                    # Si Redis no está disponible, RedisSessionManager usa fallback automático
                except Exception as e:
                    _session_manager_instance = SessionManager()
    return _session_manager_instance