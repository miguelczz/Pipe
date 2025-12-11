"""
Ejecutores de herramientas para el agente.
Cada función ejecuta una herramienta específica y retorna el resultado.
"""
import re
import logging
from typing import Any, Dict, List, Optional
from ..tools.rag_tool import RAGTool
from ..tools.ip_tool import IPTool
from ..tools.dns_tool import DNSTool
from ..agent.llm_client import LLMClient
from ..agent.helpers import (
    detect_operation_type,
    extract_domain_from_text,
    extract_domain_using_llm,
    extract_hosts_from_text,
    detect_dns_operation_type,
    extract_domains_from_text,
    extract_ip_from_text
)
from langchain_core.messages import AnyMessage

logger = logging.getLogger(__name__)

rag_tool = RAGTool()
ip_tool = IPTool()
dns_tool = DNSTool()
llm = LLMClient()


def get_conversation_context(messages: List[AnyMessage], max_messages: int = 10) -> str:
    """
    Extrae el contexto de conversación de los mensajes.
    OPTIMIZACIÓN: Limita el tamaño total del contexto para evitar problemas de memoria.
    
    Args:
        messages: Lista de mensajes
        max_messages: Número máximo de mensajes a incluir
    
    Returns:
        Contexto formateado como string (limitado a 5000 caracteres para balance entre funcionalidad y memoria)
    """
    if not messages:
        return ""
    
    conversation_context = []
    total_length = 0
    MAX_CONTEXT_LENGTH = 5000  # Límite aumentado para mantener funcionalidad pero evitar problemas de memoria
    
    # Iterar desde los mensajes más recientes hacia atrás
    for msg in reversed(messages[-max_messages:]):
        role = getattr(msg, "role", None) or getattr(msg, "type", "user")
        content = getattr(msg, "content", str(msg))
        
        if role in ["user", "human", "assistant", "agent"]:
            if role in ["human", "user"]:
                role = "user"
            elif role in ["assistant", "agent"]:
                role = "assistant"
            
            # Truncar contenido individual si es muy largo (mantener hasta 1000 chars por mensaje)
            if len(content) > 1000:
                content = content[:1000] + "..."
            
            msg_text = f"{role}: {content}"
            
            # Verificar si agregar este mensaje excedería el límite
            if total_length + len(msg_text) + 1 > MAX_CONTEXT_LENGTH:  # +1 por el \n
                break
            
            conversation_context.insert(0, msg_text)
            total_length += len(msg_text) + 1  # +1 por el \n
    
    result = "\n".join(conversation_context)
    
    # Si aún es muy largo, truncar (caso extremo)
    if len(result) > MAX_CONTEXT_LENGTH:
        result = result[:MAX_CONTEXT_LENGTH] + "..."
        logger.debug(f"[ConversationContext] Contexto truncado a {MAX_CONTEXT_LENGTH} caracteres")
    
    return result


def execute_ip_tool(step: str, prompt: str, messages: List[AnyMessage]) -> Dict[str, Any]:
    """
    Ejecuta la herramienta IP según el tipo de operación detectada.
    
    Args:
        step: Paso del plan actual
        prompt: Prompt del usuario
        messages: Mensajes de la conversación
    
    Returns:
        Resultado de la ejecución
    """
    search_text = f"{prompt} {step or ''}"
    
    # Obtener contexto de conversación para mejorar detección
    conversation_context = None
    if messages:
        conversation_context = get_conversation_context(messages, max_messages=5)
    
    operation_type = detect_operation_type(step, prompt, conversation_context)
    
    # Extraer hosts del texto
    hosts = extract_hosts_from_text(search_text, ip_tool.validate_ip_or_domain)
    
    # Si no se encontraron hosts y hay contexto de conversación, intentar extraer del contexto
    if not hosts and messages:
        conversation_context = get_conversation_context(messages, max_messages=5)
        if conversation_context:
            # Buscar en el contexto si hay aclaraciones sobre hosts (ej: "x es twitter")
            # Combinar el prompt actual con el contexto para búsqueda
            combined_text = f"{search_text} {conversation_context}"
            hosts_from_context = extract_hosts_from_text(combined_text, ip_tool.validate_ip_or_domain)
            
            # Si encontramos hosts en el contexto, usarlos
            if hosts_from_context:
                logger.info(f"[IP Tool] Hosts encontrados en contexto de conversación: {hosts_from_context}")
                hosts = hosts_from_context
    
    if operation_type == "ping":
        return _execute_ping(hosts, search_text, messages)
    elif operation_type == "traceroute":
        return _execute_traceroute(hosts, search_text)
    elif operation_type == "compare":
        return _execute_compare(hosts, search_text, messages)
    else:
        # Por defecto: si hay un dominio o host, intentar ping (operación más común)
        # Pero solo si realmente no se pudo determinar el tipo de operación
        domain = extract_domain_from_text(search_text)
        if domain:
            logger.info(f"[IP Tool] Operación 'default' detectada, intentando ping a {domain}")
            return ip_tool.ping(domain)
        elif hosts:
            logger.info(f"[IP Tool] Operación 'default' detectada, intentando ping a {hosts[0]}")
            return ip_tool.ping(hosts[0])
        else:
            return {"error": "no_valid_ip_or_host_found"}


def _execute_ping(hosts: List[str], search_text: str, messages: List[AnyMessage] = None) -> Dict[str, Any]:
    """Ejecuta operación de ping."""
    if hosts:
        ping_results = [ip_tool.ping(host, count=4) for host in hosts]
        if len(ping_results) > 1:
            return {
                "type": "multiple_ping",
                "results": ping_results,
                "summary": f"Ping ejecutado a {len(ping_results)} hosts"
            }
        return ping_results[0] if ping_results else {"error": "no_valid_ip_or_host_found"}
    
    # Intentar extraer dominios (incluyendo nombres de servicios)
    domains = extract_domains_from_text(search_text)
    if domains:
        ping_results = [ip_tool.ping(domain, count=4) for domain in domains]
        if len(ping_results) > 1:
            return {
                "type": "multiple_ping",
                "results": ping_results,
                "summary": f"Ping ejecutado a {len(ping_results)} hosts"
            }
        return ping_results[0] if ping_results else {"error": "no_valid_ip_or_host_found"}
    
    # Intentar extraer un solo dominio
    domain = extract_domain_from_text(search_text)
    if domain:
        return ip_tool.ping(domain)
    
    # Si hay contexto de conversación, intentar extraer del contexto
    if messages:
        conversation_context = get_conversation_context(messages, max_messages=5)
        if conversation_context:
            # Buscar aclaraciones en el contexto (ej: "x es twitter" → "twitter.com")
            combined_text = f"{search_text} {conversation_context}"
            
            # Intentar extraer dominio del contexto combinado
            domain_from_context = extract_domain_from_text(combined_text)
            if domain_from_context:
                logger.info(f"[Ping] Dominio encontrado en contexto: {domain_from_context}")
                return ip_tool.ping(domain_from_context)
            
            # Usar LLM para entender aclaraciones (ej: "x es twitter")
            domain_from_llm = extract_domain_using_llm(combined_text)
            if domain_from_llm:
                logger.info(f"[Ping] Dominio extraído con LLM del contexto: {domain_from_llm}")
                return ip_tool.ping(domain_from_llm)
    
    # Usar LLM como último recurso
    domain = extract_domain_using_llm(search_text)
    if domain:
        return ip_tool.ping(domain)
    
    return {"error": "no_valid_ip_or_host_found"}


def _execute_traceroute(hosts: List[str], search_text: str) -> Dict[str, Any]:
    """Ejecuta operación de traceroute."""
    if hosts:
        return ip_tool.tracert(hosts[0])
    
    # Intentar extraer dominios (incluyendo nombres de servicios)
    domains = extract_domains_from_text(search_text)
    if domains:
        return ip_tool.tracert(domains[0])
    
    domain = extract_domain_from_text(search_text)
    if domain:
        return ip_tool.tracert(domain)
    
    domain = extract_domain_using_llm(search_text)
    if domain:
        return ip_tool.tracert(domain)
    
    return {"error": "no_valid_ip_or_host_found"}


def _extract_previous_result_host(messages: List[AnyMessage], search_text: str) -> Optional[str]:
    """
    Usa el LLM para entender el contexto y extraer el dominio de un resultado anterior
    mencionado en la solicitud del usuario. No depende de palabras clave, sino que analiza
    la intención y el contexto de la conversación.
    
    Returns:
        Dominio del resultado anterior mencionado o None si no hay referencia
    """
    if not messages:
        return None
    
    try:
        # Obtener contexto de conversación
        conversation_context = get_conversation_context(messages, max_messages=10)
        if not conversation_context:
            return None
        
        # Usar LLM para entender si el usuario se refiere a un resultado anterior
        # y cuál dominio usar para la comparación
        llm_prompt = f"""
Analiza la siguiente solicitud del usuario y el contexto de conversación previa.

Solicitud actual del usuario: "{search_text}"

Contexto de conversación previa:
{conversation_context}

INSTRUCCIONES:
1. Determina si el usuario se refiere a un resultado anterior de ping o traceroute en la conversación
2. Si se refiere a un resultado anterior, identifica el dominio o host de ESE resultado específico
3. El usuario puede referirse al último resultado, al penúltimo, o a cualquier resultado anterior mencionado
4. Analiza el contexto para entender a qué resultado específico se refiere el usuario
5. Responde SOLO con el dominio completo del resultado anterior (ej: instagram.com), sin explicaciones
6. Si el usuario NO se refiere a un resultado anterior, responde "ninguno"
7. Si no encuentras un dominio claro, responde "ninguno"

Ejemplos:
- Si el usuario dice "comparalo con facebook" y antes se hizo ping a instagram.com → responde "instagram.com"
- Si el usuario dice "comparalo con el ping anterior" y el último ping fue a google.com → responde "google.com"
- Si el usuario dice "comparalo con el ping que hiciste antes del último" y hubo ping a instagram.com y luego a google.com → responde "instagram.com"
- Si el usuario dice "compara facebook con google" sin referirse a resultados anteriores → responde "ninguno"

Dominio del resultado anterior (o "ninguno"):
"""
        llm_response = llm.generate(llm_prompt, max_tokens=100).strip().lower()
        
        # Limpiar la respuesta del LLM
        llm_response = re.sub(r'[^\w\.-]', '', llm_response)
        if llm_response and llm_response != "ninguno" and '.' in llm_response:
            if ip_tool.validate_ip_or_domain(llm_response):
                logger.info(f"[Compare] Dominio del resultado anterior identificado por LLM: {llm_response}")
                return llm_response
        
    except Exception as e:
        logger.warning(f"Error al extraer dominio del resultado anterior con LLM: {e}")
    
    return None


def _execute_compare(hosts: List[str], search_text: str, messages: List[AnyMessage] = None) -> Dict[str, Any]:
    """Ejecuta operación de comparación de IPs."""
    # Detectar número de dominios solicitados
    num_domains_match = re.search(r'(\d+)\s*(?:dominios?|ips?|hosts?)', search_text.lower())
    requested_count = 2
    if num_domains_match:
        requested_count = max(2, min(5, int(num_domains_match.group(1))))
    
    # Usar LLM para entender si el usuario se refiere a un resultado anterior
    # y extraer los dominios correctos para la comparación
    previous_host = None
    if messages:
        previous_host = _extract_previous_result_host(messages, search_text)
        if previous_host:
            logger.info(f"[Compare] LLM identificó referencia a resultado anterior: {previous_host}")
            # Extraer el nuevo dominio mencionado en el texto actual
            new_hosts = extract_domains_from_text(search_text)
            if new_hosts:
                # Usar solo el anterior y el nuevo mencionado
                hosts = [previous_host, new_hosts[0]]
                logger.info(f"[Compare] Comparando {previous_host} con {new_hosts[0]}")
            else:
                # Si no se encuentra nuevo dominio en el texto, usar LLM para extraerlo
                domain_from_llm = extract_domain_using_llm(search_text)
                if domain_from_llm and domain_from_llm != previous_host:
                    hosts = [previous_host, domain_from_llm]
                    logger.info(f"[Compare] Comparando {previous_host} con {domain_from_llm} (extraído con LLM)")
                else:
                    # Si no se encuentra, mantener solo el anterior y continuar con la lógica normal
                    hosts = [previous_host]
    
    # Si NO hay referencia a resultado anterior, usar la lógica normal
    if not previous_host:
        # Si no hay suficientes hosts, intentar extraer dominios del texto actual (incluyendo nombres de servicios)
        if len(hosts) < requested_count:
            domains = extract_domains_from_text(search_text)
            for domain in domains:
                if domain not in hosts:
                    hosts.append(domain)
        
        # Si aún no hay suficientes y hay contexto de conversación, usar LLM para determinar
        # qué dominios son relevantes para esta comparación específica
        if len(hosts) < requested_count and messages:
            conversation_context = get_conversation_context(messages, max_messages=5)
            if conversation_context:
                # Usar LLM para identificar qué dominios del contexto son relevantes para esta comparación
                # Esto evita extraer dominios de comparaciones anteriores no relacionadas
                llm_prompt = f"""
Analiza la siguiente solicitud del usuario y el contexto de conversación.

Solicitud actual: "{search_text}"

Contexto de conversación:
{conversation_context}

Dominios ya identificados: {', '.join(hosts) if hosts else 'ninguno'}

INSTRUCCIONES:
1. Identifica qué dominios o hosts el usuario quiere comparar en esta solicitud específica
2. NO incluyas dominios de comparaciones anteriores que no están relacionados con esta solicitud
3. Si el usuario menciona explícitamente dominios en su solicitud, úsalos
4. Si el usuario hace referencia a un resultado anterior, identifica ese dominio específico
5. Responde SOLO con los dominios completos relevantes para esta comparación (ej: instagram.com, facebook.com), uno por línea
6. Si no hay dominios relevantes adicionales en el contexto, responde "ninguno"

Dominios relevantes para esta comparación (uno por línea):
"""
                llm_response = llm.generate(llm_prompt, max_tokens=150).strip()
                
                # Extraer dominios de la respuesta del LLM
                if llm_response and llm_response.lower() != "ninguno":
                    for line in llm_response.split('\n'):
                        line = line.strip()
                        # Limpiar la línea
                        line = re.sub(r'[^\w\.-]', '', line)
                        if line and '.' in line and len(line) > 3:
                            if ip_tool.validate_ip_or_domain(line):
                                if line not in hosts:
                                    hosts.append(line)
                                    logger.info(f"[Compare] Dominio relevante identificado por LLM: {line}")
                                    if len(hosts) >= requested_count:
                                        break
        
        # Si aún no hay suficientes, intentar obtener más usando LLM
        if len(hosts) < requested_count:
            hosts = _get_additional_hosts(hosts, search_text, requested_count)
    
    if len(hosts) >= 2:
        if len(hosts) > 2:
            # Comparar el primero con los demás
            base_host = hosts[0]
            comparison_results = []
            for other_host in hosts[1:]:
                comparison = ip_tool.compare(base_host, other_host)
                comparison_results.append({
                    "host1": base_host,
                    "host2": other_host,
                    "comparison": comparison
                })
            return {
                "type": "multiple_comparison",
                "base_host": base_host,
                "comparisons": comparison_results,
                "summary": f"Comparación de {base_host} con {len(hosts) - 1} otros hosts"
            }
        else:
            return ip_tool.compare(hosts[0], hosts[1])
    
    return {"error": f"no_two_hosts_found_for_comparison. Se encontraron {len(hosts)} hosts, se necesitan al menos 2."}


def _get_additional_hosts(existing_hosts: List[str], text: str, requested_count: int) -> List[str]:
    """Obtiene hosts adicionales usando LLM si es necesario."""
    hosts = list(existing_hosts)
    
    try:
        if len(hosts) == 0:
            prompt = f"""
El usuario quiere comparar {requested_count} dominios o servicios, pero no especificó cuáles.
Sugiere {requested_count} dominios o servicios populares y relevantes para comparar (como Google, Facebook, Amazon, Microsoft, Netflix, etc.).
Responde SOLO con los nombres de los servicios, uno por línea, sin explicaciones ni puntos.

Responde con {requested_count} nombres:
"""
        else:
            prompt = f"""
Del siguiente texto, identifica los nombres de dominio o servicios mencionados (como Instagram, Facebook, Google, etc.).
El usuario quiere comparar {requested_count} dominios en total, y ya tenemos: {', '.join(hosts)}.
Responde SOLO con los nombres de dominio encontrados, uno por línea, sin explicaciones.
Si no encuentras nombres de dominio, sugiere dominios populares para completar la comparación.

Texto: "{text}"

Responde con los nombres (uno por línea):
"""
        
        llm_response = llm.generate(prompt).strip().lower()
        extracted_names = []
        
        for line in llm_response.split('\n'):
            line = line.strip()
            if line and line != "ninguno" and len(line) > 2:
                words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9-]*\b', line)
                for word in words:
                    if len(word) > 2 and word not in ['com', 'net', 'org', 'www']:
                        extracted_names.append(word)
        
        # Agregar dominios sugeridos
        for name in extracted_names:
            if len(hosts) >= requested_count:
                break
            potential_domain = f"{name}.com"
            if potential_domain not in hosts:
                hosts.append(potential_domain)
        
        # Si aún no tenemos suficientes, agregar dominios comunes
        default_domains = ["google.com", "facebook.com", "amazon.com", "microsoft.com", "netflix.com"]
        for default_domain in default_domains:
            if len(hosts) >= requested_count:
                break
            if default_domain not in hosts:
                hosts.append(default_domain)
    
    except Exception as e:
        logger.warning(f"Error al extraer dominios: {e}")
        # Fallback: usar dominios comunes
        if len(hosts) < 2:
            default_domains = ["google.com", "facebook.com", "amazon.com", "microsoft.com", "netflix.com"]
            for default_domain in default_domains[:requested_count]:
                if default_domain not in hosts:
                    hosts.append(default_domain)
    
    return hosts


def execute_rag_tool(step: str, prompt: str, messages: List[AnyMessage]) -> Dict[str, Any]:
    """
    Ejecuta la herramienta RAG.
    
    Args:
        step: Paso del plan actual
        prompt: Prompt del usuario
        messages: Mensajes de la conversación
    
    Returns:
        Resultado de la ejecución
    """
    # Detectar si es un seguimiento de conversación
    # PRIORIDAD: RAG es más importante. Solo usar contexto de conversación si es CLARAMENTE un seguimiento directo
    is_followup = False
    if messages:
        try:
            context_text = get_conversation_context(messages, max_messages=5)
            if context_text:
                followup_detection_prompt = f"""
Eres un analizador ESTRICTO que decide si una pregunta requiere buscar información en documentos (RAG) o si es un seguimiento directo de la conversación previa.

REGLA CRÍTICA: Por defecto, usa "nueva" (RAG). Solo marca como "seguimiento" si la pregunta hace referencia EXPLÍCITA y DIRECTA a acciones, resultados o eventos específicos de la conversación previa.

Conversación previa (últimos mensajes):
{context_text}

Pregunta del usuario: "{prompt}"

INSTRUCCIONES CRÍTICAS (SÉ MUY ESTRICTO):
1. Marca como "seguimiento" SOLO si la pregunta hace referencia EXPLÍCITA a:
   - Acciones realizadas en la conversación ("el ping que hiciste", "antes del ping", "el ping anterior", "el ping hacia X")
   - Resultados de operaciones previas ("compara con el ping anterior", "diferencias con el resultado previo")
   - Eventos o hechos específicos mencionados ("a qué dominio fue", "qué IP tenía", "qué resultado dio")
   - Comparaciones directas con resultados previos ("compáralo con", "diferencias con", "comparar con el anterior")
   - Preguntas sobre acciones específicas ("qué hiciste antes", "recuerdas que hiciste ping a X")

2. Marca como "nueva" (RAG) si la pregunta:
   - Busca información general, definiciones, conceptos técnicos
   - Pide explicaciones educativas sobre protocolos o tecnologías
   - Es una pregunta nueva sobre un tema (aunque el tema haya sido mencionado antes)
   - No hace referencia EXPLÍCITA a acciones/resultados específicos de la conversación
   - Usa palabras como "explica", "qué es", "cuales son", "dime sobre", "podrías explicar" sin referirse a acciones previas

3. REGLA DE ORO: Si la pregunta es sobre un CONCEPTO o TEMA (aunque haya sido mencionado antes), es "nueva" (RAG). Solo es "seguimiento" si pregunta sobre ACCIONES o RESULTADOS específicos.

Ejemplos de "seguimiento" (usar contexto):
- "Antes del ping hacia openai, habías realizado otro ping, ¿a qué dominio fue?" → seguimiento (pregunta sobre acción específica)
- "Con el ping que hiciste hace poco, ¿podrías compararlo con un ping hacia openai?" → seguimiento (pregunta sobre resultado específico)
- "¿Qué diferencias encuentras entre este resultado y el anterior?" → seguimiento (comparación de resultados)
- "A qué dominio fue el ping anterior?" → seguimiento (pregunta sobre acción específica)

Ejemplos de "nueva" (usar RAG):
- "Qué es TCP?" → nueva (RAG) - pregunta sobre concepto
- "Cuales son los protocolos relevantes?" → nueva (RAG) - pregunta sobre conceptos
- "Explica qué es un ping" → nueva (RAG) - pregunta sobre concepto
- "Que me podrias explicar sobre el monitoreo y analitica de red?" → nueva (RAG) - pregunta sobre tema/concepto
- "Cuales son los tipos de firewalls?" → nueva (RAG) - pregunta sobre concepto, aunque firewalls haya sido mencionado antes
- "Dime más sobre DNS" → nueva (RAG) - pregunta sobre tema, no sobre acción específica

Responde SOLO con una palabra: "seguimiento" o "nueva".
"""
                llm_response = llm.generate(followup_detection_prompt).strip().lower()
                
                # Solo considerar seguimiento si el LLM es MUY claro y específico
                # Si hay cualquier ambigüedad, usar RAG (prioridad a RAG)
                # Ser más estricto: solo seguir si es claramente un seguimiento de acciones/resultados
                is_followup = (llm_response.strip().startswith("seguimiento") and \
                              len(llm_response.strip()) < 15 and \
                              "nueva" not in llm_response.lower() and \
                              "rag" not in llm_response.lower() and \
                              "documento" not in llm_response.lower())
                
                # Validación adicional: si la pregunta contiene palabras que indican búsqueda de información/conceptos, forzar RAG
                info_seeking_keywords = ["explica", "qué es", "cuales son", "dime sobre", "podrías explicar", "hablame de", "información sobre", "y las", "y los", "y el", "y la"]
                if any(keyword in prompt.lower() for keyword in info_seeking_keywords):
                    # Si es una pregunta de información/concepto, forzar RAG incluso si el LLM dice "seguimiento"
                    # Solo permitir seguimiento si hay referencia EXPLÍCITA a acciones previas
                    ref_words = ["que hiciste", "que realizaste", "anterior", "previo", "antes", "resultado", "el ping", "la consulta", "lo que", "que ejecutaste"]
                    if not any(ref_word in prompt.lower() for ref_word in ref_words):
                        is_followup = False
                        logger.info(f"[RAG] Pregunta contiene palabras de búsqueda de información sin referencia a acciones - forzando RAG")
                
                logger.info(f"[RAG] Detección de seguimiento - LLM respuesta: '{llm_response}', es seguimiento: {is_followup}")
                
                # Si NO es seguimiento, forzar búsqueda en documentos (no usar contexto de conversación)
                if not is_followup:
                    logger.info(f"[RAG] Usando RAG (búsqueda en documentos) - prioridad sobre contexto de conversación")
        except Exception as e:
            logger.warning(f"Error al detectar seguimiento con LLM: {e}. Usando RAG por defecto.")
            is_followup = False  # En caso de error, usar RAG
    
    # Si es seguimiento CLARO, usar contexto de conversación
    # Pero solo si es muy específico y directo
    if is_followup and messages:
        logger.info(f"[RAG] Detectado seguimiento de conversación - usando contexto de conversación (sin contextos de documentos)")
        try:
            context_text = get_conversation_context(messages, max_messages=10)
            if context_text:
                from ..core.cache import cache_result
                
                @cache_result("conversation_context", ttl=1800)
                def generate_from_context(context: str, user_prompt: str) -> str:
                    followup_prompt = f"""
Basándote en la siguiente conversación previa, responde la pregunta del usuario de forma DIRECTA, COMPACTA y enfocada en lo que realmente le interesa.

IMPORTANTE:
- Sé CONCISO: ve directo al punto, sin rodeos ni explicaciones innecesarias
- Responde SOLO lo que el usuario pregunta, sin información adicional no solicitada
- Si la pregunta es sobre algo mencionado anteriormente, elabora SOLO sobre eso específicamente
- Evita repeticiones y redundancias
- Máximo 3-4 párrafos, preferiblemente menos

Conversación previa:
{context}

Pregunta del usuario: {user_prompt}

Respuesta (directa y compacta):
"""
                    return llm.generate(followup_prompt).strip()
                
                answer = generate_from_context(context_text, prompt)
                # Para RAGAS: usar el contexto de conversación como contexto si no hay documentos
                # Esto permite evaluar faithfulness y relevancy incluso en seguimientos
                conversation_contexts = [context_text] if context_text else []
                return {
                    "answer": answer,
                    "hits": 0,
                    "source": "conversation_context",
                    "contexts": conversation_contexts  # Usar contexto de conversación para RAGAS
                }
        except Exception as e:
            logger.warning(f"Error al usar contexto de conversación: {e}")
    
    # Ejecutar RAG normal (búsqueda en documentos)
    # El contexto de conversación se usa como complemento para mejorar la respuesta
    logger.info(f"[RAG] Ejecutando RAG - buscando en documentos para: {prompt[:50]}...")
    
    # Obtener contexto de conversación para complementar (si existe)
    # Esto es CRÍTICO para que el RAG pueda referenciar acciones, resultados y eventos previos
    conversation_context_for_rag = None
    if messages:
        try:
            # Aumentar a 10 mensajes para tener más contexto histórico
            conversation_context_for_rag = get_conversation_context(messages, max_messages=10)
            if conversation_context_for_rag:
                logger.info(f"[RAG] Contexto de conversación disponible ({len(conversation_context_for_rag)} chars, {len(messages)} mensajes) - se usará como complemento a los documentos")
        except Exception as e:
            logger.debug(f"[RAG] No se pudo obtener contexto de conversación: {e}")
    
    # SIEMPRE buscar en documentos - el contexto de conversación es solo complementario
    try:
        logger.info(f"[RAG] Llamando a rag_tool.query() con prompt: {prompt[:100]}...")
        result = rag_tool.query(prompt, conversation_context=conversation_context_for_rag)
        logger.info(f"[RAG] rag_tool.query() retornó: {type(result)}, claves: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
    except Exception as e:
        logger.error(f"[RAG] ❌ ERROR CRÍTICO al ejecutar rag_tool.query(): {e}", exc_info=True)
        # Retornar un resultado con error pero con estructura válida para RAGAS
        result = {
            "answer": f"Error al buscar información en los documentos: {str(e)}",
            "hits": 0,
            "error": f"rag_execution_error: {str(e)}",
            "contexts": [],
            "source": "error"
        }
    
    # Log para debugging: verificar si el resultado tiene contextos
    if isinstance(result, dict):
        contexts_count = len(result.get("contexts", []))
        hits_count = result.get("hits", 0)
        source = result.get("source", "rag_tool")
        logger.info(f"[RAG] Resultado de RAG tool - hits: {hits_count}, contextos: {contexts_count}, source: {source}")
        
        # Verificar que los contextos estén presentes y sean válidos
        if "contexts" in result:
            contexts_list = result["contexts"]
            if isinstance(contexts_list, list):
                valid_contexts = [c for c in contexts_list if c and isinstance(c, str) and c.strip()]
                if len(valid_contexts) != len(contexts_list):
                    logger.warning(f"[RAG] ⚠️ Algunos contextos están vacíos o inválidos: {len(valid_contexts)} válidos de {len(contexts_list)} totales")
                    # Limpiar contextos inválidos
                    result["contexts"] = valid_contexts
                    contexts_count = len(valid_contexts)
            else:
                logger.error(f"[RAG] ❌ Campo 'contexts' no es una lista: {type(contexts_list)}")
                result["contexts"] = []
                contexts_count = 0
        
        # Si hay hits pero no contextos, hay un problema
        if hits_count > 0 and contexts_count == 0:
            logger.error(f"[RAG] ❌ PROBLEMA CRÍTICO: Hay {hits_count} hits pero 0 contextos - esto impedirá evaluación RAGAS")
            logger.error(f"[RAG] ❌ El RAG tool debería retornar contextos cuando hay hits. Revisar rag_tool.py")
        elif hits_count == 0 and contexts_count == 0:
            logger.info(f"[RAG] ℹ️ No se encontraron hits ni contextos - puede ser normal si no hay documentos relevantes")
        elif contexts_count > 0:
            logger.info(f"[RAG] ✅ Contextos disponibles para RAGAS: {contexts_count} chunks")
    
    # Si hay error (cualquier tipo), intentar usar contexto como fallback si es posible
    if result.get("error") and messages:
        error_type = result.get("error", "")
        logger.warning(f"[RAG] ⚠️ Error detectado en resultado RAG: {error_type}")
        
        # Si es error de conexión a Qdrant, usar contexto como fallback
        if error_type == "qdrant_connection_error":
            try:
                context_text = get_conversation_context(messages, max_messages=10)
                if context_text:
                    # Similar al código anterior pero sin cache para fallback
                    followup_prompt = f"""
Basándote en la siguiente conversación previa, responde la pregunta del usuario de forma DIRECTA, COMPACTA y enfocada en lo que realmente le interesa.

Conversación previa:
{context_text}

Pregunta del usuario: {prompt}

Respuesta (directa y compacta):
"""
                    answer = llm.generate(followup_prompt).strip()
                    # Para RAGAS: usar el contexto de conversación como contexto si no hay documentos
                    conversation_contexts = [context_text] if context_text else []
                    return {
                        "answer": answer,
                        "hits": 0,
                        "source": "conversation_context_fallback",
                        "contexts": conversation_contexts  # Usar contexto de conversación para RAGAS
                    }
            except Exception as e:
                logger.warning(f"Error al usar contexto como fallback: {e}")
    
    # Asegurar que el resultado siempre tenga la estructura correcta
    if not isinstance(result, dict):
        logger.error(f"[RAG] ❌ Resultado no es un diccionario: {type(result)}")
        result = {
            "answer": "Error inesperado al procesar la consulta.",
            "hits": 0,
            "error": "invalid_result_type",
            "contexts": []
        }
    elif "error" in result and "answer" not in result:
        # Si solo hay error sin answer, agregar un mensaje de error como answer
        logger.warning(f"[RAG] ⚠️ Resultado tiene error pero no tiene 'answer' - agregando mensaje de error")
        result["answer"] = result.get("answer", f"Error al procesar la consulta: {result.get('error', 'error desconocido')}")
        if "contexts" not in result:
            result["contexts"] = []
    
    return result


def execute_dns_tool(step: str, prompt: str, messages: List[AnyMessage]) -> Dict[str, Any]:
    """
    Ejecuta la herramienta DNS según el tipo de operación detectada.
    
    Args:
        step: Paso del plan actual
        prompt: Prompt del usuario
        messages: Mensajes de la conversación
    
    Returns:
        Resultado de la ejecución
    """
    search_text = f"{prompt} {step or ''}"
    operation_type, is_all_records = detect_dns_operation_type(step, prompt)
    
    # Extraer dominio o IP del mensaje actual
    domain = extract_domain_from_text(search_text)
    ip = extract_ip_from_text(search_text)
    
    # Si no se encuentra dominio en el mensaje actual, buscar en el contexto de conversación
    if not domain and messages:
        conversation_context = get_conversation_context(messages, max_messages=5)
        domain = extract_domain_from_text(conversation_context)
        if not domain:
            # Intentar con LLM usando el contexto completo
            domain = extract_domain_using_llm(conversation_context)
    
    if operation_type == "reverse":
        if ip:
            return dns_tool.reverse_lookup(ip)
        return {"error": "no_valid_ip_found_for_reverse_lookup"}
    
    elif operation_type == "compare":
        domains = extract_domains_from_text(search_text)
        
        # Si no encontramos suficientes dominios, intentar con LLM
        if len(domains) < 2:
            from ..agent.helpers import extract_domains_using_llm
            llm_domains = extract_domains_using_llm(search_text)
            domains.extend(llm_domains)
            # Eliminar duplicados
            domains = list(dict.fromkeys(domains))
        
        if len(domains) >= 2:
            # Si hay más de 2, comparar el primero con los demás
            if len(domains) > 2:
                comparison_results = []
                base_domain = domains[0]
                for other_domain in domains[1:]:
                    comparison = dns_tool.compare_dns(base_domain, other_domain)
                    comparison_results.append({
                        "domain1": base_domain,
                        "domain2": other_domain,
                        "comparison": comparison
                    })
                return {
                    "type": "multiple_dns_comparison",
                    "base_domain": base_domain,
                    "comparisons": comparison_results,
                    "summary": f"Comparación DNS de {base_domain} con {len(domains) - 1} otros dominios"
                }
            else:
                return dns_tool.compare_dns(domains[0], domains[1])
        return {"error": f"Se necesitan al menos 2 dominios para comparar. Se encontraron: {domains}"}
    
    elif operation_type == "spf":
        # Intentar extraer múltiples dominios si están mencionados
        domains = extract_domains_from_text(search_text)
        if not domains and domain:
            domains = [domain]
        
        # Si no encontramos dominios, intentar con LLM
        if not domains:
            from ..agent.helpers import extract_domains_using_llm
            llm_domains = extract_domains_using_llm(search_text)
            domains.extend(llm_domains)
            domains = list(dict.fromkeys(domains))
        
        if not domains:
            llm_domain = extract_domain_using_llm(search_text)
            if llm_domain:
                domains = [llm_domain]
        
        if domains:
            # Si hay múltiples dominios, verificar todos
            if len(domains) > 1:
                spf_results = []
                for dom in domains:
                    result = dns_tool.check_spf(dom)
                    spf_results.append({
                        "domain": dom,
                        "spf": result
                    })
                return {
                    "type": "multiple_spf_check",
                    "results": spf_results,
                    "summary": f"Verificación SPF para {len(domains)} dominios"
                }
            else:
                return dns_tool.check_spf(domains[0])
        return {"error": "No se encontró un dominio válido para verificar SPF"}
    
    elif operation_type == "dmarc":
        # Intentar extraer múltiples dominios si están mencionados
        domains = extract_domains_from_text(search_text)
        if not domains and domain:
            domains = [domain]
        
        # Si no encontramos dominios, intentar con LLM
        if not domains:
            from ..agent.helpers import extract_domains_using_llm
            llm_domains = extract_domains_using_llm(search_text)
            domains.extend(llm_domains)
            domains = list(dict.fromkeys(domains))
        
        if not domains:
            llm_domain = extract_domain_using_llm(search_text)
            if llm_domain:
                domains = [llm_domain]
        
        if domains:
            # Si hay múltiples dominios, verificar todos
            if len(domains) > 1:
                dmarc_results = []
                for dom in domains:
                    result = dns_tool.check_dmarc(dom)
                    dmarc_results.append({
                        "domain": dom,
                        "dmarc": result
                    })
                return {
                    "type": "multiple_dmarc_check",
                    "results": dmarc_results,
                    "summary": f"Verificación DMARC para {len(domains)} dominios"
                }
            else:
                return dns_tool.check_dmarc(domains[0])
        return {"error": "No se encontró un dominio válido para verificar DMARC"}
    
    elif operation_type == "domain_info":
        if domain:
            return dns_tool.get_domain_info(domain)
        # Intentar con LLM si no se encontró dominio
        llm_domain = extract_domain_using_llm(search_text)
        if llm_domain:
            return dns_tool.get_domain_info(llm_domain)
        return {"error": "No se encontró un dominio válido"}
    
    elif is_all_records:
        # Intentar extraer múltiples dominios si están mencionados
        domains = extract_domains_from_text(search_text)
        if not domains and domain:
            domains = [domain]
        
        # Si no encontramos dominios en el mensaje actual, buscar en el contexto
        if not domains and messages:
            conversation_context = get_conversation_context(messages, max_messages=5)
            context_domains = extract_domains_from_text(conversation_context)
            if context_domains:
                domains.extend(context_domains)
                domains = list(dict.fromkeys(domains))
        
        # Si aún no encontramos dominios, intentar con LLM usando contexto completo
        if not domains:
            from ..agent.helpers import extract_domains_using_llm
            llm_search_text = search_text
            if messages:
                conversation_context = get_conversation_context(messages, max_messages=5)
                llm_search_text = f"{conversation_context}\n\nMensaje actual: {search_text}"
            llm_domains = extract_domains_using_llm(llm_search_text)
            if llm_domains:
                domains.extend(llm_domains)
                domains = list(dict.fromkeys(domains))
        
        if not domains:
            llm_search_text = search_text
            if messages:
                conversation_context = get_conversation_context(messages, max_messages=5)
                llm_search_text = f"{conversation_context}\n\nMensaje actual: {search_text}"
            llm_domain = extract_domain_using_llm(llm_search_text)
            if llm_domain:
                domains = [llm_domain]
        
        if domains:
            # Si hay múltiples dominios, obtener registros para todos
            if len(domains) > 1:
                all_records_results = []
                for dom in domains:
                    result = dns_tool.get_all_records(dom)
                    all_records_results.append({
                        "domain": dom,
                        "records": result
                    })
                return {
                    "type": "multiple_all_records",
                    "results": all_records_results,
                    "summary": f"Registros DNS completos para {len(domains)} dominios"
                }
            else:
                return dns_tool.get_all_records(domains[0])
        return {"error": "no_valid_domain_found", "message": "No se encontró un dominio válido. Por favor, especifica el dominio en tu consulta, por ejemplo: 'Haz un registro DNS completo de whatsapp.com'"}
    
    else:
        # Consulta específica de tipo de registro
        if domain:
            return dns_tool.query(domain, operation_type)
        # Intentar con LLM si no se encontró dominio
        llm_domain = extract_domain_using_llm(search_text)
        if llm_domain:
            return dns_tool.query(llm_domain, operation_type)
        return {"error": "no_valid_domain_found"}


def determine_tool_from_step(step: str, prompt: str) -> str:
    """
    Determina qué herramienta usar basándose en el paso y el prompt.
    
    Args:
        step: Paso del plan
        prompt: Prompt del usuario
    
    Returns:
        Nombre de la herramienta: "rag", "ip", o "dns"
    """
    tool_determination_prompt = f"""
    Analiza el siguiente paso del plan y determina qué herramienta debe usarse.
    
    Paso del plan: "{step}"
    Pregunta original del usuario: "{prompt}"
    
    Herramientas disponibles:
    - RAG: Para consultas sobre conceptos, definiciones, explicaciones, información educativa, preguntas tipo "qué es", "explain", "define"
    - IP: Para operaciones de red como comparar IPs, traceroute, análisis de direcciones IP, comparaciones de direcciones de red
    - DNS: Para consultas DNS, registros de dominio (A, AAAA, MX, TXT, NS, CNAME), búsquedas inversas (PTR)
    
    Responde SOLO con una de estas palabras: "rag", "ip" o "dns"
    No incluyas explicaciones ni texto adicional.
    """
    
    try:
        tool_response = llm.generate(tool_determination_prompt).strip().lower()
        
        if "dns" in tool_response:
            return "dns"
        elif "rag" in tool_response and "ip" not in tool_response and "dns" not in tool_response:
            return "rag"
        elif "ip" in tool_response:
            return "ip"
        else:
            words = tool_response.split()
            if words and words[0] in ["rag", "ip", "dns"]:
                return words[0]
            raise ValueError("LLM response not valid")
    except Exception:
        # Fallback: análisis heurístico
        step_lower = step.lower()
        if any(kw in step_lower for kw in ["dns", "domain", "mx", "nameserver", "registro dns", "whois"]):
            return "dns"
        elif any(kw in step_lower for kw in ["ping", "trace", "traceroute", "compare", "ip", "network"]):
            return "ip"
        else:
            return "rag"  # Por defecto

