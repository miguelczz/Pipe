import { useState, useRef } from 'react'
import { networkAnalysisService } from '../services/api'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Loading } from '../components/ui/Loading'
import {
  Upload,
  Activity,
  AlertTriangle,
  FileText,
  Package,
  HardDrive,
  Network,
  TrendingUp,
  Server,
  Globe,
} from 'lucide-react'
import { MarkdownRenderer } from '../components/chat/MarkdownRenderer'

export function NetworkAnalysisPage() {
  const [selectedFile, setSelectedFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  
  // Inicializar estado desde localStorage si existe
  const [result, setResult] = useState(() => {
    try {
      const savedResult = localStorage.getItem('networkAnalysisResult')
      if (!savedResult) return null
      
      const parsed = JSON.parse(savedResult)
      
      // Validar integridad de datos para evitar crash por datos viejos
      if (parsed?.stats?.top_protocols?.some(p => typeof p.percentage === 'undefined')) {
        console.warn('Datos persistidos inválidos detectados, limpiando...')
        localStorage.removeItem('networkAnalysisResult')
        return null
      }
      
      return parsed
    } catch (e) {
      console.error('Error parsing saved result:', e)
      return null
    }
  })
  
  const [fileMetadata, setFileMetadata] = useState(() => {
    try {
      const savedMetadata = localStorage.getItem('networkAnalysisFileMeta')
      return savedMetadata ? JSON.parse(savedMetadata) : null
    } catch (e) {
      return null
    }
  })

  const [error, setError] = useState('')
  const fileInputRef = useRef(null)

  const handleSelectClick = () => {
    // Resetear el valor para permitir seleccionar el mismo archivo y que dispare onChange
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
    fileInputRef.current?.click()
  }

  const handleFileChange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    const lowerName = file.name.toLowerCase()
    if (!lowerName.endsWith('.pcap') && !lowerName.endsWith('.pcapng')) {
      setError('Solo se permiten archivos de captura .pcap o .pcapng.')
      setSelectedFile(null)
      e.target.value = ''
      return
    }

    // Limpiar persistencia anterior al cambiar archivo
    localStorage.removeItem('networkAnalysisResult')
    localStorage.removeItem('networkAnalysisFileMeta')
    
    setError('')
    setSelectedFile(file)
    const meta = {
      name: file.name,
      size: file.size
    }
    setFileMetadata(meta)
    setResult(null)
    
    // Disparar análisis automáticamente
    performAnalysis(file, meta)
  }

  const handleAnalyze = () => {
    if (selectedFile) {
      performAnalysis(selectedFile, fileMetadata)
    } else {
      handleSelectClick()
    }
  }

  const performAnalysis = async (file, meta) => {
    setUploading(true)
    setError('')
    setResult(null)

    try {
      const res = await networkAnalysisService.analyzeCapture(file)
      
      // Debug: Ver estructura de datos
      console.log('Respuesta del análisis:', res)
      
      // Guardar en persistencia
      setResult(res)
      localStorage.setItem('networkAnalysisResult', JSON.stringify(res))
      localStorage.setItem('networkAnalysisFileMeta', JSON.stringify(meta))
      
    } catch (err) {
      console.error('Error al analizar captura:', err)
      const message =
        err?.message ||
        err?.data?.detail ||
        'Ocurrió un error al analizar la captura de red.'
      setError(message)
    } finally {
      setUploading(false)
    }
  }

  // Función para limpiar el nombre del archivo (quitar UUID y prefijos numéricos)
  const cleanFileName = (fileName) => {
    if (!fileName) return ''
    
    let clean = fileName
    
    // 1. Remover UUID del formato: "uuid_nombre.ext"
    const parts = clean.split('_')
    if (parts.length > 1 && parts[0].length > 20) { // Probable UUID
      clean = parts.slice(1).join('_')
    }
    
    // 2. Remover prefijos tipo "7." o "01."
    clean = clean.replace(/^\d+\./, '')
    return clean.trim()
  }

  // Función para formatear el tamaño del archivo
  const formatFileSize = (bytes) => {
    if (!bytes) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  // Función para formatear el veredicto técnico a español
  const formatVerdict = (verdict) => {
    if (!verdict) return 'N/A'
    
    const mapping = {
      'EXCELLENT': 'Excelente',
      'GOOD': 'Bueno',
      'PREVENTIVE_SUCCESS': 'Éxito Preventivo',
      'FAILED_BTM_REJECT': 'Fallo: Rechazo BTM',
      'FAILED_LOOP': 'Fallo: Bucle entre APs',
      'FAILED_NO_REASSOC': 'Fallo: Sin reconexión',
      'FAILED_ALGORITHM': 'Fallo de algoritmo',
      'WARNING_INCONCLUSIVE': 'Inconcluso',
      'NOT_EVALUABLE': 'No evaluable',
      'FAILED': 'Fallido',
      'ACCEPTABLE': 'Aceptable',
      'SLOW_BUT_SUCCESSFUL': 'Lento pero Exitoso',
      'NO_DATA': 'Sin Datos',
      'NO_STEERING_EVENTS': 'Sin Eventos'
    }

    return mapping[verdict] || verdict.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase())
  }

  // Función para manejar la impresión/PDF
  const handlePrint = () => {
    const fileName = result?.file_name || fileMetadata?.name || ''
    const cleanName = cleanFileName(fileName).split('.')[0].replace(/_/g, ' ').trim()
    
    // El título del documento influye en el nombre del archivo al guardar
    const originalTitle = document.title
    document.title = `NetMind ${cleanName}`
    
    window.print()
  }

  // Obtener nombre limpio para el encabezado de impresión
  const printTitle = result || fileMetadata 
    ? cleanFileName(result?.file_name || fileMetadata?.name).split('.')[0].replace(/_/g, ' ').trim()
    : ''

  return (
    <div className="container-app py-4 sm:py-8 overflow-x-hidden min-w-0 px-4">
      

      <div className="max-w-5xl mx-auto w-full min-w-0 space-y-6 pt-4 print:pt-2">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 sm:gap-6">
          <div className="flex-1 min-w-0">
            <h1 className="text-xl sm:text-2xl font-semibold text-dark-text-primary mb-2 tracking-tight flex items-center gap-2">
              <div className="p-2 rounded-lg bg-dark-accent-primary/20">
                <Activity className="w-5 h-5 sm:w-6 sm:h-6 text-dark-accent-primary" />
              </div>
              <span>Análisis de Capturas de Red</span>
            </h1>
            <p className="text-dark-text-secondary text-sm sm:text-[15px] leading-relaxed break-words text-wrap">
              Sube un archivo de captura de red en formato{' '}
              <code className="px-1.5 py-0.5 rounded bg-dark-bg-secondary text-dark-accent-primary text-xs font-mono">
                .pcap
              </code>{' '}
              o{' '}
              <code className="px-1.5 py-0.5 rounded bg-dark-bg-secondary text-dark-accent-primary text-xs font-mono">
                .pcapng
              </code>{' '}
              y NetMind generará un análisis detallado del tráfico observado usando
              inteligencia artificial.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-center gap-3 w-full sm:w-auto">
            {result && (
              <Button
                variant="outline"
                onClick={handlePrint}
                className="w-full sm:w-auto border-dark-accent-primary/10 text-dark-accent-primary hover:bg-dark-accent-primary/10"
              >
                <HardDrive className="w-4 h-4 mr-2" />
                Exportar PDF
              </Button>
            )}
            
            <input
              ref={fileInputRef}
              type="file"
              accept=".pcap,.pcapng"
              onChange={handleFileChange}
              className="hidden"
            />
            <Button
              type="button"
              onClick={handleSelectClick}
              disabled={uploading}
              className="w-full sm:w-auto"
            >
              {uploading ? (
                <>
                  <Loading size="sm" className="sm:mr-2" />
                  <span>Analizando...</span>
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4 sm:mr-2" />
                  <span>{result ? 'Analizar otra captura' : 'Seleccionar y analizar'}</span>
                </>
              )}
            </Button>
          </div>
        </div>

        {(selectedFile || (result && fileMetadata)) && (
          <Card className="p-4 border border-dark-accent-primary/20 bg-dark-accent-primary/5">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-dark-accent-primary/20">
                <FileText className="w-5 h-5 text-dark-accent-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-dark-text-primary mb-1">
                  Archivo {result ? 'analizado' : 'seleccionado'}
                </p>
                <p className="text-xs text-dark-text-secondary break-all truncate">
                  {cleanFileName(selectedFile?.name || fileMetadata?.name || result?.file_name)}
                </p>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-sm font-semibold text-dark-text-primary">
                  {formatFileSize(selectedFile?.size || fileMetadata?.size || 0)}
                </p>
                <p className="text-xs text-dark-text-muted">
                  {(selectedFile?.size || fileMetadata?.size || 0).toLocaleString()} bytes
                </p>
              </div>
            </div>
          </Card>
        )}

        {error && (
          <Card className="p-4 border border-dark-status-error/40 bg-dark-status-error/5 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-dark-status-error mt-0.5 flex-shrink-0" />
            <p className="text-sm text-dark-status-error">{error}</p>
          </Card>
        )}

        {uploading && !result && (
          <Card className="p-12 flex flex-col items-center justify-center gap-4">
            <div className="relative">
              <div className="absolute inset-0 rounded-full bg-dark-accent-primary/20 animate-ping"></div>
              <div className="relative p-4 rounded-full bg-dark-accent-primary/10">
                <Activity className="w-8 h-8 text-dark-accent-primary animate-pulse" />
              </div>
            </div>
            <div className="text-center space-y-2">
              <p className="text-base font-medium text-dark-text-primary">
                Analizando captura de red
              </p>
              <p className="text-sm text-dark-text-secondary max-w-md">
                NetMind está procesando tu archivo y generando un análisis detallado.
                Esto puede tardar unos segundos dependiendo del tamaño del archivo.
              </p>
            </div>
            <Loading size="md" />
          </Card>
        )}

        {result && (
          <div className="space-y-6">
            {/* Estadísticas principales - Métricas de Band Steering */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card className="p-5 bg-gradient-to-br from-blue-500/10 to-blue-600/5 border-blue-500/20">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-blue-500/20">
                    <Activity className="w-5 h-5 text-blue-400" />
                  </div>
                  <div>
                    <p className="text-xs text-dark-text-muted uppercase tracking-wide">
                      Eventos 802.11
                    </p>
                    <p className="text-2xl font-bold text-dark-text-primary">
                      {result.stats?.diagnostics?.steering_events_count ?? '0'}
                    </p>
                  </div>
                </div>
              </Card>

              <Card className="p-5 bg-gradient-to-br from-green-500/10 to-green-600/5 border-green-500/20">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-green-500/20">
                    <TrendingUp className="w-5 h-5 text-green-400" />
                  </div>
                  <div>
                    <p className="text-xs text-dark-text-muted uppercase tracking-wide">
                      Transiciones exitosas
                    </p>
                    <p className="text-2xl font-bold text-dark-text-primary">
                      {result.stats?.steering_analysis?.successful_transitions ?? '0'}
                    </p>
                  </div>
                </div>
              </Card>

              <Card className="p-5 bg-gradient-to-br from-purple-500/10 to-purple-600/5 border-purple-500/20">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-purple-500/20">
                    <Network className="w-5 h-5 text-purple-400" />
                  </div>
                  <div>
                    <p className="text-xs text-dark-text-muted uppercase tracking-wide">
                      BSSIDs detectados
                    </p>
                    <p className="text-2xl font-bold text-dark-text-primary">
                      {Object.keys(result.stats?.diagnostics?.bssid_info || {}).length}
                    </p>
                  </div>
                </div>
              </Card>
            </div>

            {/* Layout principal: Estadísticas detalladas y Análisis */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
              {/* Panel lateral: Estadísticas detalladas */}
              <div className="lg:col-span-1 space-y-4">
                {/* Información del archivo */}
                <Card className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <FileText className="w-4 h-4 text-dark-accent-primary" />
                    <h3 className="text-sm font-semibold text-dark-text-primary">
                      Información del archivo
                    </h3>
                  </div>
                  <div className="space-y-2">
                    <div>
                      <p className="text-xs text-dark-text-muted mb-1">Nombre</p>
                      <p className="text-sm font-mono text-dark-text-primary break-all">
                        {cleanFileName(result.file_name || selectedFile?.name || fileMetadata?.name)}
                      </p>
                    </div>
                    {(selectedFile || fileMetadata) && (
                      <div>
                        <p className="text-xs text-dark-text-muted mb-1">Tamaño</p>
                        <p className="text-sm text-dark-text-primary">
                          {formatFileSize(selectedFile?.size || fileMetadata?.size || 0)}
                        </p>
                      </div>
                    )}
                  </div>
                </Card>

                {/* Métricas de Band Steering */}
                <Card className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Activity className="w-4 h-4 text-dark-accent-primary" />
                    <h3 className="text-sm font-semibold text-dark-text-primary">
                      Métricas de Steering
                    </h3>
                  </div>
                  <div className="space-y-3">
                    <div className="p-2 rounded-lg bg-dark-bg-secondary/50">
                      <p className="text-xs text-dark-text-muted mb-1">Estándares KVR Identificados</p>
                      <p className="text-sm font-semibold text-dark-text-primary">
                        {(() => {
                          const kvr = result.stats?.diagnostics?.band_counters?.kvr_stats || {}
                          const detected = []
                          if (kvr['11k']) detected.push('11k')
                          if (kvr['11v']) detected.push('11v')
                          if (kvr['11r']) detected.push('11r')
                          return detected.length > 0 ? detected.join(', ') : 'Ninguno'
                        })()}
                      </p>
                    </div>
                    <div className="p-2 rounded-lg bg-dark-bg-secondary/50">
                      <p className="text-xs text-dark-text-muted mb-1">Intentos de steering</p>
                      <p className="text-sm font-semibold text-dark-text-primary">
                        {result.stats?.steering_analysis?.steering_attempts ?? 0}
                      </p>
                    </div>
                    <div className="p-2 rounded-lg bg-dark-bg-secondary/50">
                      <p className="text-xs text-dark-text-muted mb-1">Tiempo promedio</p>
                      <p className="text-sm font-semibold text-dark-text-primary">
                        {result.stats?.steering_analysis?.avg_transition_time ?? 0}s
                      </p>
                    </div>
                  </div>
                </Card>

              </div>

              {/* Panel principal: Análisis de IA */}
              <Card className="lg:col-span-2 p-6">
                <div className="space-y-4">
                  {/* Header con Veredicto Visual */}
                  <div className="flex items-start justify-between gap-4 pb-4 border-b border-dark-border-primary/30">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-lg bg-dark-accent-primary/20">
                        <Activity className="w-5 h-5 text-dark-accent-primary" />
                      </div>
                      <div>
                        <h2 className="text-lg font-semibold text-dark-text-primary">
                          Análisis de Band Steering
                        </h2>
                        <p className="text-sm text-dark-text-secondary mt-1">
                          Evaluación técnica de capacidades 802.11k/v/r
                        </p>
                      </div>
                    </div>
                    
                    {/* Badge de Veredicto */}
                    {result.stats?.steering_analysis && (() => {
                      const verdict = result.stats.steering_analysis.verdict || ''
                      // Definir explícitamente qué veredictos son "Éxito" (Verde)
                      const successVerdicts = ['EXCELLENT', 'GOOD', 'PREVENTIVE_SUCCESS', 'ACCEPTABLE', 'SLOW_BUT_SUCCESSFUL']
                      const isSuccess = successVerdicts.includes(verdict)
                      
                      return (
                        <div className={`px-4 py-2 rounded-lg font-semibold text-sm flex items-center gap-2 ${
                          isSuccess 
                            ? 'bg-green-500/20 text-green-400 border border-green-500/30' 
                            : 'bg-red-500/20 text-red-400 border border-red-500/30'
                        }`}>
                          {isSuccess ? '✅' : '❌'}
                          <span>{formatVerdict(verdict).toUpperCase()}</span>
                        </div>
                      )
                    })()}
                  </div>
                  
                  {/* Contenido del Análisis */}
                  <div className="prose prose-invert prose-sm max-w-none">
                    <div className="text-dark-text-primary leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                      <MarkdownRenderer content={result.analysis || ''} />
                    </div>
                  </div>
                </div>
              </Card>

            </div>
          </div>
        )}
      </div>

      {/* Estilos para impresión */}
      <style dangerouslySetInnerHTML={{ __html: `
        @page {
          margin: 1.5cm;
          size: auto;
        }

        @media print {
          /* Ocultar elementos de UI no necesarios de forma específica */
          nav, 
          button, 
          header,
          .flex-shrink-0,
          /* Seleccionar específicamente el contenedor de botones en el header para ocultarlo */
          .container-app > div:nth-child(2) > div:first-child > div:last-child {
            display: none !important;
          }

          /* Asegurar que el título de impresión esté arriba a la derecha */
          .print\\:flex {
            display: flex !important;
            position: fixed !important;
            top: 0 !important;
            right: 0 !important;
            z-index: 1000;
          }
          
          /* Reset de Layout para PDF */
          .container-app, body, #root {
            background: white !important;
            color: black !important;
            padding: 0 !important;
            margin: 0 !important;
            height: auto !important;
            width: 100% !important;
          }

          .max-w-5xl {
            max-width: 100% !important;
            width: 100% !important;
            box-shadow: none !important;
          }
          
          /* Forzar visibilidad de texto y bordes */
          h1, h2, h3, h4, p, span, div, li, td, th {
            color: #000 !important;
            background-color: transparent !important;
          }
          
          .text-dark-text-primary, 
          .text-dark-text-secondary, 
          .text-dark-text-muted,
          .text-white {
            color: #111 !important;
          }
          
          /* Cards con bordes para definición visual en papel */
          .Card, [class*="bg-dark-accent-primary/5"], [class*="bg-gradient-to-br"] {
            background: #fff !important;
            border: 1px solid #ccc !important;
            box-shadow: none !important;
            color: black !important;
            margin-bottom: 1rem !important;
            break-inside: avoid;
          }

          /* Arreglar Grid para impresión */
          .grid {
            display: block !important;
          }
          .md\\:grid-cols-3 {
            display: flex !important;
            flex-direction: row !important;
            gap: 1% !important;
            margin-bottom: 20px !important;
          }
          .md\\:grid-cols-3 > div {
            flex: 1 !important;
            width: 32% !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            min-height: 75px !important; /* Más compactos */
            padding: 10px 15px !important; /* Menos padding */
            margin-right: 0 !important;
          }

          .lg\\:grid-cols-3 {
            display: block !important;
          }
          .lg\\:col-span-1 {
            width: 100% !important;
            margin-bottom: 20px !important;
          }
          
          /* FORZAR SALTO DE PÁGINA PARA EL ANÁLISIS */
          .lg\\:col-span-2 {
            width: 100% !important;
            page-break-before: always !important;
            margin-top: 0 !important;
            padding-top: 3rem !important; /* Espacio extra para que no pegue arriba */
          }

          /* Ajustar Markdown (prose) para impresión */
          .prose {
            color: black !important;
            max-width: 100% !important;
          }
          .prose * {
            color: black !important;
          }
          .prose h2, .prose h3 {
            border-bottom: 1px solid #eee !important;
            margin-top: 1.5rem !important;
            padding-bottom: 0.5rem !important;
          }
          
          /* Detalle de veredicto en PDF */
          [class*="rounded-lg font-semibold"] {
            border: 2px solid #000 !important;
            background: #f8f8f8 !important;
            padding: 8px 16px !important;
          }
        }
      `}} />
    </div>
  )
}

export default NetworkAnalysisPage

