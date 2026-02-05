import { AlertCircle } from 'lucide-react'
import { cn } from '../../utils/cn'

/**
 * Componente para mostrar el estado de conexión con el servidor
 * @param {Object} props
 * @param {boolean} props.isConnected - Si está conectado
 * @param {string} props.message - Mensaje a mostrar
 */
export function ConnectionStatus({ isConnected, message }) {
  if (isConnected) return null

  return (
    <div className={cn(
      'mx-0 sm:mx-4 mt-0 sm:mt-4 p-3 sm:p-4 rounded-2xl border',
      'bg-dark-status-error/10 border-dark-status-error/30',
      'text-dark-status-error shadow-gemini-sm animate-fade-in',
      'break-words overflow-wrap-anywhere'
    )}>
      <div className="flex items-start gap-2 sm:gap-3">
        <AlertCircle className="w-4 h-4 sm:w-5 sm:h-5 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-xs sm:text-sm font-medium leading-relaxed break-words">
            {message || 'No se pudo conectar con el servidor'}
          </p>
        </div>
      </div>
    </div>
  )
}

