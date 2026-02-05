import { useState, useRef, useEffect } from 'react'
import { SendHorizontal, Loader2 } from 'lucide-react'
import { Textarea } from '../ui/Textarea'

/**
 * Componente de input para el chat
 * @param {Object} props
 * @param {Function} props.onSend - Función que se ejecuta al enviar mensaje
 * @param {boolean} props.isLoading - Si está cargando
 * @param {boolean} props.disabled - Si está deshabilitado
 */
export function ChatInput({ onSend, isLoading = false, disabled = false }) {
  const [input, setInput] = useState('')
  const textareaRef = useRef(null)

  // Auto-ajustar altura del textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
    }
  }, [input])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!input.trim() || isLoading || disabled) return

    onSend(input.trim())
    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full min-w-0 max-w-full">
      <div className="px-2 pb-2 min-w-0 max-w-full">
        <div className="flex items-stretch gap-0 bg-dark-surface-primary border border-dark-border-primary/50 rounded-2xl shadow-gemini-sm focus-within:border-dark-border-focus focus-within:shadow-gemini transition-all duration-200 min-h-[48px] sm:min-h-[52px]">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Escribe tu mensaje..."
            disabled={false}
            rows={1}
            className="flex-1 min-h-10 py-2.5 sm:py-3 pl-3 sm:pl-4 pr-11 sm:pr-12 border-0 border-transparent bg-transparent resize-none focus:ring-0 focus:outline-none text-base sm:text-[15px] leading-relaxed break-words overflow-y-auto"
            style={{
              userSelect: 'text',
              WebkitUserSelect: 'text',
              wordBreak: 'break-word',
              overflowWrap: 'anywhere',
              border: 'none',
              outline: 'none'
            }}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading || disabled}
            className="flex-shrink-0 w-11 h-11 sm:w-12 sm:h-12 flex items-center justify-center border-0 border-transparent bg-transparent text-dark-accent-primary hover:text-dark-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors rounded-lg hover:bg-dark-accent-primary/10 focus:outline-none focus:ring-0"
            style={{ border: 'none', boxShadow: 'none' }}
            aria-label="Enviar mensaje"
          >
            {isLoading ? (
              <Loader2 className="w-5 h-5 shrink-0 animate-spin" />
            ) : (
              <SendHorizontal className="w-5 h-5 shrink-0" strokeWidth={2.25} />
            )}
          </button>
        </div>
      </div>
    </form>
  )
}

