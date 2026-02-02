import { Toast } from './Toast'

/**
 * Contenedor de toasts que los muestra apilados verticalmente
 */
export function ToastContainer({ toasts, onClose }) {
  if (toasts.length === 0) return null

  return (
    <div
      className="fixed bottom-12 right-4 z-50 flex flex-col-reverse gap-3 pointer-events-none"
      aria-live="polite"
      aria-atomic="true"
    >
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <Toast toast={toast} onClose={onClose} />
        </div>
      ))}
    </div>
  )
}
