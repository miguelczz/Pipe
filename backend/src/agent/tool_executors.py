"""
Ejecutores de herramientas para el agente.
Solo RAG (get_report se añadirá en Fase 4).
"""
from typing import Any, Dict, List
from ..tools.rag_tool import RAGTool
from ..tools.report_tool import get_report as get_report_tool
from ..agent.llm_client import LLMClient
from langchain_core.messages import AnyMessage

rag_tool = RAGTool()
llm = LLMClient()


def execute_get_report(report_id: str, user_question: str = "") -> dict:
    """
    Ejecuta la herramienta get_report y devuelve un resultado con la misma
    estructura que RAG (answer) para que el sintetizador lo trate como contenido.
    """
    if not report_id or not str(report_id).strip():
        return {"answer": "No se proporcionó ID de reporte.", "source": "report_tool"}
    text = get_report_tool(str(report_id).strip(), user_question or None)
    return {"answer": text, "source": "report_tool"}


def get_conversation_context(messages: List[AnyMessage], max_messages: int = 20, exclude_last: bool = False) -> str:
    """
    Extrae el contexto de conversación de los mensajes.
    Limita el tamaño total del contexto para evitar problemas de memoria.
    """
    if not messages:
        return ""

    conversation_context = []
    total_length = 0
    MAX_CONTEXT_LENGTH = 5000

    msg_list = messages
    if exclude_last and len(msg_list) > 0:
        msg_list = msg_list[:-1]

    for msg in reversed(msg_list[-max_messages:]):
        role = getattr(msg, "role", None) or getattr(msg, "type", "user")
        content = getattr(msg, "content", str(msg))

        if role in ["user", "human", "assistant", "agent"]:
            if role in ["human", "user"]:
                role = "user"
            elif role in ["assistant", "agent"]:
                role = "assistant"

            if len(content) > 1000:
                content = content[:1000] + "..."

            msg_text = f"{role}: {content}"
            if total_length + len(msg_text) + 1 > MAX_CONTEXT_LENGTH:
                break
            conversation_context.insert(0, msg_text)
            total_length += len(msg_text) + 1

    result = "\n".join(conversation_context)
    if len(result) > MAX_CONTEXT_LENGTH:
        result = result[:MAX_CONTEXT_LENGTH] + "..."
    return result


def execute_rag_tool(step: str, prompt: str, messages: List[AnyMessage], stream_callback=None) -> Dict[str, Any]:
    """
    Ejecuta la herramienta RAG.
    """
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

INSTRUCCIONES: Marca "seguimiento" solo si pregunta sobre acciones/resultados específicos de la conversación. Marca "nueva" (RAG) para conceptos, definiciones, explicaciones.

Responde SOLO con una palabra: "seguimiento" o "nueva".
"""
                llm_response = llm.generate(followup_detection_prompt).strip().lower()
                is_followup = (
                    llm_response.strip().startswith("seguimiento")
                    and len(llm_response.strip()) < 15
                    and "nueva" not in llm_response.lower()
                    and "rag" not in llm_response.lower()
                    and "documento" not in llm_response.lower()
                )
                info_seeking_keywords = ["explica", "qué es", "cuales son", "dime sobre", "podrías explicar", "hablame de", "información sobre", "y las", "y los", "y el", "y la"]
                if any(keyword in prompt.lower() for keyword in info_seeking_keywords):
                    ref_words = ["que hiciste", "que realizaste", "anterior", "previo", "antes", "resultado", "la consulta", "lo que", "que ejecutaste"]
                    if not any(ref_word in prompt.lower() for ref_word in ref_words):
                        is_followup = False
        except Exception:
            is_followup = False

    conversation_context_for_rag = None
    if messages:
        try:
            conversation_context_for_rag = get_conversation_context(messages, max_messages=10, exclude_last=True)
        except Exception:
            pass

    try:
        result = rag_tool.query(prompt, conversation_context=conversation_context_for_rag)
    except Exception as e:
        result = {
            "answer": f"Error al buscar información en los documentos: {str(e)}",
            "hits": 0,
            "error": f"rag_execution_error: {str(e)}",
            "contexts": [],
            "source": "error"
        }

    if result.get("error") and messages:
        error_type = result.get("error", "")
        if error_type == "qdrant_connection_error":
            try:
                context_text = get_conversation_context(messages, max_messages=10)
                if context_text:
                    followup_prompt = f"""
Basándote en la siguiente conversación previa, responde la pregunta del usuario de forma DIRECTA y COMPACTA.

Conversación previa:
{context_text}

Pregunta del usuario: {prompt}

Respuesta (directa y compacta):
"""
                    answer = llm.generate(followup_prompt).strip()
                    return {
                        "answer": answer,
                        "hits": 0,
                        "source": "conversation_context_fallback",
                        "contexts": [context_text] if context_text else []
                    }
            except Exception:
                pass

    if not isinstance(result, dict):
        result = {
            "answer": "Error inesperado al procesar la consulta.",
            "hits": 0,
            "error": "invalid_result_type",
            "contexts": []
        }
    elif "error" in result and "answer" not in result:
        result["answer"] = result.get("answer", f"Error al procesar la consulta: {result.get('error', 'error desconocido')}")
        if "contexts" not in result:
            result["contexts"] = []

    return result


def determine_tool_from_step(step: str, prompt: str) -> str:
    """Determina qué herramienta usar. Solo RAG está disponible."""
    return "rag"
