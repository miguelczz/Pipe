import { useEffect, useRef, useMemo, useState, useCallback } from 'react'
import { Message } from './Message'
import { Logo } from '../common/Logo'
import { cn } from '../../utils/cn'

/** Agrupa mensajes en bloques: user solo, o user + grupo de respuestas del agente */
function buildBlocks(messages) {
  const blocks = []
  let i = 0
  while (i < messages.length) {
    const msg = messages[i]
    if (msg.role === 'user') {
      blocks.push({ type: 'user', message: msg })
      i += 1
      continue
    }
    const assistants = []
    while (i < messages.length && messages[i].role === 'assistant') {
      assistants.push(messages[i])
      i += 1
    }
    if (assistants.length > 0) {
      blocks.push({
        type: 'assistantGroup',
        userMessageId: blocks[blocks.length - 1]?.message?.id ?? null,
        messages: assistants,
      })
    }
  }
  return blocks
}

/**
 * Contenedor principal del chat
 * @param {Object} props
 * @param {Array} props.messages - Array de mensajes
 * @param {boolean} props.isLoading - Si está cargando
 * @param {Function} [props.onEditUserMessage] - Callback al solicitar edición de un mensaje de usuario (legacy)
 * @param {Function} [props.onSaveEditedMessage] - Callback al guardar edición inline: (message, newContent) => void
 * @param {'report'|'docs'} [props.mode] - Modo actual (para selector al editar mensaje)
 * @param {Function} [props.onModeChange] - Callback al cambiar modo
 * @param {boolean} [props.modeLocked] - Si el modo está bloqueado (p. ej. por selección de texto)
 */
export function ChatContainer({ messages, isLoading, onEditUserMessage, onSaveEditedMessage, mode, onModeChange, modeLocked }) {
  const messagesEndRef = useRef(null)
  const containerRef = useRef(null)
  const [replyGroupIndex, setReplyGroupIndex] = useState({})
  const prevBlocksRef = useRef(null)

  const blocks = useMemo(() => buildBlocks(messages), [messages])
  const setGroupPage = useCallback((userMessageId, index) => {
    setReplyGroupIndex((prev) => ({ ...prev, [userMessageId]: index }))
  }, [])

  // Cuando se añade una nueva respuesta a un grupo, ir automáticamente a la última
  useEffect(() => {
    blocks.forEach((block) => {
      if (block.type === 'assistantGroup') {
        const prevBlock = prevBlocksRef.current?.find(
          (b) => b.type === 'assistantGroup' && b.userMessageId === block.userMessageId
        )
        if (prevBlock && block.messages.length > prevBlock.messages.length) {
          // Se añadió una nueva respuesta, ir a la última
          setReplyGroupIndex((prev) => ({
            ...prev,
            [block.userMessageId]: block.messages.length - 1,
          }))
        }
      }
    })
    prevBlocksRef.current = blocks
  }, [blocks])

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
        'flex-1 min-h-0 overflow-x-hidden flex flex-col',
        messages.length === 0 
          ? 'overflow-hidden items-center justify-center' 
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
              Bienvenido a Pipe
            </h2>
            <p className="text-dark-text-secondary text-sm sm:text-[15px] leading-relaxed max-w-lg mx-auto px-2">
              Asistente inteligente especializado en análisis de capturas Wireshark.
              Analiza archivos .pcap/.pcapng, interpreta tráfico de red, identifica protocolos y genera reportes detallados de Band Steering y comportamiento de red.
            </p>
            <div className="mt-6 sm:mt-8 flex flex-wrap gap-2 justify-center px-2">
              <span className="px-3 sm:px-4 py-1.5 sm:py-2 bg-dark-surface-primary border border-dark-border-primary/30 rounded-full text-xs sm:text-sm text-dark-text-secondary">
                Análisis .pcap/.pcapng
              </span>
              <span className="px-3 sm:px-4 py-1.5 sm:py-2 bg-dark-surface-primary border border-dark-border-primary/30 rounded-full text-xs sm:text-sm text-dark-text-secondary">
                Band Steering
              </span>
              <span className="px-3 sm:px-4 py-1.5 sm:py-2 bg-dark-surface-primary border border-dark-border-primary/30 rounded-full text-xs sm:text-sm text-dark-text-secondary">
                Protocolos WiFi
              </span>
            </div>
          </div>
        </div>
      ) : (
        <div className="py-4 sm:py-6 overflow-x-hidden w-full min-w-0 max-w-full">
          {blocks.map((block) => {
            if (block.type === 'user') {
              return (
                <Message
                  key={block.message.id}
                  message={block.message}
                  onEditUserMessage={onEditUserMessage}
                  onSaveEditedMessage={onSaveEditedMessage}
                  editMode={mode}
                  onEditModeChange={onModeChange}
                  editModeLocked={modeLocked}
                />
              )
            }
            const { userMessageId, messages: groupMessages } = block
            const currentIndex = Math.min(
              replyGroupIndex[userMessageId] ?? 0,
              groupMessages.length - 1
            )
            const currentMessage = groupMessages[currentIndex]
            const total = groupMessages.length
            return (
              <Message
                key={currentMessage.id}
                message={currentMessage}
                onEditUserMessage={onEditUserMessage}
                onSaveEditedMessage={onSaveEditedMessage}
                editMode={mode}
                onEditModeChange={onModeChange}
                editModeLocked={modeLocked}
                replyIndex={currentIndex}
                replyTotal={total}
                onReplyPrev={total > 1 ? () => setGroupPage(userMessageId, Math.max(0, currentIndex - 1)) : undefined}
                onReplyNext={total > 1 ? () => setGroupPage(userMessageId, Math.min(total - 1, currentIndex + 1)) : undefined}
              />
            )
          })}
          <div ref={messagesEndRef} />
        </div>
      )}
    </div>
  )
}

