import { Link, useLocation } from 'react-router-dom'
import { FileText, Activity, History } from 'lucide-react'
import { cn } from '../../utils/cn'
import { Logo } from '../common/Logo'
import { useChatLayout } from '../../contexts/ChatLayoutContext'

/**
 * Layout principal de la aplicación
 * @param {Object} props
 * @param {React.ReactNode} props.children - Contenido a renderizar
 */
export function Layout({ children }) {
  const location = useLocation()
  const { chatWidth, chatSide, chatPanelOpen } = useChatLayout()

  // Log temporal para depuración
  console.log('Layout render:', { chatWidth, chatSide, chatPanelOpen })

  const navItems = [
    { path: '/files', label: 'Archivos', icon: FileText },
    { path: '/network-analysis', label: 'Pruebas', icon: Activity },
    { path: '/reports', label: 'Reportes', icon: History },
  ]

  const marginLeft = chatPanelOpen && chatSide === 'left' ? `${chatWidth}px` : '0'
  const marginRight = chatPanelOpen && chatSide === 'right' ? `${chatWidth}px` : '0'
  
  console.log('Calculated margins:', { marginLeft, marginRight })

  return (
    <div 
      className="min-h-screen bg-dark-bg-primary flex flex-col overflow-x-hidden w-full transition-all duration-[450ms] ease-[cubic-bezier(0.4,0,0.2,1)]"
      style={{
        marginLeft,
        marginRight
      }}
    >
      {/* Header moderno inspirado en los mejores diseños de IA - Ahora se mueve con el contenido */}
      <header className="border-b border-dark-border-primary/30 bg-dark-bg-primary/95 backdrop-blur-xl z-40 shadow-gemini-sm overflow-x-hidden w-full min-w-0">
        <div className="container-app w-full min-w-0">
          <div className="flex items-center justify-between h-14 sm:h-16">
            <div className="flex items-center gap-2 sm:gap-4">
              {/* Logo de telecomunicaciones */}
              <Logo size="md" />
              <div>
                <h1 className="text-base sm:text-lg font-medium text-dark-text-primary tracking-tight">
                  Pipe
                </h1>
                <p className="text-[10px] sm:text-xs text-dark-text-muted -mt-0.5">Análisis de Capturas Wireshark</p>
              </div>
            </div>

            <nav className="flex items-center gap-1 sm:gap-2">
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

      {/* Main Content sin padding top ya que el header no es fijo */}
      <main className="flex-1 flex flex-col overflow-hidden min-h-0 overflow-x-hidden w-full min-w-0">
        {children}
      </main>

      {/* Footer minimalista - oculto en chat */}
      {location.pathname !== '/' && (
        <footer className="border-t border-dark-border-primary/30 bg-dark-bg-primary/50 backdrop-blur-sm py-4">
          <div className="container-app">
            <p className="text-center text-xs text-dark-text-muted">
              Pipe - Análisis inteligente de capturas Wireshark
            </p>
          </div>
        </footer>
      )}
    </div>
  )
}

export default Layout
