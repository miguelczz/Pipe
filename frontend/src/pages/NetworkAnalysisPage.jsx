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
    setFileMetadata({
      name: file.name,
      size: file.size
    })
    setResult(null)
  }

  const handleAnalyze = async () => {
    if (!selectedFile) {
      setError('Selecciona primero un archivo de captura .pcap o .pcapng.')
      return
    }

    setUploading(true)
    setError('')
    setResult(null)

    try {
      const res = await networkAnalysisService.analyzeCapture(selectedFile)
      
      // Guardar en persistencia
      setResult(res)
      localStorage.setItem('networkAnalysisResult', JSON.stringify(res))
      
      const meta = { name: selectedFile.name, size: selectedFile.size }
      setFileMetadata(meta)
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

  return (
    <div className="container-app py-4 sm:py-8 overflow-x-hidden min-w-0 px-4">
      <div className="max-w-5xl mx-auto w-full min-w-0 space-y-6">
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

          <div className="flex-shrink-0 flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
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
              <Upload className="w-4 h-4 sm:mr-2" />
              <span className="hidden sm:inline">Seleccionar archivo</span>
              <span className="sm:hidden">Seleccionar</span>
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={handleAnalyze}
              disabled={uploading || !selectedFile}
              className="w-full sm:w-auto"
            >
              {uploading ? (
                <>
                  <Loading size="sm" className="sm:mr-2" />
                  <span>Analizando...</span>
                </>
              ) : (
                <>
                  <Activity className="w-4 h-4 sm:mr-2" />
                  <span>{result ? 'Analizar otro' : 'Analizar captura'}</span>
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
                  {selectedFile?.name || fileMetadata?.name}
                </p>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-sm font-semibold text-dark-text-primary">
                  {((selectedFile?.size || fileMetadata?.size || 0) / (1024 * 1024)).toFixed(2)} MB
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
            {/* Estadísticas principales */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card className="p-5 bg-gradient-to-br from-blue-500/10 to-blue-600/5 border-blue-500/20">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-blue-500/20">
                    <Package className="w-5 h-5 text-blue-400" />
                  </div>
                  <div>
                    <p className="text-xs text-dark-text-muted uppercase tracking-wide">
                      Paquetes analizados
                    </p>
                    <p className="text-2xl font-bold text-dark-text-primary">
                      {result.stats?.total_packets?.toLocaleString() ?? '0'}
                    </p>
                  </div>
                </div>
              </Card>

              <Card className="p-5 bg-gradient-to-br from-green-500/10 to-green-600/5 border-green-500/20">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 rounded-lg bg-green-500/20">
                    <HardDrive className="w-5 h-5 text-green-400" />
                  </div>
                  <div>
                    <p className="text-xs text-dark-text-muted uppercase tracking-wide">
                      Bytes aproximados
                    </p>
                    <p className="text-2xl font-bold text-dark-text-primary">
                      {result.stats?.approx_total_bytes
                        ? (result.stats.approx_total_bytes / 1024).toFixed(2) + ' KB'
                        : '0 KB'}
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
                      Protocolos únicos
                    </p>
                    <p className="text-2xl font-bold text-dark-text-primary">
                      {result.stats?.top_protocols?.length ?? 0}
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
                        {result.file_name || selectedFile?.name || fileMetadata?.name}
                      </p>
                    </div>
                    {(selectedFile || fileMetadata) && (
                      <div>
                        <p className="text-xs text-dark-text-muted mb-1">Tamaño</p>
                        <p className="text-sm text-dark-text-primary">
                          {((selectedFile?.size || fileMetadata?.size || 0) / (1024 * 1024)).toFixed(2)} MB
                        </p>
                      </div>
                    )}
                  </div>
                </Card>

                {/* Protocolos principales */}
                {Array.isArray(result.stats?.top_protocols) &&
                  result.stats.top_protocols.length > 0 && (
                    <Card className="p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <TrendingUp className="w-4 h-4 text-dark-accent-primary" />
                        <h3 className="text-sm font-semibold text-dark-text-primary">
                          Protocolos principales
                        </h3>
                      </div>
                      <div className="space-y-2">
                        {result.stats.top_protocols.slice(0, 8).map((p, idx) => (
                          <div
                            key={p.protocol}
                            className="flex items-center justify-between gap-3 p-2 rounded-lg bg-dark-bg-secondary/50 hover:bg-dark-bg-secondary transition-colors"
                          >
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              <span className="text-xs font-medium text-dark-text-muted w-5">
                                #{idx + 1}
                              </span>
                              <span className="font-mono text-xs text-dark-text-primary truncate">
                                {p.protocol}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 flex-shrink-0">
                              <span className="text-xs text-dark-text-secondary">
                                {p.count}
                              </span>
                              <span className="text-xs text-dark-text-muted min-w-[3rem] text-right">
                                {(p.percentage ?? 0).toFixed(1)}%
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </Card>
                  )}

                {/* IPs origen */}
                {Array.isArray(result.stats?.top_sources) &&
                  result.stats.top_sources.length > 0 && (
                    <Card className="p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <Server className="w-4 h-4 text-dark-accent-primary" />
                        <h3 className="text-sm font-semibold text-dark-text-primary">
                          IPs origen (Top 5)
                        </h3>
                      </div>
                      <div className="space-y-2">
                        {result.stats.top_sources.slice(0, 5).map((s, idx) => (
                          <div
                            key={s.ip}
                            className="flex items-center justify-between gap-2 p-2 rounded-lg bg-dark-bg-secondary/50"
                          >
                            <span className="font-mono text-xs text-dark-text-primary truncate">
                              {s.ip}
                            </span>
                            <span className="text-xs text-dark-text-muted flex-shrink-0">
                              {s.count} pkt
                            </span>
                          </div>
                        ))}
                      </div>
                    </Card>
                  )}

                {/* IPs destino */}
                {Array.isArray(result.stats?.top_destinations) &&
                  result.stats.top_destinations.length > 0 && (
                    <Card className="p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <Globe className="w-4 h-4 text-dark-accent-primary" />
                        <h3 className="text-sm font-semibold text-dark-text-primary">
                          IPs destino (Top 5)
                        </h3>
                      </div>
                      <div className="space-y-2">
                        {result.stats.top_destinations.slice(0, 5).map((d, idx) => (
                          <div
                            key={d.ip}
                            className="flex items-center justify-between gap-2 p-2 rounded-lg bg-dark-bg-secondary/50"
                          >
                            <span className="font-mono text-xs text-dark-text-primary truncate">
                              {d.ip}
                            </span>
                            <span className="text-xs text-dark-text-muted flex-shrink-0">
                              {d.count} pkt
                            </span>
                          </div>
                        ))}
                      </div>
                    </Card>
                  )}
              </div>

              {/* Panel principal: Análisis de IA */}
              <Card className="lg:col-span-2 p-6">
                <div className="flex items-center gap-2 mb-5 pb-4 border-b border-dark-border-primary/30">
                  <div className="p-2 rounded-lg bg-dark-accent-primary/20">
                    <Activity className="w-5 h-5 text-dark-accent-primary" />
                  </div>
                  <h2 className="text-lg font-semibold text-dark-text-primary">
                    Análisis de Tráfico
                  </h2>
                </div>
                <div className="prose prose-invert prose-sm max-w-none">
                  <div className="text-dark-text-primary leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                    <MarkdownRenderer content={result.analysis || ''} />
                  </div>
                </div>
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default NetworkAnalysisPage

