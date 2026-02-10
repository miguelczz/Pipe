/**
 * Variables globales de colores personalizados
 * Paleta inspirada en Google Gemini
 */
export const colors = {
  // Colores de fondo - estilo Gemini
  background: {
    primary: '#0a0a0f',      // Negro azulado profundo
    secondary: '#121218',   // Gris azulado oscuro
    tertiary: '#1a1a24',     // Gris azulado medio
  },

  // Colores de superficie - estilo Gemini
  surface: {
    primary: '#161620',      // Superficie principal
    secondary: '#1e1e2a',   // Superficie secundaria
    hover: '#252532',       // Hover
  },

  // Colores de borde - estilo Gemini
  border: {
    primary: '#2a2a3a',      // Borde principal
    secondary: '#3a3a4a',   // Borde secundario
    focus: '#6366f1',       // Focus índigo
  },

  // Colores de texto - estilo Gemini
  text: {
    primary: '#e4e4e7',      // Texto principal
    secondary: '#a1a1aa',    // Texto secundario
    muted: '#71717a',       // Texto muted
    disabled: '#52525b',    // Texto deshabilitado
  },

  // Colores de acento - estilo Gemini (índigo/cyan)
  accent: {
    primary: '#6366f1',      // Índigo vibrante
    hover: '#4f46e5',        // Índigo oscuro
    active: '#4338ca',       // Índigo más oscuro
    light: '#818cf8',        // Índigo claro
    secondary: '#06b6d4',   // Cyan complementario
  },

  // Colores de estado - más vibrantes
  status: {
    success: '#10b981',      // Verde esmeralda
    warning: '#f59e0b',      // Ámbar
    error: '#ef4444',        // Rojo
    info: '#3b82f6',        // Azul
  },
}

/**
 * Clases de Tailwind para uso en componentes
 */
export const colorClasses = {
  bg: {
    primary: 'bg-dark-bg-primary',
    secondary: 'bg-dark-bg-secondary',
    tertiary: 'bg-dark-bg-tertiary',
  },
  surface: {
    primary: 'bg-dark-surface-primary',
    secondary: 'bg-dark-surface-secondary',
    hover: 'hover:bg-dark-surface-hover',
  },
  border: {
    primary: 'border-dark-border-primary',
    secondary: 'border-dark-border-secondary',
    focus: 'border-dark-border-focus',
  },
  text: {
    primary: 'text-dark-text-primary',
    secondary: 'text-dark-text-secondary',
    muted: 'text-dark-text-muted',
    disabled: 'text-dark-text-disabled',
  },
  accent: {
    primary: 'bg-dark-accent-primary',
    hover: 'hover:bg-dark-accent-hover',
    active: 'active:bg-dark-accent-active',
  },
}

export default colors

