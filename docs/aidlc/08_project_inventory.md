````markdown
# 📦 Inventario del Proyecto NetMind (Auto-documentado)

Este archivo resume los componentes reales presentes en el repositorio (backend, frontend, docs, y utilidades) para completar y actualizar la documentación AIDLC.

## Estructura principal

- **backend/**: Motor del proyecto. Archivos y carpetas clave:
  - `main.py` — Punto de entrada del servidor FastAPI.
  - `index_docs.py` — Herramienta de índice/documentación (scripts auxiliares).
  - `requirements.txt` — Dependencias Python.
  - `test_phase1.py` — Tests iniciales o de integración ligera.
  - `src/` — Código fuente principal:
    - `settings.py` — Configuración central.
    - `agent/` — Implementación del grafo y nodes de agente (`agent_graph.py`, `helpers.py`, `llm_client.py`, `router.py`, `tool_executors.py`).
    - `api/` — Endpoints públicos y herramientas (`agent.py`, `files.py`, `network_analysis.py`, `reports.py`, `streaming.py`, `tools_router.py`).
    - `core/` — Gestión de estado, caché y sesiones (`cache.py`, `graph_state.py`, `redis_session_manager.py`, `state_manager.py`).
    - `models/` — Esquemas y DB helpers (`database.py`, `schemas.py`, `btm_schemas.py`).
    - `repositories/` — Integración con Qdrant/Postgres (`document_repository.py`, `qdrant_repository.py`, `session_repository.py`).
    - `services/` — Servicios de alto nivel (`band_steering_service.py`, `embeddings_service.py`, `fragment_extractor.py`).
    - `tools/` — Herramientas especializadas (`btm_analyzer.py`, `device_classifier.py`, `dns_tool.py`, `ip_tool.py`, `rag_tool.py`, `wireshark_tool.py`).
    - `utils/` — Utilidades (`embeddings.py`, `oui_lookup.py`, `ragas_callback.py`, `ragas_evaluator.py`, `text_processing.py`).

- **data/**: Contiene `analyses/`, `fragments/` y datos de entrada/salida organizados por fabricante.
- **docs/**: Documentación del proyecto; incluye AIDLC y PDFs técnicos.
- **frontend/**: SPA en React + Vite. Contenido clave:
  - `src/` — `App.jsx`, `main.jsx`, estilos y componentes (chat, files, análisis de red, etc.).
  - `package.json` — Dependencias y scripts frontend.

## Elementos detectados en el repo pero no o incompletamente referenciados en AIDLC

- `backend/index_docs.py`: script auxiliar para generación/actualización de documentación — añadir referencia en la sección de herramientas de desarrollo.
- `backend/test_phase1.py`: pruebas iniciales — incluir en la sección de testing (05_testing_strategy.md).
- `langgraph.json`: definición/plantilla del grafo — referenciar en diseño de componentes y en `03_component_design.md`.
- `docs/pdfs/Flujo.md`: flujo detallado del agente — vincular desde `01_inception_requirements.md` y `02_architecture_design.md`.

## Recomendaciones aplicadas

- Se eliminó la documentación operativa de despliegue (Docker/Heroku/Kubernetes) y los archivos de despliegue del repo.
- Asegurar que los módulos listados en este inventario tengan referencias cruzadas en los archivos AIDLC apropiados (`01`–`07`).

---

> Nota: este inventario es una captura automatizada y debe revisarse manualmente para ampliar descripciones técnicas o añadir referencias a líneas/funciones específicas cuando se desee.

````
