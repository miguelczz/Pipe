import { useState, useEffect, useMemo } from 'react'
import { reportsService } from '../services/api'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Loading } from '../components/ui/Loading'
import { useToast } from '../hooks/useToast'
import { useSelection } from '../hooks/useSelection'
import { FilterPanel } from '../components/reports/FilterPanel'
import { StatsPanel } from '../components/reports/StatsPanel'
import { ReportsListView } from '../components/reports/ReportsListView'
import { ReportContextMenu } from '../components/reports/ReportContextMenu'
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
  ArrowRight,
  Download,
  CheckSquare,
  Square,
  X,
  FileDown,
  Grid3x3,
  List,
  BarChart3,
  ArrowUpDown
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'

export function ReportsPage() {
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL') // ALL, SUCCESS, FAILED
  const [sortBy, setSortBy] = useState(() => {
    // Cargar desde localStorage o usar default
    const saved = localStorage.getItem('reports_sort_by')
    return saved || 'date_desc'
  })
  const [expandedVendors, setExpandedVendors] = useState({})
  const [showFilterPanel, setShowFilterPanel] = useState(false)
  const [selectedVendors, setSelectedVendors] = useState([])
  const [dateRange, setDateRange] = useState({ start: null, end: null })
  const [showStats, setShowStats] = useState(false)
  const [openStatsMenu, setOpenStatsMenu] = useState(false)
  const [openSortMenu, setOpenSortMenu] = useState(false)
  const [stats, setStats] = useState(null)
  const [loadingStats, setLoadingStats] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [openExportMenu, setOpenExportMenu] = useState(false)
  const [viewMode, setViewMode] = useState(() => {
    const saved = localStorage.getItem('reports_view_mode')
    return saved || 'grid'
  })
  const [contextMenu, setContextMenu] = useState({ isOpen: false, position: null, report: null })
  const [isDeleting, setIsDeleting] = useState(null)
  const [isDownloading, setIsDownloading] = useState(null)
  const [openDownloadMenu, setOpenDownloadMenu] = useState(null) // ID del reporte con menú abierto
  const [isDeletingAll, setIsDeletingAll] = useState(false)
  const [isDeletingVendor, setIsDeletingVendor] = useState(null) // Vendor que se está eliminando
  const [isDeletingSelected, setIsDeletingSelected] = useState(false)
  const navigate = useNavigate()
  const { showToast } = useToast()
  
  // Sistema de selección múltiple
  const {
    selectedIds,
    selectedCount,
    selectionMode,
    toggleSelection,
    selectAll,
    deselectAll,
    toggleSelectionMode,
    isSelected,
    getSelectedItems,
  } = useSelection(reports, 'id')

  useEffect(() => {
    fetchReports()
    // fetchStats se llama dentro de fetchReports, no duplicar aquí
  }, [])

  // Mantener estadísticas sincronizadas con reportes
  useEffect(() => {
    // Solo actualizar si hay cambios significativos
    if (reports.length > 0) {
      // Si no hay estadísticas o están desactualizadas, calcular localmente
      if (!stats || stats.total_reports !== reports.length) {
        const localStats = calculateLocalStats(reports)
        if (localStats) {
          setStats(localStats)
        }
      }
    } else if (reports.length === 0) {
      // Si no hay reportes, limpiar estadísticas solo si existen
      if (stats) {
        setStats(null)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reports.length]) // Solo depender de la longitud para evitar loops infinitos

  const calculateLocalStats = (reportsData) => {
    if (!reportsData || reportsData.length === 0) {
      return null
    }

    const basicStats = {
      total_reports: reportsData.length,
      verdict_distribution: {},
      top_vendors: [],
      last_capture: reportsData.length > 0 ? reportsData[0].timestamp : null,
      success_rate: 0
    }
    
    // Calcular distribución básica
    reportsData.forEach(r => {
      const verdict = r.verdict || 'UNKNOWN'
      basicStats.verdict_distribution[verdict] = (basicStats.verdict_distribution[verdict] || 0) + 1
    })
    
    // Calcular top vendors
    const vendorCounts = {}
    reportsData.forEach(r => {
      const vendor = r.vendor || 'Unknown'
      vendorCounts[vendor] = (vendorCounts[vendor] || 0) + 1
    })
    basicStats.top_vendors = Object.entries(vendorCounts)
      .map(([vendor, count]) => ({ vendor, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 3)
    
    // Calcular tasa de éxito
    const successCount = reportsData.filter(r => 
      ['SUCCESS', 'EXCELLENT', 'GOOD'].includes((r.verdict || '').toUpperCase())
    ).length
    basicStats.success_rate = reportsData.length > 0 ? Math.round((successCount / reportsData.length * 100) * 100) / 100 : 0
    
    return basicStats
  }

  const fetchStats = async (forceLocal = false) => {
    // Si se fuerza cálculo local o hay reportes, calcular estadísticas locales primero
    if (forceLocal || reports.length > 0) {
      const localStats = calculateLocalStats(reports)
      if (localStats) {
        setStats(localStats)
      }
    }

    setLoadingStats(true)
    try {
      const data = await reportsService.getReportsStats()
      // Solo actualizar si las estadísticas del servidor son válidas
      if (data && data.total_reports > 0) {
        setStats(data)
      } else if (reports.length > 0) {
        // Si el servidor no tiene datos pero hay reportes locales, mantener las locales
        const localStats = calculateLocalStats(reports)
        if (localStats) {
          setStats(localStats)
        }
      }
    } catch (err) {
      console.error('Error al cargar estadísticas:', err)
      // Si falla, usar estadísticas locales si hay reportes
      if (reports.length > 0) {
        const localStats = calculateLocalStats(reports)
        if (localStats) {
          setStats(localStats)
        }
      }
    } finally {
      setLoadingStats(false)
    }
  }

  // Cerrar menú de descarga al hacer clic fuera
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (openDownloadMenu && !event.target.closest('.download-menu-container')) {
        setOpenDownloadMenu(null)
      }
      if (openExportMenu && !event.target.closest('.export-menu-container')) {
        setOpenExportMenu(false)
      }
      if (openStatsMenu && !event.target.closest('.stats-menu-container')) {
        setOpenStatsMenu(false)
      }
      if (openSortMenu && !event.target.closest('.sort-menu-container')) {
        setOpenSortMenu(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [openDownloadMenu, openExportMenu, openStatsMenu, openSortMenu])

  // Atajos de teclado globales
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Ctrl+F o Cmd+F: Focus en búsqueda
      if ((e.ctrlKey || e.metaKey) && e.key === 'f' && !e.shiftKey) {
        e.preventDefault()
        const searchInput = document.querySelector('input[type="text"][placeholder*="Buscar"]')
        if (searchInput) {
          searchInput.focus()
          searchInput.select()
        }
      }
      // Solo procesar otros atajos si estamos en modo selección
      else if (selectionMode) {
        // Ctrl+A o Cmd+A: Seleccionar todos
        if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
          e.preventDefault()
          selectAll()
        }
        // Delete: Eliminar seleccionados
        else if (e.key === 'Delete' && selectedCount > 0) {
          e.preventDefault()
          handleDeleteSelected()
        }
        // Esc: Salir del modo selección
        else if (e.key === 'Escape') {
          e.preventDefault()
          toggleSelectionMode()
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [selectionMode, selectedCount, selectAll, toggleSelectionMode])

  const fetchReports = async () => {
    setLoading(true)
    try {
      const data = await reportsService.getReports()
      
      // Asegurar que data sea un array
      const reportsArray = Array.isArray(data) ? data : []
      setReports(reportsArray)
      setError(null)
      
      // Auto-expandir la primera marca por defecto
      if (reportsArray.length > 0) {
        const firstVendor = reportsArray[0].vendor || 'Desconocido'
        setExpandedVendors({ [firstVendor]: true })
      }
      
      // Actualizar estadísticas después de cargar reportes
      // Usar cálculo local primero para mostrar inmediatamente
      if (reportsArray.length > 0) {
        const localStats = calculateLocalStats(reportsArray)
        if (localStats) {
          setStats(localStats)
        }
      }
      // Luego intentar cargar del servidor
      await fetchStats()
    } catch (err) {
      setError('No se pudieron cargar los reportes históricos.')
      setReports([]) // Asegurar que siempre sea un array
      setStats(null)
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
      await fetchStats() // Actualizar estadísticas
      showToast({ type: 'success', message: 'Reporte eliminado correctamente' })
    } catch (err) {
      showToast({ type: 'error', message: 'Error al intentar eliminar el reporte' })
    } finally {
      setIsDeleting(null)
    }
  }

  const handleDeleteAll = async () => {
    // Confirmación doble
    const firstConfirm = window.confirm('⚠️ ADVERTENCIA: Esta acción eliminará TODOS los reportes del sistema.\n\n¿Estás completamente seguro?')
    if (!firstConfirm) return
    
    const secondConfirm = window.confirm('⚠️ ÚLTIMA CONFIRMACIÓN\n\nEsta acción NO se puede deshacer. Todos los reportes serán eliminados permanentemente.\n\n¿Continuar?')
    if (!secondConfirm) return
    
    setIsDeletingAll(true)
    try {
      const result = await reportsService.deleteAllReports()
      setReports([])
      await fetchStats() // Actualizar estadísticas
      showToast({ 
        type: 'success', 
        message: `Se eliminaron ${result.deleted || 0} reportes correctamente` 
      })
    } catch (err) {
      showToast({ 
        type: 'error', 
        message: err?.message || 'Error al intentar eliminar todos los reportes' 
      })
    } finally {
      setIsDeletingAll(false)
    }
  }

  const handleDeleteVendor = async (e, vendor) => {
    e.stopPropagation()
    const vendorReports = groupedReports[vendor] || []
    const count = vendorReports.length
    
    if (!window.confirm(`¿Estás seguro de que deseas eliminar todos los reportes de ${vendor}?\n\nSe eliminarán ${count} reporte${count !== 1 ? 's' : ''}. Esta acción no se puede deshacer.`)) return
    
    setIsDeletingVendor(vendor)
    try {
      const result = await reportsService.deleteReportsByVendor(vendor)
      // Actualizar lista local eliminando los reportes de esa marca
      setReports(prev => prev.filter(r => r.vendor !== vendor))
      await fetchStats() // Actualizar estadísticas
      showToast({ 
        type: 'success', 
        message: `Se eliminaron ${result.deleted || 0} reportes de ${vendor}` 
      })
      // Cerrar el vendor si estaba expandido
      setExpandedVendors(prev => {
        const newState = { ...prev }
        delete newState[vendor]
        return newState
      })
    } catch (err) {
      showToast({ 
        type: 'error', 
        message: err?.message || `Error al intentar eliminar los reportes de ${vendor}` 
      })
    } finally {
      setIsDeletingVendor(null)
    }
  }

  const handleDeleteSelected = async () => {
    if (selectedIds.length === 0) return
    
    if (!window.confirm(`¿Estás seguro de que deseas eliminar ${selectedIds.length} reporte${selectedIds.length !== 1 ? 's' : ''} seleccionado${selectedIds.length !== 1 ? 's' : ''}?\n\nEsta acción no se puede deshacer.`)) return
    
    setIsDeletingSelected(true)
    try {
      const result = await reportsService.deleteMultipleReports(selectedIds)
      // Actualizar lista local
      setReports(prev => prev.filter(r => !selectedIds.includes(r.id)))
      await fetchStats() // Actualizar estadísticas
      showToast({ 
        type: 'success', 
        message: `Se eliminaron ${result.deleted || 0} reportes correctamente` 
      })
      deselectAll()
    } catch (err) {
      showToast({ 
        type: 'error', 
        message: err?.message || 'Error al intentar eliminar los reportes seleccionados' 
      })
    } finally {
      setIsDeletingSelected(false)
    }
  }

  const handleExport = async (format = 'json') => {
    setIsExporting(true)
    try {
      const idsToExport = selectionMode && selectedIds.length > 0 ? selectedIds : null
      const blob = await reportsService.exportReports(idsToExport, format)
      
      // Crear URL temporal para descarga
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-')
      link.download = `reports_export_${timestamp}.${format}`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      
      const message = idsToExport 
        ? `Se exportaron ${idsToExport.length} reportes en formato ${format.toUpperCase()}`
        : `Se exportaron todos los reportes en formato ${format.toUpperCase()}`
      
      showToast({ 
        type: 'success', 
        message 
      })
    } catch (err) {
      showToast({ 
        type: 'error', 
        message: err?.message || 'Error al exportar los reportes' 
      })
    } finally {
      setIsExporting(false)
    }
  }

  const handleDownloadCapture = async (e, reportId, filename) => {
    e.stopPropagation()
    setOpenDownloadMenu(null)
    setIsDownloading(reportId)
    try {
      const blob = await reportsService.downloadCapture(reportId)
      // Crear URL temporal para descarga
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      // Usar el nombre del archivo del reporte o un nombre por defecto
      const downloadName = filename || `capture_${reportId}.pcap`
      link.download = downloadName
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (err) {
      const errorMessage = err?.response?.data?.detail || err?.message || 'Error al descargar la captura'
      if (errorMessage.includes('antes de implementar')) {
        alert('Este reporte es antiguo y no tiene el archivo guardado. Solo los análisis nuevos permiten descargar la captura original.')
      } else {
        alert(`Error al descargar la captura: ${errorMessage}`)
      }
    } finally {
      setIsDownloading(null)
    }
  }

  const handleDownloadPDF = async (e, reportId, filename) => {
    e.stopPropagation()
    setOpenDownloadMenu(null)
    setIsDownloading(reportId)
    try {
      const blob = await reportsService.downloadPDF(reportId)
      // Crear URL temporal para descarga
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      // Usar el nombre del archivo del reporte o un nombre por defecto
      const baseName = filename?.replace(/\.(pcap|pcapng)$/i, '') || `report_${reportId}`
      link.download = `${baseName}.html`
      // Abrir en nueva ventana para que el usuario pueda usar "Guardar como PDF" del navegador
      link.target = '_blank'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (err) {
      const errorMessage = err?.response?.data?.detail || err?.message || 'Error al descargar el PDF'
      alert(`Error al descargar el PDF: ${errorMessage}`)
    } finally {
      setIsDownloading(null)
    }
  }

  const handleDownloadBoth = async (e, reportId, filename) => {
    e.stopPropagation()
    setOpenDownloadMenu(null)
    setIsDownloading(reportId)
    try {
      // Descargar ambos archivos secuencialmente
      await handleDownloadCapture(e, reportId, filename)
      // Pequeño delay para que el navegador procese la primera descarga
      await new Promise(resolve => setTimeout(resolve, 500))
      await handleDownloadPDF(e, reportId, filename)
    } catch (err) {
      const errorMessage = err?.response?.data?.detail || err?.message || 'Error al descargar los archivos'
      alert(`Error al descargar los archivos: ${errorMessage}`)
    } finally {
      setIsDownloading(null)
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
        band_steering: {
            analysis_id: fullDetail.analysis_id,
            verdict: fullDetail.verdict,
            device: fullDetail.devices?.[0] || {},
            fragments_count: fullDetail.fragments?.length || 0,
            compliance_checks: fullDetail.compliance_checks || [],
            btm_events: fullDetail.btm_events || [],
            transitions: fullDetail.transitions || [],
            signal_samples: fullDetail.signal_samples || []
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

      // Extraer SSID y client_mac: SIEMPRE usar user_metadata si existe, NUNCA usar bssid_info
      // El bssid_info puede contener números extraídos del pcap, no los valores del usuario
      let extractedSsid = ''
      let extractedClientMac = ''
      
      // 1. SIEMPRE priorizar user_metadata (valores ingresados por el usuario)
      if (fullDetail.raw_stats?.diagnostics?.user_metadata) {
        extractedSsid = fullDetail.raw_stats.diagnostics.user_metadata.ssid || ''
        extractedClientMac = fullDetail.raw_stats.diagnostics.user_metadata.client_mac || ''
      }
      
      // 2. Si no hay user_metadata, usar valores vacíos (NO usar bssid_info)
      // Esto asegura que nunca se muestren valores incorrectos extraídos del pcap
      
      // Asegurar que user_metadata existe en formattedResult
      if (formattedResult.stats?.diagnostics) {
        if (!formattedResult.stats.diagnostics.user_metadata) {
          formattedResult.stats.diagnostics.user_metadata = {}
        }
        // Guardar los valores del usuario (o vacío si no existen)
        formattedResult.stats.diagnostics.user_metadata.ssid = extractedSsid
        if (extractedClientMac) {
          formattedResult.stats.diagnostics.user_metadata.client_mac = extractedClientMac
        }
      }

      localStorage.setItem('networkAnalysisResult', JSON.stringify(formattedResult))
      localStorage.setItem('networkAnalysisFileMeta', JSON.stringify({
        name: fullDetail.filename,
        size: fullDetail.total_packets * 100,
        ssid: extractedSsid,
        client_mac: extractedClientMac
      }))
      navigate('/network-analysis')
    })
  }

  // Guardar ordenamiento en localStorage
  useEffect(() => {
    localStorage.setItem('reports_sort_by', sortBy)
  }, [sortBy])

  // Guardar modo de vista en localStorage
  useEffect(() => {
    localStorage.setItem('reports_view_mode', viewMode)
  }, [viewMode])

  // Mejorar búsqueda para incluir MAC y SSID
  const enhancedSearch = (report, searchTerm) => {
    if (!searchTerm) return true
    
    const term = searchTerm.toLowerCase()
    
    // Búsqueda en campos básicos
    const basicMatch = (
      report.filename?.toLowerCase().includes(term) ||
      report.vendor?.toLowerCase().includes(term) ||
      report.model?.toLowerCase().includes(term)
    )
    
    // Búsqueda por MAC (formato común: XX:XX:XX:XX:XX:XX o XXXXXXXXXXXX)
    const macPattern = /^([0-9a-f]{2}[:-]?){5}([0-9a-f]{2})$/i
    const isMacSearch = macPattern.test(term.replace(/[:\-]/g, ''))
    
    // Si parece una búsqueda MAC, buscar en el detalle del reporte
    // Por ahora solo buscamos en campos básicos, pero esto se puede expandir
    
    return basicMatch
  }

  // Función de ordenamiento
  const sortReports = (reportsToSort) => {
    const [field, order] = sortBy.split('_')
    const sorted = [...reportsToSort]
    
    sorted.sort((a, b) => {
      let comparison = 0
      
      switch (field) {
        case 'date':
          const dateA = new Date(a.timestamp || 0).getTime()
          const dateB = new Date(b.timestamp || 0).getTime()
          comparison = dateA - dateB
          break
        case 'name':
          const nameA = (a.filename || '').toLowerCase()
          const nameB = (b.filename || '').toLowerCase()
          comparison = nameA.localeCompare(nameB)
          break
        case 'vendor':
          const vendorA = (a.vendor || '').toLowerCase()
          const vendorB = (b.vendor || '').toLowerCase()
          comparison = vendorA.localeCompare(vendorB)
          break
        case 'verdict':
          const verdictA = (a.verdict || '').toUpperCase()
          const verdictB = (b.verdict || '').toUpperCase()
          comparison = verdictA.localeCompare(verdictB)
          break
        default:
          return 0
      }
      
      return order === 'desc' ? -comparison : comparison
    })
    
    return sorted
  }

  // Lógica de filtrado, ordenamiento y agrupamiento
  const groupedReports = useMemo(() => {
    // Asegurar que reports sea un array antes de usar filter
    if (!Array.isArray(reports)) {
      return {}
    }
    
    const filtered = reports.filter(report => {
      const matchSearch = enhancedSearch(report, searchTerm)
      
      const matchStatus = (
        statusFilter === 'ALL' ||
        (statusFilter === 'SUCCESS' && ['SUCCESS', 'EXCELLENT', 'GOOD'].includes(report.verdict?.toUpperCase())) ||
        (statusFilter === 'FAILED' && report.verdict?.toUpperCase() === 'FAILED')
      )

      const matchVendor = selectedVendors.length === 0 || selectedVendors.includes(report.vendor)

      const matchDateRange = (() => {
        if (!dateRange.start && !dateRange.end) return true
        const reportDate = new Date(report.timestamp || 0)
        const startDate = dateRange.start ? new Date(dateRange.start) : null
        const endDate = dateRange.end ? new Date(dateRange.end + 'T23:59:59') : null
        
        if (startDate && reportDate < startDate) return false
        if (endDate && reportDate > endDate) return false
        return true
      })()
      
      return matchSearch && matchStatus && matchVendor && matchDateRange
    })

    // Ordenar reportes
    const sorted = sortReports(filtered)

    // Agrupar por Vendor
      return sorted.reduce((groups, report) => {
      const vendor = report.vendor || 'Desconocido'
      if (!groups[vendor]) groups[vendor] = []
      groups[vendor].push(report)
      return groups
    }, {})
  }, [reports, searchTerm, statusFilter, sortBy, selectedVendors, dateRange])

  // Obtener lista única de vendors para el filtro
  const availableVendors = useMemo(() => {
    const vendors = new Set()
    reports.forEach(report => {
      if (report.vendor) vendors.add(report.vendor)
    })
    return Array.from(vendors).sort()
  }, [reports])

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
    
    // Formato 12 horas con AM/PM
    let h = date.getHours()
    const ampm = h >= 12 ? 'PM' : 'AM'
    h = h % 12
    h = h ? h : 12 // 0 debería ser 12
    const hours = String(h).padStart(2, '0')
    const min = String(date.getMinutes()).padStart(2, '0')
    const s = String(date.getSeconds()).padStart(2, '0')
    
    return `${d}/${m}/${y} ${hours}:${min}:${s} ${ampm}`
  }

  return (
    <div className="w-full min-w-0">
      {/* Header Interactivo - Horizontal Compacto con mismo ancho que navbar */}
      <div className="container-app w-full min-w-0 py-6">
        <div className="flex flex-col gap-4">
          {/* Título */}
          <div className="flex items-center gap-3">
            <History className="w-6 h-6 text-dark-accent-primary flex-shrink-0" />
            <h1 className="text-2xl font-bold text-dark-text-primary">
              Historial de Reportes
            </h1>
          </div>

          {/* Barra Horizontal con todas las funcionalidades */}
          <div className="flex flex-wrap items-center gap-3">
          {/* Búsqueda con espaciado */}
          <div className="relative w-72 flex-shrink-0 mr-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-text-muted" />
            <input
              type="text"
              placeholder="Buscar..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-dark-bg-secondary border border-dark-border-primary/30 rounded-xl py-2 pl-9 pr-3 text-sm text-dark-text-primary focus:outline-none focus:ring-2 focus:ring-dark-accent-primary/50 transition-all placeholder:text-dark-text-muted/60"
            />
          </div>


          {/* Toggle Modo Selección */}
          {reports.length > 0 && (
            <Button
              variant={selectionMode ? 'primary' : 'secondary'}
              size="sm"
              onClick={toggleSelectionMode}
              className="whitespace-nowrap"
            >
              {selectionMode ? (
                <>
                  <X className="w-4 h-4 mr-1.5" />
                  Salir
                </>
              ) : (
                <>
                  <CheckSquare className="w-4 h-4 mr-1.5" />
                  Seleccionar
                </>
              )}
            </Button>
          )}

          {/* Botón Eliminar Todo */}
          {!selectionMode && reports.length > 0 && (
            <Button
              variant="danger"
              size="sm"
              onClick={handleDeleteAll}
              disabled={isDeletingAll || loading}
              className="whitespace-nowrap"
            >
              {isDeletingAll ? (
                <>
                  <Loading size="xs" className="mr-1.5" />
                  Eliminando...
                </>
              ) : (
                <>
                  <Trash2 className="w-4 h-4 mr-1.5" />
                  Eliminar Todo
                </>
              )}
            </Button>
          )}

          {/* Botón Ordenar (Menú Desplegable) */}
          {reports.length > 0 && (
            <div className="relative sort-menu-container">
              <Button
                variant={openSortMenu ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => setOpenSortMenu(!openSortMenu)}
                className="whitespace-nowrap"
              >
                <ArrowUpDown className="w-4 h-4 mr-1.5" />
                Ordenar
              </Button>
              {openSortMenu && (
                <div className="absolute right-0 top-full mt-1.5 bg-dark-surface-primary border border-dark-border-primary/40 rounded-lg shadow-gemini z-[100] min-w-[180px] overflow-hidden">
                  <button
                    onClick={() => {
                      setSortBy('date_desc')
                      setOpenSortMenu(false)
                    }}
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 ${
                      sortBy === 'date_desc' ? 'bg-dark-bg-secondary' : ''
                    }`}
                  >
                    <span>Fecha (Reciente)</span>
                    {sortBy === 'date_desc' && <CheckCircle2 className="w-4 h-4 text-dark-accent-primary ml-auto" />}
                  </button>
                  <button
                    onClick={() => {
                      setSortBy('date_asc')
                      setOpenSortMenu(false)
                    }}
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 border-t border-dark-border-primary/20 ${
                      sortBy === 'date_asc' ? 'bg-dark-bg-secondary' : ''
                    }`}
                  >
                    <span>Fecha (Antiguo)</span>
                    {sortBy === 'date_asc' && <CheckCircle2 className="w-4 h-4 text-dark-accent-primary ml-auto" />}
                  </button>
                  <button
                    onClick={() => {
                      setSortBy('name_asc')
                      setOpenSortMenu(false)
                    }}
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 border-t border-dark-border-primary/20 ${
                      sortBy === 'name_asc' ? 'bg-dark-bg-secondary' : ''
                    }`}
                  >
                    <span>Nombre (A-Z)</span>
                    {sortBy === 'name_asc' && <CheckCircle2 className="w-4 h-4 text-dark-accent-primary ml-auto" />}
                  </button>
                  <button
                    onClick={() => {
                      setSortBy('name_desc')
                      setOpenSortMenu(false)
                    }}
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 border-t border-dark-border-primary/20 ${
                      sortBy === 'name_desc' ? 'bg-dark-bg-secondary' : ''
                    }`}
                  >
                    <span>Nombre (Z-A)</span>
                    {sortBy === 'name_desc' && <CheckCircle2 className="w-4 h-4 text-dark-accent-primary ml-auto" />}
                  </button>
                  <button
                    onClick={() => {
                      setSortBy('vendor_asc')
                      setOpenSortMenu(false)
                    }}
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 border-t border-dark-border-primary/20 ${
                      sortBy === 'vendor_asc' ? 'bg-dark-bg-secondary' : ''
                    }`}
                  >
                    <span>Marca (A-Z)</span>
                    {sortBy === 'vendor_asc' && <CheckCircle2 className="w-4 h-4 text-dark-accent-primary ml-auto" />}
                  </button>
                  <button
                    onClick={() => {
                      setSortBy('vendor_desc')
                      setOpenSortMenu(false)
                    }}
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 border-t border-dark-border-primary/20 ${
                      sortBy === 'vendor_desc' ? 'bg-dark-bg-secondary' : ''
                    }`}
                  >
                    <span>Marca (Z-A)</span>
                    {sortBy === 'vendor_desc' && <CheckCircle2 className="w-4 h-4 text-dark-accent-primary ml-auto" />}
                  </button>
                  <button
                    onClick={() => {
                      setSortBy('verdict_asc')
                      setOpenSortMenu(false)
                    }}
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 border-t border-dark-border-primary/20 ${
                      sortBy === 'verdict_asc' ? 'bg-dark-bg-secondary' : ''
                    }`}
                  >
                    <span>Veredicto (A-Z)</span>
                    {sortBy === 'verdict_asc' && <CheckCircle2 className="w-4 h-4 text-dark-accent-primary ml-auto" />}
                  </button>
                  <button
                    onClick={() => {
                      setSortBy('verdict_desc')
                      setOpenSortMenu(false)
                    }}
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 border-t border-dark-border-primary/20 ${
                      sortBy === 'verdict_desc' ? 'bg-dark-bg-secondary' : ''
                    }`}
                  >
                    <span>Veredicto (Z-A)</span>
                    {sortBy === 'verdict_desc' && <CheckCircle2 className="w-4 h-4 text-dark-accent-primary ml-auto" />}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Botón Estadísticas (Menú Desplegable) */}
          {reports.length > 0 && (
            <div className="relative stats-menu-container">
              <Button
                variant={openStatsMenu ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => setOpenStatsMenu(!openStatsMenu)}
                className="whitespace-nowrap"
              >
                <BarChart3 className="w-4 h-4 mr-1.5" />
                Estadísticas
              </Button>
              {openStatsMenu && (
                <div className="absolute right-0 top-full mt-1.5 bg-dark-surface-primary border border-dark-border-primary/40 rounded-lg shadow-gemini z-[100] min-w-[450px] sm:min-w-[500px] md:min-w-[600px] max-w-[700px] overflow-hidden">
                  <StatsPanel stats={stats} loading={loadingStats} compact={true} />
                </div>
              )}
            </div>
          )}

          {/* Botón Filtros Avanzados */}
          <Button
            variant={showFilterPanel || selectedVendors.length > 0 || dateRange.start || dateRange.end || statusFilter !== 'ALL' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setShowFilterPanel(!showFilterPanel)}
            className="whitespace-nowrap"
          >
            <Filter className="w-4 h-4 mr-1.5" />
            Filtros
            {(selectedVendors.length > 0 || dateRange.start || dateRange.end || statusFilter !== 'ALL') && (
              <span className="ml-1.5 bg-white/20 px-1.5 py-0.5 rounded text-xs">
                {selectedVendors.length + (dateRange.start ? 1 : 0) + (dateRange.end ? 1 : 0) + (statusFilter !== 'ALL' ? 1 : 0)}
              </span>
            )}
          </Button>

          {/* Toggle Vista Grid/Lista */}
          {reports.length > 0 && (
            <div className="flex bg-dark-bg-secondary/50 rounded-xl p-1 border border-dark-border-primary/20">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-2 rounded-lg transition-all ${
                  viewMode === 'grid'
                    ? 'bg-dark-accent-primary text-white'
                    : 'text-dark-text-muted hover:text-dark-text-primary'
                }`}
                title="Vista Grid"
              >
                <Grid3x3 className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-2 rounded-lg transition-all ${
                  viewMode === 'list'
                    ? 'bg-dark-accent-primary text-white'
                    : 'text-dark-text-muted hover:text-dark-text-primary'
                }`}
                title="Vista Lista"
              >
                <List className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Botón Exportar */}
          {!selectionMode && reports.length > 0 && (
            <div className="relative export-menu-container">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setOpenExportMenu(!openExportMenu)}
                disabled={isExporting}
                className="whitespace-nowrap"
              >
                {isExporting ? (
                  <>
                    <Loading size="xs" className="mr-1.5" />
                    Exportando...
                  </>
                ) : (
                  <>
                    <FileDown className="w-4 h-4 mr-1.5" />
                    Exportar
                  </>
                )}
              </Button>
              {openExportMenu && (
                <div className="absolute right-0 top-full mt-1.5 bg-dark-surface-primary border border-dark-border-primary/40 rounded-lg shadow-gemini z-50 min-w-[160px] overflow-hidden">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleExport('json')
                      setOpenExportMenu(false)
                    }}
                    className="w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2"
                  >
                    <FileDown className="w-4 h-4 text-blue-400" />
                    <span>Exportar JSON</span>
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleExport('csv')
                      setOpenExportMenu(false)
                    }}
                    className="w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 border-t border-dark-border-primary/20"
                  >
                    <FileDown className="w-4 h-4 text-green-400" />
                    <span>Exportar CSV</span>
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Contenido Principal con mismo ancho que navbar */}
      <div className=" w-full min-w-0 space-y-6 mt-12">
        {/* Panel de Filtros Avanzados */}
        {showFilterPanel && (
          <div>
            <FilterPanel
              isOpen={showFilterPanel}
              onClose={() => setShowFilterPanel(false)}
              vendors={availableVendors}
              selectedVendors={selectedVendors}
              onVendorsChange={setSelectedVendors}
              dateRange={dateRange}
              onDateRangeChange={setDateRange}
              statusFilter={statusFilter}
              onStatusFilterChange={setStatusFilter}
              onClearFilters={() => {
                setSelectedVendors([])
                setDateRange({ start: null, end: null })
                setStatusFilter('ALL')
              }}
            />
          </div>
        )}

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
          <div className="space-y-6 w-full max-w-full">
            {/* Barra de acciones flotante cuando hay seleccionados */}
            {selectionMode && selectedCount > 0 && (
              <Card className="sticky top-4 z-40 p-4 bg-dark-surface-primary border-dark-accent-primary/30 shadow-gemini">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2 text-dark-text-primary">
                      <CheckSquare className="w-5 h-5 text-dark-accent-primary" />
                      <span className="font-semibold">
                        {selectedCount} {selectedCount === 1 ? 'reporte seleccionado' : 'reportes seleccionados'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={selectAll}
                        className="text-xs text-dark-text-muted hover:text-dark-text-primary transition-colors"
                      >
                        Seleccionar todos
                      </button>
                      <span className="text-dark-text-muted">•</span>
                      <button
                        onClick={deselectAll}
                        className="text-xs text-dark-text-muted hover:text-dark-text-primary transition-colors"
                      >
                        Deseleccionar
                      </button>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {/* Menú de Exportación */}
                    <div className="relative export-menu-container">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => setOpenExportMenu(!openExportMenu)}
                        disabled={isExporting}
                      >
                        {isExporting ? (
                          <>
                            <Loading size="xs" className="mr-2" />
                            Exportando...
                          </>
                        ) : (
                          <>
                            <FileDown className="w-4 h-4 mr-2" />
                            Exportar ({selectedCount})
                          </>
                        )}
                      </Button>
                      {openExportMenu && (
                        <div className="absolute right-0 top-full mt-1.5 bg-dark-surface-primary border border-dark-border-primary/40 rounded-lg shadow-gemini z-50 min-w-[160px] overflow-hidden">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              handleExport('json')
                              setOpenExportMenu(false)
                            }}
                            className="w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2"
                          >
                            <FileDown className="w-4 h-4 text-blue-400" />
                            <span>Exportar JSON</span>
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              handleExport('csv')
                              setOpenExportMenu(false)
                            }}
                            className="w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 border-t border-dark-border-primary/20"
                          >
                            <FileDown className="w-4 h-4 text-green-400" />
                            <span>Exportar CSV</span>
                          </button>
                        </div>
                      )}
                    </div>
                    
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={handleDeleteSelected}
                      disabled={isDeletingSelected}
                    >
                      {isDeletingSelected ? (
                        <>
                          <Loading size="xs" className="mr-2" />
                          Eliminando...
                        </>
                      ) : (
                        <>
                          <Trash2 className="w-4 h-4 mr-2" />
                          Eliminar ({selectedCount})
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              </Card>
            )}
            
            {Object.entries(groupedReports).map(([vendor, vendorReports]) => {
              const isOpen = expandedVendors[vendor]
              
              return (
                <div key={vendor} className="space-y-3 w-full">
                  {/* Folder Header */}
                  <div 
                    className={`flex items-center justify-between p-4 rounded-xl transition-all border w-full ${
                      isOpen 
                        ? 'bg-dark-bg-secondary border-dark-accent-primary/30 shadow-lg' 
                        : 'bg-dark-bg-secondary/40 border-dark-border-primary/20 hover:border-dark-accent-primary/20'
                    }`}
                  >
                    <div 
                      onClick={() => toggleVendor(vendor)}
                      className="flex items-center gap-4 flex-1 cursor-pointer"
                    >
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
                    <div className="flex items-center gap-2">
                      {/* Botón Eliminar Marca */}
                      <button
                        onClick={(e) => handleDeleteVendor(e, vendor)}
                        disabled={isDeletingVendor === vendor}
                        className="p-2 rounded-lg text-dark-text-muted hover:bg-red-500/20 hover:text-red-400 transition-all disabled:opacity-50"
                        title={`Eliminar todos los reportes de ${vendor}`}
                      >
                        {isDeletingVendor === vendor ? (
                          <Loading size="xs" />
                        ) : (
                          <Trash2 className="w-4 h-4" />
                        )}
                      </button>
                      <button
                        onClick={() => toggleVendor(vendor)}
                        className="p-1 text-dark-text-muted hover:text-dark-text-primary transition-colors"
                      >
                        {isOpen ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
                      </button>
                    </div>
                  </div>

                  {/* Folder Content (Files) */}
                  {isOpen && (
                    <div className={`w-full min-w-0 ${openDownloadMenu ? 'overflow-visible' : 'overflow-hidden'}`}>
                      {viewMode === 'grid' ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-3 pl-0 md:pl-2 w-full min-w-0">
                          {vendorReports.map((report) => (
                            <Card 
                          key={report.id} 
                          className={`relative group p-5 hover:border-dark-accent-primary/40 bg-dark-surface-primary/50 hover:bg-dark-surface-primary border-dark-border-primary/20 transition-all duration-300 hover:shadow-gemini-sm ${isDeleting === report.id ? 'opacity-50 pointer-events-none' : ''} ${selectionMode ? 'cursor-default' : 'cursor-pointer'} ${openDownloadMenu === report.id ? 'overflow-visible' : ''}`}
                          onClick={() => {
                            if (selectionMode) {
                              toggleSelection(report.id)
                            } else {
                              handleViewReport(report)
                            }
                          }}
                          onContextMenu={(e) => {
                            e.preventDefault()
                            if (!selectionMode) {
                              setContextMenu({
                                isOpen: true,
                                position: { x: e.clientX, y: e.clientY },
                                report: report
                              })
                            }
                          }}
                        >
                          <div className="flex flex-col h-full space-y-4">
                            {/* Header: Checkbox (si modo selección) y Modelo */}
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex items-start gap-3 flex-1 min-w-0">
                                {selectionMode && (
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      toggleSelection(report.id)
                                    }}
                                    className="mt-0.5 flex-shrink-0"
                                  >
                                    {isSelected(report.id) ? (
                                      <CheckSquare className="w-5 h-5 text-dark-accent-primary" />
                                    ) : (
                                      <Square className="w-5 h-5 text-dark-text-muted hover:text-dark-text-primary transition-colors" />
                                    )}
                                  </button>
                                )}
                                <div className="flex-1 min-w-0">
                                  <h3 className="text-base font-semibold text-dark-text-primary truncate leading-tight group-hover:text-dark-accent-primary transition-colors">
                                    {report.model || 'Dispositivo Desconocido'}
                                  </h3>
                                  <div className="flex items-center gap-1.5 text-xs text-dark-text-muted mt-1.5">
                                    <FileText className="w-3 h-3 flex-shrink-0" />
                                    <span className="truncate" title={report.filename}>
                                      {report.filename?.includes('_') && report.filename.split('_')[0].length === 36 
                                        ? report.filename.split('_').slice(1).join('_') 
                                        : report.filename}
                                    </span>
                                  </div>
                                </div>
                              </div>
                              
                              <div className="flex items-center gap-1.5 flex-shrink-0">
                                {/* Menú de descarga desplegable */}
                                <div className="relative download-menu-container">
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      setOpenDownloadMenu(openDownloadMenu === report.id ? null : report.id)
                                    }}
                                    className="p-1.5 rounded-md text-dark-text-muted hover:bg-blue-500/15 hover:text-blue-400 transition-all opacity-0 group-hover:opacity-100"
                                    title="Opciones de descarga"
                                  >
                                    {isDownloading === report.id ? <Loading size="xs" /> : <Download className="w-3.5 h-3.5" />}
                                  </button>
                                  
                                  {/* Menú desplegable */}
                                  {openDownloadMenu === report.id && (
                                    <div className="absolute right-0 top-full mt-1.5 bg-dark-surface-primary border border-dark-border-primary/40 rounded-lg shadow-gemini z-[9999] min-w-[180px] overflow-hidden">
                                      <button
                                        onClick={(e) => handleDownloadCapture(e, report.id, report.filename)}
                                        className="w-full px-3.5 py-2 text-left text-xs text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2"
                                      >
                                        <Download className="w-3.5 h-3.5 text-blue-400" />
                                        <span>Descargar Captura</span>
                                      </button>
                                      <button
                                        onClick={(e) => handleDownloadPDF(e, report.id, report.filename)}
                                        className="w-full px-3.5 py-2 text-left text-xs text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 border-t border-dark-border-primary/20"
                                      >
                                        <FileText className="w-3.5 h-3.5 text-purple-400" />
                                        <span>Descargar PDF</span>
                                      </button>
                                      <button
                                        onClick={(e) => handleDownloadBoth(e, report.id, report.filename)}
                                        className="w-full px-3.5 py-2 text-left text-xs text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 border-t border-dark-border-primary/20"
                                      >
                                        <Download className="w-3.5 h-3.5 text-green-400" />
                                        <span>Descargar Ambos</span>
                                      </button>
                                    </div>
                                  )}
                                </div>
                                
                                <button
                                  onClick={(e) => handleDeleteReport(e, report.id)}
                                  className="p-1.5 rounded-md text-dark-text-muted hover:bg-red-500/15 hover:text-red-400 transition-all opacity-0 group-hover:opacity-100"
                                  title="Eliminar reporte"
                                >
                                  {isDeleting === report.id ? <Loading size="xs" /> : <Trash2 className="w-3.5 h-3.5" />}
                                </button>
                                
                                <div className={`flex-shrink-0 px-2 py-0.5 rounded text-[10px] font-semibold tracking-wide ${
                                  ['SUCCESS', 'EXCELLENT', 'GOOD'].includes(report.verdict?.toUpperCase())
                                    ? 'bg-green-500/15 text-green-400' 
                                    : 'bg-red-500/15 text-red-400'
                                }`}>
                                  {report.verdict === 'SUCCESS' ? 'ÉXITO' : report.verdict === 'FAILED' ? 'FALLÓ' : report.verdict}
                                </div>
                              </div>
                            </div>

                            {/* Divider sutil */}
                            <div className="h-[1px] bg-dark-border-primary/10"></div>

                            {/* Metadata y Acciones */}
                            <div className="flex items-center justify-between pt-1">
                              <div className="flex items-center gap-1.5 text-xs text-dark-text-muted">
                                <Calendar className="w-3 h-3 flex-shrink-0" />
                                <span className="font-mono">{formatDate(report.timestamp)}</span>
                              </div>
                              
                              <div className="flex items-center gap-1.5 text-dark-accent-primary text-xs font-medium transition-all bg-dark-accent-primary/8 px-2 py-1 rounded-md border border-dark-accent-primary/15 hover:bg-dark-accent-primary/12">
                                Ver Detalles
                                <ArrowRight className="w-3 h-3" />
                              </div>
                            </div>
                          </div>
                        </Card>
                      ))}
                        </div>
                      ) : (
                        <div className="pl-0 md:pl-2 w-full min-w-0">
                          <ReportsListView
                            reports={vendorReports}
                            onViewReport={handleViewReport}
                            onDeleteReport={handleDeleteReport}
                            onDownloadCapture={handleDownloadCapture}
                            onDownloadPDF={handleDownloadPDF}
                            onDownloadBoth={handleDownloadBoth}
                            isDeleting={isDeleting}
                            isDownloading={isDownloading}
                            openDownloadMenu={openDownloadMenu}
                            setOpenDownloadMenu={setOpenDownloadMenu}
                            formatDate={formatDate}
                            selectionMode={selectionMode}
                            isSelected={isSelected}
                            toggleSelection={toggleSelection}
                            CheckSquare={CheckSquare}
                            Square={Square}
                            onContextMenu={(e, report) => {
                              setContextMenu({
                                isOpen: true,
                                position: { x: e.clientX, y: e.clientY },
                                report: report
                              })
                            }}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
        </div>
        </div>
      </div>

      {/* Menú Contextual */}
      <ReportContextMenu
        isOpen={contextMenu.isOpen}
        position={contextMenu.position}
        onClose={() => setContextMenu({ isOpen: false, position: null, report: null })}
        onViewDetails={() => {
          if (contextMenu.report) {
            handleViewReport(contextMenu.report)
          }
        }}
        onDelete={(e) => {
          if (contextMenu.report) {
            handleDeleteReport(e, contextMenu.report.id)
          }
        }}
        onDownloadCapture={(e) => {
          if (contextMenu.report) {
            handleDownloadCapture(e, contextMenu.report.id, contextMenu.report.filename)
          }
        }}
        onDownloadPDF={(e) => {
          if (contextMenu.report) {
            handleDownloadPDF(e, contextMenu.report.id, contextMenu.report.filename)
          }
        }}
        report={contextMenu.report}
      />
    </div>
  )
}

export default ReportsPage
