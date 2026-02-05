/**
 * Constantes globales de la aplicación
 */

// URL de la API
// En producción (Heroku), usar URL relativa ya que frontend y backend están en el mismo dominio
// En desarrollo, usar la variable de entorno o localhost por defecto
const getApiUrl = () => {
    // Si estamos en producción y no hay VITE_API_URL configurada, usar URL relativa
    if (import.meta.env.PROD && !import.meta.env.VITE_API_URL) {
        return ""; // URL relativa - mismo dominio
    }
    // Usar variable de entorno o localhost por defecto
    return import.meta.env.VITE_API_URL || "http://localhost:8000";
};

export const API_URL = getApiUrl();

// Endpoints de la API
export const API_ENDPOINTS = {
    AGENT_QUERY: "/agent/query",
    AGENT_SESSION: "/agent/session",
    FILES_UPLOAD: "/files/upload",
    FILES_UPLOAD_MULTIPLE: "/files/upload-multiple",
    FILES_LIST: "/files/",
    FILES_DELETE: "/files",
};

// Configuración de sesión
export const SESSION_CONFIG = {
    STORAGE_KEY: "router_agent_session_id",
    MAX_CONTEXT_MESSAGES: 20,
};

// Configuración de UI
export const UI_CONFIG = {
    ANIMATION_DURATION: 200,
    DEBOUNCE_DELAY: 300,
    MESSAGE_MAX_WIDTH: "768px",
};

// Tipos de herramientas del agente
export const AGENT_TOOLS = {
    RAG: "rag",
    IP: "ip",
    DNS: "dns",
    NONE: "none",
};

// Nombres amigables de herramientas
export const TOOL_NAMES = {
    [AGENT_TOOLS.RAG]: "Búsqueda en Documentos",
    [AGENT_TOOLS.IP]: "Herramientas de Red",
    [AGENT_TOOLS.DNS]: "Consultas DNS",
    [AGENT_TOOLS.NONE]: "Sin herramienta",
};

export default {
    API_URL,
    API_ENDPOINTS,
    SESSION_CONFIG,
    UI_CONFIG,
    AGENT_TOOLS,
    TOOL_NAMES,
};
