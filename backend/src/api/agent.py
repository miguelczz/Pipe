"""
API endpoints para el agente - Refactorizado para usar modelos centralizados.
Se limita a adaptar HTTP al grafo de orquestación del agente.
"""
import json
from fastapi import APIRouter, HTTPException, Depends, Request
from langchain_core.messages import HumanMessage, AIMessage
from ..models.schemas import Message, AgentQuery, SimpleQuery
from ..core.state_manager import SessionManager, get_session_manager
from ..core.graph_state import GraphState
from ..agent.agent_graph import graph
from ..settings import settings

router = APIRouter(prefix="/agent", tags=["agent"])

@router.get("/session/{session_id}")
async def get_session_history(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """
    Obtiene el historial de mensajes de una sesión.
    """
    try:
        session_state = session_manager.get_session(session_id, None)
        
        # Convertir mensajes a formato de respuesta
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
        logging.error(f"Error al obtener historial de sesión {session_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener historial de sesión: {str(e)}"
        )

@router.delete("/session/{session_id}")
async def clear_session(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """
    Limpia el historial de mensajes de una sesión.
    """
    try:
        session_manager.clear_session(session_id)
        return {
            "session_id": session_id,
            "message": "Sesión limpiada exitosamente"
        }
    except Exception as e:
        logging.error(f"Error al limpiar sesión {session_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al limpiar sesión: {str(e)}"
        )

@router.post("/query")
async def agent_query(
    query: AgentQuery,
    session_manager: SessionManager = Depends(get_session_manager)
):
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
        
        # extraer último mensaje del usuario (mejorado)
        user_message = user_messages[-1].content
        if not user_message or not user_message.strip():
            raise HTTPException(status_code=400, detail="El último mensaje del usuario no puede estar vacío")

        # Sincronizar contexto de la sesión con los mensajes de la query (fuente de verdad del cliente)
        # Esto asegura que si el servidor se reinicia, el historial enviado por el frontend se mantenga
        if query.messages:
            # Reemplazar el contexto con lo que envía el frontend (limitado a los últimos 20)
            session_state.context_window = query.messages[-20:]
            logging.info(f"[API] Contexto de sesión {query.session_id} sincronizado con {len(session_state.context_window)} mensajes del frontend")
        else:
            # Si no hay mensajes en la query pero el mensaje de usuario es nuevo, agregarlo
            last_user_msg_in_state = None
            if session_state.context_window:
                for msg in reversed(session_state.context_window):
                    if msg.role == "user":
                        last_user_msg_in_state = msg.content
                        break
            
            if last_user_msg_in_state != user_message:
                session_state.add_message("user", user_message)
        
        # Actualizar user_id si se proporciona
        if query.user_id:
            session_state.user_id = query.user_id

        # Convertir mensajes de AgentState a mensajes de LangChain para el grafo
        # Filtrar solo mensajes user y assistant (excluir system para el grafo)
        graph_messages = []
        for msg in session_state.context_window:
            if msg.role == "user":
                graph_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                graph_messages.append(AIMessage(content=msg.content))
            # Ignorar mensajes "system" para el grafo

        # Crear estado inicial del grafo (incluir report_id si el chat es sobre un reporte)
        initial_state = GraphState(
            messages=graph_messages,
            report_id=query.report_id if getattr(query, "report_id", None) else None
        )

        # Ejecutar el grafo completo de forma asíncrona
        # OPTIMIZACIÓN: Usar ainvoke() en lugar de invoke() para procesamiento asíncrono
        logging.info(f"[API] Iniciando ejecución del grafo para sesión {query.session_id}, mensaje: {user_message[:50]}...")
        try:
            final_state = await graph.ainvoke(initial_state)
            logging.info(f"[API] Grafo ejecutado exitosamente para sesión {query.session_id}")
        except Exception as e:
            logging.error(f"[API] Error al ejecutar el grafo para sesión {query.session_id}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error al ejecutar el agente: {str(e)}"
            )

        # Obtener la respuesta final del grafo
        supervised_output = final_state.get('supervised_output')
        final_output = final_state.get('final_output')
        
        # Usar supervised_output si está disponible, sino final_output
        assistant_response = supervised_output or final_output or "No se pudo generar una respuesta."
        
        # Construir respuesta solo con los nuevos mensajes
        new_messages = [
            Message(role="assistant", content=assistant_response)
        ]
        
        # Extraer información de decisión del estado final
        executed_tools = final_state.get('executed_tools', [])
        executed_steps = final_state.get('executed_steps', [])
        thought_chain = final_state.get('thought_chain', [])
        
        # Construir decision basado en lo que se ejecutó
        decision = {
            "tool": executed_tools[0] if executed_tools else "none",
            "plan_steps": executed_steps,
            "executed_tools": executed_tools,
        }
        
        # AGREGAR MEMORIA DE CONVERSACIÓN: Incluir la respuesta del agente en el contexto de la sesión
        if assistant_response:
            session_state.add_message("assistant", assistant_response)
        
        # Persistir el estado actualizado de la sesión (con la respuesta del agente agregada)
        session_manager.update_session(query.session_id, session_state)

        # Determinar si incluir thought_chain (usar configuración de query o settings)
        include_thought_chain = query.include_thought_chain if query.include_thought_chain is not None else settings.show_thought_chain
        
        # Construir respuesta estructurada con información de observabilidad mejorada
        response = {
            "session_id": query.session_id,
            "new_messages": new_messages,
            "decision": decision,
            "session_context_length": len(session_state.context_window),
            # Información de observabilidad para debugging y transparencia
            "executed_steps": executed_steps,  # Pasos ejecutados
            "executed_tools": executed_tools,  # Herramientas usadas
            # Información adicional de calidad y proceso
            "quality_score": final_state.get('quality_score'),
            "has_supervised_output": final_state.get('supervised_output') is not None,
        }
        
        # Incluir thought_chain solo si está habilitado
        if include_thought_chain:
            response["thought_chain"] = thought_chain
        
        return response
    except HTTPException:
        # Re-lanzar excepciones HTTP sin modificar
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Error de validación: {str(e)}"
        )
    except KeyError as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error en la estructura de respuesta del agente: {str(e)}"
        )
    except Exception as e:
        # Log del error completo para debugging
        logging.error(f"Error interno en agent_query: {str(e)}", exc_info=True)
        
        # Construir detalle de error con información adicional en modo debug
        error_detail = f"Error interno del servidor: {str(e)}"
        if settings.debug:
            import traceback
            error_detail = f"Error interno del servidor: {str(e)}\n\nTipo: {type(e).__name__}\n\nTraceback:\n{traceback.format_exc()}"
        
        raise HTTPException(
            status_code=500, 
            detail=error_detail
        )