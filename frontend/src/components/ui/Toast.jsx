import { useEffect } from 'react'
import { CheckCircle2, XCircle, AlertCircle, Info, X } from 'lucide-react'
import { cn } from '../../utils/cn'

/**
 * Componente individual de Toast
 */
export function Toast({ toast, onClose }) {
  const { id, type, message, duration = 4000 } = toast

  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        onClose(id)
      }, duration)
      return () => clearTimeout(timer)
    }
  }, [id, duration, onClose])

  const icons = {
    success: CheckCircle2,
    error: XCircle,
    warning: AlertCircle,
    info: Info,
  }

  const styles = {
    success: 'bg-green-500/10 border-green-500/30 text-green-400',
    error: 'bg-red-500/10 border-red-500/30 text-red-400',
    warning: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400',
    info: 'bg-blue-500/10 border-blue-500/30 text-blue-400',
  }

  const Icon = icons[type] || Info

  return (
    <div
      className={cn(
        'flex items-start gap-3 p-4 rounded-xl border shadow-lg backdrop-blur-sm min-w-[320px] max-w-md animate-slide-in-right',
        styles[type] || styles.info
      )}
      role="alert"
    >
      <Icon className="w-5 h-5 flex-shrink-0 mt-0.5" />
      <div className="flex-1 text-sm font-medium text-dark-text-primary">
        {message}
      </div>
      <button
        onClick={() => onClose(id)}
        className="flex-shrink-0 text-dark-text-muted hover:text-dark-text-primary transition-colors p-1 rounded hover:bg-dark-bg-secondary/50"
        aria-label="Cerrar notificación"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}
