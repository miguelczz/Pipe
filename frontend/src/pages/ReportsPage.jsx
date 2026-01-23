import { useState, useEffect, useMemo } from 'react'
import { reportsService } from '../services/api'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Loading } from '../components/ui/Loading'
import { 
  FileText, 
  Calendar, 
  ChevronRight, 
  History, 
  CheckCircle2, 
  XCircle, 
  AlertCircle,
  Search,
  Filter,
  Folder,
  ChevronDown,
  Trash2,
  Smartphone,
  Cpu,
  MoreVertical,
  ArrowRight
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'

export function ReportsPage() {
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL') // ALL, SUCCESS, FAILED
  const [expandedVendors, setExpandedVendors] = useState({})
  const [isDeleting, setIsDeleting] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    fetchReports()
  }, [])

  const fetchReports = async () => {
    setLoading(true)
    try {
      const data = await reportsService.getReports()
      setReports(data)
      setError(null)
      
      // Auto-expandir la primera marca por defecto
      if (data.length > 0) {
        const firstVendor = data[0].vendor || 'Desconocido'
        setExpandedVendors({ [firstVendor]: true })
      }
    } catch (err) {
      console.error('Error al cargar reportes:', err)
      setError('No se pudieron cargar los reportes históricos.')
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteReport = async (e, reportId) => {
    e.stopPropagation()
    if (!window.confirm('¿Estás seguro de que deseas eliminar este reporte? Esta acción no se puede deshacer.')) return
    
    setIsDeleting(reportId)
    try {
      await reportsService.deleteReport(reportId)
      // Actualizar lista local
      setReports(prev => prev.filter(r => r.id !== reportId))
    } catch (err) {
      console.error('Error al eliminar:', err)
      alert('Error al intentar eliminar el reporte.')
    } finally {
      setIsDeleting(null)
    }
  }

  const handleViewReport = (report) => {
    reportsService.getReportDetail(report.id).then(fullDetail => {
      let bssidInfo = fullDetail.raw_stats?.diagnostics?.bssid_info || {}
      
      if (Object.keys(bssidInfo).length === 0 && fullDetail.btm_events && fullDetail.btm_events.length > 0) {
        fullDetail.btm_events.forEach(event => {
          if (event.ap_bssid && !bssidInfo[event.ap_bssid]) {
            bssidInfo[event.ap_bssid] = {
              band: event.band || null,
              ssid: 'Unknown',
              frequency: event.frequency || null
            }
          }
        })
      }
      
      const formattedResult = {
        file_name: fullDetail.filename,
        analysis: fullDetail.analysis_text,
        stats: fullDetail.raw_stats || {},
        aidlc: {
            analysis_id: fullDetail.analysis_id,
            verdict: fullDetail.verdict,
            device: fullDetail.devices?.[0] || {},
            compliance_checks: fullDetail.compliance_checks || [],
            fragments_count: fullDetail.fragments?.length || 0
        }
      }
      
      if (!formattedResult.stats.diagnostics) {
          formattedResult.stats = {
              diagnostics: {
                  steering_events_count: fullDetail.btm_events?.length || 0,
                  client_mac: fullDetail.devices?.[0]?.mac_address || 'Desconocido',
                  bssid_info: bssidInfo,
                  capture_quality: 'VALIDA - Reporte histórico'
              },
              steering_analysis: {
                  successful_transitions: fullDetail.successful_transitions || 0,
                  steering_attempts: fullDetail.btm_requests || 0,
                  verdict: fullDetail.verdict
              }
          }
      }

      localStorage.setItem('networkAnalysisResult', JSON.stringify(formattedResult))
      localStorage.setItem('networkAnalysisFileMeta', JSON.stringify({
        name: fullDetail.filename,
        size: fullDetail.total_packets * 100
      }))
      navigate('/network-analysis')
    })
  }

  // Lógica de filtrado y agrupamiento
  const groupedReports = useMemo(() => {
    const filtered = reports.filter(report => {
      const matchSearch = (
        report.filename?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        report.vendor?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        report.model?.toLowerCase().includes(searchTerm.toLowerCase())
      )
      
      const matchStatus = (
        statusFilter === 'ALL' ||
        (statusFilter === 'SUCCESS' && ['SUCCESS', 'EXCELLENT', 'GOOD'].includes(report.verdict?.toUpperCase())) ||
        (statusFilter === 'FAILED' && report.verdict?.toUpperCase() === 'FAILED')
      )
      
      return matchSearch && matchStatus
    })

    // Agrupar por Vendor
    return filtered.reduce((groups, report) => {
      const vendor = report.vendor || 'Desconocido'
      if (!groups[vendor]) groups[vendor] = []
      groups[vendor].push(report)
      return groups
    }, {})
  }, [reports, searchTerm, statusFilter])

  const toggleVendor = (vendor) => {
    setExpandedVendors(prev => ({
      ...prev,
      [vendor]: !prev[vendor]
    }))
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A'
    const date = new Date(dateStr)
    const d = String(date.getDate()).padStart(2, '0')
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const y = date.getFullYear()
    return `${d}/${m}/${y}`
  }

  return (
    <div className="container-app py-8 space-y-8">
      {/* Header Interactivo */}
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6">
        <div className="space-y-1">
          <h1 className="text-3xl font-bold text-dark-text-primary flex items-center gap-3">
            <History className="w-8 h-8 text-dark-accent-primary" />
            Historial de Reportes
          </h1>
          <p className="text-dark-text-secondary text-base">
            Gestión de capturas organizadas por fabricante.
          </p>
        </div>
        
        <div className="flex flex-col sm:flex-row gap-4">
          {/* Filtros de Veredicto */}
          <div className="flex bg-dark-bg-secondary/50 rounded-xl p-1 border border-dark-border-primary/20">
            {['ALL', 'SUCCESS', 'FAILED'].map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  statusFilter === s 
                    ? 'bg-dark-accent-primary text-white shadow-lg' 
                    : 'text-dark-text-muted hover:text-dark-text-primary'
                }`}
              >
                {s === 'ALL' ? 'Todos' : s === 'SUCCESS' ? 'Éxitos' : 'Fallos'}
              </button>
            ))}
          </div>

          <div className="relative w-full sm:w-80">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4.5 h-4.5 text-dark-text-muted" />
            <input
              type="text"
              placeholder="Buscar por archivo, marca o modelo..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-dark-bg-secondary border border-dark-border-primary/30 rounded-xl py-2.5 pl-11 pr-4 text-sm text-dark-text-primary focus:outline-none focus:ring-2 focus:ring-dark-accent-primary/50 transition-all placeholder:text-dark-text-muted/60"
            />
          </div>
        </div>
      </div>

      <div className="space-y-4">
        {loading ? (
          <div className="py-24 flex flex-col items-center justify-center gap-4">
            <Loading size="lg" />
            <p className="text-dark-text-secondary animate-pulse text-sm font-medium">Sincronizando reportes...</p>
          </div>
        ) : error ? (
          <Card className="p-10 text-center space-y-4 border-dark-status-error/30 bg-dark-status-error/5">
            <div className="bg-dark-status-error/10 w-16 h-16 rounded-full flex items-center justify-center mx-auto">
              <AlertCircle className="w-8 h-8 text-dark-status-error" />
            </div>
            <div className="space-y-1">
              <p className="text-dark-text-primary font-semibold text-lg">{error}</p>
              <p className="text-dark-text-secondary text-sm">Verifica tu conexión con el backend.</p>
            </div>
            <Button onClick={fetchReports} variant="outline" className="border-dark-status-error/30 text-dark-status-error hover:bg-dark-status-error/10">Reintentar</Button>
          </Card>
        ) : Object.keys(groupedReports).length === 0 ? (
          <Card className="p-16 text-center space-y-5 border-dashed border-2 border-dark-border-primary/20 bg-transparent rounded-2xl">
            <Folder className="w-16 h-16 text-dark-text-muted/30 mx-auto" />
            <div className="space-y-1">
              <p className="text-dark-text-primary font-bold text-xl">Sin reportes que mostrar</p>
              <p className="text-dark-text-secondary text-base">
                {searchTerm || statusFilter !== 'ALL' 
                  ? 'No hay reportes que coincidan con los filtros seleccionados.' 
                  : 'Aún no has generado ningún análisis. Sube una captura para comenzar.'}
              </p>
            </div>
            {!searchTerm && statusFilter === 'ALL' && (
              <Button onClick={() => navigate('/network-analysis')} className="mt-2">
                Realizar Primer Análisis
              </Button>
            )}
          </Card>
        ) : (
          <div className="space-y-6">
            {Object.entries(groupedReports).map(([vendor, vendorReports]) => {
              const isOpen = expandedVendors[vendor]
              
              return (
                <div key={vendor} className="space-y-3">
                  {/* Folder Header */}
                  <div 
                    onClick={() => toggleVendor(vendor)}
                    className={`flex items-center justify-between p-4 rounded-xl cursor-pointer transition-all border ${
                      isOpen 
                        ? 'bg-dark-bg-secondary border-dark-accent-primary/30 shadow-lg' 
                        : 'bg-dark-bg-secondary/40 border-dark-border-primary/20 hover:border-dark-accent-primary/20'
                    }`}
                  >
                    <div className="flex items-center gap-4">
                      <div className={`p-2 rounded-lg transition-colors ${isOpen ? 'bg-dark-accent-primary text-white' : 'bg-dark-bg-secondary text-dark-accent-primary'}`}>
                        <Folder className="w-5 h-5 flex-shrink-0" />
                      </div>
                      <div>
                        <h2 className="text-lg font-bold text-dark-text-primary flex items-center gap-2 uppercase tracking-wide">
                          {vendor}
                          <span className="text-xs bg-dark-bg-secondary px-2 py-0.5 rounded-full text-dark-text-muted normal-case font-medium">
                            {vendorReports.length} {vendorReports.length === 1 ? 'reporte' : 'reportes'}
                          </span>
                        </h2>
                      </div>
                    </div>
                    {isOpen ? <ChevronDown className="w-5 h-5 text-dark-text-muted" /> : <ChevronRight className="w-5 h-5 text-dark-text-muted" />}
                  </div>

                  {/* Folder Content (Files) */}
                  {isOpen && (
                    <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4 pl-0 md:pl-2">
                      {vendorReports.map((report) => (
                        <Card 
                          key={report.id} 
                          className={`relative group p-4 hover:border-dark-accent-primary/50 cursor-pointer bg-dark-bg-secondary/20 hover:bg-dark-bg-secondary/40 border-dark-border-primary/10 transition-colors duration-200 ${isDeleting === report.id ? 'opacity-50 pointer-events-none' : ''}`}
                          onClick={() => handleViewReport(report)}
                        >
                          <div className="flex flex-col h-full space-y-3">
                            {/* Header: Modelo y Veredicto */}
                            <div className="flex items-center justify-between gap-3">
                              <div className="flex-1 min-w-0">
                                <h3 className="text-lg font-bold text-dark-text-primary truncate tracking-tight group-hover:text-dark-accent-primary transition-colors">
                                  {report.model || 'Dispositivo Desconocido'}
                                </h3>
                                <div className="flex items-center gap-1.5 text-[11px] text-dark-text-muted mt-0.5">
                                  <FileText className="w-3 h-3" />
                                  <span className="truncate max-w-[180px]" title={report.filename}>
                                    {/* Limpiar UUID del nombre si existe (formato UUID_Nombre) */}
                                    {report.filename?.includes('_') && report.filename.split('_')[0].length === 36 
                                      ? report.filename.split('_').slice(1).join('_') 
                                      : report.filename}
                                  </span>
                                </div>
                              </div>
                              
                              <div className="flex items-center gap-2">
                                <button
                                  onClick={(e) => handleDeleteReport(e, report.id)}
                                  className="p-1.5 rounded-lg text-dark-text-muted hover:bg-red-500/20 hover:text-red-400 transition-all opacity-0 group-hover:opacity-100"
                                  title="Eliminar reporte"
                                >
                                  {isDeleting === report.id ? <Loading size="xs" /> : <Trash2 className="w-4 h-4" />}
                                </button>
                                
                                <div className={`flex-shrink-0 px-2.5 py-1 rounded-md font-black text-[10px] tracking-widest border ${
                                  ['SUCCESS', 'EXCELLENT', 'GOOD'].includes(report.verdict?.toUpperCase())
                                    ? 'bg-green-500/10 text-green-400 border-green-500/20' 
                                    : 'bg-red-500/10 text-red-100 border-red-500/20'
                                }`}>
                                  {report.verdict === 'SUCCESS' ? 'ÉXITO' : report.verdict === 'FAILED' ? 'FALLÓ' : report.verdict}
                                </div>
                              </div>
                            </div>

                            {/* Divider sutil */}
                            <div className="h-px bg-gradient-to-r from-dark-border-primary/20 via-transparent to-transparent"></div>

                            {/* Metadata y Acciones */}
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-1.5 text-[11px] text-dark-text-muted/70">
                                <Calendar className="w-3.5 h-3.5" />
                                {formatDate(report.timestamp)}
                              </div>
                              
                              <div className="flex items-center gap-2">
                                <div className="flex items-center gap-1.5 text-dark-accent-primary text-xs font-bold transition-all bg-dark-accent-primary/5 px-2.5 py-1 rounded-lg border border-dark-accent-primary/10">
                                  AUDITAR
                                  <ArrowRight className="w-3.5 h-3.5" />
                                </div>
                              </div>
                            </div>
                          </div>
                        </Card>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

export default ReportsPage
