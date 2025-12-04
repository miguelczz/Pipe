import { useState, useRef, useEffect } from 'react'
import { Send, Loader2 } from 'lucide-react'
import { Textarea } from '../ui/Textarea'
import { Button } from '../ui/Button'

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
    <form onSubmit={handleSubmit} className="w-full min-w-0">
      <div className="flex gap-2 sm:gap-3 items-end px-2 pb-2 min-w-0">
        <div className="flex-1 relative min-w-0">
          <div className="bg-dark-surface-primary border border-dark-border-primary/50 rounded-2xl shadow-gemini-sm focus-within:border-dark-border-focus focus-within:shadow-gemini transition-all duration-200">
            <Textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Escribe tu mensaje..."
              disabled={false}
              rows={1}
              className="min-h-[48px] sm:min-h-[52px] max-h-[200px] py-2.5 sm:py-3 px-3 sm:px-4 border-0 bg-transparent resize-none focus:ring-0 focus:outline-none text-[15px] leading-relaxed break-words overflow-wrap-anywhere"
              style={{ 
                userSelect: 'text',
                WebkitUserSelect: 'text',
                wordBreak: 'break-word',
                overflowWrap: 'anywhere'
              }}
            />
          </div>
        </div>
        <Button
          type="submit"
          disabled={!input.trim() || isLoading || disabled}
          className="flex-shrink-0 h-[48px] w-[48px] sm:h-[52px] sm:w-[52px] rounded-full p-0 shadow-gemini-sm hover:shadow-gemini transition-all duration-200 border-0"
          size="md"
          aria-label="Enviar mensaje"
        >
          {isLoading ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <Send className="w-5 h-5" />
          )}
        </Button>
      </div>
    </form>
  )
}

