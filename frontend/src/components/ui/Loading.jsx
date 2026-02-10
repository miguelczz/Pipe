/**
 * Componente de carga con spinner animado
 * @param {Object} props
 * @param {string} props.size - Tamaño del spinner (sm, md, lg)
 * @param {string} props.className - Clases adicionales
 */
export function Loading({ size = 'md', className = '' }) {
  const sizes = {
    sm: 'w-4 h-4',
    md: 'w-6 h-6',
    lg: 'w-8 h-8',
  }

  return (
    <div className={`flex items-center justify-center ${className}`}>
      <div
        className={`${sizes[size]} border-2 border-dark-border-primary/30 border-t-dark-accent-primary rounded-full animate-spin`}
        role="status"
        aria-label="Cargando"
        style={{ animationDuration: '0.8s' }}
      >
        <span className="sr-only">Cargando...</span>
      </div>
    </div>
  )
}

