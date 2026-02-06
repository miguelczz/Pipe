import { Copy, Check, AlertCircle, User, Edit3, X, SendHorizontal, FileSearch, BookOpen, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'
import { cn } from '../../utils/cn'
import { MarkdownRenderer } from './MarkdownRenderer'
import { Logo } from '../common/Logo'
import { Loading } from '../ui/Loading'

/**
 * Componente para renderizar una tabla
 */
function Table({ headers, rows }) {
  return (
    <div className="overflow-x-auto my-3 rounded-lg border border-dark-border-primary/50 -mx-2 sm:mx-0" style={{ maxWidth: 'calc(100vw - 2rem)' }}>
      <table className="w-full border-collapse min-w-[400px]">
        <thead>
          <tr className="bg-dark-surface-secondary border-b border-dark-border-primary/50">
            {headers.map((header, idx) => (
              <th
                key={idx}
                className="px-4 py-2.5 text-left text-sm font-semibold text-dark-text-primary"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIdx) => (
            <tr
              key={rowIdx}
              className="border-b border-dark-border-primary/30 hover:bg-dark-surface-hover/50 transition-colors"
            >
              {row.map((cell, cellIdx) => (
                <td
                  key={cellIdx}
                  className="px-4 py-2.5 text-sm text-dark-text-secondary"
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Componente para mostrar un mensaje en el chat
 * @param {Object} props
 * @param {Object} props.message - Objeto del mensaje
 * @param {string} props.message.role - Rol del mensaje (user/assistant)
 * @param {string} props.message.content - Contenido del mensaje
 * @param {string} props.message.tool - Herramienta usada (opcional)
 * @param {boolean} props.message.isError - Si es un mensaje de error
 * @param {Function} [props.onEditUserMessage] - Callback al hacer clic en Editar (modo legacy: rellenar input)
 * @param {Function} [props.onSaveEditedMessage] - Callback al guardar edición inline: (message, newContent) => void
 * @param {'report'|'docs'} [props.editMode] - Modo actual al editar (Reporte / Guía)
 * @param {Function} [props.onEditModeChange] - Callback al cambiar modo durante edición
 * @param {boolean} [props.editModeLocked] - Si el modo está bloqueado durante edición
 * @param {number} [props.replyIndex] - Índice de la respuesta actual (paginado del agente)
 * @param {number} [props.replyTotal] - Total de respuestas para este prompt (paginado)
 * @param {Function} [props.onReplyPrev] - Ir a la respuesta anterior
 * @param {Function} [props.onReplyNext] - Ir a la respuesta siguiente
 */
export function Message({ message, onEditUserMessage, onSaveEditedMessage, editMode = 'report', onEditModeChange, editModeLocked = false, replyIndex = 0, replyTotal = 1, onReplyPrev, onReplyNext }) {
  const [copied, setCopied] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editText, setEditText] = useState(message.content || '')
  const [modeMenuOpen, setModeMenuOpen] = useState(false)
  const editTextareaRef = useRef(null)
  const isUser = message.role === 'user'
  const isError = message.isError

  useEffect(() => {
    if (isEditing && editTextareaRef.current) {
      editTextareaRef.current.focus()
      editTextareaRef.current.select()
    }
  }, [isEditing])

  const startEditing = () => {
    setEditText(message.content || '')
    setIsEditing(true)
  }
  const cancelEditing = () => {
    setEditText(message.content || '')
    setIsEditing(false)
  }
  const submitEditing = () => {
    const trimmed = editText.trim()
    if (trimmed && onSaveEditedMessage) {
      onSaveEditedMessage(message, trimmed)
      setIsEditing(false)
    }
  }

  // Parsear contenido para detectar tablas (solo para usuarios, el agente usa markdown)
  const parsedContent = isUser ? [{ type: 'text', content: message.content }] : []

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (error) {
      // Ignorar errores de portapapeles
    }
  }

  return (
    <div
      className={cn(
        'flex gap-2 sm:gap-3 px-2 sm:px-4 py-2 animate-fade-in group min-w-0 w-full max-w-full overflow-hidden',
        isUser ? 'justify-end' : 'justify-start'
      )}
    >
      {!isUser && (
        <div className="flex-shrink-0">
          <Logo size="sm" />
        </div>
      )}

      <div
        className={cn(
          'flex flex-col gap-2 min-w-0 flex-shrink-0',
          isUser ? 'items-end' : 'items-start',
          isUser && isEditing ? 'max-w-[95%] min-w-[min(100%,420px)]' : 'max-w-[85%] sm:max-w-[80%] md:max-w-[75%]'
        )}
      >
        <div
          className={cn(
            'rounded-2xl px-4 py-3 sm:px-5 sm:py-4 break-words transition-all duration-300',
            'leading-relaxed overflow-hidden min-w-0 max-w-full',
            'word-break break-word overflow-wrap-anywhere',
            isUser && isEditing
              ? 'bg-dark-surface-primary text-dark-text-primary border border-dark-border-primary/60 shadow-gemini-sm min-w-[280px]'
              : isUser
              ? 'bg-dark-accent-primary text-white shadow-gemini-sm'
              : isError
              ? 'bg-dark-status-error/10 text-dark-status-error border border-dark-status-error/30'
              : 'bg-dark-surface-primary text-dark-text-primary border border-dark-border-primary/50 shadow-gemini-sm'
          )}
        >
          {isError && (
            <div className="flex items-center gap-2 mb-2 pb-2 border-b border-dark-status-error/20">
              <AlertCircle className="w-4 h-4" />
              <span className="text-sm font-medium">Error</span>
            </div>
          )}

          <div className="text-[15px] leading-relaxed overflow-hidden min-w-0">
            {!isUser ? (
              // Mostrar loader si está en streaming sin contenido
              message.isStreaming && !message.content ? (
                <Loading size="sm" />
              ) : (
                // Renderizar markdown para mensajes del agente
                <MarkdownRenderer content={message.content} />
              )
            ) : isEditing ? (
              // Edición inline del mensaje del usuario (color superficie; al enviar vuelve a morado)
              <div className="flex flex-col gap-3">
                <textarea
                  ref={editTextareaRef}
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      submitEditing()
                    }
                    if (e.key === 'Escape') cancelEditing()
                  }}
                  className="w-full min-h-[88px] px-0 py-0 bg-transparent border-0 resize-none focus:ring-0 focus:outline-none text-dark-text-primary placeholder-dark-text-muted text-[15px] leading-relaxed"
                  placeholder="Escribe tu mensaje..."
                  rows={3}
                />
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="relative flex items-center gap-1.5">
                    {onEditModeChange && (
                      <>
                        <button
                          type="button"
                          disabled={editModeLocked}
                          onClick={() => setModeMenuOpen((o) => !o)}
                          className={cn(
                            'inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium border border-dark-border-primary/50',
                            editMode === 'report' ? 'text-sky-400' : 'text-emerald-400',
                            editModeLocked ? 'opacity-70' : 'hover:bg-dark-bg-secondary/70'
                          )}
                          aria-label="Cambiar modo"
                        >
                          {editMode === 'report' ? <FileSearch className="w-3.5 h-3.5" /> : <BookOpen className="w-3.5 h-3.5" />}
                          <span>{editMode === 'report' ? 'Reporte' : 'Guía'}</span>
                          {!editModeLocked && <ChevronDown className="w-3 flex-shrink-0 opacity-80" />}
                        </button>
                        {!editModeLocked && modeMenuOpen && (
                          <div className="absolute left-0 bottom-full mb-1.5 z-40 min-w-[120px] rounded-lg border border-dark-border-primary/70 bg-dark-surface-primary shadow-lg overflow-hidden text-xs">
                            <button
                              type="button"
                              onClick={() => { onEditModeChange('report'); setModeMenuOpen(false) }}
                              className={cn('w-full px-3 py-1.5 text-left hover:bg-dark-bg-secondary/70 flex items-center gap-2', editMode === 'report' ? 'text-sky-400' : 'text-dark-text-primary')}
                            >
                              <FileSearch className="w-3.5 h-3.5" />
                              Reporte
                            </button>
                            <button
                              type="button"
                              onClick={() => { onEditModeChange('docs'); setModeMenuOpen(false) }}
                              className={cn('w-full px-3 py-1.5 text-left hover:bg-dark-bg-secondary/70 border-t border-dark-border-primary/40 flex items-center gap-2', editMode === 'docs' ? 'text-emerald-400' : 'text-dark-text-primary')}
                            >
                              <BookOpen className="w-3.5 h-3.5" />
                              Guía
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={submitEditing}
                      disabled={!editText.trim()}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-dark-accent-primary text-white hover:bg-dark-accent-hover disabled:opacity-50 text-xs font-medium"
                      aria-label="Enviar"
                    >
                      <SendHorizontal className="w-3.5 h-3.5" />
                      Enviar
                    </button>
                    <button
                      type="button"
                      onClick={cancelEditing}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-dark-bg-secondary text-dark-text-secondary hover:bg-dark-surface-hover text-xs font-medium border border-dark-border-primary/40"
                      aria-label="Cancelar"
                    >
                      <X className="w-3.5 h-3.5" />
                      Cancelar
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              // Texto plano para mensajes del usuario (solo lectura)
              parsedContent.map((part, idx) => {
                if (part.type === 'table') {
                  return <Table key={idx} headers={part.headers} rows={part.rows} />
                }
                return (
                  <div key={idx} className="whitespace-pre-wrap break-words overflow-wrap-anywhere">
                    {part.content}
                  </div>
                )
              })
            )}
          </div>
        </div>

        {!isError && !isEditing && (
          <div className="flex items-center gap-2 flex-wrap text-xs text-dark-text-muted transition-all duration-200 opacity-0 group-hover:opacity-100">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg hover:bg-dark-surface-hover hover:text-dark-text-secondary"
              aria-label="Copiar mensaje"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5" />
                  <span>Copiado</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copiar</span>
                </>
              )}
            </button>
            {!isUser && replyTotal > 1 && (
              <div className="flex items-center gap-0.5 rounded-lg border border-dark-border-primary/40 overflow-hidden">
                <button
                  type="button"
                  onClick={onReplyPrev}
                  disabled={replyIndex <= 0}
                  className="p-1.5 hover:bg-dark-surface-hover hover:text-dark-text-primary disabled:opacity-40 disabled:pointer-events-none"
                  aria-label="Respuesta anterior"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                </button>
                <span className="px-2 py-1 text-[11px] font-medium tabular-nums">
                  {replyIndex + 1}/{replyTotal}
                </span>
                <button
                  type="button"
                  onClick={onReplyNext}
                  disabled={replyIndex >= replyTotal - 1}
                  className="p-1.5 hover:bg-dark-surface-hover hover:text-dark-text-primary disabled:opacity-40 disabled:pointer-events-none"
                  aria-label="Siguiente respuesta"
                >
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
            {isUser && (onSaveEditedMessage || onEditUserMessage) && (
              <button
                onClick={onSaveEditedMessage ? startEditing : () => onEditUserMessage(message)}
                className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg hover:bg-dark-surface-hover hover:text-dark-text-secondary"
                aria-label="Editar mensaje"
              >
                <Edit3 className="w-3.5 h-3.5" />
                <span>Editar</span>
              </button>
            )}
          </div>
        )}
      </div>

      {isUser && (
        <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-dark-surface-secondary border border-dark-border-primary/30 flex items-center justify-center text-dark-text-secondary shadow-gemini-sm">
          <User className="w-5 h-5 stroke-[2.5]" />
        </div>
      )}
    </div>
  )
}

