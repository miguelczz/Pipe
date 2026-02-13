"""
Callback handler for LangGraph that captures data for evaluation with RAGAS.
Limits itself to orchestrating capture without logging responsibilities.
"""
from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.agents import AgentAction, AgentFinish

from .ragas_evaluator import get_evaluator


class RAGASCallbackHandler(BaseCallbackHandler):
    """
    Callback handler that captures data during agent execution
    for subsequent evaluation with RAGAS.
    
    Captures:
    - User questions
    - Generated answers
    - Contexts used (from RAG)
    - Execution metadata (tools used, timings, etc.)
    """
    
    def __init__(self, enabled: bool = True):
        """
        Initializes the callback handler.
        
        Args:
            enabled: If disabled, no data is captured
        """
        super().__init__()
        self.enabled = enabled
        self.evaluator = get_evaluator(enabled=enabled) if enabled else None
        
        # Temporary data for the current execution
        self.current_question: Optional[str] = None
        self.current_contexts: List[str] = []
        self.current_tool: Optional[str] = None
        self.current_answer: Optional[str] = None
        self.execution_metadata: Dict[str, Any] = {}
        
    def on_chain_start(
        self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any
    ) -> None:
        """Called when a chain execution starts"""
        if not self.enabled or not self.evaluator:
            return
        
        # Capture user question if in inputs
        if "messages" in inputs:
            messages = inputs["messages"]
            if messages:
                last_message = messages[-1]
                if hasattr(last_message, "content"):
                    self.current_question = last_message.content
    
    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        """Called when a tool execution starts"""
        if not self.enabled or not self.evaluator:
            return
        
        # Detect which tool is executing
        tool_name = serialized.get("name", "")
        self.current_tool = tool_name
    
    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Called when a tool execution ends"""
        if not self.enabled or not self.evaluator:
            return
        
        # If RAG, capture contexts
        if self.current_tool and "rag" in self.current_tool.lower():
            # Try to extract contexts from output if it's a dict
            if isinstance(output, dict):
                # The RAG tool returns {"answer": ..., "hits": count}
                # Contexts are not directly in output, but we can
                # try to extract them in other ways
                if "contexts" in output:
                    # If output has explicit contexts
                    contexts = output.get("contexts", [])
                    if isinstance(contexts, list):
                        self.current_contexts.extend(contexts)
                elif "context" in output:
                    # If there's a unique context
                    self.current_contexts.append(output["context"])
                elif "hits" in output and isinstance(output["hits"], list):
                    # If hits is a list of chunks
                    for hit in output["hits"]:
                        if isinstance(hit, dict):
                            if "payload" in hit and "text" in hit["payload"]:
                                self.current_contexts.append(hit["payload"]["text"])
                            elif "content" in hit:
                                self.current_contexts.append(hit["content"])
                        elif isinstance(hit, str):
                            self.current_contexts.append(hit)
            elif isinstance(output, str):
                # If output is a string, it could contain context
                # (depends on how the response is formatted)
                pass
    
    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        """Called when a chain execution ends"""
        if not self.enabled or not self.evaluator:
            return
        
        # Capture final answer
        # New flow: Supervisor → Synthesizer → END
        # final_output is the definitive response (from Synthesizer, last node)
        if "final_output" in outputs:
            self.current_answer = outputs["final_output"]
        elif "answer" in outputs:
            self.current_answer = outputs["answer"]
        
        # Try to capture contexts from state results
        # Results may contain contexts from the RAG tool
        if "results" in outputs:
            results = outputs.get("results", [])
            for result in results:
                if isinstance(result, dict):
                    # If result has contexts (from RAG tool)
                    if "contexts" in result and isinstance(result["contexts"], list):
                        self.current_contexts.extend(result["contexts"])
                    # Also search in other possible fields
                    elif "hits" in result and isinstance(result["hits"], list):
                        # If hits is a list of chunks
                        for hit in result["hits"]:
                            if isinstance(hit, dict):
                                if "payload" in hit and "text" in hit["payload"]:
                                    self.current_contexts.append(hit["payload"]["text"])
                                elif "content" in hit:
                                    self.current_contexts.append(hit["content"])
        
        # If we have question and answer, capture for evaluation
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
            
            # Calculate metrics automatically if enough data exists
            # (only if there are contexts, as RAGAS metrics require them)
            if contexts_list:
                try:
                    total_captured = len(self.evaluator.evaluation_data)
                    
                    # Evaluate all cases captured so far
                    # Ragas can evaluate with a single case, though it's better with multiple
                    if total_captured >= 1:
                        metrics = self.evaluator.evaluate_captured_data()
                        if metrics:
                            for metric_name, value in metrics.items():
                                # Format value with 4 decimals and add emoji based on value
                                emoji = "✅" if value >= 0.7 else "⚠️" if value >= 0.5 else "❌"
                            
                            # Calculate overall average
                            avg_score = sum(metrics.values()) / len(metrics) if metrics else 0.0
                except Exception as e:
                    pass
            
            # Clean temporary data
            self.current_question = None
            self.current_contexts.clear()
            self.current_tool = None
            self.current_answer = None
            self.execution_metadata.clear()
    
    def on_chain_error(
        self, error: Exception | KeyboardInterrupt, **kwargs: Any
    ) -> None:
        """Called when there is an error in chain execution"""
        if not self.enabled:
            return
        
        # Clean temporary data on error
        self.current_question = None
        self.current_contexts.clear()
        self.current_tool = None
        self.current_answer = None
        self.execution_metadata.clear()
    
    def reset(self):
        """Resets the callback state"""
        self.current_question = None
        self.current_contexts.clear()
        self.current_tool = None
        self.current_answer = None
        self.execution_metadata.clear()


def get_ragas_callback(enabled: bool = True) -> Optional[RAGASCallbackHandler]:
    """
    Gets an instance of the Ragas callback handler.
    
    Args:
        enabled: Whether it should be enabled
    
    Returns:
        Callback handler instance or None if disabled
    """
    if not enabled:
        return None
    return RAGASCallbackHandler(enabled=enabled)

