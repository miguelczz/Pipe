"""
Redis-based caching system to improve performance.
Provides caching utilities without managing logging.
"""
import json
import hashlib
from functools import wraps
from typing import Any, Optional, Callable, TYPE_CHECKING
from ..settings import settings

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    # Create a stub so code works without redis
    class RedisStub:
        class Redis:
            pass
        class ConnectionError(Exception):
            pass
        class TimeoutError(Exception):
            pass
        class RedisError(Exception):
            pass
        @staticmethod
        def from_url(*args, **kwargs):
            raise ImportError("Redis is not installed")
    redis = RedisStub()  # type: ignore

if TYPE_CHECKING:
    from redis import Redis

# Global instance of Redis client
_redis_client: Optional[Any] = None
_cache_enabled = True


def get_redis_client() -> Optional[Any]:
    """
    Gets or creates the Redis client instance.
    Returns None if Redis is not available or is disabled.
    """
    global _redis_client, _cache_enabled
    
    if not REDIS_AVAILABLE:
        _cache_enabled = False
        return None
    
    if not settings.cache_enabled:
        return None
    
    # Build Redis URL (supports Upstash format)
    redis_connection_url = _build_redis_url(settings.redis_url, settings.redis_token)
    
    # If no Redis URL, disable cache
    if not redis_connection_url:
        _cache_enabled = False
        return None
    
    if _redis_client is None:
        try:
            
            # Configure SSL if it is rediss:// (Redis with SSL)
            # For Heroku Redis and other services with self-signed certificates
            import ssl
            ssl_params = {}
            if redis_connection_url.startswith('rediss://'):
                # Disable certificate verification for self-signed certificates
                ssl_params = {
                    'ssl_cert_reqs': ssl.CERT_NONE,
                    'ssl_check_hostname': False
                }
            
            _redis_client = redis.from_url(
                redis_connection_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                **ssl_params
            )
            # Test connection
            _redis_client.ping()
            _cache_enabled = True
        except (redis.ConnectionError, redis.TimeoutError, Exception) as e:
            _cache_enabled = False
            _redis_client = None
    
    return _redis_client


def _build_redis_url(redis_url: Optional[str], redis_token: Optional[str]) -> Optional[str]:
    """
    Builds the Redis connection URL.
    Supports standard format and Upstash format (REST URL + Token).
    """
    if not redis_url:
        return None
    
    # If it is already a valid Redis URL (redis:// or rediss://), use it directly
    if redis_url.startswith('redis://') or redis_url.startswith('rediss://'):
        return redis_url
    
    # If it is an HTTPS URL (Upstash REST format), build Redis URL
    if redis_url.startswith('https://') and redis_token:
        # Extract host from REST URL
        from urllib.parse import urlparse
        parsed = urlparse(redis_url)
        host = parsed.hostname
        
        # Upstash uses port 6379 by default for Redis protocol
        # Build URL: rediss://default:TOKEN@HOST:6379
        redis_protocol_url = f"rediss://default:{redis_token}@{host}:6379"
        return redis_protocol_url
    
    # If format cannot be determined, return None
    return None


def _mask_redis_url(url: str) -> str:
    """Masks password in Redis URL for secure logging."""
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


class CacheManager:
    """
    Cache manager that provides methods to store and retrieve data.
    """
    
    def __init__(self, redis_client: Optional[Any] = None):
        """
        Initializes the cache manager.
        
        Args:
            redis_client: Redis client (optional, automatically obtained if not provided)
        """
        self.redis_client = redis_client or get_redis_client()
        self.enabled = self.redis_client is not None
    
    def get_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """
        Generates a unique cache key based on arguments.
        
        Args:
            prefix: Prefix for the key (e.g., "rag", "ip", "dns")
            *args: Positional arguments
            **kwargs: Keyword arguments
        
        Returns:
            Unique cache key
        
        Note: If conversation_context is in kwargs, it is included in the hash
        so queries with different context have different keys.
        """
        # Create a hash of arguments
        # IMPORTANT: conversation_context is included in the hash to differentiate queries
        key_data = json.dumps(
            {"args": args, "kwargs": kwargs},
            sort_keys=True,
            ensure_ascii=False
        )
        key_hash = hashlib.md5(key_data.encode()).hexdigest()
        return f"{prefix}:{key_hash}"
    
    def get(self, key: str) -> Optional[Any]:
        """
        Gets a value from cache.
        
        Args:
            key: Cache key
        
        Returns:
            Stored value or None if it doesn't exist or error occurs
        """
        if not self.enabled:
            return None
        
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            if REDIS_AVAILABLE and isinstance(e, redis.RedisError):
                pass
            elif not isinstance(e, json.JSONDecodeError):
                pass
            return None
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        """
        Stores a value in cache with a TTL (Time To Live).
        
        Args:
            key: Cache key
            value: Value to store (must be JSON serializable)
            ttl: Time to live in seconds (default: 3600 = 1 hour)
        """
        if not self.enabled:
            return
        
        try:
            serialized = json.dumps(value, ensure_ascii=False)
            self.redis_client.setex(key, ttl, serialized)
        except Exception as e:
            if REDIS_AVAILABLE and isinstance(e, redis.RedisError):
                pass
            elif not isinstance(e, TypeError):
                pass
    
    def delete(self, key: str):
        """
        Deletes a key from cache.
        
        Args:
            key: Key to delete
        """
        if not self.enabled:
            return
        
        try:
            self.redis_client.delete(key)
        except Exception as e:
            if REDIS_AVAILABLE and isinstance(e, redis.RedisError):
                pass
    
    def clear_prefix(self, prefix: str):
        """
        Deletes all keys starting with a prefix.
        
        Args:
            prefix: Prefix of keys to delete
        """
        if not self.enabled:
            return
        
        try:
            pattern = f"{prefix}:*"
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
        except Exception as e:
            if REDIS_AVAILABLE and isinstance(e, redis.RedisError):
                pass


# Global instance of cache manager
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """
    Gets the global instance of the cache manager.
    
    Returns:
        CacheManager instance
    """
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


def cache_result(prefix: str, ttl: int = 3600):
    """
    Decorator to cache function results.
    
    Args:
        prefix: Prefix for cache keys
        ttl: Time to live in seconds
    
    Example:
        @cache_result("rag", ttl=3600)
        def query(text: str):
            # ... logic ...
            return result
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_manager = get_cache_manager()
            
            # If cache is disabled, execute function directly
            if not cache_manager.enabled:
                return func(*args, **kwargs)
            
            # For instance methods, exclude 'self' from arguments for cache key
            # Only use real function arguments (without self)
            cache_args = args[1:] if args and hasattr(args[0], '__class__') else args
            
            # Generate cache key
            cache_key = cache_manager.get_cache_key(prefix, *cache_args, **kwargs)
            
            # Attempt to get from cache
            cached = cache_manager.get(cache_key)
            if cached is not None:
                return cached
            
            # Cache miss: execute function and store result
            result = func(*args, **kwargs)
            
            # Store in cache (only if no error)
            if result and not (isinstance(result, dict) and result.get("error")):
                cache_manager.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator
