"""
Tool executors for the agent.
Only RAG (get_report will be added in Phase 4).
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
    Executes the get_report tool and returns a result with the same
    structure as RAG (answer) so the synthesizer treats it as content.
    """
    if not report_id or not str(report_id).strip():
        return {"answer": "No report ID was provided.", "source": "report_tool"}
    text = get_report_tool(str(report_id).strip(), user_question or None)
    return {"answer": text, "source": "report_tool"}


def get_conversation_context(messages: List[AnyMessage], max_messages: int = 20, exclude_last: bool = False) -> str:
    """
    Extracts the conversation context from messages.
    Limits the total context size to avoid memory issues.
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


def execute_rag_tool(step: str, prompt: str, messages: List[AnyMessage], stream_callback=None, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Executes the RAG tool.
    """
    is_followup = False
    if messages:
        try:
            context_text = get_conversation_context(messages, max_messages=5)
            if context_text:
                followup_detection_prompt = f"""
You are a STRICT analyzer deciding if a question requires searching for information in documents (RAG) or if it is a direct follow-up to the previous conversation.

CRITICAL RULE: By default, use "new" (RAG). Only mark as "followup" if the question EXPLICITLY and DIRECTLY refers to specific actions, results, or events from the previous conversation.

Previous conversation (last messages):
{context_text}

User Question: "{prompt}"

INSTRUCTIONS: Mark "followup" only if asking about specific actions/results from the conversation. Mark "new" (RAG) for concepts, definitions, explanations.

Respond ONLY with one word: "followup" or "new".
"""
                llm_response = llm.generate(
                    followup_detection_prompt,
                    metadata={**(metadata or {}), "generation_name": "RAG Followup Detection"}
                ).strip().lower()
                is_followup = (
                    llm_response.strip().startswith("followup")
                    and len(llm_response.strip()) < 15
                    and "new" not in llm_response.lower()
                    and "rag" not in llm_response.lower()
                    and "document" not in llm_response.lower()
                )
                # Keywords in English and Spanish to support both
                info_seeking_keywords = [
                    "explain", "what is", "what are", "tell me about", "could you explain", "information about", "and the",
                    "explica", "qué es", "cuales son", "dime sobre", "podrías explicar", "hablame de", "información sobre", "y las", "y los", "y el", "y la"
                ]
                if any(keyword in prompt.lower() for keyword in info_seeking_keywords):
                    ref_words = [
                        "you did", "you performed", "previous", "before", "result", "the query", "what you", "executed",
                        "que hiciste", "que realizaste", "anterior", "previo", "antes", "resultado", "la consulta", "lo que", "que ejecutaste"
                    ]
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
        result = rag_tool.query(prompt, conversation_context=conversation_context_for_rag, metadata=metadata)
    except Exception as e:
        result = {
            "answer": f"Error searching information in documents: {str(e)}",
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
Based on the following previous conversation, answer the user's question directly and compactly.

Previous conversation:
{context_text}

User Question: {prompt}

Response (direct and compact):
"""
                    answer = llm.generate(
                        followup_prompt,
                        metadata={**(metadata or {}), "generation_name": "RAG Fallback Context Generation"}
                    ).strip()
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
            "answer": "Unexpected error processing query.",
            "hits": 0,
            "error": "invalid_result_type",
            "contexts": []
        }
    elif "error" in result and "answer" not in result:
        result["answer"] = result.get("answer", f"Error processing query: {result.get('error', 'unknown error')}")
        if "contexts" not in result:
            result["contexts"] = []

    return result


def determine_tool_from_step(step: str, prompt: str) -> str:
    """Determines which tool to use. Only RAG is available."""
    return "rag"
