/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Tema oscuro estilo Google Gemini
        dark: {
          bg: {
            primary: '#0a0a0f',      // Negro azulado profundo
            secondary: '#121218',    // Gris azulado oscuro
            tertiary: '#1a1a24',      // Gris azulado medio
          },
          surface: {
            primary: '#161620',      // Superficie principal
            secondary: '#1e1e2a',    // Superficie secundaria
            hover: '#252532',        // Hover
          },
          border: {
            primary: '#2a2a3a',      // Borde principal
            secondary: '#3a3a4a',    // Borde secundario
            focus: '#6366f1',        // Focus índigo
          },
          text: {
            primary: '#e4e4e7',      // Texto principal
            secondary: '#a1a1aa',    // Texto secundario
            muted: '#71717a',        // Texto muted
            disabled: '#52525b',     // Texto deshabilitado
          },
          accent: {
            primary: '#6366f1',      // Índigo vibrante
            hover: '#4f46e5',        // Índigo oscuro
            active: '#4338ca',       // Índigo más oscuro
            secondary: '#06b6d4',   // Cyan complementario
          },
          success: '#10b981',        // Verde esmeralda
          warning: '#f59e0b',        // Ámbar
          error: '#ef4444',          // Rojo
        },
      },
      fontFamily: {
        sans: ['Google Sans Text', 'Google Sans', 'system-ui', '-apple-system', 'sans-serif'],
      },
      borderRadius: {
        'xl': '0.75rem',
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
      boxShadow: {
        'gemini': '0 1px 3px 0 rgba(0, 0, 0, 0.3), 0 4px 6px -2px rgba(0, 0, 0, 0.2)',
        'gemini-lg': '0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 10px 15px -3px rgba(0, 0, 0, 0.2)',
        'gemini-sm': '0 1px 2px 0 rgba(0, 0, 0, 0.2)',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
        'slide-in-right': 'slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
        'scale-in': 'scaleIn 0.2s ease-out',
        'fade-in-up': 'fadeInUp 0.3s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideInRight: {
          '0%': { transform: 'translateX(100%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        scaleIn: {
          '0%': { transform: 'scale(0.95)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        fadeInUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}

