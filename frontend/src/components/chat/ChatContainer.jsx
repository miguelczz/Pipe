import { useEffect, useRef } from 'react'
import { Bot } from 'lucide-react'
import { Message } from './Message'
import { Loading } from '../ui/Loading'
import { Logo } from '../common/Logo'
import { cn } from '../../utils/cn'

/**
 * Contenedor principal del chat
 * @param {Object} props
 * @param {Array} props.messages - Array de mensajes
 * @param {boolean} props.isLoading - Si está cargando
 */
export function ChatContainer({ messages, isLoading }) {
  const messagesEndRef = useRef(null)
  const containerRef = useRef(null)

  // Auto-scroll inteligente
  useEffect(() => {
    const container = containerRef.current
    if (!container || !messagesEndRef.current) return

    // Verificar si el usuario está cerca del final (umbral de 100px)
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100

    // Si es un mensaje nuevo (no streaming) o el usuario está cerca del final, hacer scroll
    // Si está leyendo arriba (isNearBottom false), NO forzar scroll
    if (isNearBottom || !isLoading) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isLoading])

  return (
    <div
      ref={containerRef}
      className={cn(
        'flex-1 overflow-x-hidden',
        messages.length === 0 
          ? 'overflow-hidden flex items-center justify-center' 
          : 'overflow-y-auto scrollbar-thin scrollbar-thumb-dark-border-primary scrollbar-track-dark-bg-primary'
      )}
    >
      {messages.length === 0 ? (
        <div className="w-full px-4 py-8 sm:py-12">
          <div className="text-center max-w-2xl mx-auto">
            <div className="flex justify-center mb-4 sm:mb-6">
              <Logo size="lg" />
            </div>
            <h2 className="text-xl sm:text-2xl font-medium text-dark-text-primary mb-2 sm:mb-3 tracking-tight px-2">
              Bienvenido a NetMind
            </h2>
            <p className="text-dark-text-secondary text-sm sm:text-[15px] leading-relaxed max-w-lg mx-auto px-2">
              Asistente inteligente especializado en redes y telecomunicaciones.
              Soporte técnico en conceptos de red, consultas DNS, análisis de direcciones IP y gestión de documentación técnica.
            </p>
            <div className="mt-6 sm:mt-8 flex flex-wrap gap-2 justify-center px-2">
              <span className="px-3 sm:px-4 py-1.5 sm:py-2 bg-dark-surface-primary border border-dark-border-primary/30 rounded-full text-xs sm:text-sm text-dark-text-secondary">
                Consultas DNS
              </span>
              <span className="px-3 sm:px-4 py-1.5 sm:py-2 bg-dark-surface-primary border border-dark-border-primary/30 rounded-full text-xs sm:text-sm text-dark-text-secondary">
                Operaciones de Red
              </span>
              <span className="px-3 sm:px-4 py-1.5 sm:py-2 bg-dark-surface-primary border border-dark-border-primary/30 rounded-full text-xs sm:text-sm text-dark-text-secondary">
                Documentación RAG
              </span>
            </div>
          </div>
        </div>
      ) : (
        <div className="py-4 sm:py-6 overflow-x-hidden w-full min-w-0 max-w-full">
          {messages.map((message) => (
            <Message key={message.id} message={message} />
          ))}
          <div ref={messagesEndRef} />
        </div>
      )}
    </div>
  )
}

