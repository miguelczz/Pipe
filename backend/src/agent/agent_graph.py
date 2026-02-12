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

def messages_to_agent_state(messages: List[AnyMessage], report_id: Optional[str] = None, session_id: Optional[str] = None) -> AgentState:
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
        session_id=session_id or "graph-session",
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
    session_id = getattr(state, "session_id", None)
    context = messages_to_agent_state(state.messages, report_id=report_id, session_id=session_id)
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
            "Pregunta rechazada → Supervisor",
            "Pregunta fuera de tema, pasando al Supervisor para validar",
            "info"
        )
        return {
            "next_component": "Supervisor",
            "thought_chain": thought_chain,
            "rejection_message": rejection_message
        }
    
    # Si no hay plan, no hay nada que orquestar
    if not plan_steps:
        thought_chain = add_thought(
            thought_chain,
            "Orquestador",
            "Sin plan → Supervisor",
            "No se generó plan de ejecución",
            "info"
        )
        return {
            "next_component": "Supervisor",
            "thought_chain": thought_chain
        }
    
    # Si hay resultados pero no hay pasos pendientes, ir a Supervisor
    if results and not plan_steps:
        thought_chain = add_thought(
            thought_chain,
            "Orquestador",
            "Todos los pasos completados → Supervisor",
            f"{len(results)} resultado(s) listo(s) para validar",
            "success"
        )
        return {
            "next_component": "Supervisor",
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
    
    # Fallback: ir a Supervisor
    thought_chain = add_thought(
        thought_chain,
        "Orquestador",
        "Fallback → Supervisor",
        "Usando fallback por defecto",
        "info"
    )
    return {
        "next_component": "Supervisor",
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
            session_id = getattr(state, "session_id", None)
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
    Supervisor: Valida los resultados ANTES de sintetizar. Se ejecuta antes del Sintetizador.
    
    Responsabilidades:
    1. Verificar si hay resultados válidos de las herramientas
    2. Detectar si RAG no encontró información → generar fallback con conocimiento general
    3. Capturar datos para evaluación Ragas (en background)
    4. Aprobar o enriquecer los resultados para que el Sintetizador los procese
    
    Este nodo accede a:
    - state.results: para validar los resultados de herramientas
    - state.messages: para obtener el contexto del usuario
    - state.rejection_message: para detectar preguntas fuera de tema
    - state.supervised_output: para escribir fallback si RAG falló (el Sintetizador lo usará)
    - state.quality_score: para escribir la puntuación de calidad
    
    Retorna un diccionario parcial con solo los campos modificados.
    """
    user_prompt = get_user_prompt_from_messages(state.messages)
    thought_chain = state.thought_chain or []
    results = state.results or []
    
    # ---------------------------------------------------------
    # 1. Si hay mensaje de rechazo, aprobar directamente (el Sintetizador lo formateará)
    # ---------------------------------------------------------
    rejection_message = getattr(state, 'rejection_message', None)
    if rejection_message:
        thought_chain = add_thought(
            thought_chain,
            "Supervisor",
            "Aprobado: mensaje de rechazo",
            "Pregunta fuera de tema, el Sintetizador formateará el rechazo",
            "info"
        )
        return {
            "quality_score": 1.0,
            "thought_chain": thought_chain
        }
    
    # ---------------------------------------------------------
    # 2. Verificar si hay resultados válidos
    # ---------------------------------------------------------
    if not results:
        thought_chain = add_thought(
            thought_chain,
            "Supervisor",
            "Sin resultados para validar",
            "No se encontraron resultados de herramientas",
            "warning"
        )
        return {
            "quality_score": 0.0,
            "thought_chain": thought_chain
        }
    
    # ---------------------------------------------------------
    # 3. FALLBACK: Detectar si RAG no encontró información
    # ---------------------------------------------------------
    rag_missed_info = False
    
    # 3a. Verificar resultados de herramientas por source
    for res in results:
        if isinstance(res, dict) and res.get("source") in ["no_hits", "empty_context", "no_documents", "qdrant_connection_error"]:
            rag_missed_info = True
            break
    
    # 3b. Verificar texto de las respuestas RAG
    if not rag_missed_info:
        missing_info_keywords = [
            "no encontré información", "no tengo información", 
            "no se menciona en los documentos", "no aparece en el contexto",
            "no dispongo de información", "no está en los documentos",
            "fuera de este ámbito especializado", "fuera de este tema especializado",
            "no está relacionada con redes o tecnologías de red"
        ]
        for res in results:
            if isinstance(res, dict) and "answer" in res:
                answer_text = res["answer"].lower()
                if any(keyword in answer_text for keyword in missing_info_keywords):
                    rag_missed_info = True
                    break
    
    if rag_missed_info:
        fallback_prompt = f"""
El sistema RAG no encontró información en los documentos para la pregunta del usuario, pero el usuario requiere una respuesta de Pipe.
Genera una respuesta basada en tu CONOCIMIENTO GENERAL como experto en redes WiFi y Band Steering.

Pregunta del usuario: "{user_prompt}"

INSTRUCCIONES CRÍTICAS:
1. Comienza la respuesta EXACTAMENTE con esta frase: "⚠️ **Nota:** No encontré esta información específica en tus documentos técnicos, pero basado en estándares generales de redes WiFi:"
2. Proporciona una respuesta técnica, precisa y útil sobre el tema.
3. CONTEXTO OBLIGATORIO: Cualquier término como 'asociación' debe interpretarse EXCLUSIVAMENTE como 'asociación inalámbrica 802.11'. NO hables de ámbitos sociales o económicos.
4. Si la pregunta solicita una lista, enuméralos claramente.

Genera la respuesta técnica y profesional:
"""
        try:
            fallback_output = await llm.agenerate(
                fallback_prompt
            )
            thought_chain = add_thought(
                thought_chain,
                "Supervisor",
                "Fallback: Conocimiento General",
                "Información no encontrada en docs → Usando conocimiento general",
                "warning"
            )
            # Guardar el fallback en supervised_output para que el Sintetizador lo use directamente
            return {
                "supervised_output": fallback_output.strip(),
                "quality_score": 0.9,
                "thought_chain": thought_chain
            }
        except Exception as e:
            # Si falla, dejar que el Sintetizador trabaje con los resultados crudos
            thought_chain = add_thought(
                thought_chain,
                "Supervisor",
                "Fallback fallido",
                f"Error al generar fallback: {str(e)}",
                "error"
            )
    
    # ---------------------------------------------------------
    # 4. Resultados válidos: aprobar para el Sintetizador
    # ---------------------------------------------------------
    thought_chain = add_thought(
        thought_chain,
        "Supervisor",
        "Validación: aprobado",
        f"{len(results)} resultado(s) válido(s) para sintetizar",
        "success"
    )
    
    # ---------------------------------------------------------
    # 5. Capturar datos para evaluación Ragas (en background, no bloquea)
    # ---------------------------------------------------------
    # Nota: Se capturan los datos crudos. La respuesta final se generará en el Sintetizador.
    # La evaluación de Ragas se ejecutará con los datos disponibles.
    try:
        from ..utils.ragas_evaluator import get_evaluator
        from ..settings import settings
        
        if settings.ragas_enabled and user_prompt:
            evaluator = get_evaluator(enabled=True)
            if evaluator:
                contexts = []
                for result in results:
                    if isinstance(result, dict) and "contexts" in result:
                        result_contexts = result["contexts"]
                        if isinstance(result_contexts, list):
                            valid_contexts = [c for c in result_contexts if c and isinstance(c, str) and c.strip()]
                            contexts.extend(valid_contexts)
                
                # Extraer respuesta cruda del RAG para la evaluación
                rag_answer = ""
                for res in results:
                    if isinstance(res, dict) and "answer" in res:
                        rag_answer = res["answer"]
                        break
                
                if rag_answer:
                    evaluator.capture_evaluation(
                        question=user_prompt,
                        answer=rag_answer,
                        contexts=contexts if contexts else [],
                        metadata={
                            "tool_used": "rag",
                            "quality_score": 0.0
                        }
                    )
                    
                    if contexts:
                        try:
                            from threading import Thread
                            
                            def evaluate_in_background():
                                try:
                                    evaluator.evaluate_captured_data()
                                except Exception:
                                    pass
                            
                            eval_thread = Thread(target=evaluate_in_background, daemon=True)
                            eval_thread.start()
                        except Exception:
                            pass
    except Exception:
        pass
    
    # OPTIMIZACIÓN: Limpiar estado para evitar acumulación de memoria
    if state.messages and len(state.messages) > 30:
        state.cleanup_old_messages(max_messages=30)
    
    if state.results and len(state.results) > 10:
        state.cleanup_large_results(max_results=10)
    
    return {
        "quality_score": 0.85,
        "thought_chain": thought_chain
    }


async def synthesizer_node(state: GraphState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Sintetizador: Genera la respuesta final legible para el usuario.
    Se ejecuta DESPUÉS del Supervisor, que ya validó los resultados.
    
    Flujo: ... → Supervisor (valida datos) → Sintetizador (genera respuesta) → END
    
    Este nodo accede a:
    - state.results: para leer los resultados de las herramientas
    - state.messages: para obtener el prompt original del usuario
    - state.supervised_output: si el Supervisor generó un fallback, usarlo directamente
    - state.rejection_message: para mensajes de rechazo
    - state.final_output: para escribir la respuesta final
    
    Retorna un diccionario parcial con solo los campos modificados.
    """
    results = state.results or []
    thought_chain = state.thought_chain or []
    
    # Obtener callback de streaming si existe
    stream_callback = None
    if config and "configurable" in config:
        stream_callback = config["configurable"].get("stream_callback")
    
    # ---------------------------------------------------------
    # CASO 0: Si el Supervisor generó un fallback (supervised_output), usarlo directamente
    # Esto ocurre cuando RAG no encontró información y el Supervisor generó
    # una respuesta con conocimiento general.
    # ---------------------------------------------------------
    supervised_output = getattr(state, 'supervised_output', None)
    if supervised_output:
        thought_chain = add_thought(
            thought_chain,
            "Sintetizador",
            "Usando fallback del Supervisor",
            "El Supervisor generó una respuesta con conocimiento general",
            "info"
        )
        # Hacer streaming del fallback si hay callback
        if stream_callback:
            try:
                stream_callback(supervised_output)
            except Exception:
                pass
        return {
            "final_output": supervised_output,
            "thought_chain": thought_chain
        }
    
    # ---------------------------------------------------------
    # CASO 1: Mensaje de rechazo (pregunta fuera de tema)
    # ---------------------------------------------------------
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
    
    # ---------------------------------------------------------
    # CASO 2: No hay resultados
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # CASO 3: Resultados de herramientas - procesar respuesta con LLM
    # ---------------------------------------------------------
    has_result = any(
        isinstance(r, dict) and 'answer' in r
        for r in results
    )

    if has_result:
        # Detectar si la fuente es un reporte o RAG
        is_report_source = any(
            isinstance(r, dict) and r.get('source') == 'report_tool'
            for r in results
        )
        
        # Extraer solo el 'answer' de cada resultado
        answers = []
        for r in results:
            if isinstance(r, dict) and 'answer' in r:
                answers.append(r['answer'])
        
        if answers:
            # Combinar respuestas si hay múltiples
            combined_raw = "\n\n".join(answers).strip()
            
            # Obtener el prompt original del usuario para contexto
            user_prompt = get_user_prompt_from_messages(state.messages)
            
            # Inicializar valores por defecto
            max_tokens_synthesis = 600
            
            if is_report_source:
                # ── MODO REPORTE: respuesta basada en datos específicos del análisis ──
                synthesis_prompt = (
                    f"Pregunta del usuario: {user_prompt}\n\n"
                    "El usuario está viendo un REPORTE DE ANÁLISIS ESPECÍFICO. A continuación están los datos REALES de su reporte:\n\n"
                    f"--- DATOS DEL REPORTE ---\n{combined_raw}\n--- FIN DATOS ---\n\n"
                    "INSTRUCCIONES CRÍTICAS:\n"
                    "- Responde EXCLUSIVAMENTE con los datos del reporte proporcionado arriba. Estos son datos REALES de un análisis que el usuario hizo.\n"
                    "- CITA VALORES EXACTOS: MACs, BSSIDs, bandas, tasas de éxito, conteos de BTM, estándares soportados, etc. No redondees ni generalices.\n"
                    "- Si el usuario pregunta sobre algo que está en los datos, responde con los valores específicos. Por ejemplo:\n"
                    "  * '¿Qué estándares KVR soporta?' → Menciona exactamente cuáles son True/False del reporte.\n"
                    "  * '¿Por qué pasó/falló?' → Usa los compliance checks y el veredicto del reporte.\n"
                    "  * '¿Cuántas transiciones hubo?' → Cita el número exacto y los detalles de cada una.\n"
                    "- NO des explicaciones teóricas genéricas. El usuario quiere saber sobre SU análisis, no sobre la teoría.\n"
                    "- Si la pregunta toca algo que NO está en los datos del reporte, di que esa información no está disponible en este análisis.\n"
                    "- FORMATO:\n"
                    "  * Usa **negrita** para valores clave (MACs, nombres de estándares, veredictos).\n"
                    "  * Usa listas con viñetas para datos múltiples.\n"
                    "  * Sé directo y conciso, sin introducciones innecesarias.\n\n"
                    "Responde basándote ÚNICAMENTE en los datos del reporte:"
                )
                max_tokens_synthesis = 800
            else:
                # ── MODO RAG: respuesta basada en documentación general ──
                # Analizar complejidad
                complexity = "moderada"
                length_guidance = "Respuesta EQUILIBRADA: 100-200 palabras con explicación clara."
                
                complexity_check_prompt = f"""
Analiza la siguiente pregunta y determina su complejidad:

Pregunta: "{user_prompt}"

Determina si es:
1. "simple" - Pregunta directa que requiere una respuesta breve (ej: "¿Qué es X?", "¿Cuál es Y?")
2. "moderada" - Pregunta que requiere una explicación con algunos detalles
3. "compleja" - Pregunta que requiere explicación detallada o una lista completa de elementos

Responde SOLO con una palabra: "simple", "moderada" o "compleja".
"""
                try:
                    complexity_response = await llm.agenerate(
                        complexity_check_prompt
                    )
                    complexity = complexity_response.strip().lower()
                    
                    if "simple" in complexity:
                        length_guidance = "Respuesta BREVE: 2-4 oraciones (50-100 palabras). Ve directo al punto."
                        max_tokens_synthesis = 300  # Aumentado de 200
                    elif "compleja" in complexity:
                        length_guidance = "Respuesta COMPLETA: 300-600 palabras con explicación estructurada. Incluye TODOS los elementos si es una lista."
                        max_tokens_synthesis = 2000  # Aumentado de 1200 para evitar cortes
                    else:
                        length_guidance = "Respuesta EQUILIBRADA: 100-200 palabras con explicación clara."
                        max_tokens_synthesis = 800  # Aumentado de 500
                except Exception:
                    pass
                
                synthesis_prompt = (
                    f"Pregunta del usuario: {user_prompt}\n\n"
                    "Basándote en la siguiente respuesta del sistema RAG, genera una respuesta clara, natural y CONCISA.\n\n"
                    f"Respuesta del RAG:\n{combined_raw}\n\n"
                    "INSTRUCCIONES:\n"
                    "- FIDELIDAD TOTAL: Usa SOLO la información de la respuesta RAG. NO inventes, NO agregues conocimiento general.\n"
                    f"- LONGITUD ADAPTATIVA: {length_guidance}\n"
                    "- LENGUAJE NATURAL: Responde como un experto de manera clara y comprensible.\n"
                    "- FORMATO:\n"
                    "  * Usa **negrita** para conceptos clave y valores importantes.\n"
                    "  * Listas limpias: viñeta en la MISMA LÍNEA que el texto.\n"
                    "  * NO uses backticks ni bloques de código para valores individuales.\n"
                    "- ESTRUCTURA: Organiza la información de forma lógica.\n"
                    "- NO copies párrafos completos, parafrasea de manera natural.\n\n"
                    "Genera una respuesta clara y con formato limpio:"
                )
            
            source_label = "reporte" if is_report_source else "RAG"
            try:
                synthesis_response = await llm.agenerate(
                    synthesis_prompt,
                    stream_callback=stream_callback,
                    max_tokens=max_tokens_synthesis
                )
                final_answer = synthesis_response.strip()
                
                thought_chain = add_thought(
                    thought_chain,
                    "Sintetizador",
                    f"Síntesis: {source_label}",
                    f"Respuesta procesada ({len(answers)} resultado(s))",
                    "success"
                )
                return {
                    "final_output": final_answer,
                    "thought_chain": thought_chain
                }
            except Exception as e:
                # Fallback: usar respuesta original completa
                final_answer = combined_raw
                thought_chain = add_thought(
                    thought_chain,
                    "Sintetizador",
                    f"Síntesis: {source_label} (fallback)",
                    f"Error al procesar, usando respuesta original ({len(answers)} resultado(s))",
                    "warning"
                )
                return {
                    "final_output": final_answer,
                    "thought_chain": thought_chain
                }
    
    # ---------------------------------------------------------
    # CASO 4: Fallback - si no se detectó RAG
    # ---------------------------------------------------------
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

# Flujo de ejecución: Start → Planner → Orquestador → [Agente Ejecutor → ...] → Supervisor → Sintetizador → End
graph.add_edge(START, "Planner")
graph.add_edge("Planner", "Orquestador")

# El Orquestador decide a qué componente ir
def route_from_orchestrator(state: GraphState) -> str:
    """
    Decide desde el Orquestador a qué componente dirigirse.
    
    Esta función SOLO accede a:
    - state.next_component: para saber a qué componente ir
    - state.plan_steps: para verificar si hay pasos pendientes
    - state.results: para verificar si hay resultados
    
    NO debe acceder a otros campos del state.
    
    """
    next_component = state.next_component
    plan_steps = state.plan_steps or []
    
    # Si el orquestador decidió ir a un componente específico, usar esa decisión
    if next_component:
        return next_component
    
    # Fallback: decidir basándose en el estado
    if plan_steps:
        return "Agente_Ejecutor"
    else:
        return "Supervisor"

# Arista condicional desde Orquestador
# Nota: El Supervisor se ejecuta ANTES del Sintetizador para validar resultados
graph.add_conditional_edges(
    "Orquestador",
    route_from_orchestrator,
    {
        "Agente_Ejecutor": "Agente_Ejecutor",
        "Supervisor": "Supervisor"
    }
)

# Desde Agente Ejecutor: volver al Orquestador si hay más pasos, o ir a Supervisor
def route_from_executor(state: GraphState) -> str:
    """
    Decide desde el Agente Ejecutor a dónde ir.
    
    Esta función SOLO accede a:
    - state.plan_steps: para verificar si hay pasos pendientes
    
    NO debe acceder a otros campos del state.
    """
    plan_steps = state.plan_steps or []
    
    # Si hay más pasos, volver al Orquestador para decidir el siguiente paso
    if plan_steps:
        return "Orquestador"
    # Si no hay más pasos, ir a Supervisor (que validará antes de sintetizar)
    return "Supervisor"

graph.add_conditional_edges(
    "Agente_Ejecutor",
    route_from_executor,
    {
        "Orquestador": "Orquestador",
        "Supervisor": "Supervisor"
    }
)

# Desde Supervisor: siempre ir a Sintetizador (para generar respuesta final)
graph.add_edge("Supervisor", "Sintetizador")

# Desde Sintetizador: siempre terminar
graph.add_edge("Sintetizador", END)

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
