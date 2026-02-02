import { useState } from 'react'
import { Network } from 'lucide-react'

/**
 * Componente Logo con fallback automático - Telecomunicaciones
 * @param {Object} props
 * @param {string} props.size - Tamaño del logo (sm, md, lg)
 */
export function Logo({ size = 'md' }) {
  const [imageError, setImageError] = useState(false)

  const sizes = {
    sm: 'w-9 h-9',
    md: 'w-10 h-10',
    lg: 'w-20 h-20',
  }

  const iconSizes = {
    sm: 'w-5 h-5',
    md: 'w-7 h-7',
    lg: 'w-12 h-12',
  }

  return (
    <div className={`${sizes[size]} rounded-xl bg-dark-surface-primary border border-dark-border-primary/50 flex items-center justify-center shadow-gemini-sm`}>
      {!imageError ? (
        <img 
          src="https://img.icons8.com/ios/100/ffffff/network-cable.png" 
          alt="Pipe Logo" 
          className={`${iconSizes[size]} object-contain opacity-90`}
          onError={() => setImageError(true)}
        />
      ) : (
        <Network className={`${iconSizes[size]} text-dark-text-primary stroke-[2]`} />
      )}
    </div>
  )
}

