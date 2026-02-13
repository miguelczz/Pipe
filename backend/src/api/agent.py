"""
API endpoints for the agent - Refactored to use centralized models.
Limited to adapting HTTP to the agent's orchestration graph.
"""
import json
import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from langchain_core.messages import HumanMessage, AIMessage
from ..models.schemas import Message, AgentQuery, SimpleQuery
from ..core.state_manager import SessionManager, get_session_manager
from ..core.graph_state import GraphState
from ..agent.agent_graph import graph
from ..settings import settings
import uuid

router = APIRouter(prefix="/agent", tags=["agent"])

@router.get("/session/{session_id}")
async def get_session_history(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """
    Gets the message history of a session.
    """
    try:
        session_state = session_manager.get_session(session_id, None)
        
        # Convert messages to response format
        messages = [
            {
                "role": msg.role,
                "content": msg.content
            }
            for msg in session_state.context_window
        ]
        
        return {
            "session_id": session_id,
            "messages": messages,
            "context_length": len(session_state.context_window)
        }
    except Exception as e:
        logging.error(f"Error getting session history {session_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error getting session history: {str(e)}"
        )

@router.delete("/session/{session_id}")
async def clear_session(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """
    Clears the message history of a session.
    """
    try:
        session_manager.clear_session(session_id)
        return {
            "session_id": session_id,
            "message": "Session cleared successfully"
        }
    except Exception as e:
        logging.error(f"Error clearing session {session_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error clearing session: {str(e)}"
        )

@router.post("/query")
async def agent_query(
    query: AgentQuery,
    session_manager: SessionManager = Depends(get_session_manager)
):
    try:
        # Generate unique Trace ID to group all calls of this request in Langfuse
        trace_id = str(uuid.uuid4())
        
        # Validation: verify that there are messages
        if not query.messages:
            raise HTTPException(status_code=400, detail="Message list cannot be empty")
        
        # Validation: verify that there is at least one user message
        user_messages = [m for m in query.messages if m.role == "user"]
        if not user_messages:
            raise HTTPException(status_code=400, detail="There must be at least one message with role='user'")
        
        # Get or create session (state persistence)
        session_state = session_manager.get_session(query.session_id, query.user_id)
        
        # extract last user message (improved)
        user_message = user_messages[-1].content
        if not user_message or not user_message.strip():
            raise HTTPException(status_code=400, detail="Last user message cannot be empty")

        # Sync session context with query messages (client's source of truth)
        # This ensures that if the server restarts, the history sent by the frontend is maintained
        if query.messages:
            # Replace context with what the frontend sends (limited to last 20)
            session_state.context_window = query.messages[-20:]
        else:
            # If no messages in query but the user message is new, add it
            last_user_msg_in_state = None
            if session_state.context_window:
                for msg in reversed(session_state.context_window):
                    if msg.role == "user":
                        last_user_msg_in_state = msg.content
                        break
            
            if last_user_msg_in_state != user_message:
                session_state.add_message("user", user_message)
        
        # Update user_id if provided
        if query.user_id:
            session_state.user_id = query.user_id

        # Convert AgentState messages to LangChain messages for the graph
        # Filter only user and assistant messages (exclude system for the graph)
        graph_messages = []
        for msg in session_state.context_window:
            if msg.role == "user":
                graph_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                graph_messages.append(AIMessage(content=msg.content))
            # Ignore "system" messages for the graph

        # Create initial graph state (include report_id and selected_text if chat is about a report)
        # We pass trace_id in the state (requires updating GraphState definition)
        initial_state = GraphState(
            messages=graph_messages,
            report_id=query.report_id if getattr(query, "report_id", None) else None,
            selected_text=query.selected_text if getattr(query, "selected_text", None) else None,
            session_id=query.session_id,
            # trace_id will be passed dynamically if GraphState supports it, or hacked into session_id
        )
        # We inject trace_id into the state object dynamically if the class doesn't have it defined yet
        initial_state["trace_id"] = trace_id
        initial_state["user_id"] = query.user_id


        # Execute the full graph asynchronously
        # OPTIMIZATION: Use ainvoke() instead of invoke() for async processing
        try:
            final_state = await graph.ainvoke(initial_state)
        except Exception as e:
            logging.error(f"[API] Error executing graph for session {query.session_id}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error executing agent: {str(e)}"
            )

        # Get final output from the graph
        # New flow: Supervisor → Synthesizer → END
        # final_output is the definitive response generated by the Synthesizer (last node)
        final_output = final_state.get('final_output')
        assistant_response = final_output or "Could not generate a response."
        
        # Build response only with new messages
        new_messages = [
            Message(role="assistant", content=assistant_response)
        ]
        
        # Extract decision info from final state
        executed_tools = final_state.get('executed_tools', [])
        executed_steps = final_state.get('executed_steps', [])
        thought_chain = final_state.get('thought_chain', [])
        
        # Build decision based on what was executed
        decision = {
            "tool": executed_tools[0] if executed_tools else "none",
            "plan_steps": executed_steps,
            "executed_tools": executed_tools,
        }
        
        # ADD CONVERSATION MEMORY: Include agent response in session context
        if assistant_response:
            session_state.add_message("assistant", assistant_response)
        
        # Persist updated session state (with agent response added)
        session_manager.update_session(query.session_id, session_state)

        # Determine whether to include thought_chain (use query config or settings)
        include_thought_chain = query.include_thought_chain if query.include_thought_chain is not None else settings.show_thought_chain
        
        # Build structured response with improved observability info
        response = {
            "session_id": query.session_id,
            "new_messages": new_messages,
            "decision": decision,
            "session_context_length": len(session_state.context_window),
            # Observability info for debugging and transparency
            "executed_steps": executed_steps,  # Executed steps
            "executed_tools": executed_tools,  # Used tools
            # Additional quality and process info
            "quality_score": final_state.get('quality_score'),
            "supervisor_used_fallback": final_state.get('supervised_output') is not None,
        }
        
        # Include thought_chain only if enabled
        if include_thought_chain:
            response["thought_chain"] = thought_chain
        
        return response
    except HTTPException:
        # Re-throw HTTP exceptions without modification
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Validation error: {str(e)}"
        )
    except KeyError as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error in agent response structure: {str(e)}"
        )
    except Exception as e:
        # Log full error for debugging
        logging.error(f"Internal error in agent_query: {str(e)}", exc_info=True)
        
        # Build error detail with additional info in debug mode
        error_detail = f"Internal server error: {str(e)}"
        if settings.debug:
            import traceback
            error_detail = f"Internal server error: {str(e)}\n\nType: {type(e).__name__}\n\nTraceback:\n{traceback.format_exc()}"
        
        raise HTTPException(
            status_code=500, 
            detail=error_detail
        )
