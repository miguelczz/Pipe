# 🔍 Pipe: Análisis Inteligente de Capturas Wireshark

![Pipe Banner](https://img.shields.io/badge/Pipe-Wireshark_Analysis-blue?style=for-the-badge&logo=network)
![Status](https://img.shields.io/badge/Status-Production_Ready-green?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=for-the-badge&logo=fastapi&logoColor=white)

**Pipe** es una solución de vanguardia basada en Agentes de IA diseñada específicamente para el análisis de capturas Wireshark (.pcap/.pcapng). Combina la potencia de **LangGraph** para la orquestación de flujos complejos, **RAG** para la consulta de bases de conocimiento técnicas sobre protocolos de red y herramientas especializadas para análisis de tráfico, Band Steering y protocolos WiFi.

---

## 📋 Tabla de Contenidos
- [Capacidades Principales](#-capacidades-principales)
- [Arquitectura del Sistema](#-arquitectura-del-sistema)
- [Stack Tecnológico](#-stack-tecnológico)
- [Instalación y Despliegue](#-instalación-y-despliegue)
- [Configuración (.env)](#-configuración-env)
- [Uso y API Endpoints](#-uso-y-api-endpoints)
- [Estructura del Proyecto](#-estructura-del-proyecto)
- [Conceptos y Patrones](#-conceptos-y-patrones-implementados)

---

## 🚀 Capacidades Principales

| Herramienta | Descripción Técnica | Tecnología Base |
| :--- | :--- | :--- |
| **🧠 RAG Core** | Búsqueda semántica en documentos PDF indexados para respuestas técnicas sobre análisis de capturas Wireshark, protocolos WiFi y Band Steering. | Qdrant + OpenAI Embeddings |
| **📦 Wireshark Analyzer** | Análisis profundo de archivos .pcap/.pcapng para identificar protocolos, eventos BTM, transiciones de banda y comportamiento de red. | Python + Scapy/Wireshark |
| **🔄 Band Steering** | Análisis especializado de eventos de Band Steering, códigos de estado BTM y transiciones entre bandas 2.4GHz y 5GHz. | Protocol Analysis |
| **⚖️ Supervisor** | Capa de razonamiento crítico que valida la precisión, el tono y la relevancia de cada respuesta sobre análisis de capturas. | LLM-based Evaluation |

---

## 🏗️ Arquitectura del Sistema

Pipe implementa una arquitectura desacoplada y escalable, centrada en un motor de agentes con estado compartido especializado en análisis de capturas Wireshark.

### Flujo Operativo del Agente
El sistema utiliza un grafo cíclico de 5 nodos para garantizar que cada consulta sea procesada con rigor técnico:

```mermaid
graph TD
    User[Consulta Usuario] --> API[FastAPI Layer]
    API --> Planner[Planner: Genera Plan de Acción]
    Planner --> Orchestrator{Orchestrator: Selecciona Canal}
    Orchestrator --> Executor[Executor: Ejecuta Herramientas]
    Executor --> Orchestrator
    Orchestrator --> Synthesizer[Synthesizer: Genera Respuesta]
    Synthesizer --> Supervisor[Supervisor: Control de Calidad]
    Supervisor --> API
    API --> Client[Respuesta Final / SSE Stream]
```

---

## 🛠️ Stack Tecnológico

### **Backend & Engine**
*   **Framework**: FastAPI (Asíncrono, alto rendimiento).
*   **Orquestación de Agentes**: LangGraph (Grafos dirigidos con estado compartido).
*   **Modelos de Lenguaje**: OpenAI GPT-4o / GPT-4o-mini.
*   **Vector Database**: Qdrant (Búsqueda semántica).
*   **Base de Datos Relacional**: PostgreSQL (Metadatos de documentos y sesiones).
*   **Caché & Sesiones**: Redis (Persistencia de contexto y optimización de latencia).

### **Frontend Moderno**
*   **Core**: React 18 + Vite.
*   **Estilos**: Tailwind CSS.
*   **Animaciones**: Framer Motion.
*   **Consumo API**: TanStack Query + Axios.

---

## 📦 Instalación (Desarrollo local)

### Prerrequisitos
*   Python 3.10+.
*   OpenAI API Key habilitada.

### Pasos de Desarrollo Rápido
1.  Clonar y levantar el backend (desarrollo local):
    ```bash
    git clone https://github.com/tu-repo/pipe.git
    cd pipe/backend
    python -m venv venv
    venv\Scripts\activate   # Windows
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000
    ```
2.  Frontend (opcional):
    ```bash
    cd ../frontend
    npm install
    npm run dev
    ```

---

## ⚙️ Configuración (.env)

El sistema requiere las siguientes variables de entorno en `backend/.env`:

| Variable | Descripción | Ejemplo |
| :--- | :--- | :--- |
| `OPENAI_API_KEY` | Llave oficial de OpenAI. | `sk-proj-...` |
| `QDRANT_URL` | URL de la base de datos vectorial. | `http://localhost:6444` |
| `DATABASE_URL` | URL de conexión a PostgreSQL. | `postgresql://user:pass@localhost:5440/db` |
| `REDIS_URL` | URL para el motor de caché. | `redis://localhost:6379/0` |
| `LLM_MODEL` | Modelo principal del agente. | `gpt-4o-mini` |

---

## 📖 Uso y API Endpoints

### **Agente Query (POST /agent/query)**
Envía una consulta al agente para recibir una respuesta técnica procesada.
```bash
curl -X POST "http://localhost:8000/agent/query" \
     -H "Content-Type: application/json" \
     -d '{"session_id": "demo", "messages": [{"role": "user", "content": "¿Cómo funciona el protocolo BGP?"}]}'
```

### **Streaming SSE (POST /agent/query/stream)**
Ideal para interfaces en tiempo real, permite ver la generación de la respuesta token por token.

### **Gestión de Archivos (POST /files/upload)**
Permite alimentar la herramienta RAG con documentación técnica personalizada en PDF.

---

## 📁 Estructura del Proyecto

```bash
NetMind/
├── backend/                # Motor de Inteligencia Artificial
│   ├── src/
│   │   ├── agent/          # Nodos del grafo (Planner, Router, Executors)
│   │   ├── tools/          # Lógica de RAG, IP y DNS Tools
│   │   ├── core/           # Gestión de estado, caché y sesiones
│   │   ├── api/            # Endpoints REST y Streaming (SSE)
│   │   └── repositories/   # Capa de persistencia (PostgreSQL/Qdrant)
│   └── main.py             # Punto de entrada de la aplicación
├── frontend/               # Interfaz SPA con React
└── docs/                   # Documentación técnica extendida
```

---

## 🔍 Conceptos y Patrones Implementados

1.  **Agentic RAG**: A diferencia de un RAG simple, NetMind decide si necesita buscar en documentos o usar herramientas de red basándose en el razonamiento del Planner.
2.  **Short-Term & Long-Term Memory**: Uso sincronizado de Redis y PostgreSQL para mantener el contexto de la conversación fluido y persistente entre reinicios.
3.  **Self-Correction Loop**: El nodo Supervisor evalúa el output del Synthesizer; si la respuesta no cumple los parámetros de calidad, el grafo puede re-rutear el proceso para mejorarla.
4.  **Hybrid Search**: Combinación de búsqueda vectorial (densas) y por palabras clave (dispersas) para máxima precisión en términos técnicos.

---

<div align="center">
  <sub>Copyright © 2026 NetMind AI. Todos los derechos reservados.</sub>
</div>
