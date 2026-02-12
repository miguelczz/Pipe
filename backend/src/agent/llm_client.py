"""
LLM Client - Unified interface for LLM interactions.

Phase 1 Evolution: Now uses MSPProvider internally for intelligent routing
and automatic fallback across multiple providers (Groq, Gemini, OpenAI).

Maintains backward compatibility with existing code while adding new capabilities.
"""

from typing import Iterator, Optional, AsyncIterator
import logging

from ..settings import settings
from ..core.llm_provider import get_msp_provider, MSPProvider

logger = logging.getLogger(__name__)

# Default system message for Pipe assistant
DEFAULT_SYSTEM_MESSAGE = (
    "You are Pipe, a technical assistant expert in Wireshark capture analysis, "
    "Band Steering, and 802.11 protocols. Your specialty is interpreting "
    ".pcap/.pcapng files and analyzing network traffic."
)


class LLMClient:
    """
    LLM Client with intelligent routing and automatic fallback.
    
    Phase 1 Evolution:
    - Uses MSPProvider for multi-provider routing
    - Supports model tiers (routing, cheap, standard, quality)
    - Automatic fallback to OpenAI on errors
    - Maintains backward compatibility with existing code
    
    Usage:
        client = LLMClient()
        
        # Basic usage (uses default 'standard' tier)
        response = client.generate("What is Band Steering?")
        
        # With model tier specification
        response = await client.agenerate(
            "Classify this query",
            model_tier="routing"  # Fast classification
        )
        
        # With streaming
        response = await client.agenerate(
            "Analyze this capture",
            stream_callback=lambda chunk: print(chunk, end="")
        )
    """
    
    def __init__(self, system_message: Optional[str] = None):
        """
        Initialize LLM Client.
        
        Args:
            system_message: Optional custom system message. 
                          If None, uses DEFAULT_SYSTEM_MESSAGE.
        """
        # Validate OpenAI API key (still required as fallback)
        if not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY not found in environment. "
                "This is required as fallback provider. "
                "Add to .env file: OPENAI_API_KEY=your_api_key_here"
            )
        
        # Get MSP Provider singleton
        self.msp: MSPProvider = get_msp_provider()
        
        # Store system message
        self.system_message = system_message or DEFAULT_SYSTEM_MESSAGE
        
        # Legacy compatibility: expose model name
        self.model = settings.llm_model
        
        logger.info("LLMClient initialized with MSPProvider")
    
    async def agenerate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        stream_callback: Optional[callable] = None,
        model_tier: str = "standard",
        temperature: float = 0.7,
        system_message: Optional[str] = None
    ) -> str:
        """
        Generate text asynchronously using MSPProvider.
        Critical for streaming without blocking the event loop.
        
        Args:
            prompt: The prompt to process
            max_tokens: Maximum tokens to generate (default 1000)
            stream_callback: Optional callback receiving each generated token
            model_tier: Task tier - "routing", "cheap", "standard", or "quality"
            temperature: Sampling temperature (0.0-2.0, default 0.7)
            system_message: Optional override for system message
        
        Returns:
            Generated text response
        """
        try:
            # Use provided system message or instance default
            sys_msg = system_message or self.system_message
            
            # Call MSPProvider with appropriate tier
            response = await self.msp.agenerate(
                prompt=prompt,
                system_message=sys_msg,
                max_tokens=max_tokens,
                temperature=temperature,
                model_tier=model_tier,
                stream_callback=stream_callback
            )
            
            return response.strip() if response else ""
        
        except Exception as e:
            logger.error(f"Async LLM generation failed: {e}")
            raise RuntimeError(f"Error generating async LLM response: {str(e)}")
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        stream_callback: Optional[callable] = None,
        model_tier: str = "standard",
        temperature: float = 0.7,
        system_message: Optional[str] = None
    ) -> str:
        """
        Generate text synchronously using MSPProvider.
        
        Args:
            prompt: The prompt to process
            max_tokens: Maximum tokens to generate (default 1000)
            stream_callback: Optional callback receiving each generated token
            model_tier: Task tier - "routing", "cheap", "standard", or "quality"
            temperature: Sampling temperature (0.0-2.0, default 0.7)
            system_message: Optional override for system message
        
        Returns:
            Generated text response
        """
        try:
            # Use provided system message or instance default
            sys_msg = system_message or self.system_message
            
            # Call MSPProvider with appropriate tier
            response = self.msp.generate(
                prompt=prompt,
                system_message=sys_msg,
                max_tokens=max_tokens,
                temperature=temperature,
                model_tier=model_tier,
                stream_callback=stream_callback
            )
            
            return response.strip() if response else ""
        
        except Exception as e:
            logger.error(f"Sync LLM generation failed: {e}")
            raise RuntimeError(f"Error generating LLM response: {str(e)}")
    
    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 1000,
        model_tier: str = "standard",
        temperature: float = 0.7,
        system_message: Optional[str] = None
    ) -> Iterator[str]:
        """
        Generate text with streaming (synchronous iterator).
        
        Args:
            prompt: The prompt to process
            max_tokens: Maximum tokens to generate (default 1000)
            model_tier: Task tier - "routing", "cheap", "standard", or "quality"
            temperature: Sampling temperature (0.0-2.0, default 0.7)
            system_message: Optional override for system message
        
        Yields:
            Individual tokens as they are generated
        """
        try:
            # Use provided system message or instance default
            sys_msg = system_message or self.system_message
            
            # Collect chunks via callback
            chunks = []
            
            def collect_chunk(chunk: str):
                chunks.append(chunk)
            
            # Generate with streaming callback
            self.msp.generate(
                prompt=prompt,
                system_message=sys_msg,
                max_tokens=max_tokens,
                temperature=temperature,
                model_tier=model_tier,
                stream_callback=collect_chunk
            )
            
            # Yield collected chunks
            for chunk in chunks:
                yield chunk
        
        except Exception as e:
            logger.error(f"Streaming generation failed: {e}")
            raise RuntimeError(f"Error generating LLM response (streaming): {str(e)}")
    
    async def agenerate_stream(
        self,
        prompt: str,
        max_tokens: int = 1000,
        model_tier: str = "standard",
        temperature: float = 0.7,
        system_message: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Generate text with async streaming.
        
        Args:
            prompt: The prompt to process
            max_tokens: Maximum tokens to generate (default 1000)
            model_tier: Task tier - "routing", "cheap", "standard", or "quality"
            temperature: Sampling temperature (0.0-2.0, default 0.7)
            system_message: Optional override for system message
        
        Yields:
            Individual tokens as they are generated
        """
        try:
            # Use provided system message or instance default
            sys_msg = system_message or self.system_message
            
            # Use MSPProvider's async streaming
            async for chunk in self.msp.agenerate_stream(
                prompt=prompt,
                system_message=sys_msg,
                max_tokens=max_tokens,
                temperature=temperature,
                model_tier=model_tier
            ):
                yield chunk
        
        except Exception as e:
            logger.error(f"Async streaming generation failed: {e}")
            raise RuntimeError(f"Error generating async LLM response (streaming): {str(e)}")
    
    def complete(self, prompt: str) -> str:
        """
        Alias for generate() for backward compatibility.
        
        Args:
            prompt: The prompt to process
        
        Returns:
            Generated text response
        """
        return self.generate(prompt)
