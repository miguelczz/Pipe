import axios from 'axios';

// Determinar la URL base dinámicamente
const getBaseUrl = () => {
  // 1. Si hay una variable de entorno explícita, usarla.
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }

  const hostname = window.location.hostname;

  // 2. Detección de entorno local (localhost o IPs privadas típicas 192.168.x.x, 10.x.x.x)
  const isLocalDev = 
    hostname === 'localhost' || 
    hostname === '127.0.0.1' || 
    hostname.startsWith('192.168.') ||
    hostname.startsWith('10.');

  if (isLocalDev) {
      return `http://${hostname}:8000`;
  }

  // 3. Producción (Heroku, Vercel, etc): Usar ruta relativa.
  // Esto asume que el backend sirve tanto el frontend como la API en el mismo puerto.
  return '';
};

const api = axios.create({
  baseURL: getBaseUrl(),
});

export default api;
