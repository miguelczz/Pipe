import { useEffect, useRef } from 'react'
import { Eye, Trash2, Copy, Share2, Download, FileText } from 'lucide-react'

/**
 * Menú contextual que aparece al hacer click derecho en un reporte
 */
export function ReportContextMenu({ 
  isOpen, 
  position, 
  onClose, 
  onViewDetails,
  onDelete,
  onDownloadCapture,
  onDownloadPDF,
  report
}) {
  const menuRef = useRef(null)

  useEffect(() => {
    if (!isOpen) return

    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        onClose()
      }
    }

    const handleEscape = (event) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleEscape)

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [isOpen, onClose])

  if (!isOpen || !position) return null

  // Ajustar posición para que no se salga de la pantalla
  const style = {
    position: 'fixed',
    left: `${position.x}px`,
    top: `${position.y}px`,
    zIndex: 1000,
  }

  return (
    <div
      ref={menuRef}
      className="bg-dark-surface-primary border border-dark-border-primary/40 rounded-lg shadow-gemini min-w-[200px] overflow-hidden"
      style={style}
    >
      <button
        onClick={(e) => {
          e.stopPropagation()
          onViewDetails()
          onClose()
        }}
        className="w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2"
      >
        <Eye className="w-4 h-4 text-blue-400" />
        <span>Ver Detalles</span>
      </button>

      <div className="h-px bg-dark-border-primary/20"></div>

      <button
        onClick={(e) => {
          e.stopPropagation()
          onDownloadCapture()
          onClose()
        }}
        className="w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2"
      >
        <Download className="w-4 h-4 text-blue-400" />
        <span>Descargar Captura</span>
      </button>

      <button
        onClick={(e) => {
          e.stopPropagation()
          onDownloadPDF()
          onClose()
        }}
        className="w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2"
      >
        <FileText className="w-4 h-4 text-purple-400" />
        <span>Descargar PDF</span>
      </button>

      <div className="h-px bg-dark-border-primary/20"></div>

      <button
        onClick={(e) => {
          e.stopPropagation()
          if (report) {
            navigator.clipboard.writeText(JSON.stringify(report, null, 2))
          }
          onClose()
        }}
        className="w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2"
      >
        <Copy className="w-4 h-4 text-yellow-400" />
        <span>Copiar Datos</span>
      </button>

      <div className="h-px bg-dark-border-primary/20"></div>

      <button
        onClick={(e) => {
          e.stopPropagation()
          onDelete()
          onClose()
        }}
        className="w-full px-4 py-2.5 text-left text-sm text-red-400 hover:bg-red-500/10 transition-colors flex items-center gap-2"
      >
        <Trash2 className="w-4 h-4" />
        <span>Eliminar</span>
      </button>
    </div>
  )
}
