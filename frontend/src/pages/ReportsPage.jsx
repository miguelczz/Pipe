import { useState, useEffect, useMemo, useCallback } from 'react'
import { reportsService } from '../services/api'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Loading } from '../components/ui/Loading'
import { useToast } from '../hooks/useToast'
import { useSelection } from '../hooks/useSelection'
import { useReportsFilters } from '../hooks/useReportsFilters'
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
  AlertCircle,
  Search,
  Filter,
  Folder,
  ChevronDown,
  Trash2,
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
  const {
    searchTerm,
    setSearchTerm,
    statusFilter,
    setStatusFilter,
    sortBy,
    setSortBy,
    viewMode,
    setViewMode,
    showFilterPanel,
    setShowFilterPanel,
    selectedVendors,
    setSelectedVendors,
    dateRange,
    setDateRange,
  } = useReportsFilters()
  const [expandedVendors, setExpandedVendors] = useState({})
  const [openStatsMenu, setOpenStatsMenu] = useState(false)
  const [openSortMenu, setOpenSortMenu] = useState(false)
  const [openSelectionMenu, setOpenSelectionMenu] = useState(false)
  const [stats, setStats] = useState(null)
  const [loadingStats, setLoadingStats] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [contextMenu, setContextMenu] = useState({ isOpen: false, position: null, report: null })
  const [isDeleting, setIsDeleting] = useState(null)
  const [isDownloading, setIsDownloading] = useState(null)
  const [openDownloadMenu, setOpenDownloadMenu] = useState(null) // ID del reporte con menú abierto
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
    deselectAll,
    toggleSelectionMode,
    isSelected,
  } = useSelection(reports, 'id')

  useEffect(() => {
    fetchReports()
    // fetchStats se llama dentro de fetchReports, no duplicar aquí
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // Mejorar búsqueda para incluir MAC y SSID (movido antes de groupedReports)
  const enhancedSearch = (report, searchTerm) => {
    if (!searchTerm) return true
    
    const term = searchTerm.toLowerCase()
    
    // Búsqueda en campos básicos (filename, vendor, model)
    const basicMatch = (
      report.filename?.toLowerCase().includes(term) ||
      report.vendor?.toLowerCase().includes(term) ||
      report.model?.toLowerCase().includes(term)
    )
    // Búsqueda por MAC si el término tiene formato MAC (XX:XX:XX:XX:XX:XX o similar)
    const macNormalized = term.replace(/[:-]/g, '')
    const looksLikeMac = /^[0-9a-f]{12}$/i.test(macNormalized)
    const macMatch = looksLikeMac && (
      (report.client_mac && report.client_mac.replace(/[:-]/g, '').toLowerCase().includes(macNormalized)) ||
      (report.raw_stats?.diagnostics?.client_mac && report.raw_stats.diagnostics.client_mac.replace(/[:-]/g, '').toLowerCase().includes(macNormalized))
    )
    return basicMatch || macMatch
  }

  // Función de ordenamiento (movida antes de groupedReports)
  const sortReports = (reportsToSort) => {
    const [field, order] = sortBy.split('_')
    const sorted = [...reportsToSort]
    
    sorted.sort((a, b) => {
      let comparison = 0
      
      switch (field) {
        case 'date': {
          const dateA = new Date(a.timestamp || 0).getTime()
          const dateB = new Date(b.timestamp || 0).getTime()
          comparison = dateA - dateB
          break
        }
        case 'name': {
          const nameA = (a.filename || '').toLowerCase()
          const nameB = (b.filename || '').toLowerCase()
          comparison = nameA.localeCompare(nameB)
          break
        }
        case 'vendor': {
          const vendorA = (a.vendor || '').toLowerCase()
          const vendorB = (b.vendor || '').toLowerCase()
          comparison = vendorA.localeCompare(vendorB)
          break
        }
        case 'verdict': {
          const verdictA = (a.verdict || '').toUpperCase()
          const verdictB = (b.verdict || '').toUpperCase()
          comparison = verdictA.localeCompare(verdictB)
          break
        }
        default:
          return 0
      }
      
      return order === 'desc' ? -comparison : comparison
    })
    
    return sorted
  }

  // Lógica de filtrado, ordenamiento y agrupamiento (movido antes de selectAllVisible)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reports, searchTerm, statusFilter, sortBy, selectedVendors, dateRange]) // sortReports es estable y no necesita estar en deps

  // Obtener todos los reportes visibles (filtrados) para selección
  const visibleReports = useMemo(() => {
    return Object.values(groupedReports).flat()
  }, [groupedReports])

  // Limpiar selección de reportes que ya no están visibles cuando cambian los filtros
  useEffect(() => {
    if (selectionMode) {
      const visibleIds = new Set(visibleReports.map(r => r.id).filter(Boolean))
      const currentSelected = selectedIds.filter(id => visibleIds.has(id))
      
      // Si hay IDs seleccionados que ya no están visibles, limpiarlos
      if (currentSelected.length !== selectedIds.length) {
        // Deseleccionar los que ya no están visibles
        selectedIds.forEach(id => {
          if (!visibleIds.has(id) && isSelected(id)) {
            toggleSelection(id)
          }
        })
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleReports, selectionMode]) // No incluir selectedIds, isSelected, toggleSelection para evitar loops

  // Función para seleccionar solo los reportes visibles (filtrados)
  const selectAllVisible = useCallback(() => {
    const visibleIds = visibleReports.map(r => r.id).filter(Boolean)
    visibleIds.forEach(id => {
      if (!isSelected(id)) {
        toggleSelection(id)
      }
    })
  }, [visibleReports, isSelected, toggleSelection])

  const handleDeleteSelected = useCallback(async () => {
    // Usar selectedCount del hook en lugar de selectedIds.length para asegurar consistencia
    const actualSelectedCount = selectedCount || selectedIds.length || 0
    if (actualSelectedCount === 0) return
    
    // Verificar que los IDs seleccionados realmente existan en los reportes visibles
    const visibleReportIds = visibleReports.map(r => r.id).filter(Boolean)
    const validSelectedIds = selectedIds.filter(id => visibleReportIds.includes(id))
    
    if (validSelectedIds.length === 0) {
      showToast({
        type: 'warning',
        message: 'No hay reportes seleccionados para eliminar'
      })
      return
    }
    
    // Usar el número real de IDs válidos seleccionados
    const countToDelete = validSelectedIds.length
    
    if (!window.confirm(`¿Estás seguro de que deseas eliminar ${countToDelete} reporte${countToDelete !== 1 ? 's' : ''} seleccionado${countToDelete !== 1 ? 's' : ''}?\n\nEsta acción no se puede deshacer.`)) return
    
    setIsDeletingSelected(true)
    try {
      // Usar solo los IDs válidos que están realmente seleccionados
      const result = await reportsService.deleteMultipleReports(validSelectedIds)
      
      // Actualizar lista local solo con los que se eliminaron exitosamente
      const successfullyDeleted = validSelectedIds.filter(id => 
        !result.not_found || !result.not_found.includes(id)
      )
      setReports(prev => prev.filter(r => !successfullyDeleted.includes(r.id)))
      await fetchStats() // Actualizar estadísticas
      
      // Mostrar mensaje apropiado
      if (result.not_found && result.not_found.length > 0) {
        showToast({ 
          type: 'warning', 
          message: result.message || `Se eliminaron ${result.deleted || 0} reportes, pero ${result.not_found.length} no se encontraron` 
        })
      } else {
        showToast({ 
          type: 'success', 
          message: result.message || `Se eliminaron ${result.deleted || 0} reportes correctamente` 
        })
      }
      deselectAll()
    } catch (err) {
      // Extraer mensaje de error del backend si está disponible
      const errorMessage = err?.response?.data?.detail || err?.response?.data?.message || err?.message || 'Error al intentar eliminar los reportes seleccionados'
      showToast({ 
        type: 'error', 
        message: errorMessage
      })
    } finally {
      setIsDeletingSelected(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIds, deselectAll, showToast]) // fetchStats se llama dentro pero no necesita estar en deps

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
      // Solo mostrar error en consola si no es un 404 (endpoint no disponible)
      // El 404 es esperado si el endpoint no está implementado o no está disponible
      if (err?.status !== 404) {
        console.warn('Error al cargar estadísticas de reportes:', err)
      }
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
      if (openStatsMenu && !event.target.closest('.stats-menu-container')) {
        setOpenStatsMenu(false)
      }
      if (openSortMenu && !event.target.closest('.sort-menu-container')) {
        setOpenSortMenu(false)
      }
      if (openSelectionMenu && !event.target.closest('.selection-menu-container')) {
        setOpenSelectionMenu(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [openDownloadMenu, openStatsMenu, openSortMenu, openSelectionMenu])

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
        // Ctrl+A o Cmd+A: Seleccionar todos los visibles
        if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
          e.preventDefault()
          selectAllVisible()
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
  }, [selectionMode, selectedCount, selectAllVisible, toggleSelectionMode, handleDeleteSelected])

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

  const handleExport = async (format = 'html', specificIds = null) => {
    setIsExporting(true)
    try {
      // Si se proporcionan IDs específicos, usar esos; sino, usar los seleccionados
      const idsToExport = specificIds || (selectionMode && selectedIds.length > 0 ? selectedIds : null)
      
      
      const blob = await reportsService.exportReports(idsToExport, format)
      
      if (!blob) {
        throw new Error('No se recibió ningún archivo del servidor')
      }
      
      // Verificar que el blob tenga contenido válido
      if (!blob || blob.size === 0) {
        throw new Error('El archivo exportado está vacío')
      }
     
      // Para HTML, usar el blob directamente
      let blobToDownload = blob
      
      // Método de descarga mejorado: usar File System Access API si está disponible, sino fallback
      const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-')
      const extension = 'html'
      const filename = `reports_summary_${timestamp}.${extension}`
      
      // Intentar usar File System Access API (más confiable)
      if ('showSaveFilePicker' in window) {
        try {
          const fileHandle = await window.showSaveFilePicker({
            suggestedName: filename,
            types: [{
              description: 'HTML Files',
              accept: {
                'text/html': ['.html']
              }
            }]
          })
          
          const writable = await fileHandle.createWritable()
          await writable.write(blobToDownload)
          await writable.close()
          
          
          const message = idsToExport 
            ? `Se exportaron ${idsToExport.length} reporte${idsToExport.length !== 1 ? 's' : ''} como resumen HTML`
            : `Se exportaron todos los reportes como resumen HTML`
          
          showToast({ 
            type: 'success', 
            message 
          })
          return
        } catch (fsError) {
          // Si el usuario cancela, no es un error
          if (fsError.name === 'AbortError') {
            return
          }
        }
      }
      
      // Método alternativo: descarga tradicional mejorada
      
      // Crear el link de descarga con todos los atributos necesarios
      const url = window.URL.createObjectURL(blobToDownload)
      const link = document.createElement('a')
      link.href = url
      link.style.display = 'none'
      link.download = filename
      link.setAttribute('download', filename) // Asegurar atributo download
      link.setAttribute('type', blobToDownload.type) // Agregar tipo MIME
      
      // Agregar al DOM de forma más visible (aunque hidden)
      link.style.position = 'fixed'
      link.style.top = '-9999px'
      link.style.left = '-9999px'
      document.body.appendChild(link)
      
      // Disparar la descarga de forma simple y directa (una sola vez)
      
      // Simplemente hacer click en el link una sola vez
      link.click()
      
      
      // Limpiar después de un breve delay para asegurar que la descarga se inicie
      setTimeout(() => {
        try {
          if (link.parentNode) {
            document.body.removeChild(link)
          }
          window.URL.revokeObjectURL(url)
        } catch (cleanupError) {
          // Ignorar errores de limpieza
        }
      }, 1000)
      
      const message = idsToExport 
        ? `Se exportaron ${idsToExport.length} reporte${idsToExport.length !== 1 ? 's' : ''} como resumen HTML`
        : `Se exportaron todos los reportes como resumen HTML`
      
      showToast({ 
        type: 'success', 
        message 
      })
    } catch (err) {
      let errorMessage = 'Error al exportar los reportes'
      
      // Intentar leer el mensaje de error del blob
      if (err?.data instanceof Blob) {
        try {
          const text = await err.data.text()
          const errorData = JSON.parse(text)
          errorMessage = errorData.detail || errorData.message || errorMessage
        } catch (parseError) {
          // Si no se puede parsear, usar el mensaje del error
          if (err?.message) {
            errorMessage = err.message
          }
        }
      } else if (err?.response?.data) {
        // Si es un blob de error, intentar leerlo
        if (err.response.data instanceof Blob) {
          try {
            const text = await err.response.data.text()
            const errorData = JSON.parse(text)
            errorMessage = errorData.detail || errorData.message || errorMessage
          } catch (parseError) {
            errorMessage = `Error ${err.response.status}: ${err.response.statusText || err.message || 'Error desconocido'}`
          }
        } else {
          errorMessage = err.response.data.detail || err.response.data.message || errorMessage
        }
      } else if (err?.message) {
        errorMessage = err.message
      } else if (err?.status) {
        errorMessage = `Error ${err.status}: ${errorMessage}`
      }
      
      showToast({ 
        type: 'error', 
        message: errorMessage
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
        showToast({
          type: 'warning',
          message: 'Este reporte es antiguo y no tiene el archivo guardado. Solo los análisis nuevos permiten descargar la captura original.'
        })
      } else {
        showToast({
          type: 'error',
          message: `Error al descargar la captura: ${errorMessage}`
        })
      }
    } finally {
      setIsDownloading(null)
    }
  }

  const handleDownloadPDF = async (e, reportId) => {
    e.stopPropagation()
    setOpenDownloadMenu(null)
    setIsDownloading(reportId)
    try {
      // Descargar el PDF persistido directamente desde el backend
      const blob = await reportsService.downloadPDF(reportId)
      
      // Obtener información del reporte para el nombre del archivo
      const report = reports.find(r => r.id === reportId)
      // Intentar usar el modelo del dispositivo si está disponible
      let pdfFilename = `Pipe ${reportId}.pdf`
      if (report) {
        if (report.model && report.model !== 'Unknown' && report.model !== 'Genérico') {
          pdfFilename = `Pipe ${report.model.toUpperCase()}.pdf`
        } else {
          const fileName = report.filename || `report_${reportId}`
          const cleanName = fileName.split('.')[0].replace(/_/g, ' ').trim()
          pdfFilename = `Pipe ${cleanName.toUpperCase()}.pdf`
        }
      }
      
      // Crear URL temporal para descarga
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = pdfFilename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      
      showToast({
        type: 'success',
        message: 'PDF descargado correctamente'
      })
    } catch (err) {
      const errorMessage = err?.response?.data?.detail || err?.message || 'Error al descargar el PDF'
      
      // Si el PDF no existe, informar al usuario que debe exportarlo primero
      if (err?.response?.status === 404 || errorMessage.includes('no encontrado')) {
        showToast({
          type: 'warning',
          message: 'PDF no encontrado. Por favor, exporta el PDF primero desde la página de análisis.'
        })
      } else {
        showToast({
          type: 'error',
          message: `Error al descargar el PDF: ${errorMessage}`
        })
      }
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
      await handleDownloadPDF(e, reportId)
    } catch (err) {
      const errorMessage = err?.response?.data?.detail || err?.message || 'Error al descargar los archivos'
      showToast({
        type: 'error',
        message: `Error al descargar los archivos: ${errorMessage}`
      })
    } finally {
      setIsDownloading(null)
    }
  }

  const handleViewReport = (report) => {
    reportsService.getReportDetail(report.id)
      .then(fullDetail => {
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
      .catch((err) => {
        const message = err?.response?.data?.detail || err?.response?.data?.message || err?.message || 'No se pudo cargar el detalle del reporte'
        showToast({ type: 'error', message })
      })
  }


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
    
    // Crear fecha - manejar diferentes formatos de timestamp
    let date
    if (typeof dateStr === 'string') {
      // Si el string no tiene información de zona horaria (no termina en Z, +XX:XX, o -XX:XX)
      // y tiene el formato ISO básico (YYYY-MM-DDTHH:MM:SS), tratarlo como UTC
      const isoPattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$/
      if (isoPattern.test(dateStr) && !dateStr.includes('Z') && !dateStr.match(/[+-]\d{2}:\d{2}$/)) {
        // Agregar 'Z' para indicar UTC
        date = new Date(dateStr + 'Z')
      } else {
        date = new Date(dateStr)
      }
    } else {
      date = new Date(dateStr)
    }
    
    // Verificar que la fecha sea válida
    if (isNaN(date.getTime())) {
      return 'N/A'
    }
    
    // Usar Intl.DateTimeFormat para obtener la fecha en hora de Bogotá
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Bogota',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    })
    
    // Obtener las partes de la fecha en hora de Bogotá
    const parts = formatter.formatToParts(date)
    
    const year = parts.find(p => p.type === 'year')?.value || ''
    const month = parts.find(p => p.type === 'month')?.value || ''
    const day = parts.find(p => p.type === 'day')?.value || ''
    const hour = parts.find(p => p.type === 'hour')?.value || ''
    const minute = parts.find(p => p.type === 'minute')?.value || ''
    const second = parts.find(p => p.type === 'second')?.value || ''
    const dayPeriod = parts.find(p => p.type === 'dayPeriod')?.value || ''
    
    // Formatear en formato DD/MM/YYYY HH:MM:SS AM/PM
    return `${day}/${month}/${year} ${hour}:${minute}:${second} ${dayPeriod.toUpperCase()}`
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

        {/* Chips de Estado - Filtros y Orden Activos */}
        {(statusFilter !== 'ALL' || selectedVendors.length > 0 || dateRange.start || dateRange.end || sortBy !== 'date_desc') && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {(statusFilter !== 'ALL' || selectedVendors.length > 0 || dateRange.start || dateRange.end) && (
              <div className="flex items-center gap-1.5 bg-dark-bg-secondary/60 px-2.5 py-1 rounded-lg border border-dark-border-primary/20">
                <Filter className="w-3 h-3 text-dark-text-muted" />
                <span className="text-dark-text-muted">Filtros activos:</span>
                <span className="text-dark-text-primary font-medium">
                  {selectedVendors.length + (dateRange.start ? 1 : 0) + (dateRange.end ? 1 : 0) + (statusFilter !== 'ALL' ? 1 : 0)}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Barra Horizontal con todas las funcionalidades */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Grupo 1: Acciones de Selección */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Menú de Selección */}
            {reports.length > 0 && (
              <div className="relative selection-menu-container">
                <Button
                  variant={selectionMode ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={() => {
                    if (selectionMode) {
                      toggleSelectionMode()
                    } else {
                      setOpenSelectionMenu(!openSelectionMenu)
                    }
                  }}
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
              {!selectionMode && openSelectionMenu && (
                <div className="absolute right-0 top-full mt-1.5 bg-dark-surface-primary border border-dark-border-primary/40 rounded-lg shadow-gemini z-[100] min-w-[200px] overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
                  <button
                    onClick={() => {
                      toggleSelectionMode()
                      setOpenSelectionMenu(false)
                    }}
                    className="w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-all duration-150 ease-out flex items-center gap-2 active:scale-[0.98]"
                  >
                    <CheckSquare className="w-4 h-4 text-dark-accent-primary" />
                    <span>Activar Selección</span>
                  </button>
                  <button
                    onClick={() => {
                      toggleSelectionMode()
                      selectAllVisible()
                      setOpenSelectionMenu(false)
                    }}
                    className="w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-colors flex items-center gap-2 border-t border-dark-border-primary/20"
                  >
                    <CheckSquare className="w-4 h-4 text-green-400" />
                    <span>Seleccionar Todos Visibles</span>
                  </button>
                </div>
              )}
            </div>
          )}

          </div>

          {/* Grupo 2: Vista y Datos (Ordenar, Estadísticas, Filtros) */}
          <div className="flex flex-wrap items-center gap-2">
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
                <div className="absolute right-0 top-full mt-1.5 bg-dark-surface-primary border border-dark-border-primary/40 rounded-lg shadow-gemini z-[100] min-w-[180px] overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
                  <button
                    onClick={() => {
                      setSortBy('date_desc')
                      setOpenSortMenu(false)
                    }}
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-all duration-150 ease-out flex items-center gap-2 active:scale-[0.98] ${
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
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-all duration-150 ease-out flex items-center gap-2 border-t border-dark-border-primary/20 active:scale-[0.98] ${
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
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-all duration-150 ease-out flex items-center gap-2 border-t border-dark-border-primary/20 active:scale-[0.98] ${
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
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-all duration-150 ease-out flex items-center gap-2 border-t border-dark-border-primary/20 active:scale-[0.98] ${
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
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-all duration-150 ease-out flex items-center gap-2 border-t border-dark-border-primary/20 active:scale-[0.98] ${
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
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-all duration-150 ease-out flex items-center gap-2 border-t border-dark-border-primary/20 active:scale-[0.98] ${
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
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-all duration-150 ease-out flex items-center gap-2 border-t border-dark-border-primary/20 active:scale-[0.98] ${
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
                    className={`w-full px-4 py-2.5 text-left text-sm text-dark-text-primary hover:bg-dark-bg-secondary transition-all duration-150 ease-out flex items-center gap-2 border-t border-dark-border-primary/20 active:scale-[0.98] ${
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
          </div>

          {/* Grupo 3: Salida (Exportar, Vista) */}
          <div className="flex flex-wrap items-center gap-2">

                {/* Toggle Vista Grid/Lista */}
                {reports.length > 0 && (
                  <div className={`flex bg-dark-bg-secondary/50 rounded-xl p-1 border transition-all ${
                    viewMode === 'grid' 
                      ? 'border-dark-accent-primary/40 shadow-gemini-sm' 
                      : viewMode === 'list'
                      ? 'border-dark-accent-primary/40 shadow-gemini-sm'
                      : 'border-dark-border-primary/20'
                  }`}>
                    <button
                      onClick={() => setViewMode('grid')}
                      className={`p-1.5 rounded-lg transition-all ${
                        viewMode === 'grid'
                          ? 'bg-dark-accent-primary text-white shadow-sm'
                          : 'text-dark-text-muted hover:text-dark-text-primary hover:bg-dark-bg-secondary/50'
                      }`}
                      title="Vista Grid"
                    >
                      <Grid3x3 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => setViewMode('list')}
                      className={`p-1.5 rounded-lg transition-all ${
                        viewMode === 'list'
                          ? 'bg-dark-accent-primary text-white shadow-sm'
                          : 'text-dark-text-muted hover:text-dark-text-primary hover:bg-dark-bg-secondary/50'
                      }`}
                      title="Vista Lista"
                    >
                      <List className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </div>

          {/* Búsqueda a la derecha */}
          <div className="relative w-72 flex-shrink-0 ml-auto">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-text-muted" />
            <input
              type="text"
              placeholder="Buscar..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-dark-bg-secondary border border-dark-border-primary/30 rounded-xl py-1.5 pl-9 pr-3 text-sm text-dark-text-primary focus:outline-none focus:ring-2 focus:ring-dark-accent-primary/50 transition-all placeholder:text-dark-text-muted/60"
            />
          </div>
        </div>
      </div>

      {/* Contenido Principal con mismo ancho que navbar */}
      <div className=" w-full min-w-0 space-y-6 mt-12">
        {/* Panel de Filtros Avanzados */}
        {showFilterPanel && (
          <div className="animate-in fade-in slide-in-from-top-2 duration-300 ease-out">
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
                        onClick={selectAllVisible}
                        className="text-xs text-dark-text-muted hover:text-dark-text-primary transition-colors"
                      >
                        Seleccionar todos visibles
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
                    {/* Botón de Exportación Directo */}
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={async () => {
                        try {
                          await handleExport('html')
                        } catch (error) {
                          // El error ya se maneja en handleExport
                        }
                      }}
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
                          Exportar Resumen ({selectedCount})
                        </>
                      )}
                    </Button>
                    
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
              
              // Calcular estado de selección para esta marca
              const vendorReportIds = vendorReports.map(r => r.id)
              const selectedVendorReports = vendorReportIds.filter(id => isSelected(id))
              const allSelected = selectedVendorReports.length === vendorReportIds.length && vendorReportIds.length > 0
              const someSelected = selectedVendorReports.length > 0 && selectedVendorReports.length < vendorReportIds.length
              
              const handleToggleVendorSelection = (e) => {
                e.stopPropagation()
                if (allSelected) {
                  // Deseleccionar todos los reportes de esta marca
                  vendorReportIds.forEach(id => {
                    if (isSelected(id)) {
                      toggleSelection(id)
                    }
                  })
                } else {
                  // Seleccionar todos los reportes de esta marca
                  vendorReportIds.forEach(id => {
                    if (!isSelected(id)) {
                      toggleSelection(id)
                    }
                  })
                }
              }
              
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
                      {/* Checkbox para seleccionar todos los reportes de esta marca */}
                      {selectionMode && (
                        <button
                          onClick={handleToggleVendorSelection}
                          className="flex-shrink-0"
                          title={allSelected ? 'Deseleccionar todos' : 'Seleccionar todos'}
                        >
                          {allSelected ? (
                            <CheckSquare className="w-5 h-5 text-dark-accent-primary" />
                          ) : someSelected ? (
                            <div className="relative">
                              <Square className="w-5 h-5 text-dark-text-muted" />
                              <div className="absolute inset-0 flex items-center justify-center">
                                <div className="w-3 h-0.5 bg-dark-accent-primary"></div>
                              </div>
                            </div>
                          ) : (
                            <Square className="w-5 h-5 text-dark-text-muted hover:text-dark-text-primary transition-colors" />
                          )}
                        </button>
                      )}
                      
                      <div className={`p-2 rounded-lg transition-all duration-200 ease-out ${isOpen ? 'bg-dark-accent-primary text-white scale-110' : 'bg-dark-bg-secondary text-dark-accent-primary hover:scale-105'}`}>
                        <Folder className={`w-5 h-5 flex-shrink-0 transition-transform duration-200 ${isOpen ? 'rotate-0' : 'rotate-[-15deg]'}`} />
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
                        className="p-1 text-dark-text-muted hover:text-dark-text-primary transition-all duration-200 ease-out hover:scale-110 active:scale-95"
                      >
                        {isOpen ? <ChevronDown className="w-5 h-5 transition-transform duration-200" /> : <ChevronRight className="w-5 h-5 transition-transform duration-200" />}
                      </button>
                    </div>
                  </div>

                  {/* Folder Content (Files) */}
                  {isOpen && (
                    <div className={`w-full min-w-0 transition-all duration-300 ease-out ${openDownloadMenu ? 'overflow-visible' : 'overflow-hidden'}`}>
                      {viewMode === 'grid' ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-3 pl-0 md:pl-2 w-full min-w-0">
                          {vendorReports.map((report, index) => (
                            <Card 
                          key={report.id} 
                          className={`relative group p-5 hover:border-dark-accent-primary/40 bg-dark-surface-primary/50 hover:bg-dark-surface-primary border-dark-border-primary/20 transition-all duration-300 ease-out hover:shadow-gemini-sm hover:scale-[1.02] ${isDeleting === report.id ? 'opacity-50 pointer-events-none' : ''} ${selectionMode ? 'cursor-default' : 'cursor-pointer'} ${openDownloadMenu === report.id ? 'overflow-visible' : ''}`}
                          style={{ 
                            animation: `fadeInUp 0.3s ease-out ${index * 30}ms both`
                          }}
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
                                  <h3 className="text-base font-semibold text-dark-text-primary truncate leading-tight group-hover:text-dark-accent-primary transition-colors duration-150 ease-out">
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
                                    className="p-1.5 rounded-md text-dark-text-muted hover:bg-blue-500/15 hover:text-blue-400 transition-all duration-150 ease-out opacity-0 group-hover:opacity-100 hover:scale-110 active:scale-95"
                                    title="Opciones de descarga"
                                  >
                                    {isDownloading === report.id ? <Loading size="xs" /> : <Download className="w-3.5 h-3.5" />}
                                  </button>
                                  
                                  {/* Menú desplegable */}
                                  {openDownloadMenu === report.id && (
                                    <div className="absolute right-0 top-full mt-1.5 bg-dark-surface-primary border border-dark-border-primary/40 rounded-lg shadow-gemini z-[9999] min-w-[180px] overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
                                      <button
                                        onClick={(e) => handleDownloadCapture(e, report.id, report.filename)}
                                        className="w-full px-3.5 py-2 text-left text-xs text-dark-text-primary hover:bg-dark-bg-secondary transition-all duration-150 ease-out flex items-center gap-2 active:scale-[0.98]"
                                      >
                                        <Download className="w-3.5 h-3.5 text-blue-400 transition-transform duration-150 hover:scale-110" />
                                        <span>Descargar Captura</span>
                                      </button>
                                      <button
                                        onClick={(e) => handleDownloadPDF(e, report.id)}
                                        className="w-full px-3.5 py-2 text-left text-xs text-dark-text-primary hover:bg-dark-bg-secondary transition-all duration-150 ease-out flex items-center gap-2 border-t border-dark-border-primary/20 active:scale-[0.98]"
                                      >
                                        <FileText className="w-3.5 h-3.5 text-purple-400 transition-transform duration-150 hover:scale-110" />
                                        <span>Descargar PDF</span>
                                      </button>
                                      <button
                                        onClick={(e) => handleDownloadBoth(e, report.id, report.filename)}
                                        className="w-full px-3.5 py-2 text-left text-xs text-dark-text-primary hover:bg-dark-bg-secondary transition-all duration-150 ease-out flex items-center gap-2 border-t border-dark-border-primary/20 active:scale-[0.98]"
                                      >
                                        <Download className="w-3.5 h-3.5 text-green-400 transition-transform duration-150 hover:scale-110" />
                                        <span>Descargar Ambos</span>
                                      </button>
                                    </div>
                                  )}
                                </div>
                                
                                <button
                                  onClick={(e) => handleDeleteReport(e, report.id)}
                                  className="p-1.5 rounded-md text-dark-text-muted hover:bg-red-500/15 hover:text-red-400 transition-all duration-150 ease-out opacity-0 group-hover:opacity-100 hover:scale-110 active:scale-95"
                                  title="Eliminar reporte"
                                >
                                  {isDeleting === report.id ? <Loading size="xs" /> : <Trash2 className="w-3.5 h-3.5 transition-transform duration-150" />}
                                </button>
                                
                                <div className={`flex-shrink-0 px-2 py-0.5 rounded text-[10px] font-semibold tracking-wide ${
                                  ['SUCCESS', 'EXCELLENT', 'GOOD'].includes(report.verdict?.toUpperCase())
                                    ? 'bg-green-500/15 text-green-400' 
                                    : 'bg-red-500/15 text-red-400'
                                }`}>
                                  {['SUCCESS', 'EXCELLENT', 'GOOD'].includes(report.verdict?.toUpperCase()) 
                                    ? 'ÉXITO' 
                                    : report.verdict?.toUpperCase() === 'FAILED' 
                                      ? 'FALLÓ' 
                                      : report.verdict || 'N/A'}
                                </div>
                              </div>
                            </div>

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
            handleDownloadPDF(e, contextMenu.report.id)
          }
        }}
        report={contextMenu.report}
      />
    </div>
  )
}

export default ReportsPage
