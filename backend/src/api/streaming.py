"""
Módulo para streaming de respuestas usando Server-Sent Events (SSE)
"""
import json
import logging
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
logger = logging.getLogger(__name__)


async def stream_graph_execution(
    initial_state: GraphState,
    session_id: str
) -> AsyncIterator[str]:
    """
    Ejecuta el grafo y stream los resultados usando SSE (Streaming REAL).
    
    Args:
        initial_state: Estado inicial del grafo
        session_id: ID de sesión para logging
    
    Yields:
        Chunks de datos en formato SSE
    """
    import asyncio
    
    # Cola para comunicar eventos desde el grafo (thread/task de fondo) hacia el generador SSE
    event_queue = asyncio.Queue()
    
    # Callback para streaming de tokens desde el LLM
    def stream_callback(token):
        if token:
            event_queue.put_nowait({
                "type": "token",
                "content": token
            })
    
    # Función wrapper para ejecutar el grafo en background
    async def run_graph():
        try:
            # Configurar callback para que los nodos (Synthesizer/Supervisor) puedan usarlo
            config = {
                "configurable": {
                    "stream_callback": stream_callback
                }
            }
            
            # Ejecutar el grafo (esto puede tomar tiempo)
            # Usamos ainvoke con config para pasar el callback
            final_state = await graph.ainvoke(initial_state, config=config)
            
            # Al terminar, enviar el estado final
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
            # Señal de finalización
            event_queue.put_nowait({"type": "done"})

    # Iniciar la tarea en background
    graph_task = asyncio.create_task(run_graph())
    
    try:
        while True:
            # Esperar el siguiente evento de la cola
            # Usamos wait_for para detectar si la tarea murió silenciosamente (timeout opcional)
            event = await event_queue.get()
            
            event_type = event.get("type")
            
            if event_type == "token":
                # Enviar token inmediatamente
                token_data = {
                    "type": "token",
                    "data": {
                        "content": event.get("content")
                    }
                }
                yield f"data: {json.dumps(token_data)}\n\n"
                
            elif event_type == "node_update":
                # (Opcional) Si implementamos callbacks de nodos en el futuro
                pass
                
            elif event_type == "final_state":
                # Procesar estado final
                final_state = event.get("state")
                if final_state:
                    supervised_output = final_state.get('supervised_output')
                    final_output = final_state.get('final_output')
                    assistant_response = supervised_output or final_output or "No se pudo generar una respuesta."
                    
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
                # Salir del loop en caso de error
                break
                
            elif event_type == "done":
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                break
            
            event_queue.task_done()
            
    except Exception as e:
        # Intentar cancelar la tarea de fondo
        graph_task.cancel()
        yield f"data: {json.dumps({'type': 'error', 'data': {'message': str(e)}})}\n\n"


@router.post("/query/stream")
async def agent_query_stream(
    query: AgentQuery,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """
    Endpoint para consultas con streaming de respuestas usando Server-Sent Events.
    
    La respuesta se envía en tiempo real a medida que el agente procesa la consulta.
    CORREGIDO: Guarda el contexto de ventana después del streaming.
    """
    try:
        # Validación: verificar que haya mensajes
        if not query.messages:
            raise HTTPException(status_code=400, detail="La lista de mensajes no puede estar vacía")
        
        # Validación: verificar que haya al menos un mensaje del usuario
        user_messages = [m for m in query.messages if m.role == "user"]
        if not user_messages:
            raise HTTPException(status_code=400, detail="Debe haber al menos un mensaje con role='user'")
        
        # Obtener o crear sesión (persistencia de estado)
        session_state = session_manager.get_session(query.session_id, query.user_id)
        
        # Extraer último mensaje del usuario
        user_message = user_messages[-1].content
        if not user_message or not user_message.strip():
            raise HTTPException(status_code=400, detail="El último mensaje del usuario no puede estar vacío")

        # Agregar el nuevo mensaje del usuario al contexto de la sesión
        last_user_msg_in_state = None
        if session_state.context_window:
            for msg in reversed(session_state.context_window):
                if msg.role == "user":
                    last_user_msg_in_state = msg.content
                    break
        
        # Solo agregar si es un mensaje nuevo
        if last_user_msg_in_state != user_message:
            session_state.add_message("user", user_message)
            # Persistir mensaje del usuario inmediatamente
            session_manager.update_session(query.session_id, session_state)
        
        # Actualizar user_id si se proporciona
        if query.user_id:
            session_state.user_id = query.user_id

        # Convertir mensajes de AgentState a mensajes de LangChain para el grafo
        graph_messages = []
        for msg in session_state.context_window:
            if msg.role == "user":
                graph_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                graph_messages.append(AIMessage(content=msg.content))

        # Crear estado inicial del grafo
        initial_state = GraphState(
            messages=graph_messages
        )

        # Wrapper para capturar la respuesta final y guardarla en el contexto
        async def stream_with_context_save():
            """Wrapper que captura la respuesta final y la guarda en el contexto"""
            assistant_response = None
            
            async for chunk in stream_graph_execution(initial_state, query.session_id):
                # Capturar la respuesta final del streaming
                if '"type": "final_response"' in chunk:
                    try:
                        # Extraer el contenido de la respuesta final
                        import json
                        data_str = chunk.replace("data: ", "").strip()
                        data = json.loads(data_str)
                        if data.get("type") == "final_response":
                            assistant_response = data.get("data", {}).get("content")
                    except:
                        pass
                
                # Enviar el chunk al cliente
                yield chunk
            
            # Guardar la respuesta del asistente en el contexto de ventana y PERSISTIR EN REDIS
            if assistant_response:
                session_state.add_message("assistant", assistant_response)
                # IMPORTANTE: Persistir el cambio en Redis/Base de datos
                session_manager.update_session(query.session_id, session_state)

        # Crear respuesta de streaming
        return StreamingResponse(
            stream_with_context_save(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Deshabilitar buffering en nginx
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )


