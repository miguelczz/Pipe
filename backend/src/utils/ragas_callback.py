"""
Callback handler para LangGraph que captura datos para evaluación con RAGAS.
Se limita a orquestar la captura sin responsabilidades de logging.
"""
from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.agents import AgentAction, AgentFinish

from .ragas_evaluator import get_evaluator


class RAGASCallbackHandler(BaseCallbackHandler):
    """
    Callback handler que captura datos durante la ejecución del agente
    para evaluación posterior con RAGAS.
    
    Captura:
        pass
    - Preguntas del usuario
    - Respuestas generadas
    - Contextos utilizados (de RAG)
    - Metadatos de ejecución (herramientas usadas, tiempos, etc.)
    """
    
    def __init__(self, enabled: bool = True):
        """
        Inicializa el callback handler.
        
        Args:
            enabled: Si está deshabilitado, no captura datos
        """
        super().__init__()
        self.enabled = enabled
        self.evaluator = get_evaluator(enabled=enabled) if enabled else None
        
        # Datos temporales para la ejecución actual
        self.current_question: Optional[str] = None
        self.current_contexts: List[str] = []
        self.current_tool: Optional[str] = None
        self.current_answer: Optional[str] = None
        self.execution_metadata: Dict[str, Any] = {}
        
    def on_chain_start(
        self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any
    ) -> None:
        """Se llama cuando comienza la ejecución de una cadena"""
        if not self.enabled or not self.evaluator:
            return
        
        # Capturar pregunta del usuario si está en los inputs
        if "messages" in inputs:
            messages = inputs["messages"]
            if messages:
                last_message = messages[-1]
                if hasattr(last_message, "content"):
                    self.current_question = last_message.content
    
    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        """Se llama cuando comienza la ejecución de una herramienta"""
        if not self.enabled or not self.evaluator:
            return
        
        # Detectar qué herramienta se está ejecutando
        tool_name = serialized.get("name", "")
        self.current_tool = tool_name
    
    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Se llama cuando termina la ejecución de una herramienta"""
        if not self.enabled or not self.evaluator:
            return
        
        # Si es RAG, capturar contextos
        if self.current_tool and "rag" in self.current_tool.lower():
            # Intentar extraer contextos del output si es un dict
            if isinstance(output, dict):
                # El RAG tool retorna {"answer": ..., "hits": número}
                # Los contextos no están directamente en el output, pero podemos
                # intentar extraerlos de otras formas
                if "contexts" in output:
                    # Si el output tiene contextos explícitos
                    contexts = output.get("contexts", [])
                    if isinstance(contexts, list):
                        self.current_contexts.extend(contexts)
                elif "context" in output:
                    # Si hay un contexto único
                    self.current_contexts.append(output["context"])
                elif "hits" in output and isinstance(output["hits"], list):
                    # Si hits es una lista de chunks
                    for hit in output["hits"]:
                        if isinstance(hit, dict):
                            if "payload" in hit and "text" in hit["payload"]:
                                self.current_contexts.append(hit["payload"]["text"])
                            elif "content" in hit:
                                self.current_contexts.append(hit["content"])
                        elif isinstance(hit, str):
                            self.current_contexts.append(hit)
            elif isinstance(output, str):
                # Si el output es un string, podría contener contexto
                # (depende de cómo se formatee la respuesta)
                pass
    
    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        """Se llama cuando termina la ejecución de una cadena"""
        if not self.enabled or not self.evaluator:
            return
        
        # Capturar respuesta final
        # Nuevo flujo: Supervisor → Sintetizador → END
        # final_output es la respuesta definitiva (del Sintetizador, último nodo)
        if "final_output" in outputs:
            self.current_answer = outputs["final_output"]
        elif "answer" in outputs:
            self.current_answer = outputs["answer"]
        
        # Intentar capturar contextos desde los resultados del estado
        # Los resultados pueden contener contextos del RAG tool
        if "results" in outputs:
            results = outputs.get("results", [])
            for result in results:
                if isinstance(result, dict):
                    # Si el resultado tiene contextos (del RAG tool)
                    if "contexts" in result and isinstance(result["contexts"], list):
                        self.current_contexts.extend(result["contexts"])
                    # También buscar en otros campos posibles
                    elif "hits" in result and isinstance(result["hits"], list):
                        # Si hits es una lista de chunks
                        for hit in result["hits"]:
                            if isinstance(hit, dict):
                                if "payload" in hit and "text" in hit["payload"]:
                                    self.current_contexts.append(hit["payload"]["text"])
                                elif "content" in hit:
                                    self.current_contexts.append(hit["content"])
        
        # Si tenemos pregunta y respuesta, capturar para evaluación
        if self.current_question and self.current_answer:
            contexts_list = self.current_contexts.copy() if self.current_contexts else []
            
            self.evaluator.capture_evaluation(
                question=self.current_question,
                answer=self.current_answer,
                contexts=contexts_list,
                metadata={
                    "tool_used": self.current_tool,
                    **self.execution_metadata
                }
            )
            
            # Calcular métricas automáticamente si hay suficientes datos
            # (solo si hay contextos, ya que las métricas RAGAS los requieren)
            if contexts_list:
                try:
                    total_captured = len(self.evaluator.evaluation_data)
                    
                    # Evaluar todos los casos capturados hasta ahora
                    # Ragas puede evaluar con un solo caso, aunque es mejor con múltiples
                    if total_captured >= 1:
                        metrics = self.evaluator.evaluate_captured_data()
                        if metrics:
                            for metric_name, value in metrics.items():
                                # Formatear el valor con 4 decimales y agregar emoji según el valor
                                emoji = "✅" if value >= 0.7 else "⚠️" if value >= 0.5 else "❌"
                            
                            # Calcular promedio general
                            avg_score = sum(metrics.values()) / len(metrics) if metrics else 0.0
                except Exception as e:
                    pass
            
            # Limpiar datos temporales
            self.current_question = None
            self.current_contexts.clear()
            self.current_tool = None
            self.current_answer = None
            self.execution_metadata.clear()
    
    def on_chain_error(
        self, error: Exception | KeyboardInterrupt, **kwargs: Any
    ) -> None:
        """Se llama cuando hay un error en la ejecución de una cadena"""
        if not self.enabled:
            return
        
        # Limpiar datos temporales en caso de error
        self.current_question = None
        self.current_contexts.clear()
        self.current_tool = None
        self.current_answer = None
        self.execution_metadata.clear()
    
    def reset(self):
        """Reinicia el estado del callback"""
        self.current_question = None
        self.current_contexts.clear()
        self.current_tool = None
        self.current_answer = None
        self.execution_metadata.clear()


def get_ragas_callback(enabled: bool = True) -> Optional[RAGASCallbackHandler]:
    """
    Obtiene una instancia del callback handler para Ragas.
    
    Args:
        enabled: Si debe estar habilitado
    
    Returns:
        Instancia del callback handler o None si está deshabilitado
    """
    if not enabled:
        return None
    return RAGASCallbackHandler(enabled=enabled)

