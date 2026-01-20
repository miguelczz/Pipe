"""
Aplicación principal de NetMind
"""
import logging
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from src.api import files, agent, streaming, tools_router, network_analysis
from src.models.database import init_db
import uvicorn

# Configuración centralizada de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(name)s] - [%(levelname)s] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

app = FastAPI(title="NetMind API")

# Configurar CORS para permitir comunicación con el frontend
cors_origins = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:3000",  # Alternativa
    "http://127.0.0.1:5173",
]

# Agregar origen de producción si está configurado
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    # Agregar la URL tal cual
    cors_origins.append(frontend_url)
    # Si no termina con /, agregar también la versión con /
    if not frontend_url.endswith("/"):
        cors_origins.append(f"{frontend_url}/")
    # Si termina con /, agregar también la versión sin /
    else:
        cors_origins.append(frontend_url.rstrip("/"))

# En Heroku, el frontend se sirve desde el mismo dominio, así que permitir el origen de Heroku
heroku_app_url = os.getenv("HEROKU_APP_URL")
if heroku_app_url:
    cors_origins.append(heroku_app_url)
    if not heroku_app_url.endswith("/"):
        cors_origins.append(f"{heroku_app_url}/")
    else:
        cors_origins.append(heroku_app_url.rstrip("/"))

# En desarrollo, permitir todos los orígenes (cambiar en producción)
if os.getenv("APP_ENV") != "production":
    cors_origins.append("*")

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
    init_db()

# Incluir routers de la API (deben ir antes del catch-all del frontend)
app.include_router(files.router)
app.include_router(agent.router)
app.include_router(streaming.router)
app.include_router(tools_router.router)
app.include_router(network_analysis.router)

# Configurar archivos estáticos del frontend (solo en producción)
# El directorio frontend_dist estará en el directorio backend (generado por build.sh)
static_dir = Path(__file__).parent / "frontend_dist"
if static_dir.exists() and os.getenv("APP_ENV") == "production":
    # Montar archivos estáticos (assets, CSS, JS, etc.)
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    
    # Servir archivos estáticos individuales (favicon, robots.txt, etc.)
    @app.get("/{filename:path}")
    async def serve_frontend(filename: str):
        # Excluir rutas de API
        if filename.startswith(("files/", "agent/", "streaming/", "docs", "openapi.json", "redoc")):
            return {"error": "Not found"}
        
        # Si es un archivo estático en la raíz, servirlo
        static_file = static_dir / filename
        if static_file.exists() and static_file.is_file() and static_file.is_relative_to(static_dir):
            return FileResponse(str(static_file))
        
        # Por defecto, servir index.html (para SPA routing)
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        
        return {"error": "Not found"}
else:
    @app.get("/")
    def root():
        return {"status": "ok", "message": "Backend API - Frontend no disponible en desarrollo"}

# para development
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
