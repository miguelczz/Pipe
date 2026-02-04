import { Card } from '../ui/Card'
import { FileText, Calendar, CheckCircle2, XCircle, ArrowRight, Trash2, Download, MoreVertical } from 'lucide-react'
import { Loading } from '../ui/Loading'

const formatTime = (seconds) => {
  if (!seconds || seconds === 0) return '0s'
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const minutes = Math.floor(seconds / 60)
  const secs = (seconds % 60).toFixed(1)
  return `${minutes}m ${secs}s`
}

/**
 * Vista de lista para reportes (alternativa a la vista grid)
 */
export function ReportsListView({ 
  reports, 
  onViewReport, 
  onDeleteReport, 
  onDownloadCapture,
  onDownloadPDF,
  onDownloadBoth,
  isDeleting,
  isDownloading,
  openDownloadMenu,
  setOpenDownloadMenu,
  formatDate,
  selectionMode,
  isSelected,
  toggleSelection,
  CheckSquare,
  Square,
  onContextMenu
}) {
  if (reports.length === 0) {
    return null
  }

  return (
    <div className="space-y-2 w-full">
      {reports.map((report) => (
        <Card
          key={report.id}
          className={`group p-4 hover:border-dark-accent-primary/40 bg-dark-surface-primary/50 hover:bg-dark-surface-primary border-dark-border-primary/20 transition-all duration-200 w-full ${isDeleting === report.id ? 'opacity-50 pointer-events-none' : ''} ${selectionMode ? 'cursor-default' : 'cursor-pointer'} ${openDownloadMenu === report.id ? 'overflow-visible' : ''}`}
          onClick={() => {
            if (selectionMode) {
              toggleSelection(report.id)
            } else {
              onViewReport(report)
            }
          }}
          onContextMenu={(e) => {
            e.preventDefault()
            if (!selectionMode && onContextMenu) {
              onContextMenu(e, report)
            }
          }}
        >
          <div className="flex items-center gap-4">
            {/* Checkbox si modo selección */}
            {selectionMode && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  toggleSelection(report.id)
                }}
                className="flex-shrink-0"
              >
                {isSelected(report.id) ? (
                  <CheckSquare className="w-5 h-5 text-dark-accent-primary" />
                ) : (
                  <Square className="w-5 h-5 text-dark-text-muted hover:text-dark-text-primary transition-colors" />
                )}
              </button>
            )}

            {/* Información del Reporte */}
            <div className="flex-1 min-w-0 grid grid-cols-1 md:grid-cols-5 gap-4 items-center">
              {/* Modelo y Archivo */}
              <div className="min-w-0">
                <h3 className="text-base font-semibold text-dark-text-primary truncate group-hover:text-dark-accent-primary transition-colors">
                  {report.model || 'Dispositivo Desconocido'}
                </h3>
                <div className="flex items-center gap-1.5 text-xs text-dark-text-muted mt-1">
                  <FileText className="w-3 h-3 flex-shrink-0" />
                  <span className="truncate" title={report.filename}>
                    {report.filename?.includes('_') && report.filename.split('_')[0].length === 36 
                      ? report.filename.split('_').slice(1).join('_') 
                      : report.filename}
                  </span>
                </div>
              </div>

              {/* Marca */}
              <div className="text-sm text-dark-text-primary font-medium">
                {report.vendor || 'Desconocido'}
              </div>

              {/* Fecha */}
              <div className="flex items-center gap-1.5 text-xs text-dark-text-muted">
                <Calendar className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="font-mono">{formatDate(report.timestamp)}</span>
              </div>

              {/* Veredicto */}
              <div className={`flex-shrink-0 px-2 py-1 rounded text-[10px] font-semibold tracking-wide inline-flex items-center justify-center w-fit ${
                ['SUCCESS', 'EXCELLENT', 'GOOD'].includes(report.verdict?.toUpperCase())
                  ? 'bg-green-500/15 text-green-400' 
                  : 'bg-red-500/15 text-red-400'
              }`}>
                {report.verdict === 'SUCCESS' ? 'ÉXITO' : report.verdict === 'FAILED' ? 'FALLÓ' : report.verdict}
              </div>

              {/* Acciones */}
              <div className="flex items-center gap-2 justify-end">
                {/* Menú de descarga */}
                <div className="relative download-menu-container">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setOpenDownloadMenu(openDownloadMenu === report.id ? null : report.id)
                    }}
                    className="p-1.5 rounded-md text-dark-text-muted hover:bg-blue-500/15 hover:text-blue-400 transition-all"
                    title="Opciones de descarga"
                  >
                    {isDownloading === report.id ? <Loading size="xs" /> : <Download className="w-4 h-4" />}
                  </button>
                  
                  {openDownloadMenu === report.id && (
                    <div className="absolute right-0 top-full mt-1.5 bg-dark-surface-primary border border-dark-border-primary/40 rounded-lg shadow-gemini z-[9999] min-w-[180px] overflow-hidden">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          onDownloadCapture(e, report.id, report.filename)
                        }}
                        className="w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2"
                      >
                        <Download className="w-4 h-4 text-blue-400" />
                        <span>Descargar Captura</span>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          onDownloadPDF(e, report.id, report.filename)
                        }}
                        className="w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 border-t border-dark-border-primary/20"
                      >
                        <FileText className="w-4 h-4 text-purple-400" />
                        <span>Descargar PDF</span>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          onDownloadBoth(e, report.id, report.filename)
                        }}
                        className="w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 border-t border-dark-border-primary/20"
                      >
                        <Download className="w-4 h-4 text-green-400" />
                        <span>Descargar Ambos</span>
                      </button>
                    </div>
                  )}
                </div>

                {/* Eliminar */}
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onDeleteReport(e, report.id)
                  }}
                  className="p-1.5 rounded-md text-dark-text-muted hover:bg-red-500/15 hover:text-red-400 transition-all"
                  title="Eliminar reporte"
                >
                  {isDeleting === report.id ? <Loading size="xs" /> : <Trash2 className="w-4 h-4" />}
                </button>

                {/* Ver Detalles */}
                {!selectionMode && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      onViewReport(report)
                    }}
                    className="flex items-center gap-1.5 text-dark-accent-primary text-xs font-medium transition-all bg-dark-accent-primary/8 px-2.5 py-1.5 rounded-md border border-dark-accent-primary/15 hover:bg-dark-accent-primary/12"
                  >
                    Ver Detalles
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </Card>
      ))}
    </div>
  )
}
