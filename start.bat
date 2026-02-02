@echo off
REM Script de inicio para Pipe en servidor Windows
REM Uso: start.bat [start|stop|restart|status|logs]

set COMPOSE_FILE=docker-compose.yml
set ENV_FILE=.env

if "%1"=="start" goto start
if "%1"=="stop" goto stop
if "%1"=="restart" goto restart
if "%1"=="status" goto status
if "%1"=="logs" goto logs
if "%1"=="update" goto update
if "%1"=="dev" goto dev
if "%1"=="clean" goto clean
goto usage

:start
echo Iniciando servicios Pipe...
if not exist %ENV_FILE% (
    echo Advertencia: Archivo .env no encontrado
    if exist .env.example (
        copy .env.example .env
        echo IMPORTANTE: Edita el archivo .env con tus credenciales antes de continuar
        exit /b 1
    ) else (
        echo Error: No se encontro .env.example
        exit /b 1
    )
)
REM Limpiar contenedores detenidos si existen
echo Limpiando contenedores anteriores si existen...
docker-compose -f %COMPOSE_FILE% down 2>nul
REM Eliminar contenedores huerfanos por nombre
docker rm -f pipe-backend pipe-postgres pipe-qdrant pipe-redis 2>nul
docker-compose -f %COMPOSE_FILE% up -d
echo Servicios iniciados. Verifica el estado con: start.bat status
goto end

:stop
echo Deteniendo servicios Pipe...
docker-compose -f %COMPOSE_FILE% down
echo Servicios detenidos
goto end

:restart
echo Reiniciando servicios Pipe...
docker-compose -f %COMPOSE_FILE% restart
echo Servicios reiniciados
goto end

:status
echo Estado de los servicios:
docker-compose -f %COMPOSE_FILE% ps
goto end

:logs
if "%2"=="" (
    docker-compose -f %COMPOSE_FILE% logs -f
) else (
    docker-compose -f %COMPOSE_FILE% logs -f %2
)
goto end

:update
echo Actualizando servicios Pipe...
docker-compose -f %COMPOSE_FILE% pull
docker-compose -f %COMPOSE_FILE% up -d --build
echo Servicios actualizados
goto end

:dev
echo Iniciando servicios Pipe en modo DESARROLLO (hot-reload)...
if not exist %ENV_FILE% (
    echo Advertencia: Archivo .env no encontrado
    if exist .env.example (
        copy .env.example .env
        echo IMPORTANTE: Edita el archivo .env con tus credenciales antes de continuar
        exit /b 1
    ) else (
        echo Error: No se encontro .env.example
        exit /b 1
    )
)
REM Limpiar contenedores huerfanos antes de iniciar
echo Limpiando contenedores huerfanos...
docker rm -f pipe-backend pipe-postgres pipe-qdrant pipe-redis 2>nul
REM Asegurar que los servicios base esten corriendo primero
echo Iniciando servicios base (postgres, qdrant, redis)...
docker-compose -f %COMPOSE_FILE% up -d pipe-postgres pipe-qdrant pipe-redis
REM Esperar un momento para que los servicios base esten listos
timeout /t 5 /nobreak >nul
REM Iniciar backend en modo desarrollo
echo Iniciando backend en modo desarrollo...
docker-compose -f %COMPOSE_FILE% -f docker-compose.dev.yml up -d --build pipe-backend
echo Servicios en modo desarrollo iniciados. Los cambios en el codigo se aplicaran automaticamente.
echo Verifica el estado con: start.bat status
goto end

:clean
echo Limpiando contenedores y volúmenes de Pipe SOLAMENTE...
echo.
echo ADVERTENCIA: Esto eliminara los contenedores y volúmenes de Pipe.
echo No se afectaran otros proyectos Docker.
echo.
REM Detener y eliminar contenedores de docker-compose (solo Pipe)
docker-compose -f %COMPOSE_FILE% down -v 2>nul
REM Eliminar contenedores específicos por nombre (solo Pipe, por si hay huerfanos)
echo Eliminando contenedores de Pipe por nombre...
docker rm -f pipe-backend pipe-postgres pipe-qdrant pipe-redis 2>nul
REM Eliminar solo contenedores detenidos que tengan nombres de Pipe
echo Buscando y eliminando contenedores huerfanos de Pipe...
for /f "tokens=*" %%i in ('docker ps -a --filter "name=pipe-" --format "{{.ID}}" 2^>nul') do (
    echo Eliminando contenedor: %%i
    docker rm -f %%i 2>nul
)
echo.
echo Limpieza de Pipe completada.
echo NOTA: Otros contenedores Docker no fueron afectados.
goto end

:usage
echo Uso: %0 {start^|stop^|restart^|status^|logs [service]^|update^|dev^|clean}
echo.
echo Comandos:
echo   start   - Inicia todos los servicios
echo   stop    - Detiene todos los servicios
echo   restart - Reinicia todos los servicios
echo   status  - Muestra el estado de los servicios
echo   logs    - Muestra logs (opcional: nombre del servicio)
echo   update  - Actualiza y reconstruye los servicios
echo   dev     - Inicia en modo desarrollo con hot-reload (cambios automaticos)
echo   clean   - Limpia SOLO contenedores y volúmenes de Pipe (no afecta otros proyectos)
exit /b 1

:end
exit /b 0
