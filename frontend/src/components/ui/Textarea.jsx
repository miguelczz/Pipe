import { forwardRef } from 'react'
import { cn } from '../../utils/cn'

/**
 * Componente Textarea reutilizable con soporte para refs
 * @param {Object} props
 * @param {string} props.className - Clases adicionales
 * @param {Object} props.rest - Props adicionales del textarea
 */
export const Textarea = forwardRef(function Textarea({ className, ...rest }, ref) {
  return (
    <textarea
      ref={ref}
      className={cn(
        'w-full text-dark-text-primary placeholder-dark-text-muted',
        'focus:outline-none transition-all duration-200 resize-none',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        'leading-relaxed text-[15px]',
        className
      )}
      {...rest}
    />
  )
})

