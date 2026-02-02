#!/bin/bash
# Script de build para Pipe
# Construye el frontend y lo copia al backend para servir en producción

set -e

echo "🔨 Construyendo Pipe..."

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Construir el frontend
echo -e "${GREEN}📦 Construyendo frontend...${NC}"
cd frontend
npm install
npm run build
cd ..

# 2. Copiar el build del frontend al backend
echo -e "${GREEN}📋 Copiando frontend al backend...${NC}"
if [ -d "backend/frontend_dist" ]; then
    rm -rf backend/frontend_dist
fi
cp -r frontend/dist backend/frontend_dist

echo -e "${GREEN}✅ Build completado!${NC}"
echo -e "${YELLOW}💡 El frontend está listo para ser servido por el backend en producción${NC}"
