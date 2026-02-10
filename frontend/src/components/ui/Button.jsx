import { cn } from '../../utils/cn'

/**
 * Componente Button reutilizable con variantes
 * @param {Object} props
 * @param {React.ReactNode} props.children - Contenido del botón
 * @param {string} props.variant - Variante del botón (primary, secondary, ghost, danger)
 * @param {string} props.size - Tamaño del botón (sm, md, lg)
 * @param {boolean} props.disabled - Si el botón está deshabilitado
 * @param {string} props.className - Clases adicionales
 * @param {Function} props.onClick - Función al hacer click
 * @param {Object} props.rest - Props adicionales
 */
export function Button({
  children,
  variant = 'primary',
  size = 'md',
  disabled = false,
  className,
  onClick,
  ...rest
}) {
  const baseStyles = 'inline-flex items-center justify-center rounded-xl font-medium transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-dark-bg-primary disabled:opacity-50 disabled:cursor-not-allowed'

  const variants = {
    primary: 'bg-dark-accent-primary text-white hover:bg-dark-accent-hover active:bg-dark-accent-active focus:ring-dark-accent-primary shadow-gemini-sm hover:shadow-gemini',
    secondary: 'bg-dark-surface-secondary text-dark-text-primary border border-dark-border-primary/50 hover:bg-dark-surface-hover hover:border-dark-border-secondary focus:ring-dark-border-focus shadow-gemini-sm',
    ghost: 'text-dark-text-secondary hover:bg-dark-surface-hover hover:text-dark-text-primary focus:ring-dark-border-focus',
    danger: 'bg-dark-status-error text-white hover:bg-red-600 focus:ring-dark-status-error shadow-gemini-sm hover:shadow-gemini',
  }

  const sizes = {
    sm: 'px-3 py-1.5 text-sm h-[36px]',
    md: 'px-4 py-2 text-[15px] h-[44px]',
    lg: 'px-6 py-3 text-base h-[52px]',
  }

  return (
    <button
      className={cn(
        baseStyles,
        variants[variant],
        sizes[size],
        className
      )}
      disabled={disabled}
      onClick={onClick}
      {...rest}
    >
      {children}
    </button>
  )
}

