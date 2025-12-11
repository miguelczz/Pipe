"""
Sistema de cache con Redis para mejorar el rendimiento
"""
import json
import hashlib
import logging
from functools import wraps
from typing import Any, Optional, Callable, TYPE_CHECKING
from ..settings import settings

logger = logging.getLogger(__name__)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    # Crear un stub para que el código funcione sin redis
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
            raise ImportError("Redis no está instalado")
    redis = RedisStub()  # type: ignore
    logger.info("Redis no está instalado. El cache estará deshabilitado.")

if TYPE_CHECKING:
    from redis import Redis

# Instancia global del cliente Redis
_redis_client: Optional[Any] = None
_cache_enabled = True


def get_redis_client() -> Optional[Any]:
    """
    Obtiene o crea la instancia del cliente Redis.
    Retorna None si Redis no está disponible o está deshabilitado.
    """
    global _redis_client, _cache_enabled
    
    if not REDIS_AVAILABLE:
        _cache_enabled = False
        return None
    
    if not settings.cache_enabled:
        logger.info("Cache deshabilitado por configuración (CACHE_ENABLED=False)")
        return None
    
    # Construir URL de Redis (soporta formato Upstash)
    redis_connection_url = _build_redis_url(settings.redis_url, settings.redis_token)
    
    # Si no hay URL de Redis, deshabilitar cache
    if not redis_connection_url:
        logger.info("No se proporcionó REDIS_URL. El cache estará deshabilitado.")
        _cache_enabled = False
        return None
    
    if _redis_client is None:
        try:
            logger.info(f"Intentando conectar a Redis para cache: {_mask_redis_url(redis_connection_url)}")
            
            # Configurar SSL si es rediss:// (Redis con SSL)
            ssl_context = None
            if redis_connection_url.startswith('rediss://'):
                # Crear contexto SSL que no verifica certificados
                # Necesario para servicios como Heroku Redis que usan certificados autofirmados
                import ssl
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            
            _redis_client = redis.from_url(
                redis_connection_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                ssl=ssl_context if ssl_context else None
            )
            # Probar conexión
            _redis_client.ping()
            logger.info(f"✅ Conexión a Redis establecida correctamente para cache: {_mask_redis_url(redis_connection_url)}")
            _cache_enabled = True
        except (redis.ConnectionError, redis.TimeoutError, Exception) as e:
            logger.warning(f"⚠️ No se pudo conectar a Redis: {str(e)}. El cache estará deshabilitado.")
            _cache_enabled = False
            _redis_client = None


def _build_redis_url(redis_url: Optional[str], redis_token: Optional[str]) -> Optional[str]:
    """
    Construye la URL de conexión a Redis.
    Soporta formato estándar y formato Upstash (REST URL + Token).
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
        
        # Upstash usa el puerto 6379 por defecto para Redis protocol
        # Construir URL: rediss://default:TOKEN@HOST:6379
        redis_protocol_url = f"rediss://default:{redis_token}@{host}:6379"
        logger.info(f"Construyendo URL de Redis desde Upstash REST URL")
        return redis_protocol_url
    
    # Si no se puede determinar el formato, retornar None
    logger.warning(f"Formato de REDIS_URL no reconocido: {redis_url[:50]}...")
    return None


def _mask_redis_url(url: str) -> str:
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


class CacheManager:
    """
    Gestor de cache que proporciona métodos para almacenar y recuperar datos.
    """
    
    def __init__(self, redis_client: Optional[Any] = None):
        """
        Inicializa el gestor de cache.
        
        Args:
            redis_client: Cliente Redis (opcional, se obtiene automáticamente si no se proporciona)
        """
        self.redis_client = redis_client or get_redis_client()
        self.enabled = self.redis_client is not None
    
    def get_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """
        Genera una clave de cache única basada en los argumentos.
        
        Args:
            prefix: Prefijo para la clave (ej: "rag", "ip", "dns")
            *args: Argumentos posicionales
            **kwargs: Argumentos con nombre
        
        Returns:
            Clave de cache única
        
        Nota: Si conversation_context está en kwargs, se incluye en el hash
        para que consultas con diferente contexto tengan claves diferentes.
        """
        # Crear un hash de los argumentos
        # IMPORTANTE: conversation_context se incluye en el hash para diferenciar consultas
        key_data = json.dumps(
            {"args": args, "kwargs": kwargs},
            sort_keys=True,
            ensure_ascii=False
        )
        key_hash = hashlib.md5(key_data.encode()).hexdigest()
        return f"{prefix}:{key_hash}"
    
    def get(self, key: str) -> Optional[Any]:
        """
        Obtiene un valor del cache.
        
        Args:
            key: Clave del cache
        
        Returns:
            Valor almacenado o None si no existe o hay error
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
                logger.warning(f"Error al obtener del cache (key: {key}): {str(e)}")
            elif not isinstance(e, json.JSONDecodeError):
                logger.warning(f"Error al obtener del cache (key: {key}): {str(e)}")
            return None
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        """
        Almacena un valor en el cache con un TTL (Time To Live).
        
        Args:
            key: Clave del cache
            value: Valor a almacenar (debe ser serializable a JSON)
            ttl: Tiempo de vida en segundos (default: 3600 = 1 hora)
        """
        if not self.enabled:
            return
        
        try:
            serialized = json.dumps(value, ensure_ascii=False)
            self.redis_client.setex(key, ttl, serialized)
        except Exception as e:
            if REDIS_AVAILABLE and isinstance(e, redis.RedisError):
                logger.warning(f"Error al almacenar en cache (key: {key}): {str(e)}")
            elif not isinstance(e, TypeError):
                logger.warning(f"Error al almacenar en cache (key: {key}): {str(e)}")
    
    def delete(self, key: str):
        """
        Elimina una clave del cache.
        
        Args:
            key: Clave a eliminar
        """
        if not self.enabled:
            return
        
        try:
            self.redis_client.delete(key)
        except Exception as e:
            if REDIS_AVAILABLE and isinstance(e, redis.RedisError):
                logger.warning(f"Error al eliminar del cache (key: {key}): {str(e)}")
    
    def clear_prefix(self, prefix: str):
        """
        Elimina todas las claves que comienzan con un prefijo.
        
        Args:
            prefix: Prefijo de las claves a eliminar
        """
        if not self.enabled:
            return
        
        try:
            pattern = f"{prefix}:*"
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
                logger.info(f"Eliminadas {len(keys)} claves con prefijo '{prefix}'")
        except Exception as e:
            if REDIS_AVAILABLE and isinstance(e, redis.RedisError):
                logger.warning(f"Error al limpiar cache con prefijo '{prefix}': {str(e)}")


# Instancia global del gestor de cache
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """
    Obtiene la instancia global del gestor de cache.
    
    Returns:
        Instancia de CacheManager
    """
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


def cache_result(prefix: str, ttl: int = 3600):
    """
    Decorador para cachear resultados de funciones.
    
    Args:
        prefix: Prefijo para las claves de cache
        ttl: Tiempo de vida en segundos
    
    Ejemplo:
        @cache_result("rag", ttl=3600)
        def query(text: str):
            # ... lógica ...
            return result
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_manager = get_cache_manager()
            
            # Si el cache está deshabilitado, ejecutar función directamente
            if not cache_manager.enabled:
                return func(*args, **kwargs)
            
            # Para métodos de instancia, excluir 'self' de los argumentos para la clave de cache
            # Solo usar los argumentos reales de la función (sin self)
            cache_args = args[1:] if args and hasattr(args[0], '__class__') else args
            
            # Generar clave de cache
            cache_key = cache_manager.get_cache_key(prefix, *cache_args, **kwargs)
            
            # Intentar obtener del cache
            cached = cache_manager.get(cache_key)
            if cached is not None:
                logger.info(f"Cache HIT: {prefix} - {cache_key[:50]}...")
                return cached
            
            # Cache miss: ejecutar función y almacenar resultado
            logger.info(f"Cache MISS: {prefix} - {cache_key[:50]}...")
            result = func(*args, **kwargs)
            
            # Almacenar en cache (solo si no hay error)
            if result and not (isinstance(result, dict) and result.get("error")):
                cache_manager.set(cache_key, result, ttl)
                logger.debug(f"Resultado almacenado en cache: {prefix} - {cache_key[:50]}...")
            
            return result
        
        return wrapper
    return decorator

