"""
Module for response streaming using Server-Sent Events (SSE).
Limited to exposing the agent graph flow via SSE.
"""
import json
from typing import AsyncIterator, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage
from ..models.schemas import Message, AgentQuery
from ..core.state_manager import SessionManager, get_session_manager
from ..core.graph_state import GraphState
from ..agent.agent_graph import graph
from ..settings import settings

router = APIRouter(prefix="/agent", tags=["agent"])


async def stream_graph_execution(
    initial_state: GraphState,
    session_id: str
) -> AsyncIterator[str]:
    """
    Executes the graph and streams results using SSE (REAL Streaming).
    
    Args:
        initial_state: Initial graph state
        session_id: Session ID for logging
    
    Yields:
        Data chunks in SSE format
    """
    import asyncio
    
    # Queue to communicate events from the graph (background thread/task) to the SSE generator
    event_queue = asyncio.Queue()
    
    # Callback for token streaming from the LLM
    def stream_callback(token):
        if token:
            event_queue.put_nowait({
                "type": "token",
                "content": token
            })
    
    # Wrapper function to execute the graph in background
    async def run_graph():
        try:
            # Configure callback so nodes (Synthesizer/Supervisor) can use it
            config = {
                "configurable": {
                    "stream_callback": stream_callback
                }
            }
            
            # Execute the graph (this may take time)
            # Use ainvoke with config to pass the callback
            final_state = await graph.ainvoke(initial_state, config=config)
            
            # Upon completion, send the final state
            event_queue.put_nowait({
                "type": "final_state",
                "state": final_state
            })
            
        except Exception as e:
            event_queue.put_nowait({
                "type": "error",
                "error": str(e),
                "error_type": type(e).__name__
            })
        finally:
            # Completion signal
            event_queue.put_nowait({"type": "done"})

    # Start task in background
    graph_task = asyncio.create_task(run_graph())
    
    try:
        while True:
            # Wait for next event from queue
            # Use wait_for to detect if task died silently (optional timeout)
            event = await event_queue.get()
            
            event_type = event.get("type")
            
            if event_type == "token":
                # Send token immediately
                token_data = {
                    "type": "token",
                    "data": {
                        "content": event.get("content")
                    }
                }
                yield f"data: {json.dumps(token_data)}\n\n"
                
            elif event_type == "node_update":
                # (Optional) If we implement node callbacks in the future
                pass
                
            elif event_type == "final_state":
                # Process final state
                final_state = event.get("state")
                if final_state:
                    # New flow: Supervisor → Synthesizer → END
                    # final_output is the definitive response from the Synthesizer (last node)
                    final_output = final_state.get('final_output')
                    assistant_response = final_output or "Could not generate a response."
                    
                    response_data = {
                        "type": "final_response",
                        "data": {
                            "content": assistant_response,
                            "executed_tools": final_state.get('executed_tools', []),
                            "executed_steps": final_state.get('executed_steps', []),
                            "thought_chain": final_state.get('thought_chain', []) if settings.show_thought_chain else None,
                        }
                    }
                    yield f"data: {json.dumps(response_data)}\n\n"
            
            elif event_type == "error":
                error_data = {
                    "type": "error",
                    "data": {
                        "message": event.get("error"),
                        "type": event.get("error_type"),
                    }
                }
                if settings.debug:
                    import traceback
                    error_data["data"]["traceback"] = traceback.format_exc()
                yield f"data: {json.dumps(error_data)}\n\n"
                # Exit loop on error
                break
                
            elif event_type == "done":
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                break
            
            event_queue.task_done()
            
    except Exception as e:
        # Try to cancel background task
        graph_task.cancel()
        yield f"data: {json.dumps({'type': 'error', 'data': {'message': str(e)}})}\n\n"


@router.post("/query/stream")
async def agent_query_stream(
    query: AgentQuery,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """
    Endpoint for queries with response streaming using Server-Sent Events.
    
    The response is sent in real-time as the agent processes the query.
    CORRECTED: Saves window context after streaming.
    """
    try:
        # Validation: verify that there are messages
        if not query.messages:
            raise HTTPException(status_code=400, detail="Message list cannot be empty")
        
        # Validation: verify that there is at least one user message
        user_messages = [m for m in query.messages if m.role == "user"]
        if not user_messages:
            raise HTTPException(status_code=400, detail="There must be at least one message with role='user'")
        
        # Get or create session (state persistence)
        session_state = session_manager.get_session(query.session_id, query.user_id)
        
        # Extract last user message
        user_message = user_messages[-1].content
        if not user_message or not user_message.strip():
            raise HTTPException(status_code=400, detail="Last user message cannot be empty")

        # Add new user message to session context
        last_user_msg_in_state = None
        if session_state.context_window:
            for msg in reversed(session_state.context_window):
                if msg.role == "user":
                    last_user_msg_in_state = msg.content
                    break
        
        # Only add if it's a new message
        if last_user_msg_in_state != user_message:
            session_state.add_message("user", user_message)
            # Persist user message immediately
            session_manager.update_session(query.session_id, session_state)
        
        # Update user_id if provided
        if query.user_id:
            session_state.user_id = query.user_id

        # Convert AgentState messages to LangChain messages for the graph
        graph_messages = []
        for msg in session_state.context_window:
            if msg.role == "user":
                graph_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                graph_messages.append(AIMessage(content=msg.content))

        # Create initial graph state (include report_id and selected_text if chat is about a report)
        initial_state = GraphState(
            messages=graph_messages,
            report_id=query.report_id if getattr(query, "report_id", None) else None,
            selected_text=query.selected_text if getattr(query, "selected_text", None) else None
        )

        # Wrapper to capture final response and save it to context
        async def stream_with_context_save():
            """Wrapper that captures the final response and saves it to the context"""
            assistant_response = None
            
            async for chunk in stream_graph_execution(initial_state, query.session_id):
                # Capture final response from streaming
                if '"type": "final_response"' in chunk:
                    try:
                        # Extract final response content
                        import json
                        data_str = chunk.replace("data: ", "").strip()
                        data = json.loads(data_str)
                        if data.get("type") == "final_response":
                            assistant_response = data.get("data", {}).get("content")
                    except Exception:
                        pass
                
                # Send chunk to client
                yield chunk
            
            # Save assistant response in window context and PERSIST IN REDIS
            if assistant_response:
                session_state.add_message("assistant", assistant_response)
                # IMPORTANT: Persist change in Redis/Database
                session_manager.update_session(query.session_id, session_state)

        # Create streaming response
        return StreamingResponse(
            stream_with_context_save(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable buffering in nginx
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


