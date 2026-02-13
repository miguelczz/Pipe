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
# Global initialization
# ---------------------------------------------------------

rag_tool = RAGTool()
llm = LLMClient()


# ---------------------------------------------------------
# State conversion helpers
# ---------------------------------------------------------

def messages_to_agent_state(messages: List[AnyMessage], report_id: Optional[str] = None, session_id: Optional[str] = None) -> AgentState:
    """
    Converts graph state messages into an AgentState for the router.
    Includes report_id when the chat is in the context of a report.
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
    """Extracts the last user message from the message list."""
    if not messages:
        return ""
    for msg in reversed(messages):
        role = getattr(msg, "role", None) or getattr(msg, "type", None)
        if role in ["user", "human"]:
            return getattr(msg, "content", str(msg))
    return ""


def get_conversation_context(messages: List[AnyMessage], max_messages: int = 10) -> str:
    """
    Extracts conversation context from messages for use in follow-ups.
    Returns a formatted string with the last messages.
    """
    if not messages:
        return ""
    
    conversation_context = []
    for msg in messages[-max_messages:]:
        role = getattr(msg, "role", None) or getattr(msg, "type", "user")
        content = getattr(msg, "content", str(msg))
        if role in ["user", "human", "assistant", "agent"]:
            # Normalize roles
            if role in ["human", "user"]:
                role = "user"
            elif role in ["assistant", "agent"]:
                role = "assistant"
            conversation_context.append(f"{role}: {content}")
    
    return "\n".join(conversation_context)


def _extract_tool_from_step(step: str, report_id: Optional[str] = None) -> str:
    """
    Extracts tool from plan_step. RAG or get_report if report_id exists and step suggests it.
    """
    if not report_id:
        return "rag"
    step_lower = (step or "").lower()
    if any(kw in step_lower for kw in ["report", "capture", "analysis", "verdict", "this result", "this capture"]):
        return "get_report"
    return "rag"


@cache_result("conversation_context", ttl=1800)  # Cache for 30 minutes
def generate_from_conversation_context(context_text: str, user_prompt: str) -> str:
    """
    Generates a response based on conversation context.
    This function is cached to avoid regenerating identical responses.
    
    Args:
        context_text: Conversation context text
        user_prompt: User question
    
    Returns:
        Generated response
    """
    followup_prompt = f"""
Based on the following previous conversation, answer the user's question DIRECTLY, COMPACTLY, and focused on what they are actually interested in.

IMPORTANT:
- Be CONCISE: go straight to the point, without rambling or unnecessary explanations.
- Answer ONLY what the user asks, without unsolicited additional information.
- If the question is about something mentioned previously, elaborate ONLY on that specifically.
- Avoid repetitions and redundancies.
- Maximum 3-4 paragraphs, preferably less.

Previous conversation:
{context_text}

User Question: {user_prompt}

Response (direct and compact):
"""
    return llm.generate(followup_prompt).strip()


# ---------------------------------------------------------
# Alias for compatibility - use GraphState from core module
# ---------------------------------------------------------

# Use GraphState that implements State pattern correctly
State = GraphState

# Helper to add thoughts (uses method from GraphState)
def add_thought(thought_chain: List[Dict[str, Any]], node_name: str, action: str, details: str = "", status: str = "success") -> List[Dict[str, Any]]:
    """
    Adds a thought step to the chain.
    Wrapper for compatibility with existing code.
    
    Args:
        thought_chain: Current thought list
        node_name: Name of the node executing the action
        action: Action being performed
        details: Additional action details
        status: Action status ("success", "error", "info")
    
    Returns:
        Updated thought list
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
# Graph nodes
# ---------------------------------------------------------

def planner_node(state: GraphState) -> Dict[str, Any]:
    """
    Analyzes user message and defines the execution plan.
    
    This node ONLY accesses:
    - state.messages: to get user prompt and context
    - state.plan_steps: to write the generated plan
    
    It must NOT access or modify other state fields.
    
    Returns a partial dictionary with only the modified fields so
    LangGraph propagates values correctly with LastValue.
    """
    # Extract user prompt from messages
    user_prompt = get_user_prompt_from_messages(state.messages)
    
    if not user_prompt:
        # If no prompt, create an empty plan
        return {"plan_steps": []}
    
    # Convert messages to AgentState for the router (include report_id if it exists)
    report_id = getattr(state, "report_id", None)
    session_id = getattr(state, "session_id", None)
    context = messages_to_agent_state(state.messages, report_id=report_id, session_id=session_id)
    router = PipeAgent()

    # Pass selected_text if available in state (text highlighted by user in frontend)
    selected_text = getattr(state, "selected_text", None)
    decision = router.decide(user_prompt, context, selected_text=selected_text)
    
    # Verify if question was rejected for being off-topic
    if decision.get("rejection_message"):
        rejection_msg = decision.get("rejection_message")
        
        thought_chain = add_thought(
            state.thought_chain or [],
            "Planner",
            "Question rejected",
            "Question outside the scope of networks and telecommunications",
            "info"
        )
        
        # Return result indicating rejection
        # This will be processed by synthesizer to show rejection message
        return {
            "plan_steps": [],
            "thought_chain": thought_chain,
            "rejection_message": rejection_msg
        }
    
    plan_steps = decision.get("plan_steps", [])
    
    # Record thought: plan generated (consolidated)
    thought_chain = add_thought(
        state.thought_chain or [],
        "Planner",
        "Plan generated",
        f"{len(plan_steps)} step(s): {', '.join(plan_steps[:2])}{'...' if len(plan_steps) > 2 else ''}",
        "success"
    )
    
    # Return only the modified field as a dictionary for correct propagation
    return {
        "plan_steps": plan_steps,
        "thought_chain": thought_chain
    }


def orchestrator_node(state: GraphState) -> Dict[str, Any]:
    """
    Orchestrator: Coordinates and directs the flow between specialized components.
    Evaluates the generated plan and decides which component needs to activate.
    
    This node ONLY accesses:
    - state.plan_steps: to evaluate the generated plan
    - state.messages: to get user context
    - state.results: to verify if there are pending results to process
    - state.orchestration_decision: to write the decision
    - state.next_component: to write the next component to activate
    
    It must NOT access or modify other state fields.
    
    Returns a partial dictionary with only the modified fields so
    LangGraph propagates values correctly with LastValue.
    """
    plan_steps = state.plan_steps or []
    results = state.results or []
    thought_chain = state.thought_chain or []
    
    # Verify if there is a rejection message (off-topic question)
    # This propagates from planner when it detects an off-topic question
    rejection_message = getattr(state, 'rejection_message', None)
    if rejection_message:
        thought_chain = add_thought(
            thought_chain,
            "Orchestrator",
            "Question rejected → Supervisor",
            "Off-topic question, passing to Supervisor to validate",
            "info"
        )
        return {
            "next_component": "Supervisor",
            "thought_chain": thought_chain,
            "rejection_message": rejection_message
        }
    
    # If no plan, nothing to orchestrate
    if not plan_steps:
        thought_chain = add_thought(
            thought_chain,
            "Orchestrator",
            "No plan → Supervisor",
            "Execution plan was not generated",
            "info"
        )
        return {
            "next_component": "Supervisor",
            "thought_chain": thought_chain
        }
    
    # If there are results but no pending steps, go to Supervisor
    if results and not plan_steps:
        thought_chain = add_thought(
            thought_chain,
            "Orchestrator",
            "All steps completed → Supervisor",
            f"{len(results)} result(s) ready to validate",
            "success"
        )
        return {
            "next_component": "Supervisor",
            "thought_chain": thought_chain
        }
    
    # If there are pending steps, we need to execute tools
    if plan_steps:
        thought_chain = add_thought(
            thought_chain,
            "Orchestrator",
            "Steps pending → Executor Agent",
            f"{len(plan_steps)} pending step(s)",
            "success"
        )
        return {
            "next_component": "Executor_Agent",
            "thought_chain": thought_chain
        }
    
    # Fallback: go to Supervisor
    thought_chain = add_thought(
        thought_chain,
        "Orchestrator",
        "Fallback → Supervisor",
        "Using default fallback",
        "info"
    )
    return {
        "next_component": "Supervisor",
        "thought_chain": thought_chain
    }


def executor_agent_node(state: GraphState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Executor Agent: Executes the RAG tool according to the plan.
    Combines tool selection and execution in a single node.
    
    This node ONLY accesses:
    - state.plan_steps: to read and modify (remove actual step)
    - state.messages: to get original user prompt (context)
    - state.current_step: to write actual step (temporal)
    - state.tool_name: to write selected tool (temporal)
    - state.results: to accumulate results
    
    It must NOT access final_output, supervised_output or other fields.
    
    Returns a partial dictionary with only the modified fields so
    LangGraph propagates values correctly with LastValue.
    """
    thought_chain = state.thought_chain or []

    # Get streaming callback if exists
    stream_callback = None
    if config and "configurable" in config:
        stream_callback = config["configurable"].get("stream_callback")
    
    # Extract actual step from plan
    plan_steps_copy = list(state.plan_steps or [])
    if not plan_steps_copy:
        thought_chain = add_thought(
            thought_chain,
            "Executor_Agent",
            "No steps to execute",
            "The plan is empty",
            "error"
        )
        return {"thought_chain": thought_chain}
    
    current_step = plan_steps_copy.pop(0)
    
    # Get user prompt for context
    user_prompt = get_user_prompt_from_messages(state.messages)
    
    # Limit prompt size to avoid memory issues
    MAX_PROMPT_LENGTH = 2000
    if len(user_prompt) > MAX_PROMPT_LENGTH:
        user_prompt = user_prompt[:MAX_PROMPT_LENGTH] + "..."
    
    # Extract tool from plan_step; if report_id exists, it could be get_report
    report_id = getattr(state, "report_id", None)
    tool_name = _extract_tool_from_step(current_step, report_id)

    try:
        if tool_name == "get_report" and report_id:
            result = execute_get_report(report_id, user_prompt)
        elif tool_name == "rag":
            session_id = getattr(state, "session_id", None)
            result = execute_rag_tool(
                current_step, 
                user_prompt, 
                state.messages, 
                stream_callback=stream_callback,
                metadata={
                    "trace_id": getattr(state, "trace_id", None),
                    "user_id": getattr(state, "user_id", None),
                    "generation_name": "RAG Execution"
                }
            )
        else:
            result = {"error": "tool_not_found"}
    except Exception as e:
        result = {"error": f"Error executing {tool_name}: {str(e)}"}
    
    # Save result in accumulated list
    accumulated = state.results or []
    accumulated.append(result)

    # Determine execution status and record consolidated thought
    execution_status = "success"
    if isinstance(result, dict) and "error" in result:
        execution_status = "error"
        execution_details = f"Error: {result.get('error', 'unknown error')}"
    else:
        # Summarize executed step
        step_summary = current_step[:60] + "..." if len(current_step) > 60 else current_step
        execution_details = f"Step: {step_summary}"
    
    # Record thought: execution completed (consolidated)
    thought_chain = add_thought(
        thought_chain,
        "Executor_Agent",
        f"{tool_name.upper()} executed",
        execution_details,
        execution_status
    )

    # Save to history before cleaning (full traceability)
    executed_tools_list = state.executed_tools or []
    executed_steps_list = state.executed_steps or []
    
    if tool_name:
        executed_tools_list.append(tool_name)
    if current_step:
        executed_steps_list.append(current_step)

    # Return only modified fields as dictionary for correct propagation
    # Note: We don't return current_step and tool_name when cleaned (None) because
    # useful info is already in executed_steps and executed_tools
    return {
        "plan_steps": plan_steps_copy,
        "results": accumulated,
        "executed_tools": executed_tools_list,  # History of tools used
        "executed_steps": executed_steps_list,   # History of executed steps
        "thought_chain": thought_chain
    }


async def supervisor_node(state: GraphState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Supervisor: Validates results BEFORE synthesizing. Runs before Synthesizer.
    
    Responsibilities:
    1. Verify if there are valid tool results
    2. Detect if RAG did not find info → generate general knowledge fallback
    3. Capture data for Ragas evaluation (background)
    4. Approve or enrich results for Synthesizer to process
    
    This node accesses:
    - state.results: to validate tool results
    - state.messages: to get user context
    - state.rejection_message: to detect off-topic questions
    - state.supervised_output: to write fallback if RAG failed (Synthesizer will use it)
    - state.quality_score: to write quality score
    
    Returns a partial dictionary with only modified fields.
    """
    user_prompt = get_user_prompt_from_messages(state.messages)
    thought_chain = state.thought_chain or []
    results = state.results or []
    
    # ---------------------------------------------------------
    # 1. If there is a rejection message, approve directly (Synthesizer will format it)
    # ---------------------------------------------------------
    rejection_message = getattr(state, 'rejection_message', None)
    if rejection_message:
        thought_chain = add_thought(
            thought_chain,
            "Supervisor",
            "Approved: rejection message",
            "Off-topic question, Synthesizer will format the rejection",
            "info"
        )
        return {
            "quality_score": 1.0,
            "thought_chain": thought_chain
        }
    
    # ---------------------------------------------------------
    # 2. Verify if there are valid results
    # ---------------------------------------------------------
    if not results:
        thought_chain = add_thought(
            thought_chain,
            "Supervisor",
            "No results to validate",
            "Tool results were not found",
            "warning"
        )
        return {
            "quality_score": 0.0,
            "thought_chain": thought_chain
        }
    
    # ---------------------------------------------------------
    # 3. FALLBACK: Detect if RAG did not find information
    # ---------------------------------------------------------
    rag_missed_info = False
    
    # 3a. Verify tool results by source
    for res in results:
        if isinstance(res, dict) and res.get("source") in ["no_hits", "empty_context", "no_documents", "qdrant_connection_error"]:
            rag_missed_info = True
            break
    
    # 3b. Verify RAG response text
    if not rag_missed_info:
        missing_info_keywords = [
            "did not find information", "no info found", "no information found",
            "not mentioned in the documents", "does not appear in the context",
            "not in the documents", "outside this specialized scope",
            "not related to networking", "information is not available",
            "not found in technical documentation", "not in the guide",
            "no encontré información", "no tengo información", 
            "no se menciona en los documentos", "no aparece en el contexto",
            "no está en los documentos"
        ]
        for res in results:
            if isinstance(res, dict) and "answer" in res:
                answer_text = res["answer"].lower()
                if any(keyword in answer_text for keyword in missing_info_keywords):
                    rag_missed_info = True
                    break
    
    if rag_missed_info:
        fallback_prompt = f"""
The RAG system did not find information in the documents for the user's question, but the user requires an answer from Pipe.
Generate a response based on your GENERAL KNOWLEDGE as an expert in WiFi networks and Band Steering.

User Question: "{user_prompt}"

CRITICAL INSTRUCTIONS:
1. Start the response EXACTLY with this phrase: "⚠️ **Note:** I did not find this specific information in your technical documents, but based on general WiFi networking standards:"
2. Provide a technical, precise, and helpful response on the topic.
3. MANDATORY CONTEXT: Any term like 'association' must be interpreted EXCLUSIVELY as '802.11 wireless association'. DO NOT talk about social or economic realms.
4. If the question requests a list, enumerate them clearly.

Generate the technical and professional response:
"""
        try:
            fallback_output = await llm.agenerate(
                fallback_prompt,
                model_tier="cheap",
                metadata={
                    "trace_id": getattr(state, "trace_id", None),
                    "user_id": getattr(state, "user_id", None),
                    "generation_name": "Supervisor Fallback"
                }
            )
            thought_chain = add_thought(
                thought_chain,
                "Supervisor",
                "Fallback: General Knowledge",
                "Information not found in docs → Using general knowledge",
                "warning"
            )
            # Store fallback in supervised_output for Synthesizer to use directly
            return {
                "supervised_output": fallback_output.strip(),
                "quality_score": 0.9,
                "thought_chain": thought_chain
            }
        except Exception as e:
            # If fail, let Synthesizer work with raw results
            thought_chain = add_thought(
                thought_chain,
                "Supervisor",
                "Fallback failed",
                f"Error generating fallback: {str(e)}",
                "error"
            )
    
    # ---------------------------------------------------------
    # 4. Valid results: approve for Synthesizer
    # ---------------------------------------------------------
    thought_chain = add_thought(
        thought_chain,
        "Supervisor",
        "Validation: approved",
        f"{len(results)} valid result(s) to synthesize",
        "success"
    )
    
    # ---------------------------------------------------------
    # 5. Capture data for Ragas evaluation (background, non-blocking)
    # ---------------------------------------------------------
    # DISABLED TO AVOID RATE LIMITS AND 400 ERRORS
    # try:
    #     from ..utils.ragas_evaluator import get_evaluator
    #     from ..settings import settings
    #     
    #     if settings.ragas_enabled and user_prompt:
    #         # ... (commented code)
    #         pass
    # except Exception:
    #     pass
    
    # OPTIMIZATION: Clean state to avoid memory accumulation
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
    Synthesizer: Generates the final user-readable response.
    Runs AFTER Supervisor, which has already validated the results.
    
    Flow: ... → Supervisor (validates data) → Synthesizer (generates response) → END
    
    This node accesses:
    - state.results: to read tool results
    - state.messages: to get original user prompt
    - state.supervised_output: if Supervisor generated a fallback, use it directly
    - state.rejection_message: for rejection messages
    - state.final_output: to write final response
    
    Returns a partial dictionary with only modified fields.
    """
    results = state.results or []
    thought_chain = state.thought_chain or []
    
    # Get streaming callback if exists
    stream_callback = None
    if config and "configurable" in config:
        stream_callback = config["configurable"].get("stream_callback")
    
    # ---------------------------------------------------------
    # CASE 0: If Supervisor generated a fallback (supervised_output), use it directly
    # This occurs when RAG did not find info and Supervisor generated
    # a response with general knowledge.
    # ---------------------------------------------------------
    supervised_output = getattr(state, 'supervised_output', None)
    if supervised_output:
        thought_chain = add_thought(
            thought_chain,
            "Synthesizer",
            "Using Supervisor fallback",
            "Supervisor generated a response with general knowledge",
            "info"
        )
        # Stream fallback if callback exists
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
    # CASE 1: Rejection message (off-topic question)
    # ---------------------------------------------------------
    rejection_message = getattr(state, 'rejection_message', None)
    if rejection_message:
        thought_chain = add_thought(
            thought_chain,
            "Synthesizer",
            "Rejection message",
            "Question outside the network topic",
            "info"
        )
        return {
            "final_output": rejection_message,
            "thought_chain": thought_chain
        }
    
    # ---------------------------------------------------------
    # CASE 2: No results
    # ---------------------------------------------------------
    if not results:
        thought_chain = add_thought(
            thought_chain,
            "Synthesizer",
            "No results to synthesize",
            "Tool results were not found",
            "error"
        )
        return {
            "final_output": "No results found for the query.",
            "thought_chain": thought_chain
        }

    # ---------------------------------------------------------
    # CASE 3: Tool results - process response with LLM
    # ---------------------------------------------------------
    has_result = any(
        isinstance(r, dict) and 'answer' in r
        for r in results
    )

    if has_result:
        # Detect if source is a report or RAG
        is_report_source = any(
            isinstance(r, dict) and r.get('source') == 'report_tool'
            for r in results
        )
        
        # Extract only 'answer' from each result
        answers = []
        for r in results:
            if isinstance(r, dict) and 'answer' in r:
                answers.append(r['answer'])
        
        if answers:
            # Combine answers if multiple
            combined_raw = "\n\n".join(answers).strip()
            
            # Get original user prompt for context
            user_prompt = get_user_prompt_from_messages(state.messages)
            
            # Initial default values
            max_tokens_synthesis = 600
            synthesis_tier = "standard" # Default to Gemini for reports/quality
            
            if is_report_source:
                # ── REPORT MODE: response based on specific analysis data ──
                # For reports, we keep standard (Gemini) for precision
                synthesis_tier = "standard"
                synthesis_prompt = (
                    f"User Question: {user_prompt}\n\n"
                    "The user is viewing a SPECIFIC ANALYSIS REPORT. Below are the REAL data from their report:\n\n"
                    f"--- REPORT DATA ---\n{combined_raw}\n--- END DATA ---\n\n"
                    "CRITICAL INSTRUCTIONS:\n"
                    "- Answer EXCLUSIVELY with the data from the report provided above. These are REAL data from an analysis the user performed.\n"
                    "- CITE EXACT VALUES: MACs, BSSIDs, bands, success rates, BTM counts, supported standards, etc. Do not round or generalize.\n"
                    "- If the user asks about something in the data, answer with the specific values. For example:\n"
                    "  * 'What KVR standards does it support?' → Mention exactly which ones are True/False from the report.\n"
                    "  * 'Why did it pass/fail?' → Use the compliance checks and report verdict.\n"
                    "  * 'How many transitions were there?' → Cite the exact number and details for each.\n"
                    "- DO NOT give generic theoretical explanations. The user wants to know about THEIR analysis, not about theory.\n"
                    "- If the question touches on something NOT in the report data, state that such information is not available in this analysis.\n"
                    "- FORMAT:\n"
                    "  * Use **bold** for key values (MACs, standard names, verdicts).\n"
                    "  * Use bulleted lists for multiple data points.\n"
                    "  * Be direct and concise, without unnecessary introductions.\n\n"
                    "Respond based ONLY on the report data:"
                )
                max_tokens_synthesis = 800
            else:
                # ── RAG MODE: response based on general documentation ──
                # Analyze complexity using routing tier (cheap/fast)
                complexity = "moderate"
                length_guidance = "BALANCED response: 100-200 words with clear explanation."
                
                complexity_check_prompt = f"""
Analyze the following question and determine its complexity:

Question: "{user_prompt}"

Determine if it is:
1. "simple" - Direct question requiring a brief answer (e.g., "What is X?", "Which is Y?")
2. "moderate" - Question requiring an explanation with some details
3. "complex" - Question requiring a detailed explanation or a complete list of items

Respond ONLY with one word: "simple", "moderate", or "complex".
"""
                try:
                    complexity_response = await llm.agenerate(
                        complexity_check_prompt,
                        model_tier="routing",
                        metadata={
                            "trace_id": getattr(state, "trace_id", None),
                            "user_id": getattr(state, "user_id", None),
                            "generation_name": "Complexity Check"
                        }
                    )
                    complexity = complexity_response.strip().lower()
                    
                    if "simple" in complexity:
                        length_guidance = "BRIEF response: 2-4 sentences (50-100 words). Get straight to the point."
                        max_tokens_synthesis = 300
                        synthesis_tier = "cheap" # Use Groq
                    elif "complex" in complexity:
                        length_guidance = "COMPLETE response: 300-600 words with structured explanation. Include ALL elements if it's a list."
                        max_tokens_synthesis = 2000
                        synthesis_tier = "standard" # Use Gemini only for complex
                    else:
                        length_guidance = "BALANCED response: 100-200 words with clear explanation."
                        max_tokens_synthesis = 800
                        synthesis_tier = "cheap" # Use Groq also for moderate to save quota
                except Exception:
                    pass
                
                synthesis_prompt = (
                    f"User Question: {user_prompt}\n\n"
                    "Based on the following RAG system response, generate a clear, natural, and CONCISE response.\n\n"
                    f"RAG Response:\n{combined_raw}\n\n"
                    "INSTRUCTIONS:\n"
                    "- TOTAL FIDELITY: Use ONLY information from the RAG response. DO NOT invent, DO NOT add general knowledge.\n"
                    f"- ADAPTIVE LENGTH: {length_guidance}\n"
                    "- NATURAL LANGUAGE: Respond as an expert in a clear and understandable manner.\n"
                    "- FORMAT:\n"
                    "  * Use **bold** for key concepts and important values.\n"
                    "  * Clean lists: bullet on the SAME LINE as text.\n"
                    "  * DO NOT use backticks or code blocks for individual values.\n"
                    "- STRUCTURE: Organize information logically.\n"
                    "- DO NOT copy full paragraphs, paraphrase naturally.\n\n"
                    "Generate a clear response with clean formatting:"
                )
            
            source_label = "report" if is_report_source else "RAG"
            try:
                synthesis_response = await llm.agenerate(
                    synthesis_prompt,
                    stream_callback=stream_callback,
                    max_tokens=max_tokens_synthesis,
                    model_tier=synthesis_tier, # Use optimized tier
                    metadata={
                        "trace_id": getattr(state, "trace_id", None),
                        "user_id": getattr(state, "user_id", None),
                        "generation_name": "Final Synthesis"
                    }
                )
                final_answer = synthesis_response.strip()
                
                thought_chain = add_thought(
                    thought_chain,
                    "Synthesizer",
                    f"Synthesis: {source_label}",
                    f"Response processed ({len(answers)} result(s))",
                    "success"
                )
                return {
                    "final_output": final_answer,
                    "thought_chain": thought_chain
                }
            except Exception as e:
                # Fallback: use full original response
                final_answer = combined_raw
                thought_chain = add_thought(
                    thought_chain,
                    "Synthesizer",
                    f"Synthesis: {source_label} (fallback)",
                    f"Error processing, using original response ({len(answers)} result(s))",
                    "warning"
                )
                return {
                    "final_output": final_answer,
                    "thought_chain": thought_chain
                }
    
    # ---------------------------------------------------------
    # CASE 4: Fallback - if RAG was not detected
    # ---------------------------------------------------------
    processed_results = [str(r) for r in results]
    thought_chain = add_thought(
        thought_chain,
        "Synthesizer",
        "Synthesis: fallback",
        "Concatenating results (tools not detected)",
        "info"
    )
    return {
        "final_output": "\n\n".join(processed_results).strip(),
        "thought_chain": thought_chain
    }


# ---------------------------------------------------------
# Graph construction
# ---------------------------------------------------------

graph = StateGraph(GraphState)

# Architecture
graph.add_node("Planner", planner_node)
graph.add_node("Orchestrator", orchestrator_node)
graph.add_node("Executor_Agent", executor_agent_node)
graph.add_node("Synthesizer", synthesizer_node)
graph.add_node("Supervisor", supervisor_node)

# Execution flow: Start → Planner → Orchestrator → [Executor Agent → ...] → Supervisor → Synthesizer → End
graph.add_edge(START, "Planner")
graph.add_edge("Planner", "Orchestrator")

# The Orchestrator decides which component to go to
def route_from_orchestrator(state: GraphState) -> str:
    """
    Decides from the Orchestrator which component to go to.
    
    This function ONLY accesses:
    - state.next_component: to know which component to go to
    - state.plan_steps: to verify if there are pending steps
    - state.results: to verify if there are results
    
    It must NOT access other state fields.
    """
    next_component = state.next_component
    plan_steps = state.plan_steps or []
    
    # If orchestrator decided on a specific component, use that decision
    if next_component:
        # Map old names to new ones if necessary
        if next_component in ["Agente_Ejecutor", "ejecutor_agent_node"]:
            return "Executor_Agent"
        return next_component
    
    # Fallback: decide based on state
    if plan_steps:
        return "Executor_Agent"
    else:
        return "Supervisor"

# Conditional edge from Orchestrator
# Note: Supervisor runs BEFORE Synthesizer to validate results
graph.add_conditional_edges(
    "Orchestrator",
    route_from_orchestrator,
    {
        "Executor_Agent": "Executor_Agent",
        "Supervisor": "Supervisor"
    }
)

# From Executor Agent: back to Orchestrator if more steps, or go to Supervisor
def route_from_executor(state: GraphState) -> str:
    """
    Decides from the Executor Agent where to go.
    
    This function ONLY accesses:
    - state.plan_steps: to verify if there are pending steps
    
    It must NOT access other state fields.
    """
    plan_steps = state.plan_steps or []
    
    # If more steps, go back to Orchestrator to decide next step
    if plan_steps:
        return "Orchestrator"
    # If no more steps, go to Supervisor (which will validate before synthesizing)
    return "Supervisor"

graph.add_conditional_edges(
    "Executor_Agent",
    route_from_executor,
    {
        "Orchestrator": "Orchestrator",
        "Supervisor": "Supervisor"
    }
)

# From Supervisor: always go to Synthesizer (to generate final response)
graph.add_edge("Supervisor", "Synthesizer")

# From Synthesizer: always end
graph.add_edge("Synthesizer", END)

# Compile base graph
# Note: We export graph directly for compatibility with LangGraph Studio
# Callbacks can be added using helper functions or manually
graph = graph.compile()


# ---------------------------------------------------------
# Helper functions for optional callbacks
# ---------------------------------------------------------

def get_graph_with_callbacks(callbacks: Optional[List[Any]] = None):
    """
    Gets the compiled graph with optional callbacks.
    
    Args:
        callbacks: Optional list of LangChain/LangGraph callbacks
    
    Returns:
        Compiled graph with callbacks applied
    """
    # If no callbacks, return base graph
    if not callbacks:
        return graph
    
    # Recompile graph with callbacks
    # Note: In LangGraph, callbacks are passed during invocation,
    # not during compilation. Therefore, we return the base graph
    # and callbacks will be passed in ainvoke/invoke
    return graph


def invoke_with_ragas_callbacks(
    state: Dict[str, Any],
    enable_ragas: bool = True
) -> Dict[str, Any]:
    """
    Executes the graph with Ragas callbacks enabled.
    
    Args:
        state: Initial graph state
        enable_ragas: Whether to enable Ragas callbacks
    
    Returns:
        Graph execution result
    """
    from ..utils.ragas_callback import get_ragas_callback
    
    callbacks = []
    if enable_ragas:
        ragas_callback = get_ragas_callback(enabled=True)
        if ragas_callback:
            callbacks.append(ragas_callback)
    
    # Execute with callbacks
    if callbacks:
        return graph.invoke(state, config={"callbacks": callbacks})
    else:
        return graph.invoke(state)


async def ainvoke_with_ragas_callbacks(
    state: Dict[str, Any],
    enable_ragas: bool = True
) -> Dict[str, Any]:
    """
    Asynchronously executes the graph with Ragas callbacks enabled.
    
    Args:
        state: Initial graph state
        enable_ragas: Whether to enable Ragas callbacks
    
    Returns:
        Graph execution result
    """
    from ..utils.ragas_callback import get_ragas_callback
    
    callbacks = []
    if enable_ragas:
        ragas_callback = get_ragas_callback(enabled=True)
        if ragas_callback:
            callbacks.append(ragas_callback)
    
    # Execute with callbacks
    if callbacks:
        return await graph.ainvoke(state, config={"callbacks": callbacks})
    else:
        return await graph.ainvoke(state)


# Helper function to get config with Ragas callbacks
def get_config_with_ragas_callbacks(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Gets a config with Ragas callbacks automatically added.
    Useful for use with LangGraph Studio when running the graph directly.
    
    Example usage in LangGraph Studio:
    ```python
    from src.agent.agent_graph import get_config_with_ragas_callbacks
    config = get_config_with_ragas_callbacks()
    result = await graph.ainvoke(state, config=config)
    ```
    
    Args:
        config: Optional existing config
    
    Returns:
        Config with Ragas callbacks added (if enabled in settings)
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
