"""
Gestor de estado centralizado para el grafo de agentes.
Implementa el patrón State para compartir estado entre todos los nodos.
"""
from typing import Dict, Any, List, Optional, Callable
from pydantic import BaseModel
from langgraph.channels import LastValue
from langgraph.graph import add_messages
from langchain_core.messages import AnyMessage
from typing import Annotated
import time


class GraphState(BaseModel):
    """
    Estado compartido del grafo que se propaga entre todos los nodos.
    Implementa el patrón State para que cualquier nodo pueda leer y actualizar el estado,
    y todos los demás nodos observen los cambios automáticamente.
    
    LangGraph maneja automáticamente la propagación del estado usando los canales:
        pass
    - add_messages: Para mensajes (acumula)
    - LastValue: Para valores simples (reemplaza)
    """
    # Mensajes de la conversación (acumulativo)
    messages: Annotated[List[AnyMessage], add_messages] = []
    
    # Plan de ejecución (lista de pasos)
    plan_steps: Annotated[List[str], LastValue(list)] = []
    
    # Resultados de las herramientas ejecutadas
    results: Annotated[List[Any], LastValue(list)] = []
    
    # Salida final del sintetizador
    final_output: Annotated[Optional[str], LastValue(str)] = None
    
    # Componente siguiente (decisión del orquestador)
    next_component: Annotated[Optional[str], LastValue(str)] = None
    
    # Salida supervisada (validada por el supervisor)
    supervised_output: Annotated[Optional[str], LastValue(str)] = None
    
    # Puntuación de calidad
    quality_score: Annotated[Optional[float], LastValue(float)] = None
    
    # Historial de herramientas ejecutadas
    executed_tools: Annotated[List[str], LastValue(list)] = []
    
    # Historial de pasos ejecutados
    executed_steps: Annotated[List[str], LastValue(list)] = []
    
    # Cadena de pensamiento (razonamiento del agente)
    thought_chain: Annotated[List[Dict[str, Any]], LastValue(list)] = []
    
    # Campos temporales (no se persisten en el estado final)
    tool_name: Annotated[Optional[str], LastValue(str)] = None
    current_step: Annotated[Optional[str], LastValue(str)] = None
    
    # Mensaje de rechazo (cuando una pregunta está fuera de tema)
    rejection_message: Annotated[Optional[str], LastValue(str)] = None

    # ID del reporte actual (cuando el chat está en contexto de un reporte)
    report_id: Annotated[Optional[str], LastValue(str)] = None
    
    # Texto seleccionado por el usuario en el frontend (fragmento del reporte)
    selected_text: Annotated[Optional[str], LastValue(str)] = None
    
    def get_state_snapshot(self) -> Dict[str, Any]:
        """
        Obtiene una instantánea del estado actual.
        Útil para logging y debugging.
        """
        return {
            "messages_count": len(self.messages),
            "plan_steps_count": len(self.plan_steps or []),
            "results_count": len(self.results or []),
            "executed_tools": self.executed_tools or [],
            "executed_steps_count": len(self.executed_steps or []),
            "has_final_output": self.final_output is not None,
            "has_supervised_output": self.supervised_output is not None,
            "quality_score": self.quality_score,
            "next_component": self.next_component,
        }
    
    def add_thought(
        self, 
        node_name: str, 
        action: str, 
        details: str = "", 
        status: str = "success"
    ) -> List[Dict[str, Any]]:
        """
        Agrega un paso de pensamiento a la cadena.
        Este método actualiza thought_chain que es observable por todos los nodos.
        
        Args:
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
        current_chain = self.thought_chain or []
        current_chain.append(thought)
        
        # OPTIMIZACIÓN: Limitar el tamaño de thought_chain para evitar problemas de memoria
        MAX_THOUGHT_CHAIN = 50
        if len(current_chain) > MAX_THOUGHT_CHAIN:
            current_chain = current_chain[-MAX_THOUGHT_CHAIN:]
        
        return current_chain
    
    def cleanup_old_messages(self, max_messages: int = 30):
        """
        Limpia mensajes antiguos para evitar acumulación excesiva de memoria.
        Mantiene solo los últimos max_messages mensajes.
        
        IMPORTANTE: Solo limpia si hay más del doble del límite para evitar limpiezas frecuentes.
        
        Args:
            max_messages: Número máximo de mensajes a mantener
        """
        if len(self.messages) > max_messages * 2:  # Solo limpiar si hay más del doble
            # Mantener solo los últimos max_messages
            self.messages = self.messages[-max_messages:]
    
    def cleanup_large_results(self, max_results: int = 10):
        """
        Limpia resultados antiguos para evitar acumulación excesiva de memoria.
        Solo limpia si hay más del doble del límite.
        
        Args:
            max_results: Número máximo de resultados a mantener
        """
        if self.results and len(self.results) > max_results * 2:  # Solo limpiar si hay más del doble
            # Mantener solo los últimos max_results
            self.results = self.results[-max_results:]


class StateObserver:
    """
    Observador del estado para notificar cambios.
    Implementa el patrón Observer para que otros componentes puedan observar cambios de estado.
    """
    
    def __init__(self):
        self._observers: List[Callable[[GraphState, Dict[str, Any]], None]] = []
    
    def subscribe(self, callback: Callable[[GraphState, Dict[str, Any]], None]):
        """
        Suscribe un observador que será notificado cuando el estado cambie.
        
        Args:
            callback: Función que recibe (state, changes) cuando hay cambios
        """
        self._observers.append(callback)
    
    def notify(self, state: GraphState, changes: Dict[str, Any]):
        """
        Notifica a todos los observadores sobre cambios en el estado.
        
        Args:
            state: Estado actual
            changes: Diccionario con los campos que cambiaron
        """
        for observer in self._observers:
            try:
                observer(state, changes)
            except Exception as e:
                pass


# Instancia global del observador (opcional, para uso futuro)
_state_observer = StateObserver()


def get_state_observer() -> StateObserver:
    """Obtiene la instancia global del observador de estado."""
    return _state_observer

