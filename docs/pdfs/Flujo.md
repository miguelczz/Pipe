# Flujo Detallado del Agente NetMind

Este documento describe en detalle el flujo completo de ejecución del agente, desde que el usuario envía una consulta hasta que recibe la respuesta final.

## 🔄 Diagrama del Flujo

```
Usuario → POST /agent/query (o /agent/query/stream para SSE)
   │
   ├─> backend/src/api/agent.py:agent_query() (o streaming.py:agent_query_stream())
   │    │
   ├─> SessionManager.get_session()
   │    └─> backend/src/core/state_manager.py
   │         └─> Retorna: AgentState (backend/src/models/schemas.py)
   │    │
   ├─> Convierte AgentState → GraphState
   │    └─> backend/src/core/graph_state.py:GraphState
   │    │
   ├─> graph.invoke(initial_state) o graph.astream_events() (para streaming)
   │    └─> backend/src/agent/agent_graph.py
   │         │
   │         ├─> Planner Node
   │         │    └─> NetMindAgent.decide()
   │         │         └─> backend/src/agent/router.py
   │         │              └─> Usa: LLMClient (backend/src/agent/llm_client.py)
   │         │                   └─> Retorna: {tool, plan_steps, reason}
   │         │
   │         ├─> Orchestrator Node
   │         │    └─> Decide siguiente componente
   │         │
   │         ├─> Executor Node (si hay plan_steps)
   │         │    ├─> determine_tool_from_step()
   │         │    │    └─> backend/src/agent/tool_executors.py
   │         │    │
   │         │    └─> execute_*_tool()
   │         │         ├─> RAG: backend/src/tools/rag_tool.py
   │         │         │    └─> Usa: embeddings_service, qdrant_repository
   │         │         │
   │         │         ├─> IP: backend/src/tools/ip_tool.py
   │         │         │    └─> Ejecuta comandos de red
   │         │         │
   │         │         └─> DNS: backend/src/tools/dns_tool.py
   │         │              └─> Consultas DNS
   │         │
   │         ├─> Synthesizer Node
   │         │    └─> Combina resultados
   │         │         └─> Usa: LLMClient.generate()
   │         │
   │         └─> Supervisor Node
   │              ├─> Valida y mejora respuesta
   │              │    └─> Usa: LLMClient.generate()
   │              └─> Captura para RAGAS: backend/src/utils/ragas_evaluator.py
   │
   └─> Retorna supervised_output (o stream en tiempo real para SSE)
        └─> backend/src/api/agent.py (o streaming.py)
             ├─> SessionManager.update_session()
             └─> Retorna respuesta al usuario (o stream de tokens)
```

---

## 📝 Flujo Paso a Paso

### 1. Usuario → POST /agent/query (o /agent/query/stream)

**Acción**: El usuario envía una petición HTTP POST al endpoint `/agent/query` o `/agent/query/stream` (para streaming)

**Endpoints disponibles**:
- `/agent/query`: Respuesta completa al finalizar
- `/agent/query/stream`: Streaming de respuesta en tiempo real (SSE)

**Datos enviados**:
```json
{
  "session_id": "session-123",
  "user_id": "user-456",
  "messages": [
    {
      "role": "user",
      "content": "¿Qué es un ping?"
    }
  ]
}
```

---

### 2. backend/src/api/agent.py:agent_query() (o streaming.py:agent_query_stream())

**Ubicación**: 
- `backend/src/api/agent.py` - Para consultas estándar
- `backend/src/api/streaming.py` - Para consultas con streaming (SSE)

**Acciones realizadas**:

1. **Validaciones**:
   - Verifica que `query.messages` no esté vacío
   - Verifica que haya al menos un mensaje con `role="user"`
   - Verifica que el último mensaje del usuario no esté vacío

2. **Obtiene o crea sesión**:
   - Llama a `session_manager.get_session(query.session_id, query.user_id)`
   - Si la sesión no existe, crea un nuevo `AgentState`

3. **Agrega mensaje del usuario**:
   - Compara con el último mensaje en el contexto de la sesión
   - Si es un mensaje nuevo, lo agrega con `session_state.add_message("user", user_message)`

4. **Convierte mensajes**:
   - Filtra solo mensajes `user` y `assistant` (ignora `system`)
   - Convierte a formato LangChain:
     - `role="user"` → `HumanMessage(content=msg.content)`
     - `role="assistant"` → `AIMessage(content=msg.content)`

5. **Crea estado inicial del grafo**:
   - Crea `GraphState(messages=graph_messages)`

**Código relevante**:
```python
# Convertir mensajes de AgentState a mensajes de LangChain
graph_messages = []
for msg in session_state.context_window:
    if msg.role == "user":
        graph_messages.append(HumanMessage(content=msg.content))
    elif msg.role == "assistant":
        graph_messages.append(AIMessage(content=msg.content))

# Crear estado inicial del grafo
initial_state = GraphState(messages=graph_messages)
```

---

### 3. SessionManager.get_session()

**Ubicación**: `backend/src/core/state_manager.py` (o `backend/src/core/redis_session_manager.py` si se usa Redis)

**Acciones realizadas**:

1. **Busca sesión existente**:
   - Busca en `self._sessions` usando `session_id` como clave

2. **Crea nueva sesión si no existe**:
   ```python
   AgentState(
       session_id=session_id,
       user_id=user_id,
       context_window=[],
       variables={},
       results={}
   )
   ```

3. **Crea lock para thread-safety**:
   - Crea un `threading.Lock` para la sesión

4. **Retorna AgentState**:
   - Retorna la sesión existente o la nueva creada

---

### 4. Convierte AgentState → GraphState

**Ubicación**: 
- `backend/src/api/agent.py` (para consultas estándar)
- `backend/src/api/streaming.py` (para streaming)
- `backend/src/core/graph_state.py` (definición de GraphState)

**Acciones realizadas**:

1. **Extrae mensajes**:
   - Toma mensajes de `session_state.context_window`

2. **Convierte formato**:
   - Convierte cada `Message` (Pydantic) a `HumanMessage`/`AIMessage` (LangChain)

3. **Crea GraphState**:
   - `GraphState` incluye:
     - `messages`: Lista de mensajes (acumulativo)
     - `plan_steps`: Lista de pasos del plan
     - `results`: Resultados de herramientas
     - `final_output`: Respuesta final
     - `supervised_output`: Respuesta validada
     - `thought_chain`: Cadena de pensamiento

**Estructura GraphState**:
```python
class GraphState(BaseModel):
    messages: Annotated[List[AnyMessage], add_messages] = []
    plan_steps: Annotated[List[str], LastValue(list)] = []
    results: Annotated[List[Any], LastValue(list)] = []
    final_output: Annotated[Optional[str], LastValue(str)] = None
    supervised_output: Annotated[Optional[str], LastValue(str)] = None
    quality_score: Annotated[Optional[float], LastValue(float)] = None
    # ... más campos
```

---

### 5. graph.invoke(initial_state) o graph.astream_events()

**Ubicación**: `backend/src/agent/agent_graph.py`

**Acción**: 
- **Consulta estándar**: Ejecuta el grafo con `graph.invoke()` o `graph.ainvoke()`
- **Streaming**: Ejecuta el grafo con `graph.astream_events()` para capturar tokens en tiempo real

**Flujo del grafo**:
```
START → Planner → Orchestrator → [Executor/Synthesizer] → Supervisor → END
```

El grafo se ejecuta secuencialmente, pasando el estado entre nodos. En modo streaming, los tokens del LLM se capturan mientras se generan.

---

### 6. Planner Node

**Función**: `planner_node(state: GraphState)`

**Ubicación**: `backend/src/agent/agent_graph.py` (líneas 170-233)

**Acciones realizadas**:

1. **Extrae prompt del usuario**:
   - Busca el último `HumanMessage` en `state.messages`
   - Función: `get_user_prompt_from_messages(state.messages)`

2. **Convierte mensajes a AgentState**:
   - Usa `messages_to_agent_state()` para obtener contexto
   - Toma los últimos 10 mensajes para contexto

3. **Llama a NetMindAgent.decide()**:
   - Crea instancia de `NetMindAgent`
   - Llama a `router.decide(user_prompt, context)`

4. **Procesa decisión**:
   - Si hay `rejection_message` → retorna plan vacío y mensaje de rechazo
   - Si no hay rechazo → extrae `plan_steps` de la decisión

5. **Registra pensamiento**:
   - Agrega entrada a `thought_chain` con el plan generado

6. **Retorna**:
   ```python
   {
       "plan_steps": plan_steps,
       "thought_chain": thought_chain
   }
   ```

---

### 7. NetMindAgent.decide()

**Ubicación**: `backend/src/agent/router.py` (líneas 26-245)

**Acciones realizadas**:

1. **Validación de relevancia temática**:
   - Crea prompt para verificar si la pregunta es sobre redes/telecomunicaciones
   - Llama a LLM con `temperature=0.0`, `max_tokens=10`
   - Espera respuesta: "relevante" o "no_relevante"
   - Si no es relevante → retorna:
     ```python
     {
         "tool": "none",
         "reason": "out_of_topic",
         "plan_steps": [],
         "rejection_message": "Lo siento, solo puedo responder..."
     }
     ```

2. **Si es relevante, genera plan**:
   - Crea prompt detallado con:
     - Pregunta del usuario
     - Contexto (últimos 5 mensajes)
     - Reglas para seleccionar herramienta (RAG/IP/DNS)
     - Instrucciones para generar `plan_steps` específicos
   - Llama a LLM para obtener JSON con:
     - `tool`: "rag", "ip", "dns" o "none"
     - `reason`: explicación breve
     - `plan_steps`: lista de pasos ejecutables

3. **Procesa respuesta del LLM**:
   - Limpia delimitadores Markdown (```json)
   - Extrae JSON con regex
   - Parsea JSON
   - Valida y normaliza `plan_steps`:
     - Si está vacío, genera uno por defecto según la herramienta
     - Filtra pasos vagos ("ensure", "elaborate", etc.)

4. **Retorna**:
   ```python
   {
       "tool": "rag|ip|dns|none",
       "reason": "...",
       "plan_steps": ["step1", "step2", ...]
   }
   ```

**Ejemplo de plan_steps**:
- `["retrieve information about what ping is"]` → RAG
- `["ping to google.com"]` → IP
- `["query all DNS records for google.com"]` → DNS

---

### 8. Orchestrator Node

**Función**: `orchestrator_node(state: GraphState)`

**Ubicación**: `backend/src/agent/agent_graph.py` (líneas 236-328)

**Acciones realizadas**:

1. **Lee el estado**:
   - `plan_steps`: pasos pendientes
   - `results`: resultados acumulados
   - `rejection_message`: mensaje de rechazo (si existe)

2. **Toma decisión**:
   - Si hay `rejection_message` → `next_component = "Sintetizador"`
   - Si no hay `plan_steps` → `next_component = "Sintetizador"`
   - Si hay `results` y no hay `plan_steps` → `next_component = "Sintetizador"`
   - Si hay `plan_steps` → `next_component = "Agente_Ejecutor"`
   - Fallback → `next_component = "Sintetizador"`

3. **Registra pensamiento**:
   - Agrega entrada a `thought_chain` con la decisión

4. **Retorna**:
   ```python
   {
       "next_component": "Agente_Ejecutor" | "Sintetizador",
       "thought_chain": thought_chain
   }
   ```

---

### 9. Executor Node (si hay plan_steps)

**Función**: `ejecutor_agent_node(state: GraphState)`

**Ubicación**: `backend/src/agent/agent_graph.py` (líneas 331-425)

**Acciones realizadas**:

1. **Extrae siguiente paso**:
   - Toma el primer elemento de `plan_steps`
   - Crea copia: `plan_steps_copy = list(plan_steps)`
   - Elimina el primer paso: `current_step = plan_steps_copy.pop(0)`

2. **Obtiene prompt del usuario**:
   - Extrae el último mensaje del usuario de `state.messages`
   - Limita a 6000 caracteres si es muy largo

3. **Determina herramienta**:
   - Llama a `determine_tool_from_step(current_step, user_prompt)`

4. **Ejecuta herramienta**:
   - `tool_name == "rag"` → `execute_rag_tool(current_step, user_prompt, state.messages)`
   - `tool_name == "ip"` → `execute_ip_tool(current_step, user_prompt, state.messages)`
   - `tool_name == "dns"` → `execute_dns_tool(current_step, user_prompt, state.messages)`

5. **Guarda resultado**:
   - Agrega el resultado a `state.results`
   - Actualiza `executed_tools` y `executed_steps`

6. **Registra pensamiento**:
   - Agrega entrada con el estado de ejecución

7. **Retorna**:
   ```python
   {
       "plan_steps": plan_steps_copy,  # Sin el paso ejecutado
       "results": accumulated,
       "executed_tools": executed_tools_list,
       "executed_steps": executed_steps_list,
       "thought_chain": thought_chain
   }
   ```

8. **Decisión de ruteo**:
   - Si quedan pasos en `plan_steps` → vuelve a Orchestrator
   - Si no quedan pasos → va a Synthesizer

---

### 10. determine_tool_from_step()

**Ubicación**: `backend/src/agent/tool_executors.py` (líneas 856-904)

**Acciones realizadas**:

1. **Crea prompt para LLM**:
   - Incluye el paso del plan y el prompt original
   - Describe las herramientas disponibles (RAG/IP/DNS)
   - Pide respuesta: "rag", "ip" o "dns"

2. **Llama a LLM**:
   - Usa `llm.generate(tool_determination_prompt)`

3. **Procesa respuesta**:
   - Normaliza a minúsculas
   - Busca "dns", "rag" o "ip" en la respuesta

4. **Fallback heurístico** (si falla LLM):
   - Busca palabras clave en el paso:
     - DNS: "dns", "domain", "mx", "nameserver", "registro dns"
     - IP: "ping", "trace", "traceroute", "compare", "ip", "network"
     - RAG: por defecto

5. **Retorna**: `"rag"`, `"ip"` o `"dns"`

---

### 11. execute_*_tool()

**Ubicación**: `backend/src/agent/tool_executors.py`
- `execute_rag_tool()`: líneas 429-640
- `execute_ip_tool()`: líneas 59-114
- `execute_dns_tool()`: líneas 643-853

#### execute_rag_tool():

1. **Extrae contexto de conversación**:
   - Toma los últimos 10 mensajes anteriores al actual
   - Formatea como string

2. **Llama a rag_tool.query()**:
   - Pasa `user_prompt` y `conversation_context`
   - El RAG tool busca en documentos usando embeddings

3. **Retorna**: `{answer, contexts, hits, source}`

#### execute_ip_tool():

1. **Detecta tipo de operación**:
   - Analiza el paso y el prompt
   - Detecta: "ping", "traceroute", "compare"

2. **Extrae hosts/IPs**:
   - Busca IPs o dominios válidos en el texto

3. **Ejecuta operación**:
   - `ping` → `ip_tool.ping(host)`
   - `traceroute` → `ip_tool.tracert(host)`
   - `compare` → `ip_tool.compare(ip1, ip2)`

4. **Retorna**: `{type, results, ...}`

#### execute_dns_tool():

1. **Detecta tipo de consulta**:
   - Analiza el paso y el prompt
   - Detecta: "all records", "MX", "TXT", "NS", "comparison", "SPF", "DMARC", etc.

2. **Extrae dominio**:
   - Busca dominio válido en el texto con regex

3. **Ejecuta consulta**:
   - `get_all_records(domain)` → todos los registros
   - `query(domain, record_type)` → registro específico
   - `compare_dns(domain1, domain2)` → comparación
   - `check_spf/dmarc(domain)` → verificación

4. **Retorna**: `{domain, records, summary_text, ...}`

---

### 12. Synthesizer Node

**Función**: `synthesizer_node(state: GraphState)`

**Ubicación**: `backend/src/agent/agent_graph.py` (líneas 858-1185)

**Acciones realizadas**:

1. **Verifica mensaje de rechazo**:
   - Si hay `rejection_message` → retorna ese mensaje directamente

2. **Analiza resultados**:
   - Detecta qué herramientas se usaron:
     - RAG: tiene `'answer'` en el resultado
     - IP: tiene `'comparison'`, `'traceroute'`, `'ip'`, etc.
     - DNS: tiene `'domain'`, `'records'`, etc.

3. **Casos de síntesis**:

   **Solo RAG**:
   - Extrae `answer` de cada resultado RAG
   - Analiza complejidad de la pregunta (simple/moderada/compleja)
   - Genera respuesta con LLM:
     - Prompt: combina pregunta + respuestas RAG
     - Instrucciones: fidelidad, longitud adaptativa, lenguaje natural
     - Ajusta longitud según complejidad
   - Retorna respuesta procesada

   **Solo IP o Solo DNS**:
   - Formatea resultados usando `ip_tool.format_result()` o `dns_tool.format_result()`
   - Retorna resultados formateados directamente (sin LLM)

   **RAG + IP/DNS**:
   - Combina respuestas RAG con resultados técnicos
   - Genera respuesta con LLM que integra:
     - Información conceptual (RAG)
     - Resultados técnicos (IP/DNS)
   - Retorna respuesta combinada

4. **Retorna**: `{"final_output": respuesta_final}`

---

### 13. Supervisor Node

**Función**: `supervisor_node(state: GraphState)`

**Ubicación**: `backend/src/agent/agent_graph.py` (líneas 428-855)

**Acciones realizadas**:

1. **Lee final_output del estado**

2. **Detecta si está fuera de tema**:
   - Usa LLM para verificar si la respuesta indica que la pregunta está fuera de tema
   - Si es así, pasa la respuesta sin modificar

3. **Evalúa calidad**:
   - Crea prompt para evaluar calidad (0-10)
   - Llama a LLM para obtener puntuación
   - Normaliza a rango 0-1

4. **Analiza complejidad**:
   - Usa LLM para determinar: "simple", "moderada" o "compleja"
   - Define longitud máxima según complejidad:
     - Simple: 200 caracteres
     - Moderada: 600-1500 caracteres
     - Compleja: 2000 caracteres

5. **Mejora respuesta si es necesario**:
   - Si calidad < 0.5 o muy larga:
     - Crea prompt de mejora con instrucciones específicas
     - Llama a LLM para mejorar
     - Ajusta longitud si es necesario

6. **Captura para RAGAS** (evaluación):
   - Extrae contextos de `state.results`
   - Captura: pregunta, respuesta, contextos
   - Ejecuta evaluación en background (thread separado)

7. **Retorna**:
   ```python
   {
       "supervised_output": respuesta_mejorada,
       "quality_score": puntuación
   }
   ```

---

### 14. Retorna supervised_output

**Ubicación**: 
- `backend/src/api/agent.py` (después de `graph.invoke()` o `graph.ainvoke()`)
- `backend/src/api/streaming.py` (streaming en tiempo real con `graph.astream_events()`)

**Acciones realizadas**:

1. **Extrae respuesta final**:
   - Lee `supervised_output` del estado final
   - Si no existe, usa `final_output`
   - Si no existe, usa mensaje por defecto

2. **Construye respuesta**:
   - Crea `new_messages` con la respuesta del asistente
   - Extrae `executed_tools` y `executed_steps` del estado
   - Construye objeto `decision` con información de ejecución

3. **Actualiza sesión**:
   - Agrega respuesta del asistente al contexto: `session_state.add_message("assistant", assistant_response)`
   - Persiste sesión: `session_manager.update_session(query.session_id, session_state)`

4. **Retorna respuesta HTTP**:
   ```json
   {
       "session_id": "...",
       "new_messages": [
           {
               "role": "assistant",
               "content": "..."
           }
       ],
       "decision": {
           "tool": "rag|ip|dns",
           "plan_steps": [...],
           "executed_tools": [...]
       },
       "session_context_length": 5
   }
   ```

---

## 📁 Estructura de Archivos

```
backend/
├── main.py                    # Punto de entrada FastAPI
├── src/
│   ├── api/                   # Capa de API REST
│   │   ├── agent.py          # Endpoint principal /agent/query
│   │   ├── files.py           # Endpoint para gestión de archivos
│   │   └── streaming.py      # Endpoint para streaming de respuestas (SSE)
│   │
│   ├── agent/                 # Lógica del agente (grafo LangGraph)
│   │   ├── agent_graph.py    # Grafo principal con 5 nodos
│   │   ├── router.py         # NetMindAgent (decisión de herramientas)
│   │   ├── tool_executors.py # Ejecutores de herramientas
│   │   ├── llm_client.py     # Cliente OpenAI
│   │   └── helpers.py        # Funciones auxiliares
│   │
│   ├── tools/                 # Herramientas especializadas
│   │   ├── rag_tool.py       # RAG (búsqueda en documentos)
│   │   ├── ip_tool.py        # Operaciones de red (ping, traceroute)
│   │   └── dns_tool.py       # Consultas DNS
│   │
│   ├── core/                  # Componentes centrales
│   │   ├── graph_state.py    # GraphState (estado compartido)
│   │   ├── state_manager.py  # SessionManager (gestión de sesiones)
│   │   ├── cache.py          # Sistema de caché
│   │   └── redis_session_manager.py # Gestión de sesiones Redis
│   │
│   ├── models/                # Modelos de datos
│   │   ├── schemas.py        # Pydantic schemas (AgentState, Message)
│   │   └── database.py       # Modelos de base de datos
│   │
│   ├── repositories/         # Acceso a datos
│   │   ├── qdrant_repository.py
│   │   ├── document_repository.py
│   │   └── session_repository.py
│   │
│   ├── services/              # Servicios de negocio
│   │   └── embeddings_service.py
│   │
│   ├── utils/                 # Utilidades
│   │   ├── ragas_callback.py
│   │   ├── ragas_evaluator.py
│   │   ├── embeddings.py
│   │   └── text_processing.py # Procesamiento de texto
│   │
│   └── settings.py           # Configuración centralizada
```

---

## 🔧 Componentes Principales

### 1. API Layer (`src/api/`)
- **agent.py**: Endpoint `/agent/query` que recibe consultas y ejecuta el grafo
- **files.py**: Endpoints para gestión de archivos PDF
- **streaming.py**: Endpoint `/agent/query/stream` para streaming de respuestas (SSE)

### 2. Agent Layer (`src/agent/`)
- **agent_graph.py**: Grafo LangGraph con 5 nodos (Planner, Orchestrator, Executor, Synthesizer, Supervisor)
- **router.py**: NetMindAgent que decide qué herramienta usar
- **tool_executors.py**: Ejecutores que llaman a las herramientas específicas
- **llm_client.py**: Cliente para interactuar con OpenAI

### 3. Tools (`src/tools/`)
- **rag_tool.py**: Búsqueda semántica en documentos indexados
- **ip_tool.py**: Operaciones de red (ping, traceroute, comparación)
- **dns_tool.py**: Consultas DNS y verificaciones

### 4. Core (`src/core/`)
- **graph_state.py**: Estado compartido del grafo (GraphState)
- **state_manager.py**: Gestión de sesiones (SessionManager)
- **cache.py**: Sistema de caché con Redis

### 5. Models (`src/models/`)
- **schemas.py**: Schemas Pydantic (AgentState, Message, AgentQuery)
- **database.py**: Modelos SQLAlchemy

---

## 🔄 Resumen del Flujo Completo

```
Usuario envía pregunta
    ↓
API valida y obtiene sesión
    ↓
Convierte a GraphState
    ↓
Planner: Analiza pregunta → Genera plan (NetMindAgent)
    ↓
Orchestrator: Decide siguiente paso
    ↓
Executor: Ejecuta herramienta (RAG/IP/DNS)
    ↓ (si hay más pasos, vuelve a Orchestrator)
Synthesizer: Combina resultados → Genera respuesta
    ↓
Supervisor: Valida y mejora respuesta
    ↓
API: Guarda en sesión → Retorna al usuario
```

Cada paso actualiza el estado compartido (`GraphState`) que se propaga automáticamente entre nodos gracias a LangGraph.

---

## 📊 Flujo de Datos

```
Usuario → API → GraphState (messages)
                ↓
            Planner → plan_steps
                ↓
            Orchestrator → next_component
                ↓
            Executor → results
                ↓
            Synthesizer → final_output
                ↓
            Supervisor → supervised_output
                ↓
            API → Usuario
```

---

## 🔍 Dependencias entre Módulos

```
api/agent.py
  ├─> core/state_manager.py (SessionManager)
  ├─> core/graph_state.py (GraphState)
  ├─> agent/agent_graph.py (graph)
  └─> models/schemas.py (AgentState, Message)

agent/agent_graph.py
  ├─> agent/router.py (NetMindAgent)
  ├─> agent/tool_executors.py (execute_*_tool)
  ├─> agent/llm_client.py (LLMClient)
  ├─> core/graph_state.py (GraphState)
  └─> models/schemas.py (AgentState)

agent/tool_executors.py
  ├─> tools/rag_tool.py (RAGTool)
  ├─> tools/ip_tool.py (IPTool)
  ├─> tools/dns_tool.py (DNSTool)
  └─> agent/llm_client.py (LLMClient)

tools/rag_tool.py
  ├─> services/embeddings_service.py
  ├─> repositories/qdrant_repository.py
  └─> repositories/document_repository.py
```

---

## 📝 Notas Importantes

1. **Estado Compartido**: El `GraphState` se propaga automáticamente entre nodos usando LangGraph
2. **Thread-Safety**: El `SessionManager` usa locks para garantizar thread-safety
3. **Caché**: Las respuestas RAG se cachean por 1 hora (configurable)
4. **Contexto de Conversación**: Se mantiene por `session_id` y se limita a 20 mensajes
5. **Validación Temática**: Se valida que las preguntas sean sobre redes/telecomunicaciones
6. **Evaluación RAGAS**: Se ejecuta en background para no bloquear la respuesta

