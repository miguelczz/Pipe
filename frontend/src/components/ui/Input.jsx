import { cn } from '../../utils/cn'

/**
 * Componente Input reutilizable
 * @param {Object} props
 * @param {string} props.className - Clases adicionales
 * @param {Object} props.rest - Props adicionales del input
 */
export function Input({ className, ...rest }) {
  return (
    <input
      className={cn(
        'w-full px-4 py-2.5 bg-dark-surface-primary border border-dark-border-primary/50 rounded-xl',
        'text-dark-text-primary placeholder-dark-text-muted text-[15px]',
        'focus:outline-none focus:ring-2 focus:ring-dark-border-focus focus:border-dark-border-focus',
        'transition-all duration-200 shadow-gemini-sm focus:shadow-gemini',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        'leading-relaxed',
        className
      )}
      {...rest}
    />
  )
}

