import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Utilidad para combinar clases de Tailwind CSS
 * Combina clsx y tailwind-merge para manejar conflictos de clases
 * 
 * @param {...any} inputs - Clases de CSS a combinar
 * @returns {string} - Clases combinadas y optimizadas
 * 
 * @example
 * cn('px-2 py-1', 'px-4') // 'py-1 px-4' (px-2 se sobrescribe por px-4)
 */
export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

