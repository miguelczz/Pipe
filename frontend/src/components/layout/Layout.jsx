import { Link, useLocation } from 'react-router-dom'
import React, { useEffect, useRef, useCallback } from 'react'
import { FileText, Activity, History, MessageCircle, BarChart2 } from 'lucide-react'
import { cn } from '../../utils/cn'
import { Logo } from '../common/Logo'
import { useChatLayout } from '../../contexts/ChatLayoutContext'
import { useGlobalChat } from '../../contexts/GlobalChatContext'
import { useChat } from '../../hooks/useChat'
import { Button } from '../ui/Button'
import { GlobalChatPanel } from '../chat/GlobalChatPanel'

/**
 * Layout principal de la aplicación
 * @param {Object} props
 * @param {React.ReactNode} props.children - Contenido a renderizar
 */
export function Layout({ children }) {
  const location = useLocation()
  const { chatWidth, chatSide, chatPanelOpen, setChatPanelOpen } = useChatLayout()
  const globalChat = useGlobalChat()
  const chat = useChat()
  
  const chatRef = useRef(chat)
  chatRef.current = chat

  // Exponer sendMessage via ref para que las páginas puedan llamarlo con extras
  globalChat.sendMessageRef.current = chat.sendMessage

  // Función para configurar los callbacks por defecto del chat global
  const setupDefaultCallbacks = useCallback(() => {
    globalChat.setCallbacks({
      onSend: (content, contextText) => chatRef.current.sendMessage(content, contextText),
      onClearMessages: () => chatRef.current.clearMessages(),
      onSaveEditedMessage: (message, newContent) => {
        if (message?.role === 'user' && newContent) {
          chatRef.current.sendMessageAfterEdit(message, newContent)
        }
      },
    })
    globalChat.setDisabled(false)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Configurar callbacks por defecto al montar
  useEffect(() => {
    setupDefaultCallbacks()
  }, [setupDefaultCallbacks])

  // Restaurar callbacks por defecto cuando onSend queda null
  // (esto ocurre cuando una página llama clearCallbacks al desmontarse)
  useEffect(() => {
    if (!globalChat.onSend) {
      setupDefaultCallbacks()
    }
  }, [globalChat.onSend, setupDefaultCallbacks])

  // Sincronizar mensajes con el GlobalChatContext
  useEffect(() => {
    globalChat.setMessages(chat.messages)
  }, [chat.messages]) // eslint-disable-line react-hooks/exhaustive-deps

  // Sincronizar estado de carga
  useEffect(() => {
    globalChat.setIsLoading(chat.isLoading)
  }, [chat.isLoading]) // eslint-disable-line react-hooks/exhaustive-deps

  const navItems = [
    { path: '/files', label: 'Archivos', icon: FileText },
    { path: '/network-analysis', label: 'Pruebas', icon: Activity },
    { path: '/reports', label: 'Reportes', icon: History },
    { path: '/observability', label: 'Monitoreo', icon: BarChart2 },
  ]

  // Padding dinámico para que el contenido se comprima al abrir el chat (no se superpone)
  const paddingLeft = chatPanelOpen && chatSide === 'left' ? chatWidth : 0
  const paddingRight = chatPanelOpen && chatSide === 'right' ? chatWidth : 0

  return (
    <div 
      className="min-h-screen bg-dark-bg-primary flex flex-col overflow-x-hidden w-full transition-[padding] duration-[450ms] ease-[cubic-bezier(0.4,0,0.2,1)]"
      style={{
        paddingLeft,
        paddingRight
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
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setChatPanelOpen(!chatPanelOpen)}
                className={cn(
                  'ml-auto px-2 sm:px-3 py-1.5 sm:py-2 rounded-xl transition-all duration-200 flex items-center gap-1 sm:gap-2',
                  'text-xs sm:text-sm font-medium',
                  chatPanelOpen
                    ? 'bg-dark-accent-primary/10 text-dark-accent-primary'
                    : 'text-dark-text-secondary hover:text-dark-text-primary hover:bg-dark-surface-hover'
                )}
                title={chatPanelOpen ? 'Cerrar chat' : 'Abrir chat'}
              >
                <MessageCircle className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                <span className="hidden sm:inline">Chat</span>
              </Button>
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

      {/* Panel de chat global en todas las páginas */}
      <GlobalChatPanel />
    </div>
  )
}

export default Layout
