#!/bin/bash
# Script de inicio para Pipe en servidor
# Uso: ./start.sh [start|stop|restart|status|logs]

set -e

COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Función para verificar si .env existe
check_env() {
    if [ ! -f "$ENV_FILE" ]; then
        echo -e "${YELLOW}Advertencia: Archivo .env no encontrado${NC}"
        echo -e "${YELLOW}Creando .env desde .env.example...${NC}"
        if [ -f ".env.example" ]; then
            cp .env.example .env
            echo -e "${RED}IMPORTANTE: Edita el archivo .env con tus credenciales antes de continuar${NC}"
            exit 1
        else
            echo -e "${RED}Error: No se encontró .env.example${NC}"
            exit 1
        fi
    fi
}

# Función para iniciar servicios
start_services() {
    echo -e "${GREEN}Iniciando servicios Pipe...${NC}"
    check_env
    docker-compose -f $COMPOSE_FILE up -d
    echo -e "${GREEN}Servicios iniciados. Verifica el estado con: ./start.sh status${NC}"
}

# Función para detener servicios
stop_services() {
    echo -e "${YELLOW}Deteniendo servicios Pipe...${NC}"
    docker-compose -f $COMPOSE_FILE down
    echo -e "${GREEN}Servicios detenidos${NC}"
}

# Función para reiniciar servicios
restart_services() {
    echo -e "${YELLOW}Reiniciando servicios Pipe...${NC}"
    check_env
    docker-compose -f $COMPOSE_FILE restart
    echo -e "${GREEN}Servicios reiniciados${NC}"
}

# Función para ver estado
status_services() {
    echo -e "${GREEN}Estado de los servicios:${NC}"
    docker-compose -f $COMPOSE_FILE ps
    echo ""
    echo -e "${GREEN}Health checks:${NC}"
    docker-compose -f $COMPOSE_FILE ps --format json | jq -r '.[] | "\(.Name): \(.Health)"' 2>/dev/null || docker-compose -f $COMPOSE_FILE ps
}

# Función para ver logs
logs_services() {
    if [ -z "$2" ]; then
        docker-compose -f $COMPOSE_FILE logs -f
    else
        docker-compose -f $COMPOSE_FILE logs -f "$2"
    fi
}

# Función para actualizar
update_services() {
    echo -e "${GREEN}Actualizando servicios Pipe...${NC}"
    check_env
    docker-compose -f $COMPOSE_FILE pull
    docker-compose -f $COMPOSE_FILE up -d --build
    echo -e "${GREEN}Servicios actualizados${NC}"
}

# Función para modo desarrollo (hot-reload)
dev_services() {
    echo -e "${GREEN}Iniciando servicios Pipe en modo DESARROLLO (hot-reload)...${NC}"
    check_env
    docker-compose -f $COMPOSE_FILE -f docker-compose.dev.yml up -d --build pipe-backend
    echo -e "${GREEN}Servicios en modo desarrollo iniciados. Los cambios en el código se aplicarán automáticamente.${NC}"
    echo -e "${GREEN}Verifica el estado con: ./start.sh status${NC}"
}

# Función para limpiar (solo contenedores de Pipe)
clean_services() {
    echo -e "${YELLOW}Limpiando contenedores y volúmenes de Pipe SOLAMENTE...${NC}"
    echo ""
    echo -e "${YELLOW}ADVERTENCIA: Esto eliminará los contenedores y volúmenes de Pipe.${NC}"
    echo -e "${YELLOW}No se afectarán otros proyectos Docker.${NC}"
    echo ""
    # Detener y eliminar contenedores de docker-compose (solo Pipe)
    docker-compose -f $COMPOSE_FILE down -v 2>/dev/null
    # Eliminar contenedores específicos por nombre (solo Pipe)
    echo -e "${GREEN}Eliminando contenedores de Pipe por nombre...${NC}"
    docker rm -f pipe-backend pipe-postgres pipe-qdrant pipe-redis 2>/dev/null
    # Eliminar solo contenedores detenidos que tengan nombres de Pipe
    echo -e "${GREEN}Buscando y eliminando contenedores huérfanos de Pipe...${NC}"
    docker ps -a --filter "name=pipe-" --format "{{.ID}}" 2>/dev/null | while read container_id; do
        if [ ! -z "$container_id" ]; then
            echo "Eliminando contenedor: $container_id"
            docker rm -f "$container_id" 2>/dev/null
        fi
    done
    echo ""
    echo -e "${GREEN}Limpieza de Pipe completada.${NC}"
    echo -e "${GREEN}NOTA: Otros contenedores Docker no fueron afectados.${NC}"
}

# Main
case "$1" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    status)
        status_services
        ;;
    logs)
        logs_services "$@"
        ;;
    update)
        update_services
        ;;
    dev)
        dev_services
        ;;
    clean)
        clean_services
        ;;
    *)
        echo "Uso: $0 {start|stop|restart|status|logs [service]|update|dev|clean}"
        echo ""
        echo "Comandos:"
        echo "  start   - Inicia todos los servicios"
        echo "  stop    - Detiene todos los servicios"
        echo "  restart - Reinicia todos los servicios"
        echo "  status  - Muestra el estado de los servicios"
        echo "  logs    - Muestra logs (opcional: nombre del servicio)"
        echo "  update  - Actualiza y reconstruye los servicios"
        echo "  dev     - Inicia en modo desarrollo con hot-reload (cambios automáticos)"
        echo "  clean   - Limpia SOLO contenedores y volúmenes de Pipe (no afecta otros proyectos)"
        exit 1
        ;;
esac

exit 0
