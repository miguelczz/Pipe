@echo off
REM Script de build para Pipe en Windows
REM Construye el frontend y lo copia al backend para servir en producción

echo 🔨 Construyendo Pipe...

REM 1. Construir el frontend
echo 📦 Construyendo frontend...
cd frontend
call npm install
call npm run build
cd ..

REM 2. Copiar el build del frontend al backend
echo 📋 Copiando frontend al backend...
if exist backend\frontend_dist (
    rmdir /s /q backend\frontend_dist
)
xcopy /E /I /Y frontend\dist backend\frontend_dist

echo ✅ Build completado!
echo 💡 El frontend está listo para ser servido por el backend en producción
