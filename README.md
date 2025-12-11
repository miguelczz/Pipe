# NetMind - Sistema de Agente Inteligente para Redes y Telecomunicaciones

Sistema de agente inteligente que combina RAG (Retrieval-Augmented Generation), herramientas de red (IP y DNS) y un agente conversacional para responder preguntas técnicas sobre redes y telecomunicaciones. Implementa una arquitectura completa con LangGraph, gestión de estado distribuida y múltiples herramientas especializadas.

## 📋 Tabla de Contenidos

- [Descripción](#descripción)
- [Arquitectura](#arquitectura)
- [Stack Tecnológico](#stack-tecnológico)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Uso](#uso)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Conceptos y Patrones Implementados](#conceptos-y-patrones-implementados)
- [Documentación Adicional](#documentación-adicional)

## 📖 Descripción

NetMind es un sistema de agente inteligente que actúa como un enrutador de consultas, decidiendo automáticamente qué herramienta utilizar según la intención del usuario:

- **RAG Tool**: Responde preguntas sobre conceptos, definiciones y explicaciones técnicas basándose en documentos PDF indexados
- **IP Tool**: Realiza operaciones de red como ping, traceroute y comparación de direcciones IP
- **DNS Tool**: Consulta registros DNS (A, AAAA, MX, TXT, NS, CNAME, PTR) y realiza verificaciones SPF/DMARC

El sistema mantiene contexto de conversación entre múltiples interacciones, permitiendo conversaciones naturales y seguimiento de consultas previas.

## 🏗️ Arquitectura

### Arquitectura General del Sistema

Vista de alto nivel de los componentes principales del sistema:

```
        ┌──────────────────────────────────────────┐
        │         FastAPI (API Layer)              │
        │  ┌──────────────┐  ┌──────────────┐      │
        │  │  Files API   │  │  Agent API   │      │
        │  └──────────────┘  └──────┬───────┘      │
        └───────────────────────────┼──────────────┘
                                    │
                            ┌───────▼───────┐
                            │  LangGraph    │
                            │  Agent Graph  │
                            │  (5 Nodos)    │
                            └───────┬───────┘
                                    │
                            ┌───────▼──────┐
                            │  Tools Layer │
                            │  ┌──────┐    │
                            │  │  RAG │    │
                            │  │  IP  │    │
                            │  │  DNS │    │
                            │  └──┬───┘    │
                            └─────┼────────┘
                                  │
             ┌──-──────────────--─┼────────────────┐
             │                    │                │
        ┌────▼─────┐      ┌─────-─▼─────┐   ┌───-──▼───┐
        │  Qdrant  │      │ PostgreSQL  │   │  Redis   │
        │ (Vectors)│      │ (Metadata)  │   │ (Cache)  │
        └──────────┘      └─────────────┘   └──────────┘
```

### Flujo del Grafo LangGraph

Detalle del flujo de ejecución entre los nodos del grafo de agentes. Este diagrama muestra específicamente cómo los 5 nodos del grafo interactúan entre sí:

```
                    START
                      │
                      ▼
                  ┌─────────┐
                  │ Planner │  Genera plan de ejecución basado en la consulta
                  └────┬────┘
                       │
                       ▼
              ┌─────────────┐
              │ Orquestador │  Decide el siguiente componente a activar
              └─────┬───────┘
                ▲   │
        ┌───────│───┴───────────┐
        │ (si hay más pasos)    │
        ▼       │               ▼
┌────────────-──┐        ┌────────────┐
│Agente_Ejecutor│        │Sintetizador│
│               │        │            │
│ Ejecuta tools │        │ Combina    │
│ (RAG/IP/DNS)  │        │ resultados │
└───────┬───────┘        └──────┬─────┘
        │                       │
        │                       │
        └───────────┬───────────┘
                    │
                    ▼
            ┌─────────────┐
            │  Supervisor │  Valida y mejora la respuesta final
            └──────┬──────┘
                   │
                   ▼
                  END
```

**Componentes del Grafo:**

1. **Planner (Planificador)**
   - Analiza la consulta del usuario usando LLM
   - Genera un plan de ejecución con pasos específicos
   - Valida relevancia temática (solo redes y telecomunicaciones)
   - Determina qué herramientas se necesitan

2. **Orquestador (Orchestrator)**
   - Coordina el flujo entre componentes
   - Decide si ejecutar herramientas o sintetizar resultados
   - Gestiona el ciclo de ejecución de múltiples pasos
   - Puede dirigir el flujo a `Agente_Ejecutor` o `Sintetizador`

3. **Agente_Ejecutor (Executor)**
   - Ejecuta las herramientas especializadas según el plan
   - Soporta ejecución secuencial de múltiples pasos
   - Extrae información del contexto de conversación cuando es necesario
   - Puede volver al `Orquestador` si hay más pasos pendientes
   - Puede ir directamente a `Sintetizador` si no hay más pasos

4. **Sintetizador (Synthesizer)**
   - Combina resultados de múltiples herramientas
   - Genera respuestas coherentes usando LLM
   - Adapta la longitud según la complejidad de la pregunta
   - Puede interactuar con `Agente_Ejecutor` si se necesitan más datos

5. **Supervisor**
   - Valida la calidad de la respuesta final
   - Mejora respuestas de baja calidad
   - Captura datos para evaluación con Ragas
   - Ajusta longitud según complejidad detectada

## 🛠️ Stack Tecnológico

### Backend - Core Framework

- **Python 3.8+**: Lenguaje de programación principal
- **FastAPI**: Framework web asíncrono y moderno para APIs REST
- **Uvicorn**: Servidor ASGI de alto rendimiento con soporte estándar
- **Pydantic**: Validación de datos y configuración con type hints
- **Pydantic Settings**: Gestión de configuración desde variables de entorno

### Agentes y LLMs

- **LangGraph**: Framework para construir grafos de agentes con estado compartido
- **LangGraph API**: API para ejecutar grafos de agentes
- **LangGraph CLI**: Herramientas de línea de comandos para desarrollo y debugging
- **LangChain**: Framework para aplicaciones con LLMs
- **LangChain OpenAI**: Integración de OpenAI con LangChain
- **OpenAI**: Cliente oficial para modelos GPT y embeddings

### Bases de Datos y Almacenamiento

- **PostgreSQL**: Base de datos relacional para metadatos y sesiones
- **Psycopg2-binary**: Adaptador PostgreSQL para Python (versión binaria)
- **SQLAlchemy**: ORM para acceso a base de datos con soporte asíncrono
- **Qdrant Client**: Cliente para base de datos vectorial Qdrant
- **Redis**: Sistema de caché en memoria para optimización
- **Hiredis**: Cliente Redis de alto rendimiento (parser C)

### Procesamiento de Documentos y Texto

- **PyPDF2**: Extracción de texto de documentos PDF
- **Tiktoken**: Tokenización eficiente para embeddings y conteo de tokens
- **Python-multipart**: Manejo de archivos y formularios en FastAPI
- **Aiofiles**: Operaciones de archivo asíncronas

### Herramientas de Red

- **dnspython**: Consultas DNS y resolución de dominios (versión >=2.4.0)
- **Subprocess** (built-in): Ejecución de comandos de red (ping, traceroute)
- **Socket** (built-in): Operaciones de red de bajo nivel

### Evaluación y Testing

- **Ragas**: Framework para evaluación de calidad de sistemas RAG (versión >=0.1.0)
- **Datasets**: Manejo de datasets para evaluación (versión >=2.14.0)
- **Pandas**: Análisis de datos y procesamiento (versión >=2.0.0)
- **Pytest**: Framework de testing (versión >=7.4.0)
- **Pytest-asyncio**: Soporte asíncrono para pytest (versión >=0.21.0)

### Utilidades y Optimización

- **Python-dotenv**: Carga de variables de entorno desde archivos .env
- **Tqdm**: Barras de progreso para operaciones largas
- **Asyncio**: Programación asíncrona nativa de Python
- **Concurrent.futures**: Ejecución paralela de tareas
- **Threading**: Gestión de threads para operaciones concurrentes

### Frontend

- **React 18**: Biblioteca para interfaces de usuario
- **Vite**: Build tool y dev server de alto rendimiento
- **Tailwind CSS**: Framework CSS utility-first
- **React Router DOM**: Enrutamiento en aplicaciones React
- **Axios**: Cliente HTTP para peticiones API
- **TanStack Query (React Query)**: Gestión de estado del servidor y caché
- **Zustand**: Gestión de estado global ligera
- **React Markdown**: Renderizado de markdown en React
- **Remark GFM**: Soporte para GitHub Flavored Markdown
- **Framer Motion**: Biblioteca de animaciones
- **Lucide React**: Iconos modernos
- **Clsx / Tailwind Merge**: Utilidades para clases CSS condicionales

### Desarrollo y Build Tools

- **ESLint**: Linter para JavaScript/React
- **PostCSS**: Procesador de CSS
- **Autoprefixer**: Agregado automático de prefijos CSS
- **TypeScript Types**: Tipos para React y React DOM

### Infraestructura

- **Docker**: Contenedorización de servicios
- **Docker Compose**: Orquestación de múltiples contenedores
- **Qdrant**: Base de datos vectorial (contenedor Docker)
- **PostgreSQL**: Base de datos relacional (contenedor Docker)
- **Redis**: Sistema de caché (contenedor Docker)

## 🚀 Instalación

### Prerrequisitos

- Python 3.8 o superior
- Docker y Docker Compose
- OpenAI API Key
- Node.js 18+ (para frontend, opcional)

### Pasos de Instalación

1. **Clonar el repositorio**
```bash
git clone <repository-url>
cd RouterAgent
```

2. **Configurar entorno virtual (Backend)**
```bash
cd backend
python -m venv venv
source venv\scripts\activate
```

3. **Instalar dependencias del backend**
```bash
pip install -r requirements.txt
```

4. **Iniciar servicios con Docker Compose (Desarrollo)**
```bash
docker-compose -f docker-compose.dev.yml up -d
```

Esto iniciará:
- PostgreSQL en el puerto `5440`
- Qdrant en el puerto `6444`
- Redis en el puerto `6379`

5. **Configurar variables de entorno**

Crear archivo `.env` en `backend/`:
```env
# OpenAI
OPENAI_API_KEY=tu_api_key_aqui
EMBEDDING_MODEL=text-embedding-3-large
LLM_MODEL=gpt-4o-mini

# Qdrant
QDRANT_URL=http://localhost:6444

# PostgreSQL
POSTGRES_USER=pguser
POSTGRES_PASSWORD=pgpass
POSTGRES_DB=appdb
POSTGRES_HOST=localhost
POSTGRES_PORT=5440
DATABASE_URL=postgresql://pguser:pgpass@localhost:5440/appdb

# Redis
REDIS_URL=redis://localhost:6379/0
CACHE_ENABLED=true

# App
APP_NAME=NetMind
APP_VERSION=1.0.0
APP_PORT=8000
APP_ENV=development
SECRET_KEY=tu_secret_key_aqui

# Procesamiento
UPLOAD_DIR=./databases/uploads
CHUNK_SIZE=500
CHUNK_OVERLAP=50

# Ragas
RAGAS_ENABLED=true
```

6. **Verificar configuración (Opcional)**
```bash
cd backend
python scripts/check_env.py
```

Este script verifica que todas las variables de entorno estén configuradas correctamente.

7. **Iniciar la aplicación backend**
```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

La API estará disponible en `http://localhost:8000/docs#/`

**Nota**: En desarrollo, la aplicación continuará funcionando aunque la base de datos no esté disponible al inicio (con advertencias). Esto permite desarrollo sin necesidad de tener todos los servicios corriendo.

8. **Instalar y ejecutar frontend (Opcional)**
```bash
cd frontend
npm install
npm run dev
```

El frontend estará disponible en `http://localhost:5173`

### Configuración de Producción

Para producción, consulta la [Guía de Configuración de Entornos](docs/Configuracion_Entornos.md) que incluye:
- Configuración con Docker Compose para producción
- Configuración para Heroku
- Variables de entorno específicas para producción
- Solución de problemas comunes

## ⚙️ Configuración

### Manejo de Entornos

El proyecto está configurado para funcionar tanto en **desarrollo** como en **producción**:

- **Desarrollo**: La aplicación es tolerante a fallos de conexión a la base de datos al inicio
- **Producción**: La aplicación requiere que todos los servicios estén disponibles

Configura el entorno con la variable `APP_ENV`:
- `APP_ENV=development` (por defecto)
- `APP_ENV=production`

### Variables de Entorno Principales

| Variable | Descripción | Valor por Defecto | Requerido |
|----------|-------------|-------------------|-----------|
| `OPENAI_API_KEY` | Clave API de OpenAI | - | ✅ Sí |
| `QDRANT_URL` | URL de Qdrant | `http://localhost:6444` | ✅ Sí |
| `LLM_MODEL` | Modelo LLM a usar | `gpt-4o-mini` | No |
| `EMBEDDING_MODEL` | Modelo de embeddings | `text-embedding-3-large` | No |
| `DATABASE_URL` | URL completa de PostgreSQL | - | Opcional* |
| `POSTGRES_*` | Variables individuales de PostgreSQL | - | Opcional* |
| `REDIS_URL` | URL de Redis | `redis://localhost:6379/0` | No |
| `CACHE_ENABLED` | Habilitar caché | `true` | No |
| `APP_ENV` | Entorno de la aplicación | `development` | No |
| `CHUNK_SIZE` | Tamaño de chunks para documentos | `500` | No |
| `CHUNK_OVERLAP` | Solapamiento entre chunks | `50` | No |
| `RAGAS_ENABLED` | Habilitar evaluación Ragas | `true` | No |

*Puedes usar `DATABASE_URL` o las variables individuales (`POSTGRES_USER`, `POSTGRES_PASSWORD`, etc.)

Para más detalles sobre configuración, consulta [Configuración de Entornos](docs/Configuracion_Entornos.md).

### Configuración de Chunks

Los documentos PDF se dividen en chunks para indexación:
- **Chunk Size**: 500 caracteres (configurable)
- **Chunk Overlap**: 50 caracteres (configurable)

Estos valores afectan la granularidad de la búsqueda semántica.

## 📖 Uso

### API Endpoints

#### Gestión de Archivos

**Subir Documento PDF:**
```bash
curl -X POST "http://localhost:8000/files/upload" \
  -F "file=@documento.pdf"
```

**Listar Documentos:**
```bash
curl -X GET "http://localhost:8000/files/"
```

**Eliminar Documento:**
```bash
curl -X DELETE "http://localhost:8000/files/{document_id}"
```

#### Consultas al Agente

**Consulta Estándar:**
```bash
curl -X POST "http://localhost:8000/agent/query" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "mi-sesion",
    "user_id": "usuario-123",
    "messages": [{
      "role": "user",
      "content": "¿Qué es un ping?"
    }]
  }'
```

**Streaming de Respuestas (SSE):**
```bash
curl -X POST "http://localhost:8000/agent/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "mi-sesion",
    "messages": [{
      "role": "user",
      "content": "Explica cómo funciona DNS"
    }]
  }'
```

### Ejemplos de Consultas

**Consultas RAG (Conceptos):**
- "¿Qué es una VLAN?"
- "Explica cómo funciona el protocolo TCP/IP"
- "¿Cuál es la diferencia entre TCP y UDP?"
- "Describe el modelo OSI"

**Consultas IP Tool (Operaciones de Red):**
- "Haz ping a google.com"
- "Traceroute a facebook.com"
- "Compara las IPs de google.com y facebook.com"
- "Haz ping a 8.8.8.8"

**Consultas DNS Tool:**
- "Consulta los registros DNS de google.com"
- "MX de gmail.com"
- "Registros NS de facebook.com"
- "Verifica SPF de dominio.com"
- "Compara DNS de google.com con facebook.com"
- "Información completa de amazon.com"

**Consultas Combinadas:**
- "¿Qué es un ping? y haz ping a google.com"
- "Explica DNS y consulta los registros de facebook.com"
- "¿Qué es TCP/IP? y compara las IPs de google y facebook"

### Documentación Interactiva

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## 📁 Estructura del Proyecto

```
RouterAgent/
├── backend/              # Backend Python
│   ├── src/
│   │   ├── agent/             # Lógica del agente (LangGraph)
│   │   │   ├── agent_graph.py    # Grafo principal con 5 nodos
│   │   │   ├── router.py         # NetMindAgent - decisión de herramientas
│   │   │   ├── tool_executors.py # Ejecutores de herramientas
│   │   │   ├── llm_client.py     # Cliente LLM
│   │   │   └── helpers.py        # Funciones auxiliares
│   │   ├── tools/             # Herramientas especializadas
│   │   │   ├── rag_tool.py      # Herramienta RAG
│   │   │   ├── ip_tool.py       # Herramienta IP (ping, traceroute)
│   │   │   └── dns_tool.py      # Herramienta DNS
│   │   ├── core/              # Componentes centrales
│   │   │   ├── graph_state.py   # Estado del grafo (LangGraph)
│   │   │   ├── state_manager.py # Gestor de sesiones
│   │   │   ├── cache.py         # Sistema de caché
│   │   │   └── redis_session_manager.py # Gestión de sesiones Redis
│   │   ├── api/               # Endpoints FastAPI
│   │   │   ├── agent.py         # Endpoints del agente
│   │   │   ├── files.py         # Endpoints de archivos
│   │   │   └── streaming.py     # Endpoints de streaming
│   │   ├── repositories/      # Acceso a datos
│   │   │   ├── qdrant_repository.py    # Repositorio Qdrant
│   │   │   ├── document_repository.py  # Repositorio de documentos
│   │   │   └── session_repository.py   # Repositorio de sesiones
│   │   ├── services/                   # Servicios
│   │   │   └── embeddings_service.py   # Procesamiento de embeddings
│   │   ├── models/             # Modelos y schemas
│   │   │   ├── schemas.py       # Schemas Pydantic
│   │   │   └── database.py      # Modelos SQLAlchemy
│   │   ├── utils/              # Utilidades
│   │   │   ├── embeddings.py       # Funciones de embeddings
│   │   │   ├── text_processing.py  # Procesamiento de texto
│   │   │   ├── ragas_evaluator.py  # Evaluación Ragas
│   │   │   └── ragas_callback.py   # Callbacks Ragas
│   │   └── settings.py     # Configuración centralizada
│   ├── databases/            # Almacenamiento local
│   │   └── uploads/          # Archivos PDF subidos
│   ├── main.py             # Punto de entrada
│   ├── requirements.txt      # Dependencias Python
│   ├── Dockerfile            # Imagen Docker del backend
│   └── langgraph.json        # Configuración LangGraph
├── frontend/               # Frontend React
│   ├── src/
│   │   ├── components/ # Componentes React
│   │   ├── pages/      # Páginas de la aplicación
│   │   ├── hooks/      # Custom hooks
│   │   ├── services/   # Servicios API
│   │   └── config/     # Configuración
│   ├── package.json    # Dependencias Node.js
│   └── vite.config.js  # Configuración Vite
├── docs/               # Documentación técnica del proyecto
├── docker-compose.dev.yml  # Docker Compose para desarrollo
├── docker-compose.prod.yml # Docker Compose para producción
└── README.md           # Este archivo
```

## 🔍 Conceptos y Patrones Implementados

### 1. Arquitectura de Agentes con LangGraph

- **Grafos de agentes**: Flujo de trabajo estructurado con múltiples nodos especializados
- **Estado compartido**: Gestión de estado reactivo entre componentes usando `GraphState`
- **Orquestación**: Coordinación inteligente de múltiples herramientas
- **Patrón State**: Estado centralizado que se propaga automáticamente mediante canales de LangGraph
- **Ruteo condicional**: Decisiones dinámicas basadas en el estado del grafo

### 2. RAG (Retrieval-Augmented Generation)

- **Búsqueda semántica**: Uso de embeddings para encontrar información relevante
- **Bases de datos vectoriales**: Almacenamiento y consulta eficiente con Qdrant
- **Contexto aumentado**: Enriquecimiento de respuestas con documentos indexados
- **Validación de relevancia**: Filtrado temático para mantener precisión
- **Búsqueda híbrida**: Combinación de búsqueda semántica y por keywords
- **Chunking inteligente**: División de documentos en chunks con overlap

### 3. Enrutamiento Inteligente de Herramientas

- **Decisión basada en LLM**: Selección automática de herramientas según intención
- **Planificación**: Generación de planes de ejecución paso a paso
- **Herramientas especializadas**: RAG, IP y DNS trabajando de forma coordinada
- **Contexto de conversación**: Mantenimiento de historial para conversaciones naturales
- **Validación temática**: Rechazo de preguntas fuera del dominio de redes

### 4. Gestión de Estado y Sesiones

- **State Management**: Patrón State para estado compartido entre nodos
- **Session Management**: Persistencia de contexto por sesión de usuario
- **Thread-safety**: Gestión segura de estado en entornos concurrentes
- **Redis Sessions**: Persistencia de sesiones en Redis para alta disponibilidad
- **State Channels**: Uso de `add_messages` y `LastValue` para propagación automática

### 5. Optimización y Rendimiento

- **Sistema de caché**: Redis para optimizar respuestas frecuentes
- **Búsqueda híbrida**: Combinación de búsqueda semántica y por keywords
- **Evaluación de calidad**: Integración con Ragas para métricas de calidad
- **Ejecución asíncrona**: Uso de `asyncio` para operaciones concurrentes
- **Streaming de respuestas**: Server-Sent Events (SSE) para respuestas en tiempo real

### 6. Arquitectura Limpia y Modular

- **Separación de responsabilidades**: Cada módulo con propósito claro
- **Repository Pattern**: Abstracción del acceso a datos
- **Dependency Injection**: Gestión de dependencias con FastAPI Depends
- **Schemas Pydantic**: Validación y serialización de datos
- **Servicios especializados**: Lógica de negocio encapsulada en servicios

### 7. Características Técnicas Avanzadas

- **Validación temática**: Filtrado de preguntas fuera de tema antes de procesar
- **Evaluación RAGAS**: Métricas automáticas de calidad (faithfulness, relevancy, precision)
- **Supervisión de calidad**: Validación y mejora automática de respuestas
- **Detección de complejidad**: Ajuste automático de longitud según tipo de pregunta
- **Gestión de errores**: Manejo robusto de errores en todos los niveles

## 📚 Documentación Adicional

- **[Guía de Despliegue Completa](docs/Guia_Despliegue.md)**: Documentación detallada de despliegue
- **[Flujo Detallado](docs/Flujo.md)**: Explicación paso a paso del flujo del agente
- **[Preguntas de Ejemplo](docs/Preguntas.md)**: Casos de uso y ejemplos de consultas
- **[Optimizaciones](docs/Optimizacion.md)**: Documentación de optimizaciones implementadas
- **[Lista de Construcción](docs/Lista_Construccion.md)**: Guía paso a paso para construir el proyecto desde cero

