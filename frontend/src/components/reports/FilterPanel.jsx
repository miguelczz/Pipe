import { useState } from 'react'
import { X, Filter, Calendar, Tag, CheckCircle2, XCircle } from 'lucide-react'
import { Button } from '../ui/Button'

/**
 * Panel de filtros avanzados para reportes
 */
export function FilterPanel({ 
  isOpen, 
  onClose, 
  vendors = [],
  selectedVendors = [],
  onVendorsChange,
  dateRange = { start: null, end: null },
  onDateRangeChange,
  statusFilter = 'ALL',
  onStatusFilterChange,
  onClearFilters 
}) {
  const [localSelectedVendors, setLocalSelectedVendors] = useState(selectedVendors)

  const handleVendorToggle = (vendor) => {
    const newVendors = localSelectedVendors.includes(vendor)
      ? localSelectedVendors.filter(v => v !== vendor)
      : [...localSelectedVendors, vendor]
    setLocalSelectedVendors(newVendors)
    onVendorsChange(newVendors)
  }

  const handleClearAll = () => {
    setLocalSelectedVendors([])
    onVendorsChange([])
    onDateRangeChange({ start: null, end: null })
    onStatusFilterChange('ALL')
    onClearFilters()
  }

  const activeFiltersCount = localSelectedVendors.length + (dateRange.start ? 1 : 0) + (dateRange.end ? 1 : 0) + (statusFilter !== 'ALL' ? 1 : 0)

  if (!isOpen) return null

  return (
    <div className="bg-dark-surface-primary border border-dark-border-primary/30 rounded-xl p-5 space-y-5 shadow-gemini-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Filter className="w-5 h-5 text-dark-accent-primary" />
          <h3 className="text-lg font-semibold text-dark-text-primary">Filtros Avanzados</h3>
          {activeFiltersCount > 0 && (
            <span className="bg-dark-accent-primary text-white text-xs font-semibold px-2 py-0.5 rounded-full">
              {activeFiltersCount}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-dark-text-muted hover:bg-dark-bg-secondary hover:text-dark-text-primary transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Filtro por Veredicto */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-dark-text-primary flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" />
          Veredicto
        </label>
        <div className="flex bg-dark-bg-secondary/50 rounded-xl p-1 border border-dark-border-primary/20">
          {['ALL', 'SUCCESS', 'FAILED'].map((s) => (
            <button
              key={s}
              onClick={() => onStatusFilterChange(s)}
              className={`flex-1 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap flex items-center justify-center gap-1.5 ${
                statusFilter === s 
                  ? 'bg-dark-accent-primary text-white shadow-lg' 
                  : 'text-dark-text-muted hover:text-dark-text-primary'
              }`}
            >
              {s === 'ALL' ? (
                <>Todos</>
              ) : s === 'SUCCESS' ? (
                <>
                  <CheckCircle2 className="w-3 h-3" />
                  Éxitos
                </>
              ) : (
                <>
                  <XCircle className="w-3 h-3" />
                  Fallos
                </>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Filtro por Marca */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-dark-text-primary flex items-center gap-2">
          <Tag className="w-4 h-4" />
          Marca
        </label>
        <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
          {vendors.map((vendor) => {
            const isSelected = localSelectedVendors.includes(vendor)
            return (
              <button
                key={vendor}
                onClick={() => handleVendorToggle(vendor)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  isSelected
                    ? 'bg-dark-accent-primary text-white shadow-sm'
                    : 'bg-dark-bg-secondary text-dark-text-muted hover:bg-dark-bg-secondary/80 hover:text-dark-text-primary'
                }`}
              >
                {vendor}
              </button>
            )
          })}
        </div>
      </div>

      {/* Filtro por Rango de Fechas */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-dark-text-primary flex items-center gap-2">
          <Calendar className="w-4 h-4" />
          Rango de Fechas
        </label>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-dark-text-muted mb-1 block">Desde</label>
            <input
              type="date"
              value={dateRange.start || ''}
              onChange={(e) => onDateRangeChange({ ...dateRange, start: e.target.value })}
              className="w-full bg-dark-bg-secondary border border-dark-border-primary/30 rounded-lg py-2 px-3 text-sm text-dark-text-primary focus:outline-none focus:ring-2 focus:ring-dark-accent-primary/50"
            />
          </div>
          <div>
            <label className="text-xs text-dark-text-muted mb-1 block">Hasta</label>
            <input
              type="date"
              value={dateRange.end || ''}
              onChange={(e) => onDateRangeChange({ ...dateRange, end: e.target.value })}
              className="w-full bg-dark-bg-secondary border border-dark-border-primary/30 rounded-lg py-2 px-3 text-sm text-dark-text-primary focus:outline-none focus:ring-2 focus:ring-dark-accent-primary/50"
            />
          </div>
        </div>
      </div>

      {/* Botón Limpiar Filtros */}
      {activeFiltersCount > 0 && (
        <Button
          variant="ghost"
          size="sm"
          onClick={handleClearAll}
          className="w-full"
        >
          <X className="w-4 h-4 mr-2" />
          Limpiar Todos los Filtros
        </Button>
      )}
    </div>
  )
}
