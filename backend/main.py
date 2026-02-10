"""
Aplicación principal de Pipe
"""
import logging
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.api import files, agent, streaming, tools_router, network_analysis, reports
from src.models.database import init_db
import uvicorn

# Configuración centralizada de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(name)s] - [%(levelname)s] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
# Silenciar logs verbosos de fontTools (WeasyPrint) al generar PDFs
logging.getLogger("fontTools").setLevel(logging.WARNING)

# Logger para este módulo
logger = logging.getLogger(__name__)

app = FastAPI(title="Pipe API - Análisis de Capturas Wireshark", description="API para análisis inteligente de capturas de red, Band Steering y protocolos 802.11k/v/r")

# CORS: Frontend se sirve desde el mismo dominio (mismo contenedor)
cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar base de datos al arrancar
@app.on_event("startup")
async def startup_event():
    """Inicializa las tablas de la base de datos al arrancar la aplicación"""
    try:
        init_db()
        logger.info("Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"Error al inicializar la base de datos: {e}")
        raise

# Incluir routers de la API (deben ir antes del catch-all del frontend)
app.include_router(files.router)
app.include_router(agent.router)
app.include_router(streaming.router)
app.include_router(tools_router.router)
app.include_router(network_analysis.router)
app.include_router(reports.router)

# Redirección explícita para /reports sin barra (FastAPI no siempre redirige automáticamente)
@app.get("/reports", include_in_schema=False)
async def redirect_reports():
    """Redirige /reports a /reports/"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/reports/", status_code=301)

# Servir frontend compilado desde /frontend_dist
static_dir = Path(__file__).parent / "frontend_dist"

if static_dir.exists():
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{filename:path}")
    async def serve_frontend(filename: str):
        api_prefixes = ("files", "agent", "streaming", "network-analysis", "reports",
                        "docs", "openapi.json", "redoc")
        if any(filename == r or filename.startswith(f"{r}/") for r in api_prefixes):
            return {"error": "Not found"}

        static_file = static_dir / filename
        if static_file.exists() and static_file.is_file() and static_file.is_relative_to(static_dir):
            return FileResponse(str(static_file))

        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))

        return {"error": "Not found"}
else:
    logger.warning("frontend_dist no encontrado, solo API disponible")

    @app.get("/")
    def root():
        return {"status": "ok", "message": "Pipe API", "version": "1.0.0"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
