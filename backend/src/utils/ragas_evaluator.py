"""
RAGAS evaluator to measure the quality of agent responses.
Captures data during execution and calculates evaluation metrics,
without being coupled to any specific logging mechanism.
"""
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

# Optional ragas import - if not available, evaluator will work in degraded mode
try:
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall
    )
    from datasets import Dataset
    try:
        from langchain_openai import ChatOpenAI
        LANGCHAIN_OPENAI_AVAILABLE = True
    except ImportError:
        # Fallback: try to import from langchain.llms or langchain.chat_models
        try:
            from langchain.chat_models import ChatOpenAI
            LANGCHAIN_OPENAI_AVAILABLE = True
        except ImportError:
            LANGCHAIN_OPENAI_AVAILABLE = False
            ChatOpenAI = None
    # Try to import LangchainLLMWrapper from RAGAS to wrap the LLM
    try:
        from ragas.llms import LangchainLLMWrapper
        RAGAS_LLM_WRAPPER_AVAILABLE = True
    except ImportError:
        RAGAS_LLM_WRAPPER_AVAILABLE = False
        LangchainLLMWrapper = None
    import pandas as pd
    import numpy as np
    RAGAS_AVAILABLE = True
except ImportError as e:
    RAGAS_AVAILABLE = False
    pd = None
    np = None
    LANGCHAIN_OPENAI_AVAILABLE = False
    ChatOpenAI = None
    RAGAS_LLM_WRAPPER_AVAILABLE = False
    LangchainLLMWrapper = None


@dataclass
class EvaluationData:
    """Data structure for an individual evaluation"""
    question: str
    answer: str
    contexts: List[str] = field(default_factory=list)
    ground_truth: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class RAGASEvaluator:
    """
    Evaluator that captures data during agent execution
    and calculates RAGAS metrics to evaluate response quality.
    """
    
    def __init__(self, enabled: bool = True):
        """
        Initializes the evaluator.
        
        Args:
            enabled: If disabled, it doesn't capture data or calculate metrics
        """
        self.enabled = enabled and RAGAS_AVAILABLE
        self.evaluation_data: List[EvaluationData] = []
        self.metrics_history: List[Dict[str, Any]] = []
    
    def capture_evaluation(
        self,
        question: str,
        answer: str,
        contexts: Optional[List[str]] = None,
        ground_truth: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Captures data from an individual evaluation.
        
        Args:
            question: User question
            answer: Agent generated answer
            contexts: Contexts used to generate the answer
            ground_truth: Expected answer (optional, for evaluation)
            metadata: Additional metadata (tool used, time, etc.)
        """
        if not self.enabled:
            return
        
        eval_data = EvaluationData(
            question=question,
            answer=answer,
            contexts=contexts or [],
            ground_truth=ground_truth,
            metadata=metadata or {}
        )
        
        self.evaluation_data.append(eval_data)
        
        # OPTIMIZATION: Limit the size of evaluation_data to avoid memory issues
        MAX_EVALUATION_DATA = 50  # Keep only the last 50 evaluations
        if len(self.evaluation_data) > MAX_EVALUATION_DATA:
            # Remove oldest evaluations
            self.evaluation_data = self.evaluation_data[-MAX_EVALUATION_DATA:]
    
    def evaluate_batch(
        self,
        questions: List[str],
        answers: List[str],
        contexts: List[List[str]],
        ground_truths: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Evaluates a batch of questions and answers using RAGAS metrics.
        
        Args:
            questions: List of questions
            answers: List of generated answers
            contexts: List of context lists used for each response
            ground_truths: Optional list of expected answers
        
        Returns:
            Dictionary with calculated metrics
        """
        if not self.enabled or not RAGAS_AVAILABLE:
            return {}
        
        if len(questions) != len(answers) or len(questions) != len(contexts):
            raise ValueError("The lists of questions, answers and contexts must have the same length")
        
        try:
            # Configure OpenAI API key for RAGAS
            # RAGAS internally creates an OpenAI client, so we need to
            # ensure the environment variable is configured
            from ..settings import settings
            
            # Save the current value if it exists
            original_api_key = os.environ.get("OPENAI_API_KEY")
            
            # Configure the API key from settings
            if settings.openai_api_key:
                os.environ["OPENAI_API_KEY"] = settings.openai_api_key
            
            # Prepare dataset for Ragas
            data_dict = {
                "question": questions,
                "answer": answers,
                "contexts": contexts
            }
            
            # Add ground_truth if available
            if ground_truths:
                if len(ground_truths) != len(questions):
                    raise ValueError("ground_truths must have the same length as questions")
                data_dict["ground_truth"] = ground_truths
            
            dataset = Dataset.from_dict(data_dict)
            
            # Configure LangChain LLM for RAGAS instead of the default InstructorLLM
            # This resolves the compatibility issue with agenerate_prompt
            ragas_llm = None
            if RAGAS_AVAILABLE and LANGCHAIN_OPENAI_AVAILABLE and ChatOpenAI is not None:
                try:
                    from ..settings import settings
                    # Create the LangChain LLM
                    langchain_llm = ChatOpenAI(
                        model=settings.llm_model,
                        api_key=settings.openai_api_key,
                        temperature=0
                    )
                    # Wrap the LLM with LangchainLLMWrapper if available
                    if RAGAS_LLM_WRAPPER_AVAILABLE and LangchainLLMWrapper is not None:
                        ragas_llm = LangchainLLMWrapper(langchain_llm)
                    else:
                        # If no wrapper, use the LLM directly (may work in some versions)
                        ragas_llm = langchain_llm
                except Exception as llm_error:
                    ragas_llm = None
            
            # Define metrics to calculate
            # RAGAS metrics are objects/classes, not functions
            # The LLM is configured at the evaluate() level or via global configuration
            metrics = [
                faithfulness,      # Measures if the answer is faithful to the context
                answer_relevancy  # Measures if the answer is relevant to the question
            ]
            
            # Metrics that DO require ground truth (reference):
            # context_precision and context_recall require the 'reference' column
            if ground_truths:
                # Add metrics that require ground truth
                metrics.append(context_precision)  # Requires 'reference'
                metrics.append(context_recall)     # Requires 'reference'
            
            # Calculate metrics asynchronously to avoid BlockingError
            result = None
            eval_error_occurred = False
            try:
                # Configure the LLM for RAGAS
                # In some versions of RAGAS, the LLM can be passed to evaluate()
                # or configured via environment variables
                evaluate_kwargs = {
                    "dataset": dataset,
                    "metrics": metrics
                }
                
                # If we have a configured LLM, try passing it to evaluate()
                # RAGAS may accept the LLM in different ways depending on the version
                if ragas_llm:
                    # Try different ways of passing the LLM according to the RAGAS version
                    # Some versions accept 'llm', others 'generator_llm', others configure it globally
                    try:
                        # Method 1: Try passing as 'llm'
                        evaluate_kwargs["llm"] = ragas_llm
                    except (TypeError, KeyError):
                        try:
                            # Method 2: Try passing as 'generator_llm'
                            evaluate_kwargs["generator_llm"] = ragas_llm
                        except (TypeError, KeyError):
                            # Method 3: Configure globally (if RAGAS supports it)
                            pass
                
                # Execute RAGAS directly
                # Note: If there is a BlockingError, it can be executed with --allow-blocking or BG_JOB_ISOLATED_LOOPS=true
                result = evaluate(**evaluate_kwargs)
            except Exception as eval_error:
                # Capture errors during evaluation (may be internal RAGAS errors)
                error_msg = str(eval_error)
                eval_error_occurred = True
                if "agenerate_prompt" in error_msg or "InstructorLLM" in error_msg:
                    # Compatibility error in RAGAS (possible version issue)
                    # Even with error, RAGAS sometimes returns a partial result
                    # Try specifying to see if there is anything useful
                    pass
                else:
                    # Re-throw other errors
                    raise
            
            # If no result and there was an error, return empty
            if result is None and eval_error_occurred:
                return {}
            
            # Convert result to dictionary
            # RAGAS can return different result types
            metrics_dict = {}
            
            try:
                # Log the result type for debugging
                
                # Try to access as dictionary/Dataset object
                if hasattr(result, 'to_pandas') and pd is not None:
                    # If it's a Dataset, convert to pandas and then to dict
                    df = result.to_pandas()
                    
                    # Columns that are NOT metrics (input data)
                    non_metric_columns = ['question', 'answer', 'contexts', 'ground_truth', 'reference']
                    # Get the mean of each metric column (numeric only)
                    for col in df.columns:
                        if col not in non_metric_columns:
                            try:
                                # Try to convert to numeric and calculate mean
                                numeric_col = pd.to_numeric(df[col], errors='coerce')
                                if not numeric_col.isna().all():  # If there is at least one numeric value
                                    mean_value = numeric_col.mean()
                                    if pd.notna(mean_value):
                                        metrics_dict[col] = float(mean_value)
                            except (ValueError, TypeError) as e:
                                # If it cannot be converted to numeric, ignore this column
                                continue
                    
                    # If no metrics found, try searching for columns containing known metric names
                    if not metrics_dict:
                        known_metrics = ['faithfulness', 'answer_relevancy', 'context_precision', 'context_recall']
                        for metric_name in known_metrics:
                            # Search for columns containing the metric name
                            matching_cols = [col for col in df.columns if metric_name.lower() in col.lower()]
                            for col in matching_cols:
                                try:
                                    numeric_col = pd.to_numeric(df[col], errors='coerce')
                                    if not numeric_col.isna().all():
                                        mean_value = numeric_col.mean()
                                        if pd.notna(mean_value):
                                            metrics_dict[metric_name] = float(mean_value)
                                except Exception:
                                    continue
                elif hasattr(result, '__iter__') and not isinstance(result, (str, bytes)):
                    # Try to iterate over keys
                    try:
                        # If it has keys() method or is dict-like
                        if hasattr(result, 'keys'):
                            for metric_name in result.keys():
                                value = result[metric_name]
                                if isinstance(value, (int, float)):
                                    metrics_dict[metric_name] = float(value)
                                elif hasattr(value, 'mean'):
                                    metrics_dict[metric_name] = float(value.mean())
                                elif hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
                                    # If it's a list/series, calculate mean
                                    try:
                                        if np is not None:
                                            metrics_dict[metric_name] = float(np.mean(value))
                                        else:
                                            metrics_dict[metric_name] = float(sum(value) / len(value))
                                    except Exception:
                                        metrics_dict[metric_name] = float(sum(value) / len(value)) if value else 0.0
                        else:
                            # Try to access known metrics directly
                            for metric in metrics:
                                metric_name = getattr(metric, '__name__', str(metric))
                                if hasattr(result, metric_name):
                                    value = getattr(result, metric_name)
                                    if isinstance(value, (int, float)):
                                        metrics_dict[metric_name] = float(value)
                                    elif hasattr(value, 'mean'):
                                        metrics_dict[metric_name] = float(value.mean())
                    except Exception as e:
                        # If all fails, try converting to dict directly
                        if hasattr(result, '__dict__'):
                            metrics_dict = {k: float(v) if isinstance(v, (int, float)) else 0.0 
                                          for k, v in result.__dict__.items() 
                                          if isinstance(v, (int, float))}
                else:
                    # If not iterable and doesn't have to_pandas, try converting to dict directly
                    if hasattr(result, '__dict__'):
                        metrics_dict = {k: float(v) if isinstance(v, (int, float)) else 0.0 
                                      for k, v in result.__dict__.items() 
                                      if isinstance(v, (int, float))}
            except Exception as e:
                # If there are errors but the result has some value, try to extract it
                if hasattr(result, '__dict__'):
                    metrics_dict = {k: float(v) if isinstance(v, (int, float)) else 0.0 
                                  for k, v in result.__dict__.items() 
                                  if isinstance(v, (int, float))}
            
            # Save to history only if there are metrics
            if metrics_dict:
                self.metrics_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "num_cases": len(questions),
                    "metrics": metrics_dict
                })
            else:
                # No metrics available
                pass
            
            return metrics_dict
            
        except Exception as e:
            return {}
        finally:
            # Restore the original value of OPENAI_API_KEY if it existed
            if original_api_key is not None:
                os.environ["OPENAI_API_KEY"] = original_api_key
            elif "OPENAI_API_KEY" in os.environ and not settings.openai_api_key:
                # If there was no original value and settings has no key, delete the variable
                del os.environ["OPENAI_API_KEY"]
    
    def evaluate_captured_data(self) -> Dict[str, float]:
        """
        Evaluates all previously captured data.
        
        Returns:
            Dictionary with calculated metrics
        """
        if not self.evaluation_data:
            return {}
        
        questions = [d.question for d in self.evaluation_data]
        answers = [d.answer for d in self.evaluation_data]
        contexts = [d.contexts for d in self.evaluation_data]
        # Only include ground_truths if ALL data has ground_truth
        # If some have and others don't, RAGAS cannot evaluate correctly
        ground_truths_list = [d.ground_truth for d in self.evaluation_data]
        ground_truths = ground_truths_list if all(gt is not None and gt.strip() for gt in ground_truths_list) else None
        
        if ground_truths is None and any(gt is not None for gt in ground_truths_list):
            pass
        
        return self.evaluate_batch(questions, answers, contexts, ground_truths)
    
    def clear_data(self):
        """Clears all captured data"""
        self.evaluation_data.clear()
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Gets a summary of the evaluations performed.
        
        Returns:
            Dictionary with statistics and average metrics
        """
        summary = {
            "total_evaluations": len(self.evaluation_data),
            "total_metrics_runs": len(self.metrics_history),
            "metrics_history": self.metrics_history
        }
        
        if self.metrics_history:
            # Calculate averages of all historical metrics
            all_metrics = {}
            for run in self.metrics_history:
                for metric_name, value in run.get("metrics", {}).items():
                    if metric_name not in all_metrics:
                        all_metrics[metric_name] = []
                    all_metrics[metric_name].append(value)
            
            summary["average_metrics"] = {
                metric_name: sum(values) / len(values)
                for metric_name, values in all_metrics.items()
            }
        
        return summary


# Global evaluator instance (optional, can be disabled)
_global_evaluator: Optional[RAGASEvaluator] = None


def get_evaluator(enabled: bool = True) -> RAGASEvaluator:
    """
    Gets the global evaluator instance.
    
    Args:
        enabled: Whether it should be enabled (only affects first creation)
    
    Returns:
        Evaluator instance
    """
    global _global_evaluator
    if _global_evaluator is None:
        _global_evaluator = RAGASEvaluator(enabled=enabled)
    return _global_evaluator


def reset_evaluator():
    """Resets the global evaluator (useful for tests)"""
    global _global_evaluator
    _global_evaluator = None

