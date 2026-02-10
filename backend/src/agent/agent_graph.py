from langgraph.graph import StateGraph, START, END, add_messages
from langchain_core.messages import AnyMessage
from langchain_core.runnables import RunnableConfig
from langgraph.channels import LastValue
from ..models.schemas import AgentState, Message
from ..core.graph_state import GraphState
from ..agent.tool_executors import execute_rag_tool, execute_get_report
from typing import Annotated, List, Dict, Any, Optional
from ..tools.rag_tool import RAGTool
from ..agent.router import PipeAgent
from ..agent.llm_client import LLMClient
from ..core.cache import cache_result
import re
import time


# ---------------------------------------------------------
# Inicialización global
# ---------------------------------------------------------

rag_tool = RAGTool()
llm = LLMClient()


# ---------------------------------------------------------
# Helpers para conversión de estado
# ---------------------------------------------------------

def messages_to_agent_state(messages: List[AnyMessage], report_id: Optional[str] = None) -> AgentState:
    """
    Convierte los mensajes del State del grafo a un AgentState para el router.
    Incluye report_id cuando el chat está en contexto de un reporte.
    """
    context_window = []
    for msg in messages[-20:]:
        role = getattr(msg, "role", None) or getattr(msg, "type", "user")
        content = getattr(msg, "content", str(msg))
        if role in ["user", "human", "assistant", "agent", "system"]:
            if role in ["human", "user"]:
                role = "user"
            elif role in ["assistant", "agent"]:
                role = "assistant"
            context_window.append(Message(role=role, content=content))
    return AgentState(
        session_id="graph-session",
        context_window=context_window,
        report_id=report_id
    )


def get_user_prompt_from_messages(messages: List[AnyMessage]) -> str:
    """Extrae el último mensaje del usuario de la lista de mensajes."""
    if not messages:
        return ""
    for msg in reversed(messages):
        role = getattr(msg, "role", None) or getattr(msg, "type", None)
        if role in ["user", "human"]:
            return getattr(msg, "content", str(msg))
    return ""


def get_conversation_context(messages: List[AnyMessage], max_messages: int = 10) -> str:
    """
    Extrae el contexto de conversación de los mensajes para usar en seguimientos.
    Retorna una cadena formateada con los últimos mensajes.
    """
    if not messages:
        return ""
    
    conversation_context = []
    for msg in messages[-max_messages:]:
        role = getattr(msg, "role", None) or getattr(msg, "type", "user")
        content = getattr(msg, "content", str(msg))
        if role in ["user", "human", "assistant", "agent"]:
            # Normalizar roles
            if role in ["human", "user"]:
                role = "user"
            elif role in ["assistant", "agent"]:
                role = "assistant"
            conversation_context.append(f"{role}: {content}")
    
    return "\n".join(conversation_context)


def _extract_tool_from_step(step: str, report_id: Optional[str] = None) -> str:
    """
    Extrae la herramienta del plan_step. RAG o get_report si hay report_id y el paso lo sugiere.
    """
    if not report_id:
        return "rag"
    step_lower = (step or "").lower()
    if any(kw in step_lower for kw in ["reporte", "report", "captura", "análisis", "analisis", "veredicto", "este resultado", "esta captura"]):
        return "get_report"
    return "rag"


@cache_result("conversation_context", ttl=1800)  # Cache por 30 minutos
def generate_from_conversation_context(context_text: str, user_prompt: str) -> str:
    """
    Genera una respuesta basada en el contexto de conversación.
    Esta función está cacheada para evitar regenerar respuestas idénticas.
    
    Args:
        context_text: Texto del contexto de conversación
        user_prompt: Pregunta del usuario
    
    Returns:
        Respuesta generada
    """
    followup_prompt = f"""
Basándote en la siguiente conversación previa, responde la pregunta del usuario de forma DIRECTA, COMPACTA y enfocada en lo que realmente le interesa.

IMPORTANTE:
    pass
- Sé CONCISO: ve directo al punto, sin rodeos ni explicaciones innecesarias
- Responde SOLO lo que el usuario pregunta, sin información adicional no solicitada
- Si la pregunta es sobre algo mencionado anteriormente, elabora SOLO sobre eso específicamente
- Evita repeticiones y redundancias
- Máximo 3-4 párrafos, preferiblemente menos

Conversación previa:
    pass
{context_text}

Pregunta del usuario: {user_prompt}

Respuesta (directa y compacta):
    pass
"""
    return llm.generate(followup_prompt).strip()


# ---------------------------------------------------------
# Alias para compatibilidad - usar GraphState del módulo core
# ---------------------------------------------------------

# Usar GraphState que implementa el patrón State correctamente
State = GraphState

# Helper para agregar pensamientos (usa el método del GraphState)
def add_thought(thought_chain: List[Dict[str, Any]], node_name: str, action: str, details: str = "", status: str = "success") -> List[Dict[str, Any]]:
    """
    Agrega un paso de pensamiento a la cadena.
    Wrapper para compatibilidad con código existente.
    
    Args:
        thought_chain: Lista actual de pensamientos
        node_name: Nombre del nodo que está ejecutando la acción
        action: Acción que se está realizando
        details: Detalles adicionales de la acción
        status: Estado de la acción ("success", "error", "info")
    
    Returns:
        Lista actualizada de pensamientos
    """
    thought = {
        "node": node_name,
        "action": action,
        "details": details,
        "status": status,
        "timestamp": time.time()
    }
    thought_chain = thought_chain or []
    thought_chain.append(thought)
    return thought_chain


# ---------------------------------------------------------
# Nodos del grafo
# ---------------------------------------------------------

def planner_node(state: GraphState) -> Dict[str, Any]:
    """
    Analiza el mensaje del usuario y define el plan de ejecución.
    
    Este nodo SOLO accede a:
        pass
    - state.messages: para obtener el prompt del usuario y contexto
    - state.plan_steps: para escribir el plan generado
    
    NO debe acceder ni modificar otros campos del state.
    
    Retorna un diccionario parcial con solo los campos modificados para que
    LangGraph propague correctamente los valores con LastValue.
    """
    # Extraer el prompt del usuario desde messages
    user_prompt = get_user_prompt_from_messages(state.messages)
    
    if not user_prompt:
        # Si no hay prompt, crear un plan vacío
        return {"plan_steps": []}
    
    # Convertir messages a AgentState para el router (incluir report_id si existe)
    report_id = getattr(state, "report_id", None)
    context = messages_to_agent_state(state.messages, report_id=report_id)
    router = PipeAgent()

    # Pasar selected_text si está disponible en el estado (texto resaltado por el usuario en el frontend)
    selected_text = getattr(state, "selected_text", None)
    decision = router.decide(user_prompt, context, selected_text=selected_text)
    
    # Verificar si la pregunta fue rechazada por estar fuera de tema
    if decision.get("rejection_message"):
        rejection_msg = decision.get("rejection_message")
        
        thought_chain = add_thought(
            state.thought_chain or [],
            "Planner",
            "Pregunta rechazada",
            "Pregunta fuera de la temática de redes y telecomunicaciones",
            "info"
        )
        
        # Retornar un resultado que indique el rechazo
        # Esto será procesado por el sintetizador para mostrar el mensaje de rechazo
        return {
            "plan_steps": [],
            "thought_chain": thought_chain,
            "rejection_message": rejection_msg
        }
    
    plan_steps = decision.get("plan_steps", [])
    
    # Registrar pensamiento: plan generado (consolidado)
    thought_chain = add_thought(
        state.thought_chain or [],
        "Planner",
        "Plan generado",
        f"{len(plan_steps)} paso(s): {', '.join(plan_steps[:2])}{'...' if len(plan_steps) > 2 else ''}",
        "success"
    )
    
    # Retornar solo el campo modificado como diccionario para propagación correcta
    return {
        "plan_steps": plan_steps,
        "thought_chain": thought_chain
    }


def orchestrator_node(state: GraphState) -> Dict[str, Any]:
    """
    Orquestador: Coordina y dirige el flujo entre los componentes especializados.
    Evalúa el plan generado y decide qué componente necesita activar.
    
    Este nodo SOLO accede a:
        pass
    - state.plan_steps: para evaluar el plan generado
    - state.messages: para obtener el contexto del usuario
    - state.results: para verificar si hay resultados pendientes de procesar
    - state.orchestration_decision: para escribir la decisión
    - state.next_component: para escribir el siguiente componente a activar
    
    NO debe acceder ni modificar otros campos del state.
    
    Retorna un diccionario parcial con solo los campos modificados para que
    LangGraph propague correctamente los valores con LastValue.
    """
    plan_steps = state.plan_steps or []
    results = state.results or []
    thought_chain = state.thought_chain or []
    
    # Verificar si hay un mensaje de rechazo (pregunta fuera de tema)
    # Esto se propaga desde el planner cuando detecta una pregunta fuera de tema
    rejection_message = getattr(state, 'rejection_message', None)
    if rejection_message:
        thought_chain = add_thought(
            thought_chain,
            "Orquestador",
            "Pregunta rechazada → Sintetizador",
            "Pregunta fuera de tema, pasando mensaje de rechazo",
            "info"
        )
        # Agregar el mensaje de rechazo como resultado para que el sintetizador lo procese
        return {
            "next_component": "Sintetizador",
            "thought_chain": thought_chain,
            "rejection_message": rejection_message
        }
    
    # Si no hay plan, no hay nada que orquestar
    if not plan_steps:
        thought_chain = add_thought(
            thought_chain,
            "Orquestador",
            "Sin plan → Sintetizador",
            "No se generó plan de ejecución",
            "info"
        )
        return {
            "next_component": "Sintetizador",
            "thought_chain": thought_chain
        }
    
    # Si hay resultados pero no hay pasos pendientes, ir a Sintetizador
    if results and not plan_steps:
        thought_chain = add_thought(
            thought_chain,
            "Orquestador",
            "Todos los pasos completados → Sintetizador",
            f"{len(results)} resultado(s) listo(s) para sintetizar",
            "success"
        )
        return {
            "next_component": "Sintetizador",
            "thought_chain": thought_chain
        }
    
    # Si hay pasos pendientes, necesitamos ejecutar herramientas
    if plan_steps:
        thought_chain = add_thought(
            thought_chain,
            "Orquestador",
            "Hay pasos pendientes → Agente Ejecutor",
            f"{len(plan_steps)} paso(s) pendiente(s)",
            "success"
        )
        return {
            "next_component": "Agente_Ejecutor",
            "thought_chain": thought_chain
        }
    
    # Fallback: ir a Sintetizador
    thought_chain = add_thought(
        thought_chain,
        "Orquestador",
        "Fallback → Sintetizador",
        "Usando fallback por defecto",
        "info"
    )
    return {
        "next_component": "Sintetizador",
        "thought_chain": thought_chain
    }


def ejecutor_agent_node(state: GraphState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Agente Ejecutor: Ejecuta la herramienta RAG según el plan.
    Combina la selección de herramienta y su ejecución en un solo nodo.
    
    Este nodo SOLO accede a:
        pass
    - state.plan_steps: para leer y modificar (quitar el paso actual)
    - state.messages: para obtener el prompt original del usuario (contexto)
    - state.current_step: para escribir el paso actual (temporal)
    - state.tool_name: para escribir la herramienta seleccionada (temporal)
    - state.results: para acumular los resultados
    
    NO debe acceder a final_output, supervised_output u otros campos.
    
    Retorna un diccionario parcial con solo los campos modificados para que
    LangGraph propague correctamente los valores con LastValue.
    """
    thought_chain = state.thought_chain or []

    # Obtener callback de streaming si existe
    stream_callback = None
    if config and "configurable" in config:
        stream_callback = config["configurable"].get("stream_callback")
    
    # Extraer el paso actual del plan
    plan_steps_copy = list(state.plan_steps or [])
    if not plan_steps_copy:
        thought_chain = add_thought(
            thought_chain,
            "Agente_Ejecutor",
            "No hay pasos para ejecutar",
            "El plan está vacío",
            "error"
        )
        return {"thought_chain": thought_chain}
    
    current_step = plan_steps_copy.pop(0)
    
    # Obtener el prompt del usuario para contexto
    user_prompt = get_user_prompt_from_messages(state.messages)
    
    # Limitar tamaño del prompt para evitar problemas de memoria
    MAX_PROMPT_LENGTH = 2000
    if len(user_prompt) > MAX_PROMPT_LENGTH:
        user_prompt = user_prompt[:MAX_PROMPT_LENGTH] + "..."
    
    # Extraer herramienta del plan_step; si hay report_id, puede ser get_report
    report_id = getattr(state, "report_id", None)
    tool_name = _extract_tool_from_step(current_step, report_id)

    try:
        if tool_name == "get_report" and report_id:
            result = execute_get_report(report_id, user_prompt)
        elif tool_name == "rag":
            result = execute_rag_tool(current_step, user_prompt, state.messages, stream_callback=stream_callback)
        else:
            result = {"error": "tool_not_found"}
    except Exception as e:
        result = {"error": f"Error ejecutando {tool_name}: {str(e)}"}
    
    # Guardar resultado en la lista acumulada
    accumulated = state.results or []
    accumulated.append(result)

    # Determinar estado de la ejecución y registrar pensamiento consolidado
    execution_status = "success"
    if isinstance(result, dict) and "error" in result:
        execution_status = "error"
        execution_details = f"Error: {result.get('error', 'error desconocido')}"
    else:
        # Resumir el paso ejecutado
        step_summary = current_step[:60] + "..." if len(current_step) > 60 else current_step
        execution_details = f"Paso: {step_summary}"
    
    # Registrar pensamiento: ejecución completada (consolidado)
    thought_chain = add_thought(
        thought_chain,
        "Agente_Ejecutor",
        f"{tool_name.upper()} ejecutado",
        execution_details,
        execution_status
    )

    # Guardar en el historial antes de limpiar (trazabilidad completa)
    executed_tools_list = state.executed_tools or []
    executed_steps_list = state.executed_steps or []
    
    if tool_name:
        executed_tools_list.append(tool_name)
    if current_step:
        executed_steps_list.append(current_step)

    # Retornar solo los campos modificados como diccionario para propagación correcta
    # Nota: No retornamos current_step y tool_name cuando se limpian (None) porque
    # la información útil ya está en executed_steps y executed_tools
    return {
        "plan_steps": plan_steps_copy,
        "results": accumulated,
        "executed_tools": executed_tools_list,  # Historial de herramientas usadas
        "executed_steps": executed_steps_list,   # Historial de pasos ejecutados
        "thought_chain": thought_chain
    }


async def supervisor_node(state: GraphState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Supervisor: Valida la calidad de la respuesta final y corrige errores si es necesario.
    Asegura que la respuesta cumple con estándares de calidad antes de enviarla al usuario.
    
    Este nodo SOLO accede a:
        pass
    - state.final_output: para leer la respuesta generada
    - state.messages: para obtener el contexto del usuario
    - state.supervised_output: para escribir la respuesta supervisada/corregida
    - state.quality_score: para escribir la puntuación de calidad
    
    NO debe acceder a plan_steps, results, tool_name u otros campos.
    
    Retorna un diccionario parcial con solo los campos modificados para que
    LangGraph propague correctamente los valores con LastValue.
    """
    final_output = state.final_output or ""
    user_prompt = get_user_prompt_from_messages(state.messages)
    thought_chain = state.thought_chain or []
    
    # Capturar datos para evaluación con Ragas (automático)
    try:
        from ..utils.ragas_evaluator import get_evaluator
        from ..settings import settings
        
        if settings.ragas_enabled and user_prompt and final_output:
            evaluator = get_evaluator(enabled=True)
            if evaluator:
                # Extraer contextos de los resultados si están disponibles
                contexts = []
                if state.results:
                    for i, result in enumerate(state.results):
                        if isinstance(result, dict):
                            # Log de la estructura del resultado para debugging
                            result_keys = list(result.keys())
                            
                            # Buscar contextos directamente (el RAG tool los retorna aquí)
                            if "contexts" in result:
                                result_contexts = result["contexts"]
                                if isinstance(result_contexts, list):
                                    # Filtrar contextos vacíos o None
                                    valid_contexts = [c for c in result_contexts if c and isinstance(c, str) and c.strip()]
                                    contexts.extend(valid_contexts)
                                else:
                                    pass
                            # Si no hay contextos pero hay answer, puede ser resultado de RAG
                            if "answer" in result:
                                # El RAG tool retorna {"answer": ..., "hits": número, "contexts": [...]}
                                # Si no está "contexts", puede ser que se usó contexto de conversación
                                source = result.get("source", "unknown")
                                hits = result.get("hits", 0)
                                
                                if source == "conversation_context" or source == "conversation_context_fallback":
                                    pass
                                elif hits > 0:
                                    # Hay hits pero no contextos - esto es un problema
                                    pass
                                else:
                                    pass
                        else:
                            pass
                else:
                    pass
                
                # Si no hay contextos, intentar obtenerlos de otras fuentes
                if not contexts:
                    pass
                
                # Capturar para evaluación
                evaluator.capture_evaluation(
                    question=user_prompt,
                    answer=final_output,
                    contexts=contexts if contexts else [],
                    metadata={
                        "tool_used": "rag",  # Se puede mejorar detectando qué herramienta se usó
                        "quality_score": state.quality_score if hasattr(state, 'quality_score') else 0.0
                    }
                )
                
                # Calcular métricas si hay contextos (en background para no bloquear)
                # Nota: RAGAS puede generar BlockingError en entornos asíncronos
                # Solución: ejecutar con --allow-blocking o configurar BG_JOB_ISOLATED_LOOPS=true
                # IMPORTANTE: La evaluación se ejecuta en background para no bloquear la respuesta al usuario
                if contexts:
                    try:
                        # Ejecutar evaluación en background (thread separado) para no bloquear
                        from threading import Thread
                        
                        def evaluate_in_background():
                            """Ejecuta la evaluación de RAGAS en un thread separado"""
                            try:
                                metrics = evaluator.evaluate_captured_data()
                                if metrics:
                                    for metric_name, value in metrics.items():
                                        emoji = "✅" if value >= 0.7 else "⚠️" if value >= 0.5 else "❌"
                                    avg_score = sum(metrics.values()) / len(metrics) if metrics else 0.0
                                else:
                                    pass
                            except Exception as bg_error:
                                error_msg = str(bg_error)
                                if "BlockingError" in error_msg or "blocking" in error_msg.lower():
                                    pass
                                else:
                                    pass
                        
                        # Iniciar thread en background (daemon=True para que no bloquee el cierre)
                        eval_thread = Thread(target=evaluate_in_background, daemon=True)
                        eval_thread.start()
                    except Exception as e:
                        error_msg = str(e)
                        # No fallar si hay error al iniciar el thread
    except Exception as e:
        # No fallar si Ragas no está disponible o hay error
        pass
    
    if not final_output:
        thought_chain = add_thought(
            thought_chain,
            "Supervisor",
            "No hay respuesta para validar",
            "No se generó ninguna respuesta final",
            "error"
        )
        return {
            "supervised_output": "No se pudo generar una respuesta.",
            "quality_score": 0.0,
            "thought_chain": thought_chain
        }
    
    # Validar calidad de la respuesta usando LLM
    # OPTIMIZACIÓN: Se eliminó la verificación de "fuera de tema" redundante (ya la hace el Planner)
    
    # ---------------------------------------------------------
    # FALLBACK: INFORMACIÓN NO ENCONTRADA EN DOCUMENTOS
    # ---------------------------------------------------------
    # Si el RAG no encontró información, intentar responder con conocimiento general
    # para cumplir con la regla "debe dar una respuesta si no la tiene"
    
    rag_missed_info = False
    
    # 1. Verificar resultados de herramientas
    if state.results:
        for res in state.results:
            if isinstance(res, dict) and res.get("source") in ["no_hits", "empty_context", "no_documents", "qdrant_connection_error"]:
                rag_missed_info = True
                break
    
    # 2. Verificar texto de la respuesta actual
    if not rag_missed_info:
        missing_info_keywords = [
            "no encontré información", "no tengo información", 
            "no se menciona en los documentos", "no aparece en el contexto",
            "no dispongo de información", "no está en los documentos",
            "fuera de este ámbito especializado", "fuera de este tema especializado",
            "no está relacionada con redes o tecnologías de red"
        ]
        if any(keyword in final_output.lower() for keyword in missing_info_keywords):
            rag_missed_info = True

    if rag_missed_info:
        
        fallback_prompt = f"""
El sistema RAG no encontró información en los documentos para la pregunta del usuario, pero el usuario requiere una respuesta de Pipe.
Genera una respuesta basada en tu CONOCIMIENTO GENERAL como experto en redes WiFi y Band Steering.

Pregunta del usuario: "{user_prompt}"

INSTRUCCIONES CRÍTICAS:
    pass
1. Comienza la respuesta EXACTAMENTE con esta frase: "⚠️ **Nota:** No encontré esta información específica en tus documentos técnicos, pero basado en estándares generales de redes WiFi:"
2. Proporciona una respuesta técnica, precisa y útil sobre el tema.
3. CONTEXTO OBLIGATORIO: Cualquier término como 'asociación' debe interpretarse EXCLUSIVAMENTE como 'asociación inalámbrica 802.11'. NO hables de ámbitos sociales o económicos.
4. Si la pregunta solicita una lista, enuméralos claramente.

Genera la respuesta técnica y profesional:
    pass
"""
        try:
            # ASYNC CHANGE
            fallback_output = await llm.agenerate(fallback_prompt)
            thought_chain = add_thought(
                thought_chain,
                "Supervisor",
                "Fallback: Conocimiento General",
                "Información no encontrada en docs → Usando conocimiento general",
                "warning"
            )
            return {
                "supervised_output": fallback_output.strip(),
                "quality_score": 0.9, # Asumimos buena calidad del fallback
                "thought_chain": thought_chain
            }
        except Exception as e:
            # Si falla, continuar con flujo normal (probablemente mejorará la respuesta "no se" original)
            pass
    
    # Obtener callback de streaming si existe (para mejoras)
    stream_callback = None
    if config and "configurable" in config:
        stream_callback = config["configurable"].get("stream_callback")

    # Validar calidad de la respuesta usando LLM
    quality_prompt = f"""
Evalúa la siguiente respuesta generada para el usuario y determina:
    pass
1. Si responde directamente a la pregunta del usuario
2. Si es clara y concisa
3. Si contiene información relevante
4. Si hay errores obvios o información incorrecta
5. Si la respuesta indica que la pregunta está FUERA DEL TEMA de redes/telecomunicaciones (ej: "No puedo responder preguntas sobre cocina", etc).

Pregunta del usuario: "{user_prompt}"

Respuesta generada:
    pass
{final_output}

INSTRUCCIONES DE PUNTUACIÓN:
    pass
- Si la respuesta indica CORRECTAMENTE que la pregunta está fuera de tema, asigna un puntaje de 10 (Excelente manejo de límites).
- Si la respuesta es técnica y correcta, asigna puntaje alto.
- Si la respuesta es vaga, incorrecta o no responde, asigna puntaje bajo.

Responde SOLO con un número del 0 al 10 (donde 10 es excelente) seguido de una breve explicación.
Formato: "Puntuación: X. Explicación: ..."
"""
    
    try:
        # ASYNC CHANGE
        quality_response = await llm.agenerate(quality_prompt)
        
        # Extraer puntuación de la respuesta
        score_match = re.search(r"(\d+(?:\.\d+)?)", quality_response)
        if score_match:
            quality_score = float(score_match.group(1))
            # Normalizar a rango 0-1
            quality_score = min(max(quality_score / 10.0, 0.0), 1.0)
        else:
            quality_score = 0.7  # Puntuación por defecto si no se puede extraer
        
        # Analizar la complejidad de la pregunta para determinar si la longitud es apropiada
        # IMPORTANTE: Si la pregunta incluye operaciones de red (ping, traceroute, etc.), es al menos "moderada"
        has_network_operation = any(keyword in user_prompt.lower() for keyword in [
            "ping", "traceroute", "trace", "haz ping", "hacer ping", "compara", "comparar", "dns", "registros"
        ])
        
        complexity_check_prompt = f"""
Analiza la siguiente pregunta y determina su complejidad:

Pregunta: "{user_prompt}"

Determina si es:
    pass
1. "simple" - Pregunta directa que requiere una respuesta breve (ej: "¿Qué es X?", "¿Cuál es Y?")
2. "moderada" - Pregunta que requiere una explicación con algunos detalles O incluye operaciones de red (ej: "¿Cómo funciona X?", "Explica Y", "haz ping a X", "¿Qué es X? y haz Y")
3. "compleja" - Pregunta que requiere una explicación detallada, múltiples aspectos, O una lista completa de elementos (ej: "Compara X e Y", "Explica todos los aspectos de Z", "¿Cuáles son las capas del modelo OSI?", "Menciona todos los tipos de X", "Lista todas las capas", "¿Cuáles son todas las...?")

IMPORTANTE: 
    pass
- Si la pregunta combina una explicación Y una operación (ej: "¿Qué es X? y haz Y"), es "moderada" o "compleja", NO "simple".
- Si la pregunta requiere una LISTA COMPLETA de elementos (ej: "capas del modelo OSI", "tipos de firewalls", "protocolos de red", "todas las capas", "cuáles son las capas"), debe ser marcada como "compleja" para asegurar que se incluyan TODOS los elementos sin omitir ninguno.

Responde SOLO con una palabra: "simple", "moderada" o "compleja".
"""
        
        try:
            # ASYNC CHANGE
            complexity_response = await llm.agenerate(complexity_check_prompt)
            complexity = complexity_response.strip().lower()
            
            # Determinar longitud apropiada según complejidad
            # AUMENTADO: Límites más permisivos para evitar recorte de respuestas importantes
            # Si hay operaciones de red, aumentar significativamente el límite para preservar resultados técnicos
            if "simple" in complexity and not has_network_operation:
                max_appropriate_length = 500  # Aumentado de 200 a 500 para preguntas simples
            elif "compleja" in complexity:
                max_appropriate_length = 5000  # Aumentado de 2000 a 5000 para preguntas complejas
            else:  # moderada o simple con operaciones de red
                max_appropriate_length = 3000 if has_network_operation else 1500  # Aumentado significativamente
        except Exception as e:
            complexity = "moderada"  # Valor por defecto
            max_appropriate_length = 2000  # Aumentado de 800 a 2000
        
        # NUEVA ESTRATEGIA: Solo modificar en casos EXTREMOS para minimizar doble respuesta
        # - Calidad MUY baja (< 0.4) en lugar de (< 0.5)
        # - Respuesta EXTREMADAMENTE larga (> 3x límite) en lugar de (> 2x límite)
        # Esto reduce drásticamente las modificaciones del Supervisor
        response_too_long = len(final_output) > (max_appropriate_length * 3)  # Más permisivo
        
        if quality_score < 0.4 or response_too_long:  # Umbral más bajo
            # Determinar guía de longitud según complejidad
            if "simple" in complexity:
                length_guidance = "Respuesta MUY BREVE y DIRECTA: máximo 2-3 oraciones (30-60 palabras). Ve directo al punto sin explicaciones adicionales, sin introducciones largas, sin conclusiones innecesarias."
            elif "compleja" in complexity:
                length_guidance = "Respuesta COMPLETA y DETALLADA: 200-400 palabras con explicación estructurada, ejemplos si son relevantes, y organización clara."
            else:  # moderada
                length_guidance = "Respuesta EQUILIBRADA: 80-150 palabras con explicación clara y algunos detalles relevantes. Evita información redundante."
            
            improvement_prompt = f"""
La siguiente respuesta tiene problemas de calidad o no está adaptada a la complejidad de la pregunta. Mejórala para que:
    pass
1. Responda DIRECTAMENTE a la pregunta del usuario de manera clara y natural
2. Sea ADAPTADA a la complejidad de la pregunta: {length_guidance}
3. Mantenga FIDELIDAD TOTAL a la información proporcionada (NO inventes, NO agregues conocimiento general)
4. Use lenguaje natural y comprensible
5. Esté bien estructurada y organizada

INSTRUCCIONES:
    pass
- FIDELIDAD: Usa SOLO la información de la respuesta original. NO inventes información.
- LONGITUD ADAPTATIVA: {length_guidance}
- LENGUAJE NATURAL: Habla como un experto explicando a un usuario, de manera clara y accesible
- ESTRUCTURA: Organiza la información de forma lógica
- PRESERVAR RESULTADOS TÉCNICOS: Si la respuesta incluye resultados de operaciones de red (ping, traceroute, comparaciones, DNS), PRESERVA estos resultados completos. NO los resumas ni elimines información técnica importante.
- NO copies párrafos completos, parafrasea de manera natural
- Para preguntas simples, ve directo al punto sin rodeos

Pregunta del usuario: "{user_prompt}"

Respuesta original (con problemas o no adaptada):
    pass
{final_output[:2000]}{"..." if len(final_output) > 2000 else ""}

Respuesta mejorada (clara, natural, adaptada a la complejidad y fiel a la información):
    pass
"""
            try:
                improved_output = await llm.agenerate(
                    improvement_prompt, 
                    stream_callback=None # Evitar doble streaming/reemplazo visual
                )
                thought_chain = add_thought(
                    thought_chain,
                    "Supervisor",
                    "Validación: mejorada",
                    f"Calidad: {quality_score:.2f}, se aplicaron mejoras",
                    "success"
                )
                return {
                    "supervised_output": improved_output.strip(),
                    "quality_score": quality_score,
                    "thought_chain": thought_chain
                }
            except Exception as e:
                logging.warning(f"Error al mejorar respuesta: {e}")
                thought_chain = add_thought(
                    thought_chain,
                    "Supervisor",
                    "Error al mejorar respuesta",
                    f"No se pudo mejorar la respuesta: {str(e)}",
                    "error"
                )
                # Si falla la mejora, usar la respuesta original
                return {
                    "supervised_output": final_output,
                    "quality_score": quality_score,
                    "thought_chain": thought_chain
                }
        else:
            # La calidad es aceptable, pero SIEMPRE asegurar que sea concisa
            supervised_output = final_output.strip()
            
            # SOLO ajustar si es EXCESIVAMENTE larga (más del doble del límite)
            # Esto evita recortar respuestas que están ligeramente por encima del límite
            if len(supervised_output) > (max_appropriate_length * 2):
                # Determinar guía de longitud según complejidad
                if "simple" in complexity:
                    length_guidance = "Respuesta MUY BREVE: máximo 2-3 oraciones (30-60 palabras). Ve directo al punto."
                elif "compleja" in complexity:
                    length_guidance = "Respuesta COMPLETA: 200-400 palabras con explicación estructurada."
                else:  # moderada
                    length_guidance = "Respuesta EQUILIBRADA: 80-150 palabras con explicación clara. Evita redundancias."
                
                shortening_prompt = f"""
Ajusta la siguiente respuesta para que sea apropiada en longitud según la complejidad de la pregunta, manteniendo la información esencial y un lenguaje natural.

INSTRUCCIONES:
    pass
- FIDELIDAD: Mantén SOLO la información de la respuesta original. NO inventes información.
- LONGITUD ADAPTATIVA: {length_guidance}
- LENGUAJE NATURAL: Mantén un tono claro y comprensible
- ESTRUCTURA: Organiza la información de forma lógica
- PRESERVAR RESULTADOS TÉCNICOS: Si la respuesta incluye resultados de operaciones de red (ping, traceroute, comparaciones, DNS), PRESERVA estos resultados completos. NO los resumas ni elimines información técnica importante.
- NO copies párrafos completos, parafrasea de manera natural
- Si la pregunta requiere contexto, mantén una breve introducción (1-2 oraciones)
- Para preguntas simples, ve directo al punto sin rodeos

Pregunta: "{user_prompt}"

Respuesta actual (muy larga para esta pregunta):
    pass
{supervised_output[:min(max_appropriate_length + 500, len(supervised_output))]}...

Respuesta ajustada (adaptada a la complejidad, natural y fiel a la información):
    pass
"""
                try:
                    # DESHABILITADO: El usuario prefiere respuestas largas a que se "cambie" el texto frente a sus ojos.
                    # shortened = await llm.agenerate(
                    #     shortening_prompt,
                    #     stream_callback=None # Evitar doble streaming/reemplazo visual
                    # )
                    # supervised_output = shortened.strip()
                    pass
                    
                    thought_chain = add_thought(
                        thought_chain,
                        "Supervisor",
                        "Validación: aprobada",
                        f"Calidad: {quality_score:.2f}, respuesta validada ({len(supervised_output)} caracteres)",
                        "success"
                    )
                except Exception as e:
                    supervised_output = final_output
                    thought_chain = add_thought(
                        thought_chain,
                        "Supervisor",
                        "Validación: aprobada (con errores)",
                        f"Calidad: {quality_score:.2f}, no se pudo acortar: {str(e)}",
                        "warning"
                    )
            else:
                # Calidad buena y longitud apropiada - NO modificar
                # El streaming ya se hizo en el Synthesizer
                thought_chain = add_thought(
                    thought_chain,
                    "Supervisor",
                    "Validación: aprobada sin modificaciones",
                    f"Calidad: {quality_score:.2f}, respuesta aceptada tal cual",
                    "success"
                )
            
            # OPTIMIZACIÓN: Limpiar estado para evitar acumulación de memoria (solo si hay mucho contenido)
            if state.messages and len(state.messages) > 30:
                state.cleanup_old_messages(max_messages=30)
            
            if state.results and len(state.results) > 10:
                state.cleanup_large_results(max_results=10)
            
            return {
                "supervised_output": supervised_output,
                "quality_score": quality_score,
                "thought_chain": thought_chain
            }
    except Exception as e:
        logging.warning(f"Error en supervisor: {e}")
        thought_chain = add_thought(
            thought_chain,
            "Supervisor",
            "Error en validación",
            f"Error al validar respuesta: {str(e)}, usando respuesta original",
            "error"
        )
        # OPTIMIZACIÓN: Limpiar estado para evitar acumulación de memoria (solo si hay mucho contenido)
        if state.messages and len(state.messages) > 30:
            state.cleanup_old_messages(max_messages=30)
        
        if state.results and len(state.results) > 10:
            state.cleanup_large_results(max_results=10)
        
        # Si falla la validación, usar la respuesta original
        return {
            "supervised_output": final_output,
            "quality_score": 0.7,  # Puntuación por defecto
            "thought_chain": thought_chain
        }


async def synthesizer_node(state: GraphState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Combina los resultados de los pasos anteriores y produce una respuesta final legible.
    SOLO interviene cuando se usaron múltiples herramientas (RAG + IP).
    Si solo se usó una herramienta, devuelve el resultado directamente sin modificar.
    
    Este nodo SOLO accede a:
        pass
    - state.results: para leer los resultados de las herramientas
    - state.messages: para obtener el prompt original del usuario (contexto para síntesis)
    - state.final_output: para escribir la respuesta final
    
    NO debe acceder a plan_steps, tool_name, current_step u otros campos.
    
    Retorna un diccionario parcial con solo los campos modificados para que
    LangGraph propague correctamente los valores con LastValue.
    """
    results = state.results or []
    thought_chain = state.thought_chain or []
    
    # Obtener callback de streaming si existe
    stream_callback = None
    if config and "configurable" in config:
        stream_callback = config["configurable"].get("stream_callback")
    
    # Verificar si hay un mensaje de rechazo (pregunta fuera de tema)
    rejection_message = getattr(state, 'rejection_message', None)
    if rejection_message:
        thought_chain = add_thought(
            thought_chain,
            "Sintetizador",
            "Mensaje de rechazo",
            "Pregunta fuera de la temática de redes",
            "info"
        )
        return {
            "final_output": rejection_message,
            "thought_chain": thought_chain
        }
    
    if not results:
        thought_chain = add_thought(
            thought_chain,
            "Sintetizador",
            "No hay resultados para sintetizar",
            "No se encontraron resultados de herramientas",
            "error"
        )
        return {
            "final_output": "No se encontraron resultados para la consulta.",
            "thought_chain": thought_chain
        }

    # Detectar qué herramientas se usaron (sin pensamiento redundante, se registrará al final)

    # Detectar si se usó RAG (única herramienta actual)
    has_rag_result = any(
        isinstance(r, dict) and 'answer' in r
        for r in results
    )

    # CASO 1: Solo RAG - procesar respuesta con LLM para asegurar concisión
    if has_rag_result:
        # Extraer solo el 'answer' de cada resultado RAG
        rag_answers = []
        for r in results:
            if isinstance(r, dict) and 'answer' in r:
                rag_answers.append(r['answer'])
        
        if rag_answers:
            # Combinar respuestas si hay múltiples
            combined_raw = "\n\n".join(rag_answers).strip()
            
            # Obtener el prompt original del usuario para contexto
            user_prompt = get_user_prompt_from_messages(state.messages)
            
            # Analizar complejidad de la pregunta para adaptar la respuesta
            complexity_check_prompt = f"""
Analiza la siguiente pregunta y determina su complejidad:

Pregunta: "{user_prompt}"

Determina si es:
    pass
1. "simple" - Pregunta directa que requiere una respuesta breve (ej: "¿Qué es X?", "¿Cuál es Y?")
2. "moderada" - Pregunta que requiere una explicación con algunos detalles (ej: "¿Cómo funciona X?", "Explica Y")
3. "compleja" - Pregunta que requiere una explicación detallada, múltiples aspectos, O una lista completa de elementos (ej: "Compara X e Y", "Explica todos los aspectos de Z", "¿Cuáles son las capas del modelo OSI?", "Menciona todos los tipos de X", "Lista todas las capas", "¿Cuáles son todas las...?")

IMPORTANTE: Si la pregunta requiere una LISTA COMPLETA de elementos (ej: "capas del modelo OSI", "tipos de firewalls", "protocolos de red", "todas las capas", "cuáles son las capas"), debe ser marcada como "compleja" para asegurar que se incluyan TODOS los elementos sin omitir ninguno.

Responde SOLO con una palabra: "simple", "moderada" o "compleja".
"""
            
            # Inicializar valores por defecto
            complexity = "moderada"
            length_guidance = "Respuesta EQUILIBRADA: 80-150 palabras con explicación clara."
            max_tokens_synthesis = 300
            
            try:
                # ASYNC CHANGE
                complexity_response = await llm.agenerate(complexity_check_prompt)
                complexity = complexity_response.strip().lower()
                
                # Determinar guía de longitud según complejidad
                # AUMENTADO: Límites más altos para asegurar respuestas completas
                if "simple" in complexity:
                    length_guidance = "Respuesta BREVE: 2-4 oraciones (50-100 palabras). Ve directo al punto sin introducciones innecesarias."
                    max_tokens_synthesis = 200  # Aumentado de 100 a 200
                elif "compleja" in complexity:
                    length_guidance = "Respuesta COMPLETA: 300-600 palabras con explicación estructurada. Si la pregunta requiere una lista completa (ej: todas las capas del modelo OSI, todos los tipos), asegúrate de incluir TODOS los elementos sin omitir ninguno."
                    max_tokens_synthesis = 1200  # Aumentado de 600 a 1200 para listas completas
                else:  # moderada
                    length_guidance = "Respuesta EQUILIBRADA: 100-200 palabras con explicación clara. Si la pregunta requiere una lista, incluye todos los elementos importantes."
                    max_tokens_synthesis = 500  # Aumentado de 300 a 500
            except Exception as e:
                complexity = "moderada"
                length_guidance = "Respuesta EQUILIBRADA: 80-150 palabras con explicación clara."
                max_tokens_synthesis = 300
            
            # Procesar con LLM para asegurar respuesta natural, equilibrada y fiel a la documentación
            synthesis_prompt = (
                f"Pregunta del usuario: {user_prompt}\n\n"
                "Basándote en la siguiente respuesta del sistema RAG, genera una respuesta clara, natural y CONCISA adaptada a la complejidad de la pregunta.\n\n"
                f"Respuesta del RAG:\n{combined_raw}\n\n"
                "INSTRUCCIONES:\n"
                "- FIDELIDAD TOTAL: Usa SOLO la información de la respuesta RAG. NO inventes, NO agregues conocimiento general.\n"
                f"- LONGITUD ADAPTATIVA: {length_guidance}\n"
                "- LENGUAJE NATURAL: Responde como un experto explicando de manera clara y comprensible.\n"
                "- FORMATO ESTÉTICO (MUY IMPORTANTE):\n"
                "  * Usa **negrita** para conceptos clave, IPs, dominios y valores importantes. Ej: **8.8.8.8**, **Capa de Red**.\n"
                "  * LISTAS LIMPIAS: Cuando uses listas, la viñeta (• o -) debe estar en la MISMA LÍNEA que el texto.\n"
                "    INCORRECTO:\n    •\n    **Concepto:** Definición\n"
                "    CORRECTO:\n    • **Concepto:** Definición\n"
                "  * NO USES backticks (`) ni bloques de código (```) para valores individuales.\n"
                "  * Evita tablas complejas. Prefiere listas claras con viñetas para enumerar datos.\n"
                "- ESTRUCTURA: Organiza la información de forma lógica y fácil de leer.\n"
                "- NO copies párrafos completos, parafrasea de manera natural\n\n"
                "Genera una respuesta clara y con formato limpio (sin bloques innecesarios):"
            )
            
            try:
                # Usar max_tokens adaptado según complejidad
                # No recortar respuestas - permitir respuestas completas según max_tokens configurado
                # RESTAURADO: Hacer streaming aquí para velocidad óptima
                # El Supervisor solo modificará en casos EXTREMOS
                # ASYNC CHANGE
                final_answer = await llm.agenerate(
                    synthesis_prompt, 
                    max_tokens=max_tokens_synthesis,
                    stream_callback=stream_callback  # Streaming directo para velocidad
                )
                final_answer = final_answer.strip()
                
                thought_chain = add_thought(
                    thought_chain,
                    "Sintetizador",
                    "Síntesis: solo RAG",
                    f"Respuesta procesada y acortada ({len(rag_answers)} resultado(s))",
                    "success"
                )
                return {
                    "final_output": final_answer,
                    "thought_chain": thought_chain
                }
            except Exception as e:
                # Fallback: usar respuesta original completa sin truncar
                final_answer = combined_raw
                thought_chain = add_thought(
                    thought_chain,
                    "Sintetizador",
                    "Síntesis: solo RAG (fallback)",
                    f"Error al procesar, usando respuesta original ({len(rag_answers)} resultado(s))",
                    "warning"
                )
                return {
                    "final_output": final_answer,
                    "thought_chain": thought_chain
                }
    
    # CASO 2: Fallback - si no se detectó RAG
    # Simplemente concatenar los resultados
    processed_results = [str(r) for r in results]
    thought_chain = add_thought(
        thought_chain,
        "Sintetizador",
        "Síntesis: fallback",
        "Concatenando resultados (herramientas no detectadas)",
        "info"
    )
    return {
        "final_output": "\n\n".join(processed_results).strip(),
        "thought_chain": thought_chain
    }


# ---------------------------------------------------------
# Construcción del grafo
# ---------------------------------------------------------

graph = StateGraph(GraphState)

# Arquitectura
graph.add_node("Planner", planner_node)
graph.add_node("Orquestador", orchestrator_node)
graph.add_node("Agente_Ejecutor", ejecutor_agent_node)
graph.add_node("Sintetizador", synthesizer_node)
graph.add_node("Supervisor", supervisor_node)

# Flujo de ejecución: Start → Planner → Orquestador → [Agente Ejecutor, Sintetizador, Supervisor] → End
graph.add_edge(START, "Planner")
graph.add_edge("Planner", "Orquestador")

# El Orquestador decide a qué componente ir
def route_from_orchestrator(state: GraphState) -> str:
    """
    Decide desde el Orquestador a qué componente dirigirse.
    
    Esta función SOLO accede a:
        pass
    - state.next_component: para saber a qué componente ir
    - state.plan_steps: para verificar si hay pasos pendientes
    - state.results: para verificar si hay resultados
    
    NO debe acceder a otros campos del state.
    """
    next_component = state.next_component
    plan_steps = state.plan_steps or []
    results = state.results or []
    
    # Si el orquestador decidió ir a un componente específico, usar esa decisión
    if next_component:
        return next_component
    
    # Fallback: decidir basándose en el estado
    if plan_steps:
        return "Agente_Ejecutor"
    elif results:
        return "Sintetizador"
    else:
        return "Sintetizador"

# Arista condicional desde Orquestador
# Nota: El Supervisor solo se alcanza desde Sintetizador, nunca directamente desde Orquestador
graph.add_conditional_edges(
    "Orquestador",
    route_from_orchestrator,
    {
        "Agente_Ejecutor": "Agente_Ejecutor",
        "Sintetizador": "Sintetizador"
    }
)

# Desde Agente Ejecutor: volver al Orquestador si hay más pasos, o ir a Sintetizador
def route_from_executor(state: GraphState) -> str:
    """
    Decide desde el Agente Ejecutor a dónde ir.
    
    Esta función SOLO accede a:
        pass
    - state.plan_steps: para verificar si hay pasos pendientes
    
    NO debe acceder a otros campos del state.
    """
    plan_steps = state.plan_steps or []
    
    # Si hay más pasos, volver al Orquestador para decidir el siguiente paso
    if plan_steps:
        return "Orquestador"
    # Si no hay más pasos, ir a Sintetizador
    return "Sintetizador"

graph.add_conditional_edges(
    "Agente_Ejecutor",
    route_from_executor,
    {
        "Orquestador": "Orquestador",
        "Sintetizador": "Sintetizador"
    }
)

# Desde Sintetizador: siempre ir a Supervisor
graph.add_edge("Sintetizador", "Supervisor")

# Desde Supervisor: siempre terminar
graph.add_edge("Supervisor", END)

# Compilar el grafo base
# Nota: Exportamos el grafo directamente para compatibilidad con LangGraph Studio
# Los callbacks se pueden agregar usando las funciones helper o manualmente
graph = graph.compile()


# ---------------------------------------------------------
# Funciones helper para callbacks opcionales
# ---------------------------------------------------------

def get_graph_with_callbacks(callbacks: Optional[List[Any]] = None):
    """
    Obtiene el grafo compilado con callbacks opcionales.
    
    Args:
        callbacks: Lista opcional de callbacks de LangChain/LangGraph
    
    Returns:
        Grafo compilado con callbacks aplicados
    """
    # Si no hay callbacks, retornar el grafo base
    if not callbacks:
        return graph
    
    # Recompilar el grafo con callbacks
    # Nota: En LangGraph, los callbacks se pasan durante la invocación,
    # no durante la compilación. Por lo tanto, retornamos el grafo base
    # y los callbacks se pasarán en ainvoke/invoke
    return graph


def invoke_with_ragas_callbacks(
    state: Dict[str, Any],
    enable_ragas: bool = True
) -> Dict[str, Any]:
    """
    Ejecuta el grafo con callbacks de Ragas habilitados.
    
    Args:
        state: Estado inicial del grafo
        enable_ragas: Si debe habilitar callbacks de Ragas
    
    Returns:
        Resultado de la ejecución del grafo
    """
    from ..utils.ragas_callback import get_ragas_callback
    
    callbacks = []
    if enable_ragas:
        ragas_callback = get_ragas_callback(enabled=True)
        if ragas_callback:
            callbacks.append(ragas_callback)
    
    # Ejecutar con callbacks
    if callbacks:
        return graph.invoke(state, config={"callbacks": callbacks})
    else:
        return graph.invoke(state)


async def ainvoke_with_ragas_callbacks(
    state: Dict[str, Any],
    enable_ragas: bool = True
) -> Dict[str, Any]:
    """
    Ejecuta el grafo de forma asíncrona con callbacks de Ragas habilitados.
    
    Args:
        state: Estado inicial del grafo
        enable_ragas: Si debe habilitar callbacks de Ragas
    
    Returns:
        Resultado de la ejecución del grafo
    """
    from ..utils.ragas_callback import get_ragas_callback
    
    callbacks = []
    if enable_ragas:
        ragas_callback = get_ragas_callback(enabled=True)
        if ragas_callback:
            callbacks.append(ragas_callback)
    
    # Ejecutar con callbacks
    if callbacks:
        return await graph.ainvoke(state, config={"callbacks": callbacks})
    else:
        return await graph.ainvoke(state)


# Función helper para obtener config con callbacks de Ragas
def get_config_with_ragas_callbacks(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Obtiene un config con callbacks de Ragas agregados automáticamente.
    Útil para usar con LangGraph Studio cuando se ejecuta el grafo directamente.
    
    Ejemplo de uso en LangGraph Studio:
        pass
    ```python
    from src.agent.agent_graph import get_config_with_ragas_callbacks
    config = get_config_with_ragas_callbacks()
    result = await graph.ainvoke(state, config=config)
    ```
    
    Args:
        config: Config opcional existente
    
    Returns:
        Config con callbacks de Ragas agregados (si están habilitados en settings)
    """
    from ..utils.ragas_callback import get_ragas_callback
    from ..settings import settings
    
    config = config or {}
    
    if settings.ragas_enabled:
        callbacks = config.get("callbacks", [])
        ragas_callback = get_ragas_callback(enabled=True)
        if ragas_callback and ragas_callback not in callbacks:
            callbacks.append(ragas_callback)
            config["callbacks"] = callbacks
    
    return config
