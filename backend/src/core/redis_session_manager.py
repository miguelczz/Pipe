"""
Session manager with persistence in Redis.
Allows sessions to survive server restarts and work with multiple instances.
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
    Session manager that uses Redis for persistence.
    Thread-safe and allowed persistence between server restarts.
    """
    
    def __init__(self, redis_url: Optional[str] = None, ttl_seconds: int = 86400):
        """
        Initializes the session manager with Redis.
        
        Args:
            redis_url: Redis connection URL (default: settings.redis_url)
            ttl_seconds: Life time of sessions in seconds (default: 24 hours)
        """
        self.redis_url = redis_url or settings.redis_url
        self.ttl_seconds = ttl_seconds
        
        # Build Redis URL (supports Upstash format)
        redis_connection_url = self._build_redis_url(self.redis_url, settings.redis_token)
        
        # If no Redis URL, use in-memory fallback directly
        if not redis_connection_url:
            self.redis_available = False
            self.redis_client = None
            self._fallback_sessions: Dict[str, AgentState] = {}
            return
        
        try:
            # Attempt to connect to Redis
            
            # Configure SSL if it is rediss:// (Redis with SSL)
            # For Heroku Redis and other services with self-signed certificates
            ssl_params = {}
            if redis_connection_url.startswith('rediss://'):
                # Disable certificate verification for self-signed certificates
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
            # Test connection
            self.redis_client.ping()
            self.redis_available = True
        except Exception as e:
            self.redis_available = False
            self.redis_client = None
            # Fallback: use in-memory dictionary
            self._fallback_sessions: Dict[str, AgentState] = {}
    
    def _build_redis_url(self, redis_url: Optional[str], redis_token: Optional[str]) -> Optional[str]:
        """
        Builds the Redis connection URL.
        Supports standard format and Upstash format (REST URL + Token).
        
        Upstash provides:
        - REST URL: https://xxx.upstash.io (for REST API)
        - Redis URL: redis://xxx.upstash.io:6379 (for Redis protocol)
        - Token: for authentication
        """
        if not redis_url:
            return None
        
        # If it's already a valid Redis URL (redis:// or rediss://), use it directly
        if redis_url.startswith('redis://') or redis_url.startswith('rediss://'):
            return redis_url
        
        # If it's an HTTPS URL (Upstash REST format), build Redis URL
        if redis_url.startswith('https://') and redis_token:
            # Extract host from REST URL
            from urllib.parse import urlparse
            parsed = urlparse(redis_url)
            host = parsed.hostname
            
            # Upstash requires SSL for Redis protocol
            # Build URL: rediss://default:TOKEN@HOST:6379
            redis_protocol_url = f"rediss://default:{redis_token}@{host}:6379"
            return redis_protocol_url
        
        # If format cannot be determined, return None
        return None
    
    def _mask_redis_url(self, url: str) -> str:
        """Masks the password in the Redis URL for secure logging."""
        try:
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(url)
            if parsed.password:
                # Replace password with asterisks
                masked_netloc = f"{parsed.username}:{'*' * len(parsed.password)}@{parsed.hostname}"
                if parsed.port:
                    masked_netloc += f":{parsed.port}"
                masked_parsed = parsed._replace(netloc=masked_netloc)
                return urlunparse(masked_parsed)
            return url
        except Exception:
            # If error parsing, return partially masked URL
            if "@" in url:
                parts = url.split("@")
                if len(parts) == 2:
                    return f"{parts[0].split(':')[0]}:****@{parts[1]}"
            return url
    
    def _serialize_state(self, state: AgentState) -> str:
        """Serializes an AgentState to JSON."""
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
        """Deserializes JSON to AgentState."""
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
        Gets or creates a session. If the session does not exist, a new one is created.
        """
        if self.redis_available and self.redis_client:
            try:
                # Attempt to get from Redis
                cached_data = self.redis_client.get(f"session:{session_id}")
                if cached_data:
                    state = self._deserialize_state(cached_data, session_id)
                    # Update user_id if provided
                    if user_id:
                        state.user_id = user_id
                        self.update_session(session_id, state)
                    return state
            except Exception as e:
                pass
        
        # Create new session (Redis not available or session doesn't exist)
        new_state = AgentState(session_id=session_id, user_id=user_id)
        
        # Save in Redis if available
        if self.redis_available and self.redis_client:
            try:
                self.update_session(session_id, new_state)
            except Exception as e:
                pass
        else:
            # Fallback: save in memory
            self._fallback_sessions[session_id] = new_state
        
        return new_state
    
    def update_session(self, session_id: str, state: AgentState):
        """
        Updates the state of an existing session.
        """
        if self.redis_available and self.redis_client:
            try:
                serialized = self._serialize_state(state)
                # Save in Redis with TTL
                self.redis_client.setex(
                    f"session:{session_id}",
                    self.ttl_seconds,
                    serialized
                )
            except Exception as e:
                # Fallback: save in memory
                self._fallback_sessions[session_id] = state
        else:
            # Fallback: save in memory
            self._fallback_sessions[session_id] = state
    
    def clear_session(self, session_id: str):
        """Clears a specific session."""
        if self.redis_available and self.redis_client:
            try:
                self.redis_client.delete(f"session:{session_id}")
            except Exception as e:
                # Fallback: clear from memory
                if session_id in self._fallback_sessions:
                    self._fallback_sessions[session_id].context_window = []
        else:
            # Fallback: clear from memory
            if session_id in self._fallback_sessions:
                self._fallback_sessions[session_id].context_window = []
    
    def delete_session(self, session_id: str):
        """Completely deletes a session."""
        if self.redis_available and self.redis_client:
            try:
                self.redis_client.delete(f"session:{session_id}")
            except Exception as e:
                # Fallback: delete from memory
                self._fallback_sessions.pop(session_id, None)
        else:
            # Fallback: delete from memory
            self._fallback_sessions.pop(session_id, None)
    
    def get_all_sessions(self) -> Dict[str, AgentState]:
        """
        Gets all sessions (useful for debugging).
        Only works with in-memory fallback, Redis requires scan.
        """
        if not self.redis_available:
            return self._fallback_sessions.copy()
        
        # For Redis, SCAN would be necessary, but it's not critical
        return {}
