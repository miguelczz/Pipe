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
    try:
        init_db()
    except Exception as e:
        # Detectar si el error es por hostname de Docker
        error_msg = str(e)
        is_docker_hostname_error = "pipe-postgres" in error_msg or "could not translate host name" in error_msg.lower()
        
        if is_docker_hostname_error:
            # Si está ejecutándose fuera de Docker pero el .env tiene hostname de Docker
            logger.error("❌ Error de conexión a PostgreSQL:")
            logger.error("   El hostname 'pipe-postgres' es un nombre de servicio de Docker.")
            logger.error("   ")
            logger.error("   SOLUCIONES:")
            logger.error("   1. Si estás en DESARROLLO LOCAL (fuera de Docker):")
            logger.error("      Cambia en tu .env: POSTGRES_HOST=localhost")
            logger.error("   2. Si estás en PRODUCCIÓN (con Docker):")
            logger.error("      Ejecuta: docker-compose up -d")
            logger.error("      El hostname 'pipe-postgres' es correcto dentro de Docker.")
            logger.error("   ")
            logger.error("   La aplicación NO puede continuar sin base de datos.")
            # En producción, no debería continuar sin BD
            if os.getenv("APP_ENV") == "production":
                raise
        else:
            logger.error(f"❌ Error al inicializar la base de datos: {e}")
            # En producción, no debería continuar sin BD
            if os.getenv("APP_ENV") == "production":
                raise
        
        # Solo en desarrollo, permitir continuar sin BD
        if os.getenv("APP_ENV") != "production":
            logger.warning("   ⚠️ Modo desarrollo: La aplicación continuará sin base de datos.")
            logger.warning("   Algunas funcionalidades pueden no estar disponibles.")

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

# Configurar archivos estáticos del frontend (solo en producción)
# El directorio frontend_dist estará en el directorio backend (generado por build.sh)
static_dir = Path(__file__).parent / "frontend_dist"
if static_dir.exists() and os.getenv("APP_ENV") == "production":
    # Montar archivos estáticos (assets, CSS, JS, etc.)
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    
    # Servir archivos estáticos individuales (favicon, robots.txt, etc.)
    # IMPORTANTE: Esta ruta debe ir DESPUÉS de todos los routers de API
    # FastAPI evalúa las rutas en orden, así que las rutas más específicas deben ir primero
    @app.get("/{filename:path}")
    async def serve_frontend(filename: str):
        # Excluir rutas de API para evitar conflictos
        # IMPORTANTE: No interceptar rutas de API - estas ya fueron manejadas por los routers
        # Solo servir archivos estáticos que realmente existan
        api_routes_prefixes = ("files", "agent", "streaming", "network-analysis", "reports", 
                              "docs", "openapi.json", "redoc")
        # Si la ruta comienza con un prefijo de API, no servirla como archivo estático
        if any(filename == route or filename.startswith(f"{route}/") for route in api_routes_prefixes):
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
        return {"status": "ok", "message": "Pipe API - Análisis de capturas Wireshark", "version": "1.0.0"}

# para development
if __name__ == "__main__":
    import socket
    # Permitir configurar el puerto mediante variable de entorno, por defecto 8000
    port = int(os.getenv("PORT", 8000))
    
    # Verificar si el puerto está disponible
    def is_port_available(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return True
            except OSError:
                return False
    
    # Si el puerto no está disponible, intentar con 8001
    if not is_port_available(port):
        print(f"⚠️  Puerto {port} no disponible. Usando puerto 8001...")
        port = 8001
        if not is_port_available(port):
            print(f"❌ Puerto {port} tampoco está disponible. Por favor, cierra otros procesos o usa otro puerto.")
            print(f"💡 Ejecuta: uvicorn main:app --reload --port 8002")
            exit(1)
    
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True)
