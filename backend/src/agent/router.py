import re
import json
from openai import OpenAI
from ..settings import settings
from ..tools.rag_tool import RAGTool
from ..models.schemas import AgentState
from ..core.cache import cache_result

# Cliente moderno de OpenAI
client = OpenAI(api_key=settings.openai_api_key)


class PipeAgent:
    def __init__(self):
        self.rag = RAGTool()
        self.llm_model = settings.llm_model
        self.client = client

    def decide(self, user_input: str, state: AgentState) -> dict:
        """
        Decide qué herramienta usar según la intención del usuario.
        Solo RAG está disponible (get_report se añadirá en Fase 4).
        """
        context_for_cache = ""
        context_messages_str = ""
        if state.context_window and len(state.context_window) > 0:
            context_messages = state.context_window[:-1][-3:] if len(state.context_window) > 1 else state.context_window[-3:]
            if context_messages:
                context_parts = []
                for msg in context_messages:
                    role = msg.role if hasattr(msg, 'role') else 'user'
                    content = msg.content if hasattr(msg, 'content') else str(msg)
                    context_parts.append(f"{role}: {content[:150]}")
                context_for_cache = "\n".join(context_parts)

            last_10_messages = state.context_window[-10:]
            context_messages_str = "\n".join([f"{m.role if hasattr(m, 'role') else 'user'}: {m.content if hasattr(m, 'content') else str(m)}" for m in last_10_messages])

        report_id = getattr(state, "report_id", None)
        return self._decide_cached(user_input, context_for_cache, context_messages_str, report_id=report_id)

    @cache_result("router_decision", ttl=300)
    def _decide_cached(self, user_input: str, context_text: str, context_messages_str: str, report_id: str = None) -> dict:
        if context_text:
            context_text = "\n\nContexto de conversación previa:\n" + context_text

        report_instruction = ""
        if report_id:
            report_instruction = """
CURRENT REPORT CONTEXT: The user has a report open (report_id is set). If the user is asking about THIS report, this analysis, this capture, the verdict, what happened, "explain this", "why did it fail/pass", "what does this mean", then use tool "get_report" and plan_steps like ["get report for current analysis"]. Otherwise use RAG for general concepts and documentation.
"""

        combined_prompt = f"""
You are Pipe, a smart agent specialized in Wireshark capture analysis that decides which internal tool to use for a user's request.

STEP 1: Determine if the question is relevant to Wireshark capture analysis, Band Steering, network protocols, or the documentation/guide for understanding captures and results.
STEP 2: If relevant, choose the right tool and create a short plan step.
{report_instruction}

{context_text}

User request: \"\"\"{user_input}\"\"\"
Context (last messages):
{context_messages_str}

RELEVANCE RULES (STEP 1):
- CORE DOMAIN: Wireshark capture analysis, Band Steering, 802.11k/v/r, and interpretation of capture results.
- MANDATORY RELEVANCE: "La prueba", "el análisis", "la guía", "el procedimiento", or "con qué me guío" ALWAYS refer to the Band Steering / capture documentation. Mark RELEVANT.
- Any request about network behavior, WiFi standards (BTM, KVR), or "how to interpret results" is RELEVANT.
- FOLLOW-UP: Ambiguous questions like "what are the states?", "and the difference?" MUST be marked RELEVANT if the previous context is technical (Wireshark, BTM, WiFi).

TOOL DECISION (STEP 2 - only if relevant):
- Use get_report when: the user has a report open and is asking about THIS report/capture/analysis (veredicto, qué pasó, explica esto, por qué falló/pasó).
- Use RAG for: concepts, definitions, explanations, "what is", "explain", "define", follow-ups, conclusions, summaries, and any question about the documentation or how to understand captures/results in general.
- Generate ONE plan_step that is specific (e.g. "get report for current analysis" or "retrieve information about BTM status codes").

OUTPUT FORMAT:
Respond with a valid JSON containing:
- is_relevant: true if the question is relevant, false otherwise
- tool: one of ["rag", "get_report", "none"] (use "none" if not relevant)
- reason: short explanation
- plan_steps: list of short, concrete steps (empty if not relevant)
- rejection_message: (only if not relevant) a friendly message explaining why the question is out of scope

Respond ONLY in JSON format. No extra text or markdown.
"""

        try:
            response = client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": "You are the Pipe Router. Your domain is Wireshark Capture Analysis (Band Steering/Network Protocols). Always respond with valid JSON."},
                    {"role": "user", "content": combined_prompt}
                ],
                max_tokens=500,
            )

            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.replace("```json", "").replace("```", "").strip()
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                text = match.group(0)

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = {"is_relevant": False, "tool": "none", "reason": "parse_fail", "plan_steps": [], "rejection_message": "Error al procesar la solicitud."}

        except Exception as e:
            data = {"is_relevant": False, "tool": "none", "reason": f"llm_error: {str(e)}", "plan_steps": [], "rejection_message": "Error al procesar la solicitud."}

        is_relevant = data.get("is_relevant", True)
        if not is_relevant:
            rejection_msg = data.get("rejection_message", "Lo siento, como asistente de Pipe mi especialidad es el análisis de capturas Wireshark, Band Steering y protocolos de red. Tu pregunta parece estar fuera de este ámbito técnico.")
            return {"tool": "none", "reason": "out_of_topic", "plan_steps": [], "rejection_message": rejection_msg}

        tool = data.get("tool", "").lower().strip()
        plan = data.get("plan_steps", [])

        if not plan:
            if tool == "rag":
                plan = [f"retrieve information about {user_input[:50]}"]
            elif tool == "get_report":
                plan = ["get report for current analysis"]

        vague_keywords = ["ensure", "elaborate", "clarify", "improve", "enhance", "refine", "polish"]
        plan = [step for step in plan if not any(keyword in step.lower() for keyword in vague_keywords)]
        if not plan:
            if tool == "rag":
                plan = [f"retrieve information about {user_input[:50]}"]
            elif tool == "get_report":
                plan = ["get report for current analysis"]

        if tool not in ["rag", "get_report", "none"]:
            tool = "rag"

        data["tool"] = tool
        data["plan_steps"] = plan
        return data

    def handle(self, user_input: str, state: AgentState) -> dict:
        """Ejecuta la herramienta correspondiente. Solo RAG."""
        decision = self.decide(user_input, state)
        tool = decision.get("tool")
        plan_steps = decision.get("plan_steps", [])

        if tool == "rag" and not plan_steps:
            plan_steps = ["query documents"]

        if tool == "rag":
            conversation_context = None
            if state.context_window and len(state.context_window) > 1:
                context_messages = state.context_window[:-1][-5:]
                if context_messages:
                    context_parts = []
                    for msg in context_messages:
                        role = msg.role if hasattr(msg, 'role') else 'user'
                        content = msg.content if hasattr(msg, 'content') else str(msg)
                        context_parts.append(f"{role}: {content}")
                    conversation_context = "\n".join(context_parts)

            out = self.rag.query(user_input, conversation_context=conversation_context)
            state.add_message("system", f"User: {user_input}\nRAG: {out.get('answer', 'No answer')}")
            return {"tool": "rag", "result": out, "decision": decision}

        state.add_message("system", f"User: {user_input}\nSystem: no action taken.")
        return {"tool": "none", "result": None, "decision": decision}
