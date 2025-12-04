"""
Herramienta RAG - Refactorizado para usar repositorios y utilidades
OPTIMIZADO: Búsqueda híbrida paralela con asyncio.gather() y pre-compilación de prompts
"""
import logging
import re
import asyncio
import concurrent.futures
from typing import Optional, List, Dict, Any
from openai import OpenAI
from ..settings import settings
from ..repositories.qdrant_repository import QdrantRepository
from ..utils.embeddings import embedding_for_text
from ..core.cache import cache_result

# Cliente OpenAI para generación de respuestas
# NOTA: Este cliente es síncrono. Todas las llamadas deben envolverse con asyncio.to_thread()
# para evitar bloquear el event loop. El cliente puede usar time.sleep internamente para retries.
client = OpenAI(
    api_key=settings.openai_api_key,
    max_retries=2  # Limitar retries para reducir tiempo de bloqueo
)
logger = logging.getLogger(__name__)


class RAGTool:
    """
    Herramienta RAG optimizada con búsqueda híbrida paralela usando asyncio.gather().
    
    OPTIMIZACIÓN: Usa asyncio.gather() para ejecutar búsquedas densa y dispersa en paralelo,
    mejorando el rendimiento al reducir la latencia total de las búsquedas.
    """
    
    # OPTIMIZACIÓN: Pre-compilar prompts estáticos para evitar reconstruirlos en cada llamada
    RELEVANCE_CHECK_PROMPT_TEMPLATE = """
Analiza si la siguiente pregunta está relacionada EXCLUSIVAMENTE con la temática de redes, telecomunicaciones, protocolos de red, tecnologías de red, o temas técnicos de TI relacionados con redes.

Pregunta del usuario: "{query_text}"

INSTRUCCIONES CRÍTICAS:
- Sé MUY ESTRICTO: solo marca como relevante si la pregunta está CLARAMENTE y DIRECTAMENTE relacionada con redes, protocolos de red, telecomunicaciones o tecnologías de red
- Preguntas sobre física general, matemáticas, historia, literatura, medicina, cocina, deportes, etc. son NO RELEVANTES
- Preguntas sobre teoría de la relatividad, mecánica cuántica, biología, química, etc. son NO RELEVANTES
- Solo son relevantes preguntas sobre: protocolos de red (TCP/IP, HTTP, DNS, etc.), dispositivos de red (routers, switches, etc.), tecnologías de red (WiFi, Ethernet, etc.), operaciones de red (ping, traceroute, etc.), configuración de red, seguridad de red, etc.

Ejemplos de NO RELEVANTES:
- "¿Qué es la teoría de la relatividad?" → NO RELEVANTE
- "¿Cómo funciona la fotosíntesis?" → NO RELEVANTE
- "¿Quién ganó el mundial?" → NO RELEVANTE
- "¿Cómo se cocina una pizza?" → NO RELEVANTE
- "¿Cómo funciona un motor de combustión?" → NO RELEVANTE
- "¿Qué es la mecánica cuántica?" → NO RELEVANTE
- "¿Cómo funciona el sistema digestivo?" → NO RELEVANTE

Ejemplos de RELEVANTES:
- "¿Qué es un ping?" → RELEVANTE
- "¿Cómo funciona DNS?" → RELEVANTE
- "¿Qué es TCP/IP?" → RELEVANTE
- "Haz ping a google.com" → RELEVANTE

Responde SOLO con una palabra: "relevante" o "no_relevante".
"""
    
    COMPLEXITY_PROMPT_TEMPLATE = """
Analiza la siguiente pregunta y determina su complejidad:

Pregunta: "{query_text}"

Determina si es:
1. "simple" - Pregunta directa que requiere una respuesta breve (ej: "¿Qué es X?", "¿Cuál es Y?")
2. "moderada" - Pregunta que requiere una explicación con algunos detalles (ej: "¿Cómo funciona X?", "Explica Y")
3. "compleja" - Pregunta que requiere una explicación detallada, múltiples aspectos, O una lista completa de elementos (ej: "Compara X e Y", "Explica todos los aspectos de Z", "¿Cuáles son las capas del modelo OSI?", "Menciona todos los tipos de X", "Lista todas las capas", "¿Cuáles son todas las...?")

IMPORTANTE: Si la pregunta requiere una LISTA COMPLETA de elementos (ej: "capas del modelo OSI", "tipos de firewalls", "protocolos de red", "todas las capas", "cuáles son las capas"), debe ser marcada como "compleja" para asegurar que se incluyan TODOS los elementos sin omitir ninguno.

Responde SOLO con una palabra: "simple", "moderada" o "compleja".
"""
    
    BASE_PROMPT_TEMPLATE = """
Eres un asistente experto en redes y telecomunicaciones. Responde la pregunta del usuario de manera clara, natural y adaptada a su complejidad.

INSTRUCCIONES:
1. ANALIZA LA PREGUNTA: Determina si hace referencia a acciones/eventos de la conversación previa o busca información técnica general.
2. FIDELIDAD: 
   - Si la pregunta es sobre acciones/eventos de la conversación (ej: "antes del ping", "el ping que hiciste", "a qué dominio fue"): usa el CONTEXTO DE CONVERSACIÓN como fuente principal
   - Si la pregunta es sobre conceptos técnicos (qué es, cómo funciona): usa los DOCUMENTOS como fuente principal
   - NO inventes información que no esté en el contexto proporcionado
3. LENGUAJE NATURAL: Responde como si fueras un experto explicando a un usuario, de manera clara y comprensible.
4. LONGITUD ADAPTATIVA: {length_guidance}
5. ESTRUCTURA CLARA: Organiza la información de forma lógica y fácil de leer.

REGLAS CRÍTICAS DE FIDELIDAD:
- Si la pregunta menciona "antes", "anterior", "que hiciste", "que realizaste", "a qué dominio", "qué IP", busca esa información en el CONTEXTO DE CONVERSACIÓN
- Si la pregunta es sobre conceptos técnicos (qué es, cómo funciona), usa EXCLUSIVAMENTE los DOCUMENTOS
- FIDELIDAD ABSOLUTA: SOLO menciona información que esté EXPLÍCITAMENTE escrita en el CONTEXTO DE DOCUMENTOS
- Si el documento menciona protocolos específicos, SOLO menciona esos protocolos. NO agregues protocolos relacionados que no estén en el documento
- Si la información solicitada NO está en el contexto de documentos, indica claramente que no tienes esa información en los documentos disponibles
- NO uses conocimiento general sobre el tema que no esté en el contexto
- NO copies párrafos completos, parafrasea de manera natural pero mantén la información exacta
- Mantén un tono profesional pero accesible
- Para preguntas simples, ve directo al punto sin rodeos
- ENFOQUE: Tu función es explicar conceptos y proporcionar información educativa basada SOLO en los documentos, o responder sobre acciones previas en la conversación.

{context_section}
CONTEXTO DE DOCUMENTOS (ÚNICA FUENTE DE INFORMACIÓN - NO agregues información que no esté aquí):
{context}

Pregunta: {query_text}

IMPORTANTE: 
- Si la información solicitada NO está en el CONTEXTO DE DOCUMENTOS, indica que no tienes esa información en los documentos disponibles
- SOLO menciona protocolos, conceptos o información que esté EXPLÍCITAMENTE escrita en el contexto
- NO agregues protocolos relacionados o información complementaria que no esté en el documento

Genera una respuesta clara, natural y adaptada a la complejidad de la pregunta usando EXCLUSIVAMENTE la información del CONTEXTO DE DOCUMENTOS:
"""
    
    SYSTEM_MESSAGE = "Eres un asistente experto en redes y telecomunicaciones. Tu función es explicar conceptos y proporcionar información educativa basada EXCLUSIVAMENTE en el contexto proporcionado.\n\nREGLAS CRÍTICAS DE FIDELIDAD:\n1. SOLO puedes usar información que esté EXPLÍCITAMENTE escrita en el CONTEXTO DE DOCUMENTOS proporcionado\n2. NO puedes agregar conocimiento general, información de otras fuentes, o inferencias que no estén en el contexto\n3. Si la información solicitada NO está en el contexto, debes indicar que no tienes esa información en los documentos disponibles\n4. NO inventes nombres de protocolos, características, o detalles técnicos que no aparezcan en el contexto\n5. Si el contexto menciona protocolos específicos, SOLO menciona esos. NO agregues protocolos relacionados que no estén mencionados\n6. Mantén fidelidad ABSOLUTA: cada afirmación debe estar respaldada por el texto del contexto\n\nADAPTA la longitud según la complejidad: preguntas simples requieren respuestas MUY BREVES (2-3 oraciones), preguntas moderadas requieren respuestas equilibradas (80-150 palabras), preguntas complejas requieren respuestas detalladas (200-400 palabras). Habla de manera natural como un experto explicando a un usuario, pero sé CONCISO y ve directo al punto. ENFOQUE: Solo explica conceptos e información técnica. NO menciones limitaciones sobre ejecutar comandos, NO sugieras acciones manuales del usuario. Tu trabajo es educar, no instruir sobre qué hacer."
    
    RELEVANCE_SYSTEM_MESSAGE = "Eres un analizador ESTRICTO que determina si una pregunta está relacionada EXCLUSIVAMENTE con redes y telecomunicaciones. Sé MUY ESTRICTO: solo marca como relevante si está CLARAMENTE relacionada con redes, protocolos, telecomunicaciones o tecnologías de red. Rechaza CUALQUIER pregunta sobre otros temas (física general, matemáticas, historia, literatura, medicina, etc.)."
    
    COMPLEXITY_SYSTEM_MESSAGE = "Eres un analizador que determina la complejidad de preguntas."
    
    # Keywords comunes para búsqueda dispersa
    KEYWORD_PATTERNS = {
        'wifi': ['wifi', 'wi-fi', 'wireless'],
        '802.11': ['802.11', '802.11a', '802.11b', '802.11g', '802.11n', '802.11ac', '802.11ax'],
        'ethernet': ['ethernet', 'ethernet cable', 'rj45'],
        'tcp': ['tcp', 'tcp/ip', 'transmission control protocol'],
        'dns': ['dns', 'domain name system', 'name server'],
        'http': ['http', 'https', 'hypertext transfer protocol'],
        'ip': ['ip address', 'ipv4', 'ipv6', 'internet protocol'],
    }
    
    def __init__(self):
        self.qdrant_repo = QdrantRepository()

    async def _query_without_cache(self, query_text: str, top_k: int = 8, conversation_context: Optional[str] = None):
        """
        Método interno que realiza la consulta RAG sin usar cache.
        Se usa cuando hay contexto de conversación para evitar cachear respuestas contextualizadas.
        """
        return await self._execute_query(query_text, top_k, conversation_context)

    async def _query_with_cache(self, query_text: str, top_k: int = 8, conversation_context: Optional[str] = None):
        """
        Método interno que realiza la consulta RAG con cache.
        Solo se usa cuando NO hay contexto de conversación.
        IMPORTANTE: conversation_context debe ser None siempre cuando se llama este método.
        """
        # Si por alguna razón se pasa contexto, no usar cache
        if conversation_context:
            logger.warning("_query_with_cache llamado con conversation_context - usando método sin cache")
            return await self._query_without_cache(query_text, top_k, conversation_context)
        
        # Usar el decorador de cache solo cuando no hay contexto
        return await self._execute_query_cached(query_text, top_k)
    
    @cache_result("rag", ttl=3600)  # Cache por 1 hora
    async def _execute_query_cached(self, query_text: str, top_k: int = 8):
        """
        Método interno cacheado que ejecuta la consulta RAG.
        Solo se llama cuando NO hay contexto de conversación.
        """
        return await self._execute_query(query_text, top_k, None)

    def query(self, query_text: str, top_k: int = 8, conversation_context: Optional[str] = None):
        """
        Realiza una consulta RAG sobre los documentos indexados.
        
        Args:
            query_text: Texto de la consulta
            top_k: Número de resultados a recuperar (aumentado a 8 para mejor cobertura)
            conversation_context: Contexto opcional de la conversación previa (últimos mensajes)
        
        Returns:
            Dict con 'answer' y 'hits'
        
        Nota: Si se proporciona conversation_context, NO se usará cache para evitar
        devolver respuestas de consultas anteriores sin contexto.
        
        Nota: Este método es síncrono pero internamente usa asyncio para paralelización.
        Maneja correctamente el caso cuando ya hay un event loop corriendo (FastAPI/LangGraph).
        """
        # Helper para ejecutar async desde función síncrona
        def _run_async(coro):
            """Ejecuta una corrutina, manejando el caso cuando ya hay un event loop."""
            try:
                # Intentar obtener el event loop actual (si está corriendo)
                loop = asyncio.get_running_loop()
                # Si hay un loop corriendo, ejecutar en un thread separado con su propio loop
                # Esto evita el error "RuntimeError: asyncio.run() cannot be called from a running event loop"
                def run_in_new_loop():
                    """Ejecuta la corrutina en un nuevo event loop en este thread."""
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(coro)
                    finally:
                        new_loop.close()
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_new_loop)
                    return future.result()
            except RuntimeError:
                # No hay event loop corriendo, usar asyncio.run() normalmente
                return asyncio.run(coro)
        
        # Si hay contexto de conversación, NO usar cache (evitar respuestas incorrectas)
        if conversation_context:
            logger.info(f"Consulta RAG con contexto de conversación ({len(conversation_context)} chars) - NO usando cache")
            return _run_async(self._query_without_cache(query_text, top_k, conversation_context))
        else:
            # Sin contexto, usar cache normal
            logger.debug(f"Consulta RAG sin contexto - usando cache")
            return _run_async(self._query_with_cache(query_text, top_k, None))

    def _extract_keywords(self, query_text: str) -> List[str]:
        """
        Extrae keywords relevantes de la consulta para búsqueda dispersa.
        OPTIMIZACIÓN: Usa patrones predefinidos para mejor rendimiento.
        """
        query_lower = query_text.lower()
        keywords = []
        
        # Buscar patrones de keywords
        for pattern_key, pattern_list in self.KEYWORD_PATTERNS.items():
            if any(pattern in query_lower for pattern in pattern_list):
                keywords.extend(pattern_list)
        
        # Keywords adicionales específicas
        if 'wifi' in query_lower or 'wi-fi' in query_lower:
            keywords.extend(['wifi', 'wi-fi'])
        if '802.11' in query_text:
            keywords.append('802.11')
        
        # Eliminar duplicados manteniendo orden
        return list(dict.fromkeys(keywords))
    
    async def _dense_search(self, query_text: str, top_k: int) -> List[Dict[str, Any]]:
        """
        Realiza búsqueda densa (vectorial) en Qdrant.
        OPTIMIZACIÓN: Método asíncrono para ejecución paralela con asyncio.gather().
        """
        try:
            # Ejecutar embedding y búsqueda en thread separado (operaciones síncronas)
            def _sync_dense_search():
                query_vector = embedding_for_text(query_text)
                # Aumentar top_k a mínimo 10 para tener mejor cobertura
                search_top_k = max(top_k, 10)
                logger.debug(f"[RAG] Búsqueda densa con top_k={search_top_k} para: '{query_text[:50]}...'")
                results = self.qdrant_repo.search(
                    query_vector=query_vector,
                    top_k=search_top_k
                )
                logger.debug(f"[RAG] Búsqueda densa retornó {len(results)} resultados")
                return results
            
            # Usar asyncio.to_thread para ejecutar operación síncrona sin bloquear
            hits = await asyncio.to_thread(_sync_dense_search)
            return hits
        except Exception as e:
            logger.error(f"Error en búsqueda densa: {e}")
            return []
    
    async def _sparse_search(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """
        Realiza búsqueda dispersa (por keywords) en Qdrant.
        OPTIMIZACIÓN: Método asíncrono para ejecución paralela con asyncio.gather().
        """
        if not keywords:
            return []
        
        try:
            # Ejecutar búsqueda dispersa en thread separado (operación síncrona)
            def _sync_sparse_search():
                from qdrant_client import QdrantClient
                # Normalizar URL (quitar puerto si es HTTPS)
                qdrant_url = settings.qdrant_url
                if qdrant_url.startswith('https://') and ':6333' in qdrant_url:
                    qdrant_url = qdrant_url.replace(':6333', '')
                
                # Configurar cliente con API key si está disponible
                client_kwargs = {"url": qdrant_url, "prefer_grpc": False}
                if settings.qdrant_api_key:
                    client_kwargs["api_key"] = settings.qdrant_api_key
                
                direct_client = QdrantClient(**client_kwargs)
                
                # OPTIMIZACIÓN: Limitar scroll a menos puntos si hay muchos keywords
                scroll_limit = min(500, 100 * len(keywords))
                scroll_result = direct_client.scroll(
                    collection_name="documents",
                    limit=scroll_limit
                )
                
                keyword_hits = []
                keywords_lower = [kw.lower() for kw in keywords]
                
                for point in scroll_result[0]:
                    text = point.payload.get("text", "").lower()
                    # OPTIMIZACIÓN: Verificar todos los keywords de una vez
                    if any(kw in text for kw in keywords_lower):
                        keyword_hits.append({
                            "id": point.id,
                            "score": 1.0,  # Score alto para matches directos
                            "payload": point.payload
                        })
                        # Limitar resultados temprano para mejor rendimiento
                        if len(keyword_hits) >= 10:
                            break
                
                return keyword_hits
            
            # Usar asyncio.to_thread para ejecutar operación síncrona sin bloquear
            keyword_hits = await asyncio.to_thread(_sync_sparse_search)
            return keyword_hits
        except Exception as e:
            logger.warning(f"Error en búsqueda dispersa: {e}")
            return []
    
    def _has_keyword_match(self, hits: List[Dict[str, Any]], keywords: List[str]) -> bool:
        """
        Verifica si algún hit contiene las keywords.
        OPTIMIZACIÓN: Método separado para mejor legibilidad y testing.
        """
        if not keywords or not hits:
            return False
        
        keywords_lower = [kw.lower() for kw in keywords]
        return any(
            any(kw in h["payload"].get("text", "").lower() for kw in keywords_lower)
            for h in hits
        )
    
    async def _execute_query(self, query_text: str, top_k: int = 8, conversation_context: Optional[str] = None):
        """
        Método interno que ejecuta la consulta RAG real.
        OPTIMIZACIÓN: Búsqueda híbrida paralela (densa + dispersa) usando asyncio.gather().
        
        Args:
            query_text: Texto de la consulta
            top_k: Número de resultados a recuperar
            conversation_context: Contexto opcional de la conversación previa
        
        Returns:
            Dict con 'answer' y 'hits'
        """
        # Validación básica
        if not query_text or not isinstance(query_text, str) or not query_text.strip():
            return {"answer": "La consulta no puede estar vacía.", "hits": 0, "contexts": []}
        
        try:
            # OPTIMIZACIÓN: Extraer keywords antes de las búsquedas
            keywords = self._extract_keywords(query_text)
            
            # OPTIMIZACIÓN: Ejecutar búsqueda densa y dispersa en paralelo usando asyncio.gather()
            # Esto es más eficiente que ThreadPoolExecutor para operaciones I/O
            tasks = [self._dense_search(query_text, top_k)]
            
            # Agregar búsqueda dispersa solo si hay keywords
            if keywords:
                tasks.append(self._sparse_search(keywords))
            
            # Ejecutar ambas búsquedas en paralelo
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Procesar resultados
            hits = results[0] if not isinstance(results[0], Exception) else []
            keyword_hits = results[1] if len(results) > 1 and not isinstance(results[1], Exception) else []
            
            # Manejar excepciones
            if isinstance(results[0], Exception):
                logger.error(f"Error en búsqueda densa: {results[0]}")
            if len(results) > 1 and isinstance(results[1], Exception):
                logger.warning(f"Error en búsqueda dispersa: {results[1]}")
            
            # Combinar resultados solo si hay keyword_hits y no hay match en hits densos
            if keyword_hits and not self._has_keyword_match(hits, keywords):
                # Priorizar keyword matches al inicio
                hits = keyword_hits[:3] + hits
            elif keyword_hits:
                # Si ya hay match, agregar algunos keyword hits adicionales
                hits = keyword_hits[:2] + hits

            if not hits:
                # Verificar si hay documentos en la colección
                try:
                    collection_info = self.qdrant_repo.get_collection_info()
                    points_count = collection_info.get('points_count', 0) if isinstance(collection_info, dict) else 0
                    if points_count == 0:
                        logger.error(f"[RAG] ❌ No hay documentos indexados en Qdrant (0 puntos en la colección)")
                        return {
                            "answer": "No hay documentos disponibles en la base de datos. Por favor, sube documentos PDF relacionados con redes y telecomunicaciones para que pueda responder tus preguntas.",
                            "hits": 0,
                            "contexts": [],
                            "source": "no_documents"
                        }
                    else:
                        logger.warning(f"[RAG] ⚠️ Hay {points_count} puntos en Qdrant pero la búsqueda no encontró resultados para: '{query_text[:50]}...'")
                        logger.warning(f"[RAG] ⚠️ Esto puede indicar que la consulta no coincide con el contenido de los documentos")
                except Exception as e:
                    logger.error(f"[RAG] Error al verificar colección: {e}")
                
                return {
                    "answer": "No encontré información específica sobre tu pregunta en los documentos disponibles. Por favor, asegúrate de que tu pregunta esté relacionada con redes, telecomunicaciones o protocolos de red.",
                    "hits": 0,
                    "contexts": [],
                    "source": "no_hits"
                }
        except Exception as e:
            # Si Qdrant no está disponible o hay error de conexión, retornar error
            error_msg = str(e)
            if "conexión" in error_msg.lower() or "connection" in error_msg.lower() or "10061" in error_msg:
                return {
                    "answer": "No se pudo conectar con la base de datos de documentos. Por favor, verifica que Qdrant esté ejecutándose.",
                    "hits": 0,
                    "error": "qdrant_connection_error",
                    "contexts": []
                }
            else:
                return {
                    "answer": f"Error al buscar en los documentos: {error_msg}",
                    "hits": 0,
                    "error": "rag_error",
                    "contexts": []
                }

        # OPTIMIZACIÓN: Validar relevancia y analizar complejidad en paralelo usando asyncio.gather()
        # IMPORTANTE: La validación de relevancia debe considerar el contexto de conversación
        async def check_relevance():
            """Verifica si la pregunta es relevante para la temática."""
            try:
                # Si hay contexto de conversación, incluirlo en la validación
                # Esto evita que preguntas de seguimiento sean marcadas como no relevantes
                if conversation_context:
                    # Construir prompt con contexto para mejor validación
                    relevance_prompt_with_context = f"""
Analiza si la siguiente pregunta está relacionada EXCLUSIVAMENTE con la temática de redes, telecomunicaciones, protocolos de red, tecnologías de red, o temas técnicos de TI relacionados con redes.

CONTEXTO DE CONVERSACIÓN PREVIA:
{conversation_context}

Pregunta del usuario: "{query_text}"

INSTRUCCIONES CRÍTICAS:
- Si la pregunta hace referencia a algo mencionado en el CONTEXTO DE CONVERSACIÓN (ej: "los tipos", "cuales son", "menciona", "explica más"), y el contexto es sobre redes/telecomunicaciones, marca como RELEVANTE
- Si la pregunta está relacionada con redes, protocolos, telecomunicaciones o tecnologías de red, marca como RELEVANTE
- Solo marca como NO RELEVANTE si la pregunta claramente NO está relacionada con redes/telecomunicaciones Y no hace referencia al contexto previo

Ejemplos de RELEVANTES (con contexto):
- Si el contexto menciona "firewalls" y la pregunta es "Cuales son los tipos?" → RELEVANTE (se refiere a tipos de firewalls)
- Si el contexto menciona "DNS" y la pregunta es "Explica más" → RELEVANTE
- Si el contexto menciona "ping" y la pregunta es "Qué otros comandos hay?" → RELEVANTE

Ejemplos de NO RELEVANTES:
- "¿Qué es la teoría de la relatividad?" → NO RELEVANTE
- "¿Cómo funciona la fotosíntesis?" → NO RELEVANTE
- "¿Quién ganó el mundial?" → NO RELEVANTE

Responde SOLO con una palabra: "relevante" o "no_relevante".
"""
                    relevance_prompt = relevance_prompt_with_context
                else:
                    relevance_prompt = self.RELEVANCE_CHECK_PROMPT_TEMPLATE.format(query_text=query_text)
                
                # Ejecutar llamada a OpenAI en thread separado (operación síncrona)
                def _sync_relevance_check():
                    relevance_response = client.chat.completions.create(
                        model=settings.llm_model,
                        messages=[
                            {"role": "system", "content": self.RELEVANCE_SYSTEM_MESSAGE},
                            {"role": "user", "content": relevance_prompt}
                        ],
                        temperature=0.0,
                        max_tokens=10
                    )
                    return relevance_response.choices[0].message.content.strip().lower()
                
                response_text = await asyncio.to_thread(_sync_relevance_check)
                is_relevant = "relevante" in response_text and "no_relevante" not in response_text
                logger.info(f"[RAG] Validación de relevancia: respuesta LLM='{response_text}', is_relevant={is_relevant}, tiene_contexto={bool(conversation_context)}")
                return is_relevant
            except Exception as e:
                logger.warning(f"[RAG] Error al verificar relevancia: {e}. Continuando con respuesta normal.")
                return True  # En caso de error, permitir respuesta
        
        async def check_complexity():
            """Analiza la complejidad de la pregunta."""
            try:
                complexity_prompt = self.COMPLEXITY_PROMPT_TEMPLATE.format(query_text=query_text)
                
                # Ejecutar llamada a OpenAI en thread separado (operación síncrona)
                def _sync_complexity_check():
                    complexity_response = client.chat.completions.create(
                        model=settings.llm_model,
                        messages=[
                            {"role": "system", "content": self.COMPLEXITY_SYSTEM_MESSAGE},
                            {"role": "user", "content": complexity_prompt}
                        ],
                        temperature=0.0,
                        max_tokens=10
                    )
                    return complexity_response.choices[0].message.content.strip().lower()
                
                complexity = await asyncio.to_thread(_sync_complexity_check)
                return complexity
            except Exception as e:
                logger.warning(f"[RAG] Error al analizar complejidad: {e}. Usando longitud moderada por defecto.")
                return "moderada"
        
        # OPTIMIZACIÓN: Ejecutar validación de relevancia y complejidad en paralelo usando asyncio.gather()
        is_relevant, complexity = await asyncio.gather(
            check_relevance(),
            check_complexity(),
            return_exceptions=True
        )
        
        # Manejar excepciones
        if isinstance(is_relevant, Exception):
            logger.warning(f"[RAG] Error en check_relevance: {is_relevant}. Asumiendo relevante.")
            is_relevant = True
        if isinstance(complexity, Exception):
            logger.warning(f"[RAG] Error en check_complexity: {complexity}. Usando moderada.")
            complexity = "moderada"
        
        # Si no es relevante, retornar mensaje indicando que no puede responder
        if not is_relevant:
            logger.info(f"[RAG] Pregunta no relacionada con la temática de redes: '{query_text}'")
            return {
                "answer": "Lo siento, solo puedo responder preguntas relacionadas con redes, telecomunicaciones, protocolos de red y tecnologías de red. Tu pregunta parece estar fuera de esta temática.",
                "hits": 0,
                "contexts": [],
                "source": "out_of_topic"
            }
        
        # Filtrar y concatenar los chunks más relevantes
        # IMPORTANTE: Usar un umbral más bajo (0.3) para incluir más resultados relevantes
        # En búsquedas vectoriales, scores de 0.3-0.5 pueden ser aún relevantes
        relevant_hits = [h for h in hits if h.get('score', 0) > 0.3]
        
        # Si no hay hits con score > 0.3, usar los top 3 resultados (incluso con scores bajos)
        # Esto asegura que siempre tengamos contexto para generar una respuesta
        if not relevant_hits:
            logger.warning(f"[RAG] No hay hits con score > 0.3. Usando top {min(3, len(hits))} resultados disponibles (scores: {[h.get('score', 0) for h in hits[:3]]})")
            relevant_hits = hits[:3] if hits else []
        else:
            # Limitar a máximo 3 chunks más relevantes para tener mejor cobertura
            relevant_hits = relevant_hits[:3]
        
        # Concatenar los textos más relevantes
        context = "\n\n".join([h["payload"].get("text", "") for h in relevant_hits])
        
        # Logging detallado para debugging
        if relevant_hits:
            scores = [h.get('score', 0) for h in relevant_hits]
            logger.info(f"[RAG] Usando {len(relevant_hits)} chunks más relevantes (de {len(hits)} totales) con scores: {scores}")
        else:
            logger.warning(f"[RAG] ⚠️ No hay chunks relevantes disponibles después del filtrado")
        
        # Si el contexto está vacío después del filtrado, retornar error
        if not context or not context.strip():
            logger.error(f"[RAG] ❌ Contexto vacío después del filtrado. Hits totales: {len(hits)}")
            return {
                "answer": "No encontré información específica sobre tu pregunta en los documentos disponibles. Por favor, asegúrate de que tu pregunta esté relacionada con redes, telecomunicaciones o protocolos de red.",
                "hits": len(hits),
                "contexts": [],
                "source": "empty_context"
            }

        # Construir el prompt con contexto de conversación si está disponible
        # El contexto de conversación puede contener acciones, resultados y eventos previos
        context_section = ""
        if conversation_context:
            context_section = f"""
CONTEXTO DE CONVERSACIÓN PREVIA:
{conversation_context}

INSTRUCCIONES SOBRE EL CONTEXTO DE CONVERSACIÓN:
1. Si la pregunta hace referencia directa a acciones, resultados o eventos mencionados en el contexto de conversación (ej: "el ping que hiciste", "antes del ping", "el resultado anterior", "a qué dominio fue"), USA esa información del contexto de conversación para responder.
2. Si la pregunta es un SEGUIMIENTO de algo mencionado en el contexto (ej: "cuales son los tipos?", "explica más", "menciona otros", "qué más hay"), y el contexto menciona un tema de redes/telecomunicaciones, entonces:
   - USA el CONTEXTO DE CONVERSACIÓN para entender a qué se refiere la pregunta
   - BUSCA en los DOCUMENTOS información relacionada con ese tema del contexto
   - COMBINA ambas fuentes: usa el contexto para entender la referencia y los documentos para la información técnica
3. Si la pregunta es sobre conceptos técnicos, definiciones o información educativa SIN referencia al contexto, usa EXCLUSIVAMENTE los DOCUMENTOS.
4. Si la pregunta pregunta específicamente sobre algo que pasó en la conversación previa (dominios, IPs, resultados de operaciones), el contexto de conversación es la fuente PRINCIPAL de información.
5. Para información técnica general (qué es, cómo funciona, definiciones), los DOCUMENTOS son la ÚNICA fuente de información. NO agregues conocimiento general.

EJEMPLOS DE SEGUIMIENTO:
- Contexto: "Los firewalls son dispositivos de seguridad..."
- Pregunta: "Cuales son los tipos?"
- Respuesta: Buscar en documentos información sobre "tipos de firewalls" y responder basándose en los documentos.

- Contexto: "Hice ping a google.com y obtuve..."
- Pregunta: "A qué dominio fue?"
- Respuesta: Usar el contexto de conversación (google.com).
"""

        # Logging detallado para debugging: mostrar qué chunks se recuperaron
        logger.info(f"[RAG] Chunks recuperados para consulta '{query_text[:50]}...': {len(hits)} hits totales")
        if hits:
            logger.info(f"[RAG] Top 5 hits con sus scores:")
            for i, hit in enumerate(hits[:5], 1):  # Mostrar los primeros 5
                chunk_text = hit["payload"].get("text", "")[:150]  # Primeros 150 chars
                score = hit.get('score', 0)
                document_id = hit["payload"].get("document_id", "unknown")
                logger.info(f"[RAG]   {i}. Score: {score:.4f} | Doc: {document_id[:8]}... | Texto: {chunk_text}...")
        else:
            logger.warning(f"[RAG] ⚠️ No se encontraron chunks para la consulta: '{query_text}'")
            logger.warning(f"[RAG] ⚠️ Esto puede indicar que:")
            logger.warning(f"[RAG]     - Los documentos no están indexados en Qdrant")
            logger.warning(f"[RAG]     - La búsqueda vectorial no encontró coincidencias semánticas")
            logger.warning(f"[RAG]     - El embedding de la consulta no es similar a los embeddings de los documentos")
        
        # Determinar longitud objetivo según complejidad (ya obtenida en paralelo)
        # AUMENTADO: Límites más altos para asegurar respuestas completas, especialmente para listas
        if "simple" in complexity:
            length_guidance = "Respuesta BREVE y DIRECTA: 2-4 oraciones (50-100 palabras). Ve directo al punto sin explicaciones largas."
            max_tokens_response = 200  # Aumentado de 100 a 200
        elif "compleja" in complexity:
            length_guidance = "Respuesta COMPLETA y DETALLADA: 200-400 palabras con explicación estructurada, ejemplos si son relevantes, y organización clara. Si la pregunta requiere una lista completa (ej: todas las capas del modelo OSI, todos los tipos de algo), asegúrate de incluir TODOS los elementos de la lista sin omitir ninguno."
            max_tokens_response = 1200  # Aumentado de 600 a 1200 para listas completas
        else:  # moderada
            length_guidance = "Respuesta EQUILIBRADA: 100-200 palabras con explicación clara y algunos detalles relevantes. Si la pregunta requiere una lista, incluye todos los elementos importantes."
            max_tokens_response = 500  # Aumentado de 300 a 500
        
        # OPTIMIZACIÓN: Usar template pre-compilado para construir el prompt
        prompt = self.BASE_PROMPT_TEMPLATE.format(
            length_guidance=length_guidance,
            context_section=context_section,
            context=context,
            query_text=query_text
        )
        
        # Ejecutar llamada a OpenAI en thread separado (operación síncrona bloqueante)
        def _sync_generate_answer():
            """Genera la respuesta usando OpenAI (operación síncrona)."""
            completion = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_MESSAGE},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Temperatura baja para mayor fidelidad y determinismo
                max_tokens=max_tokens_response  # Tokens adaptados según complejidad de la pregunta
            )
            return completion.choices[0].message.content.strip()
        
        # Usar asyncio.to_thread para ejecutar la operación bloqueante sin bloquear el event loop
        answer = await asyncio.to_thread(_sync_generate_answer)
        
        # Validación post-generación general: verificar que afirmaciones clave estén respaldadas por el contexto
        # Este es un sistema de validación general que funciona para cualquier tipo de pregunta
        context_lower = context.lower()
        answer_lower = answer.lower()
        
        # Extraer frases clave de la respuesta (aproximación simple)
        # Dividir la respuesta en oraciones y verificar que conceptos principales estén en el contexto
        sentences = re.split(r'[.!?]\s+', answer)
        
        potential_hallucinations = []
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            # Extraer palabras clave importantes (nombres propios, tecnologías, conceptos técnicos)
            # Palabras que son probablemente conceptos técnicos (mayúsculas, acrónimos, etc.)
            words = re.findall(r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\b', sentence)
            tech_patterns = re.findall(r'\b[a-z]+(?:\s+[a-z]+)*\b', sentence.lower())
            
            # Verificar si la oración menciona conceptos que no están en el contexto
            sentence_lower = sentence.lower()
            # Si la oración es muy específica y no tiene palabras clave del contexto, podría ser alucinada
            # Pero esto es una heurística simple - no perfecta
            
            # Lista de tecnologías/conceptos comunes que suelen ser alucinados (para logging)
            common_hallucination_keywords = {
                "frame relay", "atm", "asynchronous transfer mode", "sd-wan", 
                "software-defined wan", "dsl", "digital subscriber line", "adsl",
                "cable modem", "ftth", "fiber to the home"
            }
            
            for keyword in common_hallucination_keywords:
                if keyword in sentence_lower and keyword not in context_lower:
                    potential_hallucinations.append(f"'{keyword}' mencionado pero no está en el contexto")
        
        if potential_hallucinations:
            logger.warning(f"⚠️ POSIBLE ALUCINACIÓN DETECTADA: {len(potential_hallucinations)} posibles problemas")
            logger.warning(f"Detalles: {', '.join(potential_hallucinations[:5])}")  # Mostrar solo los primeros 5
            logger.debug(f"Contexto recuperado ({len(hits)} chunks): {context[:500]}...")
            logger.debug(f"Respuesta generada: {answer[:500]}...")
        
        # Retornar respuesta con contextos para evaluación (si se necesita)
        # Los contextos se pueden usar para evaluación con Ragas
        contexts_list = [h["payload"].get("text", "") for h in hits[:10] if h.get("payload", {}).get("text")]  # Primeros 10 chunks
        
        logger.info(f"[RAG] Retornando {len(contexts_list)} contextos de {len(hits)} hits totales")
        
        result = {
            "answer": answer,
            "hits": len(hits),
            # Incluir contextos para evaluación (primeros chunks como lista)
            "contexts": contexts_list
        }
        
        return result



# Test