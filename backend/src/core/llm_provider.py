"""
MSP Provider - Model Service Provider
Unified LLM abstraction layer with intelligent routing and fallback.

Phase 1: LiteLLM + MSP Custom
- Routes to Groq (fast/cheap tasks) and Gemini (quality tasks)
- OpenAI as fallback only
- Automatic retry with fallback on rate limits or errors
- Streaming support for real-time responses
- Langfuse observability integration (Phase 2)
"""

import os
import logging
from typing import Optional, Callable, Dict, Any, AsyncIterator
from enum import Enum

try:
    import litellm
    from litellm import completion, acompletion
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logging.warning("LiteLLM not installed. Install with: pip install litellm>=1.40.0")

try:
    from langfuse import Langfuse
    from langfuse.decorators import observe, langfuse_context
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    logging.info("Langfuse not available. Observability disabled.")

from ..settings import settings

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    """Model tier classification for task-appropriate routing."""
    ROUTING = "routing"      # Intent classification, JSON structured output (fastest)
    CHEAP = "cheap"          # Yes/no decisions, single-word responses (fast)
    STANDARD = "standard"    # Text generation with context (quality)
    QUALITY = "quality"      # Synthesis, long-form reports (best quality)


class MSPProvider:
    """
    Model Service Provider - Unified LLM abstraction.
    
    Routes requests to optimal providers based on task tier:
    - ROUTING/CHEAP → Groq Llama 3.3 70B (free, fast)
    - STANDARD/QUALITY → Gemini 2.0 Flash (free, high quality)
    - Fallback → OpenAI gpt-4o-mini (paid, reliable)
    
    Features:
    - Automatic fallback on rate limits or errors
    - Streaming support for real-time responses
    - Langfuse observability integration
    - Configurable via environment variables
    """
    
    # Model tier mapping: tier → (primary_model, fallback_model)
    TIER_MAP: Dict[str, tuple[str, str]] = {
        ModelTier.ROUTING: (
            settings.llm_routing_model,
            settings.llm_fallback_model
        ),
        ModelTier.CHEAP: (
            settings.llm_cheap_model,
            settings.llm_fallback_model
        ),
        ModelTier.STANDARD: (
            settings.llm_standard_model,
            settings.llm_fallback_model
        ),
        ModelTier.QUALITY: (
            settings.llm_quality_model,
            settings.llm_fallback_model
        ),
    }
    
    def __init__(self):
        """Initialize MSP Provider with API keys and Langfuse client."""
        if not LITELLM_AVAILABLE:
            raise ImportError(
                "LiteLLM is required for MSPProvider. "
                "Install with: pip install litellm>=1.40.0"
            )
        
        # Configure LiteLLM with API keys
        self._configure_litellm()
        
        # Initialize Langfuse client if available
        self.langfuse_client = None
        if LANGFUSE_AVAILABLE and settings.langfuse_host:
            try:
                self.langfuse_client = Langfuse(
                    host=settings.langfuse_host,
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                )
                logger.info("Langfuse observability enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize Langfuse: {e}")
        
        logger.info("MSPProvider initialized with LiteLLM")
    
    def _configure_litellm(self):
        """Configure LiteLLM with API keys from settings."""
        # Set API keys in environment for LiteLLM
        if settings.openai_api_key:
            os.environ["OPENAI_API_KEY"] = settings.openai_api_key
        
        if settings.google_api_key:
            os.environ["GOOGLE_API_KEY"] = settings.google_api_key
            os.environ["GEMINI_API_KEY"] = settings.google_api_key
        
        if settings.groq_api_key:
            os.environ["GROQ_API_KEY"] = settings.groq_api_key
        
        # Configure LiteLLM settings
        litellm.drop_params = True  # Drop unsupported params instead of erroring
        litellm.set_verbose = settings.debug  # Enable verbose logging in debug mode
    
    def _get_models_for_tier(self, model_tier: str) -> tuple[str, str]:
        """
        Get primary and fallback models for a given tier.
        
        Args:
            model_tier: One of "routing", "cheap", "standard", "quality"
        
        Returns:
            Tuple of (primary_model, fallback_model)
        """
        tier = ModelTier(model_tier)
        primary, fallback = self.TIER_MAP[tier]
        return primary, fallback
    
    def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        model_tier: str = "standard",
        stream_callback: Optional[Callable[[str], None]] = None,
        **kwargs
    ) -> str:
        """
        Synchronous text generation with automatic fallback.
        
        Args:
            prompt: User prompt/query
            system_message: System message for context
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-2.0)
            model_tier: Task tier ("routing", "cheap", "standard", "quality")
            stream_callback: Optional callback for streaming chunks
            **kwargs: Additional parameters for LiteLLM
        
        Returns:
            Generated text response
        """
        primary_model, fallback_model = self._get_models_for_tier(model_tier)
        
        # Build messages
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        # Prepare completion kwargs
        completion_kwargs = {
            "model": primary_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "fallbacks": [fallback_model],  # Automatic fallback
            **kwargs
        }
        
        try:
            if stream_callback:
                # Streaming mode
                response = completion(stream=True, **completion_kwargs)
                full_response = ""
                for chunk in response:
                    if hasattr(chunk.choices[0].delta, 'content'):
                        content = chunk.choices[0].delta.content
                        if content:
                            full_response += content
                            stream_callback(content)
                return full_response
            else:
                # Non-streaming mode
                response = completion(**completion_kwargs)
                return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # Last resort: try fallback directly
            try:
                logger.info(f"Attempting direct fallback to {fallback_model}")
                completion_kwargs["model"] = fallback_model
                completion_kwargs.pop("fallbacks", None)
                response = completion(**completion_kwargs)
                return response.choices[0].message.content
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {fallback_error}")
                raise
    
    async def agenerate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        model_tier: str = "standard",
        stream_callback: Optional[Callable[[str], None]] = None,
        **kwargs
    ) -> str:
        """
        Asynchronous text generation with automatic fallback.
        
        Args:
            prompt: User prompt/query
            system_message: System message for context
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-2.0)
            model_tier: Task tier ("routing", "cheap", "standard", "quality")
            stream_callback: Optional callback for streaming chunks
            **kwargs: Additional parameters for LiteLLM
        
        Returns:
            Generated text response
        """
        primary_model, fallback_model = self._get_models_for_tier(model_tier)
        
        # Build messages
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        # Prepare completion kwargs
        completion_kwargs = {
            "model": primary_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "fallbacks": [fallback_model],  # Automatic fallback
            **kwargs
        }
        
        try:
            if stream_callback:
                # Streaming mode
                response = await acompletion(stream=True, **completion_kwargs)
                full_response = ""
                async for chunk in response:
                    if hasattr(chunk.choices[0].delta, 'content'):
                        content = chunk.choices[0].delta.content
                        if content:
                            full_response += content
                            stream_callback(content)
                return full_response
            else:
                # Non-streaming mode
                response = await acompletion(**completion_kwargs)
                return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"Async LLM generation failed: {e}")
            # Last resort: try fallback directly
            try:
                logger.info(f"Attempting direct fallback to {fallback_model}")
                completion_kwargs["model"] = fallback_model
                completion_kwargs.pop("fallbacks", None)
                response = await acompletion(**completion_kwargs)
                return response.choices[0].message.content
            except Exception as fallback_error:
                logger.error(f"Async fallback also failed: {fallback_error}")
                raise
    
    async def agenerate_stream(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        model_tier: str = "standard",
        **kwargs
    ) -> AsyncIterator[str]:
        """
        Asynchronous streaming generation.
        
        Args:
            prompt: User prompt/query
            system_message: System message for context
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-2.0)
            model_tier: Task tier ("routing", "cheap", "standard", "quality")
            **kwargs: Additional parameters for LiteLLM
        
        Yields:
            Text chunks as they are generated
        """
        primary_model, fallback_model = self._get_models_for_tier(model_tier)
        
        # Build messages
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        # Prepare completion kwargs
        completion_kwargs = {
            "model": primary_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "fallbacks": [fallback_model],
            **kwargs
        }
        
        try:
            response = await acompletion(**completion_kwargs)
            async for chunk in response:
                if hasattr(chunk.choices[0].delta, 'content'):
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content
        
        except Exception as e:
            logger.error(f"Streaming generation failed: {e}")
            # Try fallback
            try:
                logger.info(f"Attempting direct fallback to {fallback_model}")
                completion_kwargs["model"] = fallback_model
                completion_kwargs.pop("fallbacks", None)
                response = await acompletion(**completion_kwargs)
                async for chunk in response:
                    if hasattr(chunk.choices[0].delta, 'content'):
                        content = chunk.choices[0].delta.content
                        if content:
                            yield content
            except Exception as fallback_error:
                logger.error(f"Streaming fallback also failed: {fallback_error}")
                raise


# Global singleton instance
_msp_instance: Optional[MSPProvider] = None


def get_msp_provider() -> MSPProvider:
    """
    Get or create the global MSPProvider instance.
    
    Returns:
        MSPProvider singleton instance
    """
    global _msp_instance
    if _msp_instance is None:
        _msp_instance = MSPProvider()
    return _msp_instance
