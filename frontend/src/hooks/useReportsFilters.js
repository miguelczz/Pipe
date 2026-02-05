import { useState, useEffect } from 'react'

/**
 * Maneja el estado básico de filtros/orden/búsqueda y vista de ReportsPage.
 * Extraído para mantener la página más limpia y con una sola responsabilidad.
 */
export function useReportsFilters() {
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL') // ALL, SUCCESS, FAILED

  const [sortBy, setSortBy] = useState(() => {
    const saved = localStorage.getItem('reports_sort_by')
    return saved || 'date_desc'
  })

  const [viewMode, setViewMode] = useState(() => {
    const saved = localStorage.getItem('reports_view_mode')
    return saved || 'grid'
  })

  const [showFilterPanel, setShowFilterPanel] = useState(false)
  const [selectedVendors, setSelectedVendors] = useState([])
  const [dateRange, setDateRange] = useState({ start: null, end: null })

  // Persistir ordenamiento
  useEffect(() => {
    localStorage.setItem('reports_sort_by', sortBy)
  }, [sortBy])

  // Persistir modo de vista
  useEffect(() => {
    localStorage.setItem('reports_view_mode', viewMode)
  }, [viewMode])

  return {
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
  }
}

