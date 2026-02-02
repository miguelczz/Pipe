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
from ..repositories.qdrant_repository import QdrantRepository, get_qdrant_repository
from ..utils.embeddings import embedding_for_text
from ..core.cache import cache_result

# Cliente OpenAI para generación de respuestas
# NOTA: Este cliente es síncrono. Todas las llamadas deben envolverse con asyncio.to_thread()
# para evitar bloquear el event loop. El cliente puede usar time.sleep internamente para retries.
client = OpenAI(
    api_key=settings.openai_api_key,
    max_retries=2
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
Analiza si la siguiente pregunta puede ser respondida basándose en la documentación técnica interna, los resultados de análisis de capturas Wireshark almacenados o las capacidades de Pipe.

Pregunta del usuario: "{query_text}"

- CORE MISSION RELEVANCE: Mark as RELEVANT any question seeking technical guidance, procedural understanding, or explanation of network behaviors typical of Band Steering and Wireshark.
- MANDATORY RELEVANCE: "La prueba", "el análisis", "la guía", "el procedimiento", or asking "con qué me guío" ALWAYS refer to the Band Steering project documentation. Mark them as RELEVANT immediately.
- DOMAIN OVER KEYWORDS: Do not rely solely on specific words. If the intent is technical or related to interpreting network outcomes, it is RELEVANT.
- CONTEXTUAL CONTINUITY: If the question is a follow-up or relates to the core system functionalities (BTM, KVR, 802.11 standards), it is RELEVANT.

Responde SOLO con una palabra: "relevante" o "no_relevante".
"""


    
    COMPLEXITY_PROMPT_TEMPLATE = """
Analiza la siguiente pregunta y determina su complejidad:

Pregunta: "{query_text}"

Determina si es:
    pass
1. "simple" - Pregunta directa que requiere una respuesta breve (ej: "¿Qué es X?", "¿Cuál es Y?")
2. "moderada" - Pregunta que requiere una explicación con algunos detalles (ej: "¿Cómo funciona X?", "Explica Y")
3. "compleja" - Pregunta que requiere una explicación detallada, múltiples aspectos, O una lista completa de elementos (ej: "Compara X e Y", "Explica todos los aspectos de Z", "¿Cuáles son las capas del modelo OSI?", "Menciona todos los tipos de X", "Lista todas las capas", "¿Cuáles son todas las...?")

IMPORTANTE: Si la pregunta requiere una LISTA COMPLETA de elementos (ej: "capas del modelo OSI", "tipos de firewalls", "protocolos de red", "todas las capas", "cuáles son las capas"), debe ser marcada como "compleja" para asegurar que se incluyan TODOS los elementos sin omitir ninguno.

Responde SOLO con una palabra: "simple", "moderada" o "compleja".
"""
    
    BASE_PROMPT_TEMPLATE = """
Eres un asistente experto en análisis de capturas Wireshark, redes WiFi y Band Steering. Tu objetivo es ayudar al usuario respondiendo sus preguntas basándote en la documentación técnica proporcionada por Pipe.
Importante: Cualquier dato ambiguo debe interpretarse bajo el espectro de redes (ej: asociación = asociación WiFi 802.11).

INSTRUCCIONES DE RESPUESTA:
    pass
1. **FUENTE DE VERDAD ABSOLUTA**: Usa EXCLUSIVAMENTE la información contenida en el "CONTEXTO DE DOCUMENTOS". Tienes acceso a los manuales técnicos de Band Steering basados en Wireshark. Si el dato no está en el documento, NO lo inventes ni uses conocimiento general de redes.
2. **CONTEXTO WIRESHARK**: Todo análisis de Band Steering aquí se basa en Wireshark. Si el usuario pregunta por "la prueba" o "guiarse", refiérete a los criterios técnicos del documento.
3. **ESTILO EXPLICATIVO**: Explica de manera técnica pero accesible. Prioriza códigos de estado BTM y eventos de transición mencionados en el texto.
   - **Valores simples**: Usa `código en línea` (un backtick) para IPs, dominios, comandos cortos, códigos BTM y rutas. Ej: `Status Code 0`, `BTM Request`.
   - **NO USES BLOQUES DE CÓDIGO** (```) para una sola línea o un solo valor. Los bloques son solo para scripts largos o configuraciones extensas.
   - **NO USES TABLAS** a menos que sea estrictamente necesario para comparar muchos datos. Para listas de valores, usa listas con viñetas (• o -).
   - **LISTAS CORRECTAS**: La viñeta y el texto deben estar en la MISMA LÍNEA. No pongas la viñeta sola en una línea.
     * Bien: • **Fase 1:** Diseño de requerimientos.
     * Mal: •\n**Fase 1:** Diseño de requerimientos.
   - **Evita scroll horizontal**: Mantén las líneas contenidas y usa formatos compactos.
4. **NO INVENTAR DATOS**: Si el documento menciona 3 conceptos o fases, explica esos 3.
5. **MANEJO DE VACÍOS**: Si la información sobre Band Steering no está en los documentos, indícalo suavemente indicando que no se encuentra en la documentación técnica actual.

{context_section}
CONTEXTO DE DOCUMENTOS (Documentación Band Steering):
    pass
{context}

Pregunta: {query_text}

Genera una respuesta natural, útil y precisa. Recuerda: usa `código en línea` para valores técnicos, NO bloques grandes, y listas bien formateadas.
Respuesta:
    pass
"""
    
    SYSTEM_MESSAGE = """Eres un experto en análisis de capturas Wireshark de Pipe, especializado EXCLUSIVAMENTE en el análisis de Band Steering y protocolos de red. 

TU MISIÓN:
    pass
1. Responder ÚNICAMENTE basándote en los documentos técnicos proporcionados.
2. Todo concepto debe interpretarse desde la perspectiva de análisis de capturas Wireshark y el proyecto Pipe.
3. Si la información no está en los documentos, indica: "No encontré esta información específica en los manuales técnicos de Band Steering, pero basándome en el contexto de la prueba...".
4. PROHIBIDO: Dar explicaciones generales de redes que no aporten al análisis de Band Steering.
5. MEMORIA: Mantén el hilo de la conversación para entender a qué se refiere el usuario (ej: si pregunta por "la diferencia", se refiere a la diferencia entre los conceptos de red explicados anteriormente en el contexto de Band Steering).
"""
    
    RELEVANCE_SYSTEM_MESSAGE = "Eres un analizador técnico de Pipe. 'La prueba', 'el análisis', 'la guía' o 'guiarse' se refieren SIEMPRE al análisis de capturas Wireshark y Band Steering y deben marcarse como RELEVANTES de forma obligatoria."
    
    COMPLEXITY_SYSTEM_MESSAGE = "Eres un analizador que determina la complejidad de preguntas."
    
    # Keywords comunes para búsqueda dispersa
    KEYWORD_PATTERNS = {
        'wifi': ['wifi', 'wi-fi', 'wireless', '802.11', 'association', 'reassociation', 'asociación', 'reasociación', 'asosacion', 'reasosacion', 'asosiacion'],
        'band_steering': ['band steering', 'btm', 'bss transition', '802.11v', '802.11k', '802.11r', 'kvr', 'steering', 'transicion', 'transición'],
        'ethernet': ['ethernet', 'cable', 'rj45', 'lan'],
        'tcp': ['tcp', 'retransmisión', 'retransmission', 'window size'],
        'dns': ['dns', 'domain', 'lookup', 'mx', 'txt'],
        'ip': ['ip address', 'v4', 'v6', 'icmp', 'ping', 'traceroute'],
    }
    
    def __init__(self):
        self.qdrant_repo = get_qdrant_repository()

    async def _query_without_cache(self, query_text: str, top_k: int = 8, conversation_context: Optional[str] = None):
        """
        Método interno que realiza la consulta RAG sin usar cache.
        Se usa cuando hay contexto de conversación para evitar cachear respuestas contextualizadas.
        """
        return await self._execute_query(query_text, top_k, conversation_context)

    async def _query_with_cache(self, query_text: str, top_k: int = 12, conversation_context: Optional[str] = None):
        """
        Método interno que realiza la consulta RAG con cache.
        Solo se usa cuando NO hay contexto de conversación.
        IMPORTANTE: conversation_context debe ser None siempre cuando se llama este método.
        """
        # Si por alguna razón se pasa contexto, no usar cache
        if conversation_context:
            return await self._query_without_cache(query_text, top_k, conversation_context)
        
        # Usar el decorador de cache solo cuando no hay contexto
        return await self._execute_query_cached(query_text, top_k)
    
    @cache_result("rag", ttl=7200)  # Cache por 2 horas (optimizado para mejor rendimiento)
    async def _execute_query_cached(self, query_text: str, top_k: int = 12):
        """
        Método interno cacheado que ejecuta la consulta RAG.
        Solo se llama cuando NO hay contexto de conversación.
        """
        return await self._execute_query(query_text, top_k, None)

    def query(self, query_text: str, top_k: int = 12, conversation_context: Optional[str] = None):
        """
        Realiza una consulta RAG sobre los documentos indexados.
        
        Args:
            query_text: Texto de la consulta
            top_k: Número de resultados a recuperar (aumentado a 12 para mejor cobertura)
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
            return _run_async(self._query_without_cache(query_text, top_k, conversation_context))
        else:
            # Sin contexto, usar cache normal
            return _run_async(self._query_with_cache(query_text, top_k, None))

    def _extract_keywords(self, query_text: str) -> List[str]:
        """
        Extrae keywords relevantes de la consulta para búsqueda dispersa.
        OPTIMIZADO: Ahora extrae palabras significativas de la consulta del usuario,
        no solo de una lista predefinida, para mejorar el matching de frases exactas.
        """
        query_lower = query_text.lower()
        keywords = []
        
        # 1. Buscar patrones técnicos predefinidos (alta prioridad)
        for pattern_key, pattern_list in self.KEYWORD_PATTERNS.items():
            if any(pattern in query_lower for pattern in pattern_list):
                keywords.extend(pattern_list)
        
        # 2. Extraer sustantivos y términos significativos de la query
        # Eliminar palabras comunes/stopwords (lista básica en español e inglés)
        stopwords = {
            'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'y', 'o', 'de', 'del', 'al', 'a', 'en', 
            'con', 'por', 'para', 'sin', 'sobre', 'que', 'cual', 'quien', 'como', 'donde', 'cuando', 
            'es', 'son', 'fue', 'fueron', 'tiene', 'tienen', 'hay', 'hacer', 'esta', 'este', 'ese', 'esa',
            'what', 'is', 'are', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'
        }
        
        # Limpiar caracteres no alfanuméricos simples
        clean_text = re.sub(r'[^\w\s]', '', query_lower)
        words = clean_text.split()
        
        for word in words:
            # Filtrar palabras cortas (<3 chars) y stopwords
            if len(word) >= 3 and word not in stopwords:
                # Evitar duplicados
                if word not in keywords:
                    keywords.append(word)
        
        # Logging para debugging de qué keywords se están usando
        if keywords:
            pass
            
        return keywords
    
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
                results = self.qdrant_repo.search(
                    query_vector=query_vector,
                    top_k=search_top_k
                )
                return results
            
            # Usar asyncio.to_thread para ejecutar operación síncrona sin bloquear
            hits = await asyncio.to_thread(_sync_dense_search)
            return hits
        except Exception as e:
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
    
    async def _execute_query(self, query_text: str, top_k: int = 12, conversation_context: Optional[str] = None):
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
            # OPTIMIZACIÓN: Refinar la consulta usando el contexto de conversación para mejorar el search
            # Esto "des-referencia" preguntas como "¿y cual es la diferencia?" a algo técnico completo
            search_query = query_text
            if conversation_context:
                try:
                    refinement_prompt = f"""
Transforma la siguiente "Pregunta Corta" en una "Consulta Técnica Completa" buscando resolver la referencia técnica basada en el "Contexto de Conversación".

EL ENFOQUE DEBE SER EXCLUSIVAMENTE: Band Steering, análisis de capturas Wireshark, BTM, WiFi 802.11 y el proyecto Pipe.

CONTEXTO DE CONVERSACIÓN (Historial previo):
    pass
{conversation_context}

PREGUNTA CORTA ACTUAL: "{query_text}"

INSTRUCCIONES:
    pass
1. Si el usuario pregunta "cual es la diferencia", identifica qué términos se comparaban en el historial y genera una consulta técnica como "Diferencia técnica entre [Termino A] y [Termino B] en el contexto de Band Steering y Wireshark".
2. Si el usuario pregunta por "eso" o "la prueba", relaciónalo con los conceptos técnicos de la conversación.
3. El resultado debe ser una frase técnica óptima para buscar en manuales de ingeniería de redes.
4. Responde SOLO con la consulta técnica refinada, sin introducciones.

Consulta técnica refinada:
    pass
"""
                    def _sync_refine():
                        res = client.chat.completions.create(
                            model=settings.llm_model,
                            messages=[{"role": "system", "content": "Eres un refinador de consultas técnicas."}, {"role": "user", "content": refinement_prompt}],
                            temperature=0,
                            max_tokens=60
                        )
                        return res.choices[0].message.content.strip()
                    
                    refined = await asyncio.to_thread(_sync_refine)
                    if refined and len(refined) > 5:
                        search_query = refined
                except Exception as e:
                    pass

            # OPTIMIZACIÓN: Extraer keywords antes de las búsquedas
            keywords = self._extract_keywords(search_query)
            
            # OPTIMIZACIÓN: Ejecutar búsqueda densa y dispersa en paralelo usando asyncio.gather()
            # Esto es más eficiente que ThreadPoolExecutor para operaciones I/O
            tasks = [self._dense_search(search_query, top_k)]
            
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
                pass
            if len(results) > 1 and isinstance(results[1], Exception):
                pass
            
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
                        return {
                            "answer": "No hay documentos disponibles en la base de datos. Por favor, sube documentos PDF relacionados con redes y telecomunicaciones para que pueda responder tus preguntas.",
                            "hits": 0,
                            "contexts": [],
                            "source": "no_documents"
                        }
                    else:
                        # Intentar una búsqueda más amplia con top_k mayor
                        try:
                            query_vector = embedding_for_text(query_text)
                            alternative_hits = self.qdrant_repo.search(query_vector=query_vector, top_k=20)
                            if alternative_hits:
                                hits = alternative_hits
                        except Exception as e:
                            pass
                except Exception as e:
                    pass
                
                # Si después de la búsqueda alternativa aún no hay hits, retornar mensaje
                if not hits:
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
Analiza si la siguiente pregunta es relevante para Pipe (Análisis de capturas Wireshark y Band Steering).

CONTEXTO DE CONVERSACIÓN PREVIA:
    pass
{conversation_context}

Pregunta del usuario: "{query_text}"

INSTRUCCIONES CRÍTICAS:
    pass
- CORE DOMAIN: Si la pregunta trata sobre "la prueba", "guiarse", "resultados", o cualquier aspecto técnico de red mencionado en los manuales, es RELEVANTE.
- CONTINUIDAD: Si la pregunta es un seguimiento de un tema de redes o del proyecto Pipe, marca como RELEVANTE.
- No seas restrictivo con las palabras; si el usuario busca ayuda técnica o procedimental del sistema, es RELEVANTE.

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
                return is_relevant
            except Exception as e:
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
                return "moderada"
        
        # OPTIMIZACIÓN: Ejecutar validación de relevancia y complejidad en paralelo usando asyncio.gather()
        is_relevant, complexity = await asyncio.gather(
            check_relevance(),
            check_complexity(),
            return_exceptions=True
        )
        
        # Manejar excepciones
        if isinstance(is_relevant, Exception):
            is_relevant = True
        if isinstance(complexity, Exception):
            complexity = "moderada"
        
        # Si no es relevante, retornar mensaje indicando que no puede responder
        if not is_relevant:
            return {
                "answer": "Lo siento, mi conocimiento está limitado a la documentación técnica de Pipe y análisis de capturas Wireshark y Band Steering. Tu pregunta parece estar fuera de este ámbito especializado.",
                "hits": 0,
                "contexts": [],
                "source": "out_of_topic"
            }
        
        # Filtrar y concatenar los chunks más relevantes
        # IMPORTANTE: Usar un umbral más bajo (0.25) para incluir más resultados relevantes y aumentar cobertura
        relevant_hits = [h for h in hits if h.get('score', 0) > 0.25]
        
        # Si no hay hits con score > 0.25, usar los top 5 resultados (incluso con scores bajos)
        if not relevant_hits:
            relevant_hits = hits[:5] if hits else []
        else:
            # Limitar a máximo 6 chunks más relevantes para tener mejor cobertura (antes 3)
            relevant_hits = relevant_hits[:6]
        
        # Concatenar los textos más relevantes
        context = "\n\n".join([h["payload"].get("text", "") for h in relevant_hits])
        
        # OPTIMIZACIÓN: Limitar tamaño del contexto para evitar problemas de memoria y latencia
        MAX_CONTEXT_LENGTH = 5500  # Reducido de 7000 para mejorar velocidad y evitar timeouts
        if len(context) > MAX_CONTEXT_LENGTH:
            # Truncar contexto manteniendo los primeros chunks más relevantes
            context = context[:MAX_CONTEXT_LENGTH]
        
        # Logging detallado para debugging
        if relevant_hits:
            scores = [h.get('score', 0) for h in relevant_hits]
        
        # Si el contexto está vacío después del filtrado, retornar error
        if not context or not context.strip():
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
    pass
{conversation_context}

INSTRUCCIONES SOBRE EL CONTEXTO DE CONVERSACIÓN:
    pass
1. Si la pregunta hace referencia directa a acciones, resultados o eventos mencionados en el contexto de conversación (ej: "el ping que hiciste", "antes del ping", "el resultado anterior", "a qué dominio fue"), USA esa información del contexto de conversación para responder.
2. Si la pregunta es un SEGUIMIENTO de algo mencionado en el contexto (ej: "cuales son los tipos?", "explica más", "menciona otros", "qué más hay"), y el contexto menciona un tema de redes/telecomunicaciones, entonces:
   - USA el CONTEXTO DE CONVERSACIÓN para entender a qué se refiere la pregunta
   - BUSCA en los DOCUMENTOS información relacionada con ese tema del contexto
   - COMBINA ambas fuentes: usa el contexto para entender la referencia y los documentos para la información técnica
3. Si la pregunta es sobre conceptos técnicos, definiciones o información educativa SIN referencia al contexto, usa EXCLUSIVAMENTE los DOCUMENTOS.
4. Si la pregunta pregunta específicamente sobre algo que pasó en la conversación previa (dominios, IPs, resultados de operaciones), el contexto de conversación es la fuente PRINCIPAL de información.
5. Para información técnica general (qué es, cómo funciona, definiciones), los DOCUMENTOS son la ÚNICA fuente de información. NO agregues conocimiento general.

EJEMPLOS DE SEGUIMIENTO:
    pass
- Contexto: "Los firewalls son dispositivos de seguridad..."
- Pregunta: "Cuales son los tipos?"
- Respuesta: Buscar en documentos información sobre "tipos de firewalls" y responder basándose en los documentos.

- Contexto: "Hice ping a google.com y obtuve..."
- Pregunta: "A qué dominio fue?"
- Respuesta: Usar el contexto de conversación (google.com).
"""

        # Logging detallado para debugging: mostrar qué chunks se recuperaron
        if hits:
            for i, hit in enumerate(hits[:5], 1):  # Mostrar los primeros 5
                chunk_text = hit["payload"].get("text", "")[:150]  # Primeros 150 chars
                score = hit.get('score', 0)
                document_id = hit["payload"].get("document_id", "unknown")
        
        # Determinar longitud objetivo según complejidad (ya obtenida en paralelo)
        # AUMENTADO: Límites más altos para asegurar respuestas completas, especialmente para listas
        if "simple" in complexity:
            length_guidance = "Respuesta BREVE y DIRECTA: 2-4 oraciones (50-100 palabras). Ve directo al punto sin explicaciones largas."
            max_tokens_response = 200  # Aumentado de 100 a 200
        elif "compleja" in complexity:
            length_guidance = "Respuesta COMPLETA y DETALLADA: 200-400 palabras con explicación estructurada, ejemplos si son relevantes, y organización clara. Si la pregunta requiere una lista completa (ej: todas las capas del modelo OSI, todos los tipos de algo), asegúrate de incluir TODOS los elementos de la lista sin omitir ninguno."
            max_tokens_response = 800  # Optimizado para velocidad (antes 1200)
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
            pass
        
        # Retornar respuesta con contextos para evaluación (si se necesita)
        # Los contextos se pueden usar para evaluación con Ragas
        contexts_list = [h["payload"].get("text", "") for h in hits[:10] if h.get("payload", {}).get("text")]  # Primeros 10 chunks
        
        
        result = {
            "answer": answer,
            "hits": len(hits),
            # Incluir contextos para evaluación (primeros chunks como lista)
            "contexts": contexts_list
        }
        
        return result



# Test