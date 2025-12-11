import { Link, useLocation } from 'react-router-dom'
import { MessageSquare, FileText, Trash2 } from 'lucide-react'
import { cn } from '../../utils/cn'
import { useChatContext } from '../../contexts/ChatContext'
import { Button } from '../ui/Button'
import { Logo } from '../common/Logo'

/**
 * Layout principal de la aplicación
 * @param {Object} props
 * @param {React.ReactNode} props.children - Contenido a renderizar
 */
export function Layout({ children }) {
  const location = useLocation()
  const { clearChatAction, hasMessages } = useChatContext()

  const navItems = [
    { path: '/', label: 'Chat', icon: MessageSquare },
    { path: '/files', label: 'Archivos', icon: FileText },
  ]

  return (
    <div className="min-h-screen bg-dark-bg-primary flex flex-col overflow-x-hidden w-full">
      {/* Header moderno inspirado en los mejores diseños de IA - Fijo en móvil */}
      <header className="border-b border-dark-border-primary/30 bg-dark-bg-primary/95 backdrop-blur-xl fixed top-0 left-0 right-0 z-50 shadow-gemini-sm overflow-x-hidden w-full min-w-0">
        <div className="container-app w-full min-w-0">
          <div className="flex items-center justify-between h-14 sm:h-16">
            <div className="flex items-center gap-2 sm:gap-4">
              {/* Logo de telecomunicaciones */}
              <Logo size="md" />
              <div>
                <h1 className="text-base sm:text-lg font-medium text-dark-text-primary tracking-tight">
                  NetMind
                </h1>
                <p className="text-[10px] sm:text-xs text-dark-text-muted -mt-0.5">Asistente Inteligente</p>
              </div>
            </div>

            <nav className="flex items-center gap-1 sm:gap-2">
              {/* Botón de limpiar conversación - solo en chat y cuando hay mensajes */}
              {location.pathname === '/' && hasMessages && clearChatAction && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearChatAction}
                  className="text-dark-text-muted hover:text-dark-status-error hover:bg-dark-status-error/10 rounded-xl transition-all duration-200 p-1.5 sm:p-2"
                >
                  <Trash2 className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                  <span className="hidden sm:inline ml-1.5">Limpiar</span>
                </Button>
              )}
              {navItems.map((item) => {
                const Icon = item.icon
                const isActive = location.pathname === item.path

                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={cn(
                      'flex items-center gap-1 sm:gap-2 px-2 sm:px-4 py-1.5 sm:py-2 rounded-xl transition-all duration-200',
                      'font-medium text-xs sm:text-sm',
                      isActive
                        ? 'bg-dark-accent-primary text-white shadow-gemini-sm'
                        : 'text-dark-text-secondary hover:text-dark-text-primary hover:bg-dark-surface-hover'
                    )}
                  >
                    <Icon className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                    <span className="hidden sm:inline">{item.label}</span>
                  </Link>
                )
              })}
            </nav>
          </div>
        </div>
      </header>

      {/* Main Content con padding top para compensar el header fijo */}
      <main className="flex-1 flex flex-col overflow-hidden min-h-0 overflow-x-hidden w-full min-w-0 pt-14 sm:pt-16">
        {children}
      </main>

      {/* Footer minimalista - oculto en chat */}
      {location.pathname !== '/' && (
        <footer className="border-t border-dark-border-primary/30 bg-dark-bg-primary/50 backdrop-blur-sm py-4">
          <div className="container-app">
            <p className="text-center text-xs text-dark-text-muted">
              NetMind - Sistema inteligente de enrutamiento de consultas
            </p>
          </div>
        </footer>
      )}
    </div>
  )
}

export default Layout

