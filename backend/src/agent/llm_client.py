from openai import OpenAI, AsyncOpenAI
from ..settings import settings
from typing import Iterator

class LLMClient:
    def __init__(self):
        # Usar settings en lugar de cargar manualmente
        if not settings.openai_api_key:
            raise ValueError(
                "No se encontró la variable de entorno OPENAI_API_KEY. "
                "Asegúrate de tener un archivo .env con la línea:\n"
                "OPENAI_API_KEY=tu_api_key_aqui"
            )

        # Inicializar cliente de OpenAI (Síncrono y Asíncrono)
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.aclient = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.llm_model

    async def agenerate(self, prompt: str, max_tokens: int = 1000, stream_callback=None) -> str:
        """
        Genera texto usando OpenAI Chat Completions de forma ASÍNCRONA.
        Crucial para permitir que el streaming funcione sin bloquear el event loop.
        
        Args:
            prompt: El prompt a procesar
            max_tokens: Número máximo de tokens a generar (por defecto 1000)
            stream_callback: Función opcional que recibe cada token generado (para streaming real)
        """
        try:
            # Si hay callback, usar streaming real
            if stream_callback:
                full_response = []
                stream = await self.aclient.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "Eres Pipe, un asistente técnico experto en análisis de capturas Wireshark, Band Steering y protocolos 802.11. Tu especialidad es interpretar archivos .pcap/.pcapng y analizar tráfico de red."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    stream=True,
                )
                
                async for chunk in stream:
                    content = chunk.choices[0].delta.content
                    if content:
                        # Llamar al callback con el nuevo token
                        # Nota: stream_callback puede ser sync o async, pero aquí lo llamamos directamente
                        # Si es sync (como queue.put_nowait), funciona bien.
                        if stream_callback:
                            stream_callback(content)
                        full_response.append(content)
                
                return "".join(full_response).strip()
            
            # Modo normal (sin streaming)
            else:
                response = await self.aclient.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "Eres Pipe, un asistente técnico experto en análisis de capturas Wireshark, Band Steering y protocolos 802.11. Tu especialidad es interpretar archivos .pcap/.pcapng y analizar tráfico de red."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"Error al generar respuesta asíncrona con LLM: {str(e)}")

    def generate(self, prompt: str, max_tokens: int = 1000, stream_callback=None) -> str:
        """
        Genera texto usando OpenAI Chat Completions.
        
        Args:
            prompt: El prompt a procesar
            max_tokens: Número máximo de tokens a generar (por defecto 1000)
            stream_callback: Función opcional que recibe cada token generado (para streaming real)
        """
        try:
            # Si hay callback, usar streaming real
            if stream_callback:
                full_response = []
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "Eres Pipe, un asistente técnico experto en análisis de capturas Wireshark, Band Steering y protocolos 802.11. Tu especialidad es interpretar archivos .pcap/.pcapng y analizar tráfico de red."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    stream=True,
                )
                
                for chunk in stream:
                    content = chunk.choices[0].delta.content
                    if content:
                        # Llamar al callback con el nuevo token
                        stream_callback(content)
                        full_response.append(content)
                
                return "".join(full_response).strip()
            
            # Modo normal (sin streaming)
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "Eres Pipe, un asistente técnico experto en análisis de capturas Wireshark, Band Steering y protocolos 802.11. Tu especialidad es interpretar archivos .pcap/.pcapng y analizar tráfico de red."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"Error al generar respuesta con LLM: {str(e)}")
    
    def generate_stream(self, prompt: str, max_tokens: int = 1000) -> Iterator[str]:
        """
        Genera texto usando OpenAI Chat Completions con streaming.
        
        Args:
            prompt: El prompt a procesar
            max_tokens: Número máximo de tokens a generar (por defecto 1000)
            
        Yields:
            Tokens individuales a medida que se generan
        """
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                stream=True,  # Habilitar streaming
            )
            
            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            raise RuntimeError(f"Error al generar respuesta con LLM (streaming): {str(e)}")
    
    def complete(self, prompt: str) -> str:
        """
        Alias para generate() para compatibilidad con código existente.
        """
        return self.generate(prompt)

