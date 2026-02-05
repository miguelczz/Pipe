"""
Evaluador RAGAS para medir la calidad de las respuestas del agente.
Captura datos durante la ejecución y calcula métricas de evaluación,
sin acoplarse a ningún mecanismo de logging específico.
"""
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

# Import opcional de ragas - si no está disponible, el evaluador funcionará en modo degradado
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
        # Fallback: intentar importar desde langchain.llms o langchain.chat_models
        try:
            from langchain.chat_models import ChatOpenAI
            LANGCHAIN_OPENAI_AVAILABLE = True
        except ImportError:
            LANGCHAIN_OPENAI_AVAILABLE = False
            ChatOpenAI = None
    # Intentar importar LangchainLLMWrapper de RAGAS para envolver el LLM
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
    """Estructura de datos para una evaluación individual"""
    question: str
    answer: str
    contexts: List[str] = field(default_factory=list)
    ground_truth: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class RAGASEvaluator:
    """
    Evaluador que captura datos durante la ejecución del agente
    y calcula métricas RAGAS para evaluar la calidad de las respuestas.
    """
    
    def __init__(self, enabled: bool = True):
        """
        Inicializa el evaluador.
        
        Args:
            enabled: Si está deshabilitado, no captura datos ni calcula métricas
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
        Captura datos de una evaluación individual.
        
        Args:
            question: Pregunta del usuario
            answer: Respuesta generada por el agente
            contexts: Contextos utilizados para generar la respuesta
            ground_truth: Respuesta esperada (opcional, para evaluación)
            metadata: Metadatos adicionales (herramienta usada, tiempo, etc.)
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
        
        # OPTIMIZACIÓN: Limitar el tamaño de evaluation_data para evitar problemas de memoria
        MAX_EVALUATION_DATA = 50  # Mantener solo las últimas 50 evaluaciones
        if len(self.evaluation_data) > MAX_EVALUATION_DATA:
            # Eliminar las evaluaciones más antiguas
            self.evaluation_data = self.evaluation_data[-MAX_EVALUATION_DATA:]
    
    def evaluate_batch(
        self,
        questions: List[str],
        answers: List[str],
        contexts: List[List[str]],
        ground_truths: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Evalúa un lote de preguntas y respuestas usando métricas RAGAS.
        
        Args:
            questions: Lista de preguntas
            answers: Lista de respuestas generadas
            contexts: Lista de listas de contextos usados para cada respuesta
            ground_truths: Lista opcional de respuestas esperadas
        
        Returns:
            Diccionario con las métricas calculadas
        """
        if not self.enabled or not RAGAS_AVAILABLE:
            return {}
        
        if len(questions) != len(answers) or len(questions) != len(contexts):
            raise ValueError("Las listas de questions, answers y contexts deben tener la misma longitud")
        
        try:
            # Configurar API key de OpenAI para RAGAS
            # RAGAS internamente crea un cliente OpenAI, así que necesitamos
            # asegurarnos de que la variable de entorno esté configurada
            from ..settings import settings
            
            # Guardar el valor actual si existe
            original_api_key = os.environ.get("OPENAI_API_KEY")
            
            # Configurar la API key desde settings
            if settings.openai_api_key:
                os.environ["OPENAI_API_KEY"] = settings.openai_api_key
            
            # Preparar dataset para Ragas
            data_dict = {
                "question": questions,
                "answer": answers,
                "contexts": contexts
            }
            
            # Agregar ground_truth si está disponible
            if ground_truths:
                if len(ground_truths) != len(questions):
                    raise ValueError("ground_truths debe tener la misma longitud que questions")
                data_dict["ground_truth"] = ground_truths
            
            dataset = Dataset.from_dict(data_dict)
            
            # Configurar LLM de LangChain para RAGAS en lugar de InstructorLLM por defecto
            # Esto resuelve el problema de compatibilidad con agenerate_prompt
            ragas_llm = None
            if RAGAS_AVAILABLE and LANGCHAIN_OPENAI_AVAILABLE and ChatOpenAI is not None:
                try:
                    from ..settings import settings
                    # Crear el LLM de LangChain
                    langchain_llm = ChatOpenAI(
                        model=settings.llm_model,
                        api_key=settings.openai_api_key,
                        temperature=0
                    )
                    # Envolver el LLM con LangchainLLMWrapper si está disponible
                    if RAGAS_LLM_WRAPPER_AVAILABLE and LangchainLLMWrapper is not None:
                        ragas_llm = LangchainLLMWrapper(langchain_llm)
                    else:
                        # Si no hay wrapper, usar el LLM directamente (puede funcionar en algunas versiones)
                        ragas_llm = langchain_llm
                except Exception as llm_error:
                    ragas_llm = None
            
            # Definir métricas a calcular
            # Las métricas de RAGAS son objetos/clases, no funciones
            # El LLM se configura a nivel de evaluate() o mediante configuración global
            metrics = [
                faithfulness,      # Mide si la respuesta es fiel al contexto
                answer_relevancy  # Mide si la respuesta es relevante para la pregunta
            ]
            
            # Métricas que SÍ requieren ground truth (reference):
            # context_precision y context_recall requieren la columna 'reference'
            if ground_truths:
                # Agregar métricas que requieren ground truth
                metrics.append(context_precision)  # Requiere 'reference'
                metrics.append(context_recall)     # Requiere 'reference'
            
            # Calcular métricas de forma asíncrona para evitar BlockingError
            result = None
            eval_error_occurred = False
            try:
                # Configurar el LLM para RAGAS
                # En algunas versiones de RAGAS, el LLM se puede pasar a evaluate()
                # o configurar mediante variables de entorno
                evaluate_kwargs = {
                    "dataset": dataset,
                    "metrics": metrics
                }
                
                # Si tenemos un LLM configurado, intentar pasarlo a evaluate()
                # RAGAS puede aceptar el LLM de diferentes formas según la versión
                if ragas_llm:
                    # Intentar diferentes formas de pasar el LLM según la versión de RAGAS
                    # Algunas versiones aceptan 'llm', otras 'generator_llm', otras lo configuran globalmente
                    try:
                        # Método 1: Intentar pasar como 'llm'
                        evaluate_kwargs["llm"] = ragas_llm
                    except (TypeError, KeyError):
                        try:
                            # Método 2: Intentar pasar como 'generator_llm'
                            evaluate_kwargs["generator_llm"] = ragas_llm
                        except (TypeError, KeyError):
                            # Método 3: Configurar globalmente (si RAGAS lo soporta)
                            pass
                
                # Ejecutar RAGAS directamente
                # Nota: Si hay BlockingError, se puede ejecutar con --allow-blocking o BG_JOB_ISOLATED_LOOPS=true
                result = evaluate(**evaluate_kwargs)
            except Exception as eval_error:
                # Capturar errores durante la evaluación (pueden ser errores internos de RAGAS)
                error_msg = str(eval_error)
                eval_error_occurred = True
                if "agenerate_prompt" in error_msg or "InstructorLLM" in error_msg:
                    # Error de compatibilidad en RAGAS (posible problema de versión)
                    # Aunque hay error, RAGAS a veces retorna un resultado parcial
                    # Intentar continuar para ver si hay algo útil
                    pass
                else:
                    # Re-lanzar otros errores
                    raise
            
            # Si no hay resultado y hubo error, retornar vacío
            if result is None and eval_error_occurred:
                return {}
            
            # Convertir resultado a diccionario
            # RAGAS puede retornar diferentes tipos de resultados
            metrics_dict = {}
            
            try:
                # Log del tipo de resultado para debugging
                
                # Intentar acceder como diccionario/objeto Dataset
                if hasattr(result, 'to_pandas') and pd is not None:
                    # Si es un Dataset, convertir a pandas y luego a dict
                    df = result.to_pandas()
                    
                    # Columnas que NO son métricas (datos de entrada)
                    non_metric_columns = ['question', 'answer', 'contexts', 'ground_truth', 'reference']
                    # Obtener la media de cada columna de métricas (solo numéricas)
                    for col in df.columns:
                        if col not in non_metric_columns:
                            try:
                                # Intentar convertir a numérico y calcular media
                                numeric_col = pd.to_numeric(df[col], errors='coerce')
                                if not numeric_col.isna().all():  # Si hay al menos un valor numérico
                                    mean_value = numeric_col.mean()
                                    if pd.notna(mean_value):
                                        metrics_dict[col] = float(mean_value)
                            except (ValueError, TypeError) as e:
                                # Si no se puede convertir a numérico, ignorar esta columna
                                continue
                    
                    # Si no encontramos métricas, intentar buscar columnas que contengan nombres de métricas conocidas
                    if not metrics_dict:
                        known_metrics = ['faithfulness', 'answer_relevancy', 'context_precision', 'context_recall']
                        for metric_name in known_metrics:
                            # Buscar columnas que contengan el nombre de la métrica
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
                    # Intentar iterar sobre las claves
                    try:
                        # Si tiene método keys() o es un dict-like
                        if hasattr(result, 'keys'):
                            for metric_name in result.keys():
                                value = result[metric_name]
                                if isinstance(value, (int, float)):
                                    metrics_dict[metric_name] = float(value)
                                elif hasattr(value, 'mean'):
                                    metrics_dict[metric_name] = float(value.mean())
                                elif hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
                                    # Si es una lista/serie, calcular media
                                    try:
                                        if np is not None:
                                            metrics_dict[metric_name] = float(np.mean(value))
                                        else:
                                            metrics_dict[metric_name] = float(sum(value) / len(value))
                                    except Exception:
                                        metrics_dict[metric_name] = float(sum(value) / len(value)) if value else 0.0
                        else:
                            # Intentar acceder directamente a las métricas conocidas
                            for metric in metrics:
                                metric_name = getattr(metric, '__name__', str(metric))
                                if hasattr(result, metric_name):
                                    value = getattr(result, metric_name)
                                    if isinstance(value, (int, float)):
                                        metrics_dict[metric_name] = float(value)
                                    elif hasattr(value, 'mean'):
                                        metrics_dict[metric_name] = float(value.mean())
                    except Exception as e:
                        # Si todo falla, intentar convertir a dict directamente
                        if hasattr(result, '__dict__'):
                            metrics_dict = {k: float(v) if isinstance(v, (int, float)) else 0.0 
                                          for k, v in result.__dict__.items() 
                                          if isinstance(v, (int, float))}
                else:
                    # Si no es iterable ni tiene to_pandas, intentar convertir a dict directamente
                    if hasattr(result, '__dict__'):
                        metrics_dict = {k: float(v) if isinstance(v, (int, float)) else 0.0 
                                      for k, v in result.__dict__.items() 
                                      if isinstance(v, (int, float))}
            except Exception as e:
                # Si hay errores pero el resultado tiene algún valor, intentar extraerlo
                if hasattr(result, '__dict__'):
                    metrics_dict = {k: float(v) if isinstance(v, (int, float)) else 0.0 
                                  for k, v in result.__dict__.items() 
                                  if isinstance(v, (int, float))}
            
            # Guardar en historial solo si hay métricas
            if metrics_dict:
                self.metrics_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "num_cases": len(questions),
                    "metrics": metrics_dict
                })
            else:
                # No hay métricas disponibles
                pass
            
            return metrics_dict
            
        except Exception as e:
            return {}
        finally:
            # Restaurar el valor original de OPENAI_API_KEY si existía
            if original_api_key is not None:
                os.environ["OPENAI_API_KEY"] = original_api_key
            elif "OPENAI_API_KEY" in os.environ and not settings.openai_api_key:
                # Si no había valor original y settings no tiene key, eliminar la variable
                del os.environ["OPENAI_API_KEY"]
    
    def evaluate_captured_data(self) -> Dict[str, float]:
        """
        Evalúa todos los datos capturados previamente.
        
        Returns:
            Diccionario con las métricas calculadas
        """
        if not self.evaluation_data:
            return {}
        
        questions = [d.question for d in self.evaluation_data]
        answers = [d.answer for d in self.evaluation_data]
        contexts = [d.contexts for d in self.evaluation_data]
        # Solo incluir ground_truths si TODOS los datos tienen ground_truth
        # Si algunos tienen y otros no, RAGAS no puede evaluar correctamente
        ground_truths_list = [d.ground_truth for d in self.evaluation_data]
        ground_truths = ground_truths_list if all(gt is not None and gt.strip() for gt in ground_truths_list) else None
        
        if ground_truths is None and any(gt is not None for gt in ground_truths_list):
            pass
        
        return self.evaluate_batch(questions, answers, contexts, ground_truths)
    
    def clear_data(self):
        """Limpia todos los datos capturados"""
        self.evaluation_data.clear()
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Obtiene un resumen de las evaluaciones realizadas.
        
        Returns:
            Diccionario con estadísticas y métricas promedio
        """
        summary = {
            "total_evaluations": len(self.evaluation_data),
            "total_metrics_runs": len(self.metrics_history),
            "metrics_history": self.metrics_history
        }
        
        if self.metrics_history:
            # Calcular promedios de todas las métricas históricas
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


# Instancia global del evaluador (opcional, puede ser deshabilitado)
_global_evaluator: Optional[RAGASEvaluator] = None


def get_evaluator(enabled: bool = True) -> RAGASEvaluator:
    """
    Obtiene la instancia global del evaluador.
    
    Args:
        enabled: Si debe estar habilitado (solo afecta la primera creación)
    
    Returns:
        Instancia del evaluador
    """
    global _global_evaluator
    if _global_evaluator is None:
        _global_evaluator = RAGASEvaluator(enabled=enabled)
    return _global_evaluator


def reset_evaluator():
    """Reinicia el evaluador global (útil para tests)"""
    global _global_evaluator
    _global_evaluator = None

