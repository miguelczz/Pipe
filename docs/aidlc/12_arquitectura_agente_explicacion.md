# 🏗️ Explicación de la Arquitectura del Sistema Agéntico

## 📋 Resumen Ejecutivo

Pipe implementa un **sistema agéntico inteligente** que utiliza **LangGraph** para orquestar múltiples herramientas especializadas (RAG, IP, DNS) y generar respuestas contextualizadas sobre análisis de Band Steering y redes WiFi.

---

## 🎯 Visión General de la Arquitectura

### Arquitectura en Capas

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (React)                      │
│  - Interfaz de usuario                                  │
│  - Chat interactivo                                     │
│  - Visualización de análisis                            │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP/REST
┌────────────────────▼────────────────────────────────────┐
│              API LAYER (FastAPI)                        │
│  - /agent/query: Endpoint principal                    │
│  - Gestión de sesiones                                  │
│  - Streaming de respuestas                             │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│         COMPONENTE AGÉNTICO (LangGraph)                 │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Planner → Orchestrator → Executor → Synthesizer │  │
│  │                    ↓                              │  │
│  │                 Supervisor                        │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              HERRAMIENTAS ESPECIALIZADAS                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │   RAG    │  │    IP    │  │   DNS    │            │
│  │  Tool    │  │   Tool   │  │   Tool   │            │
│  └──────────┘  └──────────┘  └──────────┘            │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              SERVICIOS Y REPOSITORIOS                   │
│  - Embeddings Service (Qdrant)                         │
│  - Document Repository                                 │
│  - Session Manager                                      │
└─────────────────────────────────────────────────────────┘
```

---

## 🤖 El Componente Agéntico: El Corazón del Sistema

### ¿Qué es LangGraph?

**LangGraph** es un framework de LangChain que permite construir **grafos de estado** para sistemas agénticos. En lugar de tener un flujo lineal, creamos un **grafo de nodos** que se comunican a través de un **estado compartido**.

### ¿Por qué es importante?

1. **Modularidad**: Cada nodo tiene una responsabilidad específica
2. **Flexibilidad**: El flujo se adapta según la consulta del usuario
3. **Observabilidad**: Podemos rastrear cada paso del proceso
4. **Escalabilidad**: Fácil agregar nuevos nodos o herramientas

---

## 🔄 Flujo de Ejecución del Agente

### Diagrama de Flujo Completo

```
Usuario envía pregunta
        ↓
┌───────────────────────┐
│  1. PLANNER           │  ← Analiza la pregunta y genera un plan
│  - Lee el mensaje     │
│  - Usa PipeAgent   │
│  - Genera plan_steps  │
└───────────┬───────────┘
            ↓
┌───────────────────────┐
│  2. ORCHESTRATOR      │  ← Decide qué hacer a continuación
│  - Evalúa el plan     │
│  - Decide siguiente   │
│    componente         │
└───────────┬───────────┘
            ↓
    ┌───────┴───────┐
    │              │
    ↓              ↓
┌─────────┐   ┌──────────┐
│ 3a.     │   │ 3b.      │
│ EXECUTOR│   │SYNTHESIZER│
│         │   │          │
│ Ejecuta│   │ Combina   │
│ herramienta│ resultados│
│ (RAG/IP/│   │ y genera  │
│  DNS)   │   │ respuesta │
└────┬────┘   └─────┬────┘
     │              │
     │              ↓
     │         ┌──────────┐
     │         │ 4.       │
     │         │ SUPERVISOR│
     │         │          │
     │         │ Valida y │
     │         │ mejora   │
     │         │ respuesta│
     │         └─────┬────┘
     │               │
     └───────┬───────┘
             ↓
      Respuesta final
```

### Flujo Detallado Paso a Paso

#### **Paso 1: Planner (Planificador)**

**Responsabilidad**: Entender qué quiere el usuario y crear un plan de acción.

```python
# Ejemplo de lo que hace el Planner
Usuario pregunta: "¿Qué es BTM? y haz ping a google.com"

Planner analiza:
  - "¿Qué es BTM?" → Necesita información → RAG Tool
  - "haz ping a google.com" → Operación de red → IP Tool

Plan generado:
  plan_steps = [
    "retrieve information about BTM (802.11v)",
    "ping to google.com"
  ]
```

**Componentes involucrados**:
- `PipeAgent.decide()`: Usa un LLM para analizar la intención
- Valida que la pregunta esté relacionada con redes/telecomunicaciones
- Genera pasos específicos y ejecutables

---

#### **Paso 2: Orchestrator (Orquestador)**

**Responsabilidad**: Decidir qué componente activar según el estado actual.

```python
# Lógica del Orchestrator
if hay plan_steps pendientes:
    → Ir a EXECUTOR (ejecutar herramientas)
elif hay resultados pero no hay pasos:
    → Ir a SYNTHESIZER (combinar resultados)
else:
    → Ir a SYNTHESIZER (generar respuesta)
```

**Decisiones clave**:
- ¿Hay pasos pendientes? → Ejecutor
- ¿Hay resultados listos? → Sintetizador
- ¿Pregunta fuera de tema? → Sintetizador (con mensaje de rechazo)

---

#### **Paso 3a: Executor (Ejecutor)**

**Responsabilidad**: Ejecutar las herramientas según el plan.

**Herramientas disponibles**:

1. **RAG Tool** (Retrieval Augmented Generation)
   - Busca información en documentos técnicos indexados
   - Usa embeddings y Qdrant para búsqueda semántica
   - Retorna respuestas contextualizadas

2. **IP Tool** (Operaciones de Red)
   - Ping a hosts
   - Traceroute
   - Comparación de IPs

3. **DNS Tool** (Consultas DNS)
   - Registros DNS (A, MX, TXT, NS, etc.)
   - Búsqueda inversa (PTR)
   - Verificación SPF/DMARC

```python
# Ejemplo de ejecución
plan_step = "ping to google.com"
tool_name = "ip"  # Detectado automáticamente

resultado = execute_ip_tool(plan_step, user_prompt, messages)
# Retorna: {"ip": "142.250.185.14", "latency": "15ms", ...}
```

**Características importantes**:
- Detecta automáticamente qué herramienta usar según el paso
- Mantiene contexto de conversación para seguimientos
- Maneja errores gracefully

---

#### **Paso 3b: Synthesizer (Sintetizador)**

**Responsabilidad**: Combinar resultados y generar una respuesta coherente.

**Casos de uso**:

1. **Solo RAG**: Procesa la respuesta del RAG para hacerla más natural
2. **Solo IP/DNS**: Formatea los resultados técnicos de manera clara
3. **RAG + IP/DNS**: Combina información conceptual con datos técnicos

```python
# Ejemplo: Combinar RAG + IP
resultados = [
    {"answer": "BTM es BSS Transition Management..."},  # RAG
    {"ip": "142.250.185.14", "latency": "15ms"}         # IP
]

Synthesizer:
  - Toma ambos resultados
  - Usa LLM para combinarlos naturalmente
  - Genera: "BTM es BSS Transition Management... 
            Además, el ping a google.com muestra una latencia de 15ms..."
```

**Optimizaciones**:
- Adapta la longitud según la complejidad de la pregunta
- Preserva resultados técnicos importantes
- Usa streaming para respuestas más rápidas

---

#### **Paso 4: Supervisor (Supervisor)**

**Responsabilidad**: Validar y mejorar la calidad de la respuesta final.

**Validaciones**:
1. **Calidad**: ¿Responde directamente la pregunta?
2. **Longitud**: ¿Es apropiada para la complejidad?
3. **Precisión**: ¿Hay errores obvios?
4. **Relevancia**: ¿Está dentro del tema?

```python
# Ejemplo de validación
respuesta = "BTM es un protocolo..."
pregunta = "¿Qué es BTM?"

Supervisor evalúa:
  - Calidad: 8.5/10 ✅
  - Longitud: Apropiada ✅
  - Precisión: Correcta ✅
  
Si calidad < 0.4 o muy larga:
  → Mejora la respuesta usando LLM
```

**Mejoras aplicadas**:
- Ajusta longitud según complejidad
- Corrige errores obvios
- Asegura lenguaje natural
- Preserva información técnica importante

---

## 📊 Estado Compartido (GraphState)

### ¿Qué es el Estado Compartido?

El **GraphState** es un objeto que se propaga automáticamente entre todos los nodos. Cada nodo puede **leer** y **escribir** en el estado, y los cambios son visibles para todos.

### Estructura del Estado

```python
class GraphState:
    # Mensajes de la conversación (acumulativo)
    messages: List[AnyMessage] = []
    
    # Plan de ejecución
    plan_steps: List[str] = []
    
    # Resultados de herramientas
    results: List[Any] = []
    
    # Respuesta final
    final_output: Optional[str] = None
    
    # Respuesta validada
    supervised_output: Optional[str] = None
    
    # Puntuación de calidad
    quality_score: Optional[float] = None
    
    # Historial de ejecución
    executed_tools: List[str] = []
    executed_steps: List[str] = []
    
    # Cadena de pensamiento (para observabilidad)
    thought_chain: List[Dict] = []
```

### Flujo de Datos en el Estado

```
Usuario pregunta: "¿Qué es BTM?"
        ↓
messages = [HumanMessage("¿Qué es BTM?")]
        ↓
[PLANNER] → plan_steps = ["retrieve info about BTM"]
        ↓
[ORCHESTRATOR] → next_component = "Agente_Ejecutor"
        ↓
[EXECUTOR] → results = [{"answer": "BTM es..."}]
        ↓
[SYNTHESIZER] → final_output = "BTM es BSS Transition Management..."
        ↓
[SUPERVISOR] → supervised_output = "BTM es BSS Transition Management... [mejorada]"
        ↓
Usuario recibe respuesta
```

---

## 🔧 Componentes Técnicos Clave

### 1. PipeAgent (Router)

**Ubicación**: `backend/src/agent/router.py`

**Función**: Decide qué herramienta usar según la intención del usuario.

```python
class PipeAgent:
    def decide(self, user_input: str, state: AgentState) -> dict:
        """
        Analiza la pregunta y decide:
        - ¿Es relevante? (redes/telecomunicaciones)
        - ¿Qué herramienta usar? (RAG, IP, DNS)
        - ¿Qué pasos ejecutar?
        """
        # Usa LLM para analizar intención
        decision = llm.analyze(user_input)
        
        return {
            "tool": "rag",  # o "ip", "dns"
            "plan_steps": ["retrieve info about BTM"],
            "reason": "User asking for concept explanation"
        }
```

**Características**:
- Validación de relevancia (solo redes/telecomunicaciones)
- Detección inteligente de intención
- Generación de planes específicos
- Caché de decisiones (optimización)

---

### 2. Tool Executors

**Ubicación**: `backend/src/agent/tool_executors.py`

**Función**: Ejecuta las herramientas específicas.

```python
def execute_rag_tool(step, prompt, messages):
    """Ejecuta búsqueda en documentos"""
    conversation_context = get_conversation_context(messages)
    result = rag_tool.query(prompt, conversation_context)
    return result

def execute_ip_tool(step, prompt, messages):
    """Ejecuta operaciones de red"""
    operation = detect_operation_type(step, prompt)
    if operation == "ping":
        return ip_tool.ping(host)
    elif operation == "traceroute":
        return ip_tool.tracert(host)
    # ...
```

**Características**:
- Detección automática de tipo de operación
- Manejo de contexto de conversación
- Extracción inteligente de parámetros (hosts, dominios)
- Manejo de errores robusto

---

### 3. Herramientas Especializadas

#### RAG Tool

**Función**: Búsqueda semántica en documentación técnica.

**Proceso**:
1. Genera embedding de la pregunta
2. Busca en Qdrant (base de datos vectorial)
3. Recupera chunks relevantes
4. Genera respuesta usando LLM con contexto

**Ventajas**:
- Respuestas basadas en documentación real
- Contexto técnico preciso
- Soporte para seguimientos de conversación

#### IP Tool

**Función**: Operaciones de red (ping, traceroute, comparación).

**Características**:
- Ejecuta comandos de red reales
- Formatea resultados técnicos
- Soporta comparaciones múltiples

#### DNS Tool

**Función**: Consultas DNS y verificaciones.

**Características**:
- Consulta registros DNS reales
- Verificación SPF/DMARC
- Comparación entre dominios

---

## 🎨 Patrones de Diseño Utilizados

### 1. State Pattern (Patrón de Estado)

El `GraphState` se propaga automáticamente entre nodos usando canales de LangGraph:
- `add_messages`: Acumula mensajes
- `LastValue`: Reemplaza valores simples

### 2. Strategy Pattern (Patrón de Estrategia)

Cada herramienta (RAG, IP, DNS) es una estrategia diferente que se selecciona dinámicamente según la intención del usuario.

### 3. Observer Pattern (Patrón Observador)

El `StateObserver` permite que otros componentes observen cambios en el estado (útil para logging y debugging).

### 4. Repository Pattern (Patrón Repositorio)

Separación entre acceso a datos (repositorios) y lógica de negocio (servicios).

---

## 🚀 Ventajas de esta Arquitectura

### 1. **Modularidad**
- Cada nodo tiene una responsabilidad clara
- Fácil agregar nuevos nodos o herramientas
- Código mantenible y testeable

### 2. **Flexibilidad**
- El flujo se adapta según la consulta
- Soporta múltiples herramientas simultáneamente
- Fácil extender funcionalidad

### 3. **Observabilidad**
- `thought_chain` rastrea cada paso
- Logs detallados de ejecución
- Métricas de calidad

### 4. **Escalabilidad**
- Procesamiento asíncrono
- Caché de decisiones
- Optimizaciones de rendimiento

### 5. **Robustez**
- Manejo de errores en cada nivel
- Validación de calidad
- Fallbacks automáticos

---

## 📝 Ejemplo Completo de Ejecución

### Escenario: Usuario pregunta sobre BTM y hace ping

```
1. Usuario envía:
   "¿Qué es BTM? y haz ping a google.com"

2. API recibe y crea GraphState:
   messages = [HumanMessage("¿Qué es BTM? y haz ping a google.com")]

3. PLANNER ejecuta:
   - Analiza con PipeAgent
   - Genera plan:
     plan_steps = [
       "retrieve information about BTM",
       "ping to google.com"
     ]

4. ORCHESTRATOR ejecuta:
   - Ve que hay plan_steps
   - Decide: next_component = "Agente_Ejecutor"

5. EXECUTOR ejecuta (paso 1):
   - Detecta: "retrieve information about BTM" → RAG
   - Ejecuta: execute_rag_tool()
   - Resultado: {"answer": "BTM es BSS Transition Management..."}
   - Actualiza: results = [resultado_rag]
   - Quita paso: plan_steps = ["ping to google.com"]

6. ORCHESTRATOR ejecuta (de nuevo):
   - Ve que aún hay plan_steps
   - Decide: next_component = "Agente_Ejecutor"

7. EXECUTOR ejecuta (paso 2):
   - Detecta: "ping to google.com" → IP
   - Ejecuta: execute_ip_tool()
   - Resultado: {"ip": "142.250.185.14", "latency": "15ms"}
   - Actualiza: results = [resultado_rag, resultado_ip]
   - Quita paso: plan_steps = []

8. ORCHESTRATOR ejecuta (de nuevo):
   - Ve que no hay plan_steps pero hay results
   - Decide: next_component = "Sintetizador"

9. SYNTHESIZER ejecuta:
   - Detecta: RAG + IP
   - Combina resultados con LLM
   - Genera: "BTM es BSS Transition Management... 
             Además, el ping a google.com muestra..."
   - Actualiza: final_output = respuesta_combinada

10. SUPERVISOR ejecuta:
    - Valida calidad: 9.0/10 ✅
    - Longitud apropiada ✅
    - Aproba sin cambios
    - Actualiza: supervised_output = final_output

11. API retorna respuesta al usuario
```

---

## 🔍 Puntos Clave para Entender el Sistema

### 1. **Estado Compartido es Central**
Todo el sistema gira alrededor del `GraphState`. Cada nodo lee y escribe en él, y los cambios se propagan automáticamente.

### 2. **Flujo Condicional**
El flujo no es lineal. El Orchestrator decide dinámicamente qué hacer según el estado actual.

### 3. **Herramientas Son Independientes**
Cada herramienta (RAG, IP, DNS) es un módulo separado que puede ejecutarse independientemente.

### 4. **LLM Como Coordinador**
El LLM no solo genera texto, sino que también:
- Analiza intenciones (Planner)
- Combina resultados (Synthesizer)
- Valida calidad (Supervisor)

### 5. **Contexto de Conversación**
El sistema mantiene contexto de conversación para:
- Entender referencias ("el ping anterior")
- Mejorar búsquedas RAG
- Generar respuestas coherentes

---

## 🎓 Conceptos Importantes

### LangGraph Channels

- **`add_messages`**: Acumula mensajes (no reemplaza)
- **`LastValue`**: Reemplaza el valor anterior

### Nodos vs Herramientas

- **Nodos**: Componentes del grafo (Planner, Orchestrator, etc.)
- **Herramientas**: Funcionalidades específicas (RAG, IP, DNS)

### Estado vs Sesión

- **GraphState**: Estado temporal durante ejecución del grafo
- **AgentState**: Estado persistente de la sesión del usuario

---

## 📚 Referencias

- **LangGraph Documentation**: https://langchain-ai.github.io/langgraph/
- **LangChain Documentation**: https://python.langchain.com/
- **Código fuente**: `backend/src/agent/agent_graph.py`
- **Router**: `backend/src/agent/router.py`
- **Tool Executors**: `backend/src/agent/tool_executors.py`

---

## ✅ Resumen

El componente agéntico de Pipe es un **sistema inteligente y modular** que:

1. **Analiza** la intención del usuario (Planner)
2. **Orquesta** la ejecución (Orchestrator)
3. **Ejecuta** herramientas especializadas (Executor)
4. **Combina** resultados (Synthesizer)
5. **Valida** la calidad (Supervisor)

Todo esto usando **LangGraph** para un flujo flexible y observable, con un **estado compartido** que permite comunicación entre componentes.

La arquitectura es **escalable**, **mantenible** y **robusta**, permitiendo agregar nuevas herramientas o nodos sin modificar el código existente.
