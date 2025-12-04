#!/bin/bash
# Script de build para Heroku
# Este script compila el frontend y lo copia al directorio backend/frontend_dist

set -e

echo "🔨 Iniciando build para Heroku..."

# Copiar requirements.txt del backend a la raíz (necesario para Heroku Python buildpack)
echo "📋 Copiando requirements.txt del backend a la raíz..."
cp backend/requirements.txt requirements.txt

# Navegar al directorio del frontend
cd frontend

# Instalar dependencias (incluyendo devDependencies para el build)
echo "📦 Instalando dependencias del frontend..."
npm ci --include=dev

# Construir el frontend
echo "🏗️  Construyendo el frontend..."
npm run build

# Crear directorio de destino en el backend
echo "📁 Copiando archivos estáticos al backend..."
cd ..
mkdir -p backend/frontend_dist

# Copiar archivos construidos
cp -r frontend/dist/* backend/frontend_dist/

echo "✅ Archivos copiados a backend/frontend_dist/"
echo "✅ Build completado exitosamente!"
echo "📦 Los archivos del frontend están en backend/frontend_dist/"