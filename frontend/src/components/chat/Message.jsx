import { Copy, Check, AlertCircle, User } from 'lucide-react'
import { useState } from 'react'
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
 */
export function Message({ message }) {
  const [copied, setCopied] = useState(false)
  const isUser = message.role === 'user'
  const isError = message.isError
  
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
          isUser ? 'items-end max-w-[85%] sm:max-w-[80%] md:max-w-[75%]' : 'items-start max-w-[85%] sm:max-w-[80%] md:max-w-[75%]'
        )}
      >
        <div
          className={cn(
            'rounded-2xl px-4 py-3 sm:px-5 sm:py-4 break-words transition-all duration-300',
            'leading-relaxed overflow-hidden min-w-0 max-w-full',
            'word-break break-word overflow-wrap-anywhere',
            isUser
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
            ) : (
              // Texto plano para mensajes del usuario
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

        {!isUser && !isError && (
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 text-xs text-dark-text-muted hover:text-dark-text-secondary transition-all duration-200 px-2 py-1 rounded-lg hover:bg-dark-surface-hover opacity-0 group-hover:opacity-100"
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

