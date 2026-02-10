import { useToast as useToastContext } from '../contexts/ToastContext'

/**
 * Hook personalizado para mostrar toasts
 * 
 * @example
 * const { showToast } = useToast()
 * showToast({ type: 'success', message: 'Operación exitosa' })
 */
export function useToast() {
  return useToastContext()
}
