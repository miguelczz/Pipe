import { useState, useRef, useEffect } from 'react'
import { SendHorizontal, Loader2, ChevronDown, X as XIcon, BookOpen, FileSearch } from 'lucide-react'
import { Textarea } from '../ui/Textarea'

/**
 * Componente de input para el chat unificado (Guía / Reporte)
 *
 * @param {Object} props
 * @param {Function} props.onSend        - Función al enviar mensaje. Firma: (content, contextText) => void
 * @param {boolean}  props.isLoading     - Si el agente está respondiendo
 * @param {boolean}  props.disabled      - Si el input está deshabilitado
 * @param {'report'|'docs'} [props.mode='report'] - Modo actual: 'report' (reporte) o 'docs' (documentación)
 * @param {boolean} [props.modeLocked] - Si el modo está bloqueado (no se puede cambiar)
 * @param {Function} [props.onModeChange] - Callback al cambiar de modo
 * @param {string}   [props.contextText]  - Texto de contexto (fragmento seleccionado del reporte)
 * @param {Function} [props.onClearContext] - Callback para limpiar el contexto
 * @param {string}   [props.externalValue] - Valor externo para rellenar el input (por ejemplo, al editar un mensaje)
 * @param {Function} [props.onStopExternalEditing] - Callback al enviar un mensaje editado (para limpiar estado externo)
 */
export function ChatInput({
  onSend,
  isLoading = false,
  disabled = false,
  mode = 'report',
  modeLocked = false,
  onModeChange,
  contextText = null,
  onClearContext,
  externalValue,
  onStopExternalEditing,
}) {
  const [input, setInput] = useState('')
  const [modeMenuOpen, setModeMenuOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const textareaRef = useRef(null)

  // Auto-ajustar altura del textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
    }
  }, [input])

  // Rellenar el input cuando llega un valor externo (edición de mensaje)
  useEffect(() => {
    if (typeof externalValue === 'string') {
      setInput(externalValue)
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
        textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
      }
    }
  }, [externalValue])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!input.trim() || isLoading || disabled) return

    onSend?.(input.trim(), contextText || null)
    // Si veníamos de una edición, notificar para limpiar estado externo
    if (onStopExternalEditing) {
      onStopExternalEditing()
    }
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

  const currentModeLabel = mode === 'docs' ? 'Guía' : 'Reporte'

  const handleModeSelect = (newMode) => {
    if (newMode === mode) {
      setModeMenuOpen(false)
      return
    }
    if (onModeChange) {
      onModeChange(newMode)
    }
    setModeMenuOpen(false)
  }

  return (
    <form onSubmit={handleSubmit} className="w-full min-w-0 max-w-full">
      <div className="px-2 pb-2 min-w-0 max-w-full">
        <div className="flex flex-col gap-1">
          {contextText && (
            <div className="mb-1 px-3 py-2 rounded-xl bg-dark-bg-secondary/70 border border-dark-border-primary/60 min-h-2 max-h-28 overflow-y-auto text-xs text-dark-text-secondary flex items-start gap-2">
              <div className="flex-1 whitespace-pre-wrap break-words">
                {contextText}
              </div>
              {onClearContext && (
                <button
                  type="button"
                  onClick={onClearContext}
                  className="ml-2 flex-shrink-0 text-dark-text-muted hover:text-dark-text-primary hover:bg-dark-bg-primary/70 rounded-full p-1.5 transition-colors border border-dark-border-primary/60"
                  aria-label="Limpiar contexto"
                >
                  <XIcon className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          )}

          {/* Contenedor principal del input: textarea arriba, barra de acciones abajo (mismo color de fondo) */}
          <div className="flex flex-col bg-dark-surface-primary border border-dark-border-primary/50 rounded-2xl shadow-gemini-sm focus-within:border-dark-border-focus focus-within:shadow-gemini transition-all duration-200">
            {/* Área de texto (no afecta tamaño de botones) */}
            <div className="px-3 pt-1 pb-1 sm:px-3.5 sm:pt-1.5 sm:pb-1.5">
              <Textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Escribe tu pregunta..."
                disabled={disabled}
                rows={1}
                className="w-full border-0 border-transparent bg-transparent resize-none focus:ring-0 focus:outline-none text-xs sm:text-[14px] leading-relaxed break-words scrollbar-none"
                style={{
                  userSelect: 'text',
                  WebkitUserSelect: 'text',
                  wordBreak: 'break-word',
                  overflowWrap: 'anywhere',
                  border: 'none',
                  outline: 'none',
                  maxHeight: '120px',
                  overflowY: 'auto',
                }}
              />
            </div>

            {/* Barra inferior fija con selector de modo (izquierda) y enviar (derecha) */}
            <div className="relative flex items-center justify-between px-2.5 sm:px-3 py-1 rounded-b-2xl">
              {/* Selector de modo (Guía / Reporte) - tamaño fijo con ayuda contextual */}
              <div className="relative flex items-center gap-1.5">
                <button
                  type="button"
                  disabled={disabled || modeLocked}
                  onClick={() => setModeMenuOpen((open) => !open)}
                  className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg text-[11px] sm:text-xs font-medium border border-dark-border-primary/40 focus:outline-none ${
                    mode === 'report'
                      ? 'text-sky-400'
                      : 'text-emerald-400'
                  } ${disabled || modeLocked ? 'opacity-70' : 'hover:bg-dark-bg-secondary/60'}`}
                >
                  {mode === 'report' ? (
                    <FileSearch className="w-3.5 h-3.5" />
                  ) : (
                    <BookOpen className="w-3.5 h-3.5" />
                  )}
                  <span>{currentModeLabel}</span>
                  {!modeLocked && <ChevronDown className="w-3 flex-shrink-0 opacity-80" />}
                </button>
                {!modeLocked && modeMenuOpen && (
                  <div className="absolute left-0 bottom-full mb-1.5 z-40 min-w-[130px] rounded-lg border border-dark-border-primary/70 bg-dark-surface-primary shadow-gemini-sm overflow-hidden text-xs">
                    <button
                      type="button"
                      onClick={() => handleModeSelect('report')}
                      className={`w-full px-3 py-1.5 text-left hover:bg-dark-bg-secondary/70 transition-colors flex items-center gap-2 ${
                        mode === 'report' ? 'text-sky-400' : 'text-dark-text-primary'
                      }`}
                    >
                      <FileSearch className="w-3.5 h-3.5" />
                      <span>Reporte</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleModeSelect('docs')}
                      className={`w-full px-3 py-1.5 text-left hover:bg-dark-bg-secondary/70 border-t border-dark-border-primary/40 transition-colors flex items-center gap-2 ${
                        mode === 'docs' ? 'text-emerald-400' : 'text-dark-text-primary'
                      }`}
                    >
                      <BookOpen className="w-3.5 h-3.5" />
                      <span>Guía</span>
                    </button>
                  </div>
                )}

                {/* Icono de ayuda sobre el comportamiento con texto seleccionado */}
                <div className="relative">
                  <button
                    type="button"
                    className="p-1 rounded-full text-dark-text-muted hover:text-white focus:outline-none"
                    aria-label="Ayuda sobre modos de chat"
                    onClick={() => setHelpOpen((open) => !open)}
                  >
                    ?
                  </button>
                </div>
              </div>

              {/* Botón enviar (tamaño fijo) */}
              <button
                type="submit"
                disabled={!input.trim() || isLoading || disabled}
                className="flex items-center justify-center w-8 h-8 sm:w-9 sm:h-9 rounded-full bg-transparent text-dark-accent-primary hover:bg-dark-accent-primary/10 hover:text-dark-accent-hover disabled:opacity-40 disabled:cursor-not-allowed border border-transparent focus:outline-none focus:ring-0"
                aria-label="Enviar mensaje"
              >
                {isLoading ? (
                  <Loader2 className="w-4 h-4 shrink-0 animate-spin" />
                ) : (
                  <SendHorizontal className="w-4 h-4 shrink-0" strokeWidth={2.25} />
                )}
              </button>

              {/* Tooltip simple explicativo: anclado a la barra, se ajusta al ancho del chat */}
              {helpOpen && (
                <div className="absolute left-0 bottom-full mb-1 w-full max-w-full rounded-md border border-dark-border-primary/70 bg-dark-surface-primary shadow-gemini-sm px-4 py-3 text-[11px] leading-snug text-dark-text-secondary z-40 whitespace-normal text-left">
                  Cuando selecciones texto del informe, el chat se fija temporalmente en modo{' '}
                  <span className="font-semibold text-dark-text-primary">Reporte</span> para garantizar
                  que la respuesta use ese análisis. Podrás cambiar de modo nuevamente al terminar la
                  respuesta o al borrar el fragmento seleccionado.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </form>
  )
}

