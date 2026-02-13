from ..models.schemas import AgentState
from datetime import datetime
from typing import Optional, Dict, Any
import threading
from ..settings import settings


# GlobalState removed - not used anywhere in the code
# State is now managed through GraphState in src/core/graph_state.py
# which implements the State pattern correctly for sharing state between nodes

class SessionManager:
    """
    Session manager that maintains state by session_id.
    Thread-safe and allows session persistence.
    
    Note: FastAPI will handle the single instance via Dependency Injection.
    No need to use Singleton - FastAPI creates the instance once and reuses it.
    """
    _lock = threading.Lock()
    
    def __init__(self):
        self._sessions: Dict[str, AgentState] = {}
        self._session_locks: Dict[str, threading.Lock] = {}
        self._lock = threading.Lock()
    
    def get_session(self, session_id: str, user_id: Optional[str] = None) -> AgentState:
        """
        Gets or creates a session. If the session does not exist, a new one is created.
        """
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = AgentState(session_id=session_id, user_id=user_id)
                self._session_locks[session_id] = threading.Lock()
        
        return self._sessions[session_id]
    
    def update_session(self, session_id: str, state: AgentState):
        """
        Updates the state of an existing session.
        """
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = state
                self._session_locks[session_id] = threading.Lock()
            else:
                self._sessions[session_id] = state
    
    def get_session_lock(self, session_id: str) -> threading.Lock:
        """Gets the lock for a specific session."""
        with self._lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = threading.Lock()
            return self._session_locks[session_id]
    
    def clear_session(self, session_id: str):
        """Clears a specific session."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].context_window = []
    
    def delete_session(self, session_id: str):
        """Completely deletes a session."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
            if session_id in self._session_locks:
                del self._session_locks[session_id]


# ============================================================================
# Single instances for FastAPI Dependency Injection
# ============================================================================

# Single instances that are reused (equivalent to Singleton but more explicit)
_session_manager_instance: Optional[SessionManager] = None
_instance_lock = threading.Lock()


def get_session_manager():
    """
    FastAPI Dependency that provides a single instance of SessionManager.
    Attempts to use RedisSessionManager if Redis is available, otherwise uses in-memory SessionManager.
    
    Advantages:
    - Persistence between restarts if Redis is available
    - Automatic fallback to memory if Redis is not available
    - Thread-safe and testable
    
    Usage:
        @router.post("/endpoint")
        def endpoint(session_mgr = Depends(get_session_manager)):
            ...
    """
    global _session_manager_instance
    if _session_manager_instance is None:
        with _instance_lock:
            if _session_manager_instance is None:
                # Attempt to use Redis if configured
                try:
                    from .redis_session_manager import RedisSessionManager
                    _session_manager_instance = RedisSessionManager()
                    # If Redis is not available, RedisSessionManager uses automatic fallback
                except Exception as e:
                    _session_manager_instance = SessionManager()
    return _session_manager_instance