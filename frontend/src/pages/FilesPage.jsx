import { useState, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { filesService } from '../services/api'
import { Button } from '../components/ui/Button'
import { Loading } from '../components/ui/Loading'
import { Upload, Trash2, FileText, Calendar } from 'lucide-react'
import { useToast } from '../hooks/useToast'

/**
 * Página para gestionar archivos subidos
 */
export function FilesPage() {
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef(null)
  const { showToast } = useToast()

  const {
    data: files = [],
    isLoading,
    error: filesError,
    refetch,
  } = useQuery({
    queryKey: ['files'],
    queryFn: filesService.getFiles,
    retry: 1,
    refetchOnWindowFocus: false,
  })

  const handleFileSelect = () => {
    fileInputRef.current?.click()
  }

  const handleFileUpload = async (e) => {
    const selectedFiles = e.target.files ? Array.from(e.target.files) : []
    if (!selectedFiles.length) return

    const pdfs = selectedFiles.filter((f) => f.type === 'application/pdf')
    const skipped = selectedFiles.length - pdfs.length
    if (skipped > 0) {
      showToast({
        type: 'warning',
        message: `${skipped} archivo(s) omitido(s): solo se permiten PDF`,
      })
    }
    if (!pdfs.length) {
      e.target.value = ''
      return
    }

    setUploading(true)
    try {
      const results = await filesService.uploadFiles(pdfs)
      await refetch()
      const ok = results.filter((r) => r.status === 'processed').length
      const err = results.filter((r) => r.status?.startsWith('error') || r.status === 'skipped').length
      if (err === 0) {
        showToast({ type: 'success', message: ok === 1 ? 'Archivo subido correctamente' : `${ok} archivos subidos correctamente` })
      } else if (ok > 0) {
        showToast({ type: 'warning', message: `${ok} subido(s), ${err} con error u omitidos` })
      } else {
        showToast({ type: 'error', message: results[0]?.status || 'Error al subir archivos' })
      }
      e.target.value = ''
    } catch (error) {
      showToast({
        type: 'error',
        message: `Error al subir archivos: ${error.message || 'Error desconocido'}`,
      })
      e.target.value = ''
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (documentId) => {
    if (!confirm('¿Estás seguro de eliminar este archivo?')) return

    try {
      await filesService.deleteFile(documentId)
      await refetch()
    } catch (error) {
      showToast({
        type: 'error',
        message: `Error al eliminar archivo: ${error.message}`,
      })
    }
  }

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A'
    const date = new Date(dateString)
    return date.toLocaleDateString('es-ES', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  return (
    <div className="container-app py-4 sm:py-8 overflow-x-hidden min-w-0 px-4">
      <div className="max-w-4xl mx-auto w-full min-w-0">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6 sm:mb-8 gap-4 sm:gap-6">
          <div className="flex-1 min-w-0">
            <h1 className="text-xl sm:text-2xl font-medium text-dark-text-primary mb-1 sm:mb-2 tracking-tight">
              Gestión de Archivos
            </h1>
            <p className="text-dark-text-secondary text-sm sm:text-[15px] leading-relaxed break-words text-wrap">
              Sube uno o varios PDF como guía para entender capturas de Wireshark y sus resultados. El agente los usará para responder consultas.
            </p>
          </div>

          <div className="flex-shrink-0">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              multiple
              onChange={handleFileUpload}
              disabled={uploading}
              className="hidden"
            />
            <Button
              type="button"
              onClick={handleFileSelect}
              disabled={uploading}
              className="w-full sm:w-auto"
            >
              {uploading ? (
                <>
                  <Loading size="sm" className="sm:mr-2" />
                  <span className="hidden sm:inline">Subiendo...</span>
                  <span className="sm:hidden">Subiendo...</span>
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4 sm:mr-2" />
                  <span className="hidden sm:inline">Subir PDF(s)</span>
                  <span className="sm:hidden">Subir PDF(s)</span>
                </>
              )}
            </Button>
          </div>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-16">
            <Loading size="lg" />
          </div>
        ) : filesError ? (
          <div className="card-gemini p-12 text-center">
            <FileText className="w-16 h-16 mx-auto mb-4 text-dark-text-muted opacity-50" />
            <p className="text-dark-text-secondary mb-6 text-[15px] leading-relaxed">
              Error al cargar archivos: {filesError.message || 'Error desconocido'}
            </p>
            <Button onClick={() => refetch()} variant="secondary" size="sm">
              Reintentar
            </Button>
          </div>
        ) : files.length === 0 ? (
          <div className="card-gemini p-12 text-center">
            <FileText className="w-16 h-16 mx-auto mb-4 text-dark-text-muted opacity-50" />
            <p className="text-dark-text-secondary text-[15px] leading-relaxed">
              No hay archivos subidos. Sube un PDF para comenzar.
            </p>
          </div>
        ) : (
          <div className="space-y-2 sm:space-y-3 w-full min-w-0">
            {files.map((file) => (
              <div
                key={file.document_id}
                className="card-gemini p-3 sm:p-4 flex items-center justify-between group gap-3 sm:gap-4 w-full min-w-0 overflow-hidden"
              >
                <div className="flex items-center gap-3 sm:gap-4 flex-1 min-w-0 overflow-hidden">
                  <div className="flex-shrink-0 w-10 h-10 sm:w-11 sm:h-11 rounded-xl bg-dark-accent-primary/15 flex items-center justify-center border border-dark-accent-primary/20">
                    <FileText className="w-4 h-4 sm:w-5 sm:h-5 text-dark-accent-primary" />
                  </div>
                  <div className="flex-1 min-w-0 overflow-hidden">
                    <h3 className="font-medium text-dark-text-primary truncate text-sm sm:text-[15px]">
                      {file.filename}
                    </h3>
                    <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4 mt-1 sm:mt-1.5 text-xs sm:text-sm text-dark-text-muted">
                      <span className="flex items-center gap-1.5 truncate">
                        <Calendar className="w-3 h-3 sm:w-3.5 sm:h-3.5 flex-shrink-0" />
                        <span className="truncate">{formatDate(file.uploaded_at)}</span>
                      </span>
                      {file.chunk_count && (
                        <span className="hidden sm:inline flex-shrink-0">{file.chunk_count} fragmentos</span>
                      )}
                    </div>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDelete(file.document_id)}
                  className="text-dark-status-error hover:bg-dark-status-error/10 ml-2 sm:ml-4 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity rounded-xl flex-shrink-0"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default FilesPage

