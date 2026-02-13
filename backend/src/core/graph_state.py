"""
Centralized state manager for the agent graph.
Implements the State pattern to share state among all nodes.
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
    Shared graph state that propagates between all nodes.
    Implements the State pattern so any node can read and update the state,
    and all other nodes observe the changes automatically.
    
    LangGraph automatically handles state propagation using channels:
    - add_messages: For messages (accumulates)
    - LastValue: For simple values (replaces)
    """
    # Conversation messages (cumulative)
    messages: Annotated[List[AnyMessage], add_messages] = []
    
    # Execution plan (list of steps)
    plan_steps: Annotated[List[str], LastValue(list)] = []
    
    # Results of executed tools
    results: Annotated[List[Any], LastValue(list)] = []
    
    # Final output from synthesizer
    final_output: Annotated[Optional[str], LastValue(str)] = None
    
    # Next component (orchestrator decision)
    next_component: Annotated[Optional[str], LastValue(str)] = None
    
    # Supervised output (validated by supervisor)
    supervised_output: Annotated[Optional[str], LastValue(str)] = None
    
    # Quality score
    quality_score: Annotated[Optional[float], LastValue(float)] = None
    
    # History of executed tools
    executed_tools: Annotated[List[str], LastValue(list)] = []
    
    # History of executed steps
    executed_steps: Annotated[List[str], LastValue(list)] = []
    
    # Thought chain (agent reasoning)
    thought_chain: Annotated[List[Dict[str, Any]], LastValue(list)] = []
    
    # Temporary fields (not persisted in final state)
    tool_name: Annotated[Optional[str], LastValue(str)] = None
    current_step: Annotated[Optional[str], LastValue(str)] = None
    
    # Rejection message (when a question is off-topic)
    rejection_message: Annotated[Optional[str], LastValue(str)] = None

    # Current report ID (when chat is in context of a report)
    report_id: Annotated[Optional[str], LastValue(str)] = None
    
    # Text selected by user in frontend (report fragment)
    selected_text: Annotated[Optional[str], LastValue(str)] = None
    
    # Session ID for observability
    session_id: Annotated[Optional[str], LastValue(str)] = None

    # Trace ID for distributed observability (Langfuse)
    trace_id: Annotated[Optional[str], LastValue(str)] = None
    
    # User ID for context
    user_id: Annotated[Optional[str], LastValue(str)] = None
    
    def get_state_snapshot(self) -> Dict[str, Any]:
        """
        Gets a snapshot of the current state.
        Useful for logging and debugging.
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
        Adds a thought step to the chain.
        This method updates thought_chain which is observable by all nodes.
        
        Args:
            node_name: Name of the node executing the action
            action: Action being performed
            details: Additional details of the action
            status: Action status ("success", "error", "info")
        
        Returns:
            Updated thought chain list
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
        
        # OPTIMIZATION: Limit thought_chain size to avoid memory issues
        MAX_THOUGHT_CHAIN = 50
        if len(current_chain) > MAX_THOUGHT_CHAIN:
            current_chain = current_chain[-MAX_THOUGHT_CHAIN:]
        
        return current_chain
    
    def cleanup_old_messages(self, max_messages: int = 30):
        """
        Cleans up old messages to avoid excessive memory accumulation.
        Keeps only the last max_messages messages.
        
        IMPORTANT: Only cleans up if there are more than double the limit to avoid frequent cleanups.
        
        Args:
            max_messages: Maximum number of messages to keep
        """
        if len(self.messages) > max_messages * 2:  # Only clean if more than double
            # Keep only the last max_messages
            self.messages = self.messages[-max_messages:]
    
    def cleanup_large_results(self, max_results: int = 10):
        """
        Cleans up old results to avoid excessive memory accumulation.
        Only cleans up if there are more than double the limit.
        
        Args:
            max_results: Maximum number of results to keep
        """
        if self.results and len(self.results) > max_results * 2:  # Only clean if more than double
            # Keep only the last max_results
            self.results = self.results[-max_results:]


class StateObserver:
    """
    State observer to notify of changes.
    Implements the Observer pattern so other components can observe state changes.
    """
    
    def __init__(self):
        self._observers: List[Callable[[GraphState, Dict[str, Any]], None]] = []
    
    def subscribe(self, callback: Callable[[GraphState, Dict[str, Any]], None]):
        """
        Subscribes an observer that will be notified when the state changes.
        
        Args:
            callback: Function that receives (state, changes) when changes occur
        """
        self._observers.append(callback)
    
    def notify(self, state: GraphState, changes: Dict[str, Any]):
        """
        Notifies all observers of changes in the state.
        
        Args:
            state: Current state
            changes: Dictionary with fields that changed
        """
        for observer in self._observers:
            try:
                observer(state, changes)
            except Exception as e:
                pass


# Global observer instance (optional, for future use)
_state_observer = StateObserver()


def get_state_observer() -> StateObserver:
    """Gets the global instance of the state observer."""
    return _state_observer
