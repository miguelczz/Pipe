# NetMind - Frontend

Frontend moderno y minimalista para NetMind, construido con React, Vite y Tailwind CSS.

## 🚀 Características

- **Interfaz minimalista** con tema oscuro
- **Chat interactivo** con el agente inteligente
- **Gestión de archivos** PDF
- **Diseño responsive** para todos los dispositivos
- **Código modular** y mantenible
- **Variables globales de color** para fácil personalización

## 📦 Instalación

1. Instalar dependencias:
```bash
npm install
```

2. Configurar variables de entorno:
Crea un archivo `.env` en la raíz del frontend:
```env
VITE_API_URL=http://localhost:8000
```

3. Iniciar servidor de desarrollo:
```bash
npm run dev
```

El frontend estará disponible en `http://localhost:5173`

## 🏗️ Estructura del Proyecto

```
frontend/
├── src/
│   ├── components/      # Componentes React
│   │   ├── ui/         # Componentes base reutilizables
│   │   ├── chat/       # Componentes de chat
│   │   └── layout/     # Componentes de layout
│   ├── pages/          # Páginas de la aplicación
│   ├── hooks/          # Custom hooks
│   ├── services/       # Servicios API
│   ├── config/         # Configuración y constantes
│   ├── utils/          # Utilidades
│   ├── App.jsx         # Componente principal
│   └── main.jsx        # Punto de entrada
├── package.json
├── vite.config.js
└── tailwind.config.js
```

## 🎨 Variables de Color

Los colores están centralizados en `src/config/colors.js` y `tailwind.config.js` para fácil personalización.

## 🔧 Scripts Disponibles

- `npm run dev` - Inicia servidor de desarrollo
- `npm run build` - Construye para producción
- `npm run preview` - Previsualiza build de producción
- `npm run lint` - Ejecuta el linter

## 📝 Notas

- Asegúrate de que el backend FastAPI esté corriendo en el puerto 8000
- El backend debe tener CORS configurado para permitir peticiones desde `http://localhost:5173`

