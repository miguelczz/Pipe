import { createContext, useContext, useState, useCallback } from 'react'
import { ToastContainer } from '../components/ui/ToastContainer'

const ToastContext = createContext(null)

/**
 * Provider de Toast que maneja el estado global de las notificaciones
 */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const showToast = useCallback(({ type = 'info', message, duration = 4000 }) => {
    const id = Date.now() + Math.random()
    const newToast = { id, type, message, duration }
    
    setToasts((prev) => [...prev, newToast])
    
    return id
  }, [])

  const closeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id))
  }, [])

  const value = {
    showToast,
    closeToast,
  }

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastContainer toasts={toasts} onClose={closeToast} />
    </ToastContext.Provider>
  )
}

/**
 * Hook para usar el contexto de Toast
 */
// eslint-disable-next-line react-refresh/only-export-components -- Contexto exporta Provider y hook por diseño
export function useToast() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast debe usarse dentro de ToastProvider')
  }
  return context
}
