import { BarChart3, TrendingUp, Package, Clock, CheckCircle2, XCircle } from 'lucide-react'

/**
 * Panel de estadísticas de reportes
 */
export function StatsPanel({ stats, loading, compact = false }) {
  if (loading) {
    return (
      <div className={compact ? "p-4" : "p-6 border-dark-border-primary/20"}>
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-dark-bg-secondary rounded w-1/3"></div>
          <div className="h-20 bg-dark-bg-secondary rounded"></div>
        </div>
      </div>
    )
  }

  if (!stats || stats.total_reports === 0) {
    return (
      <div className={compact ? "p-4 text-center" : "p-6 border-dark-border-primary/20 text-center"}>
        <Package className="w-12 h-12 text-dark-text-muted/30 mx-auto mb-3" />
        <p className="text-dark-text-muted">No hay estadísticas disponibles</p>
      </div>
    )
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
    
    return `${d}/${m}/${y} ${hours}:${min} ${ampm}`
  }

  const successCount = stats.verdict_distribution?.SUCCESS || 0
  const excellentCount = stats.verdict_distribution?.EXCELLENT || 0
  const goodCount = stats.verdict_distribution?.GOOD || 0
  const failedCount = stats.verdict_distribution?.FAILED || 0
  const totalSuccess = successCount + excellentCount + goodCount

  // Calcular porcentajes para el gráfico
  const total = stats.total_reports || 1
  const successPercent = (totalSuccess / total) * 100
  const failedPercent = (failedCount / total) * 100

  return (
    <div className={compact ? "p-5 sm:p-6 bg-dark-surface-primary" : "p-6 border-dark-border-primary/20 bg-dark-surface-primary/50"}>
      <div className="space-y-6 sm:space-y-7">
        {/* Título */}
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-dark-accent-primary" />
          <h3 className="text-lg font-semibold text-dark-text-primary">Estadísticas</h3>
        </div>

        {/* Grid de Métricas */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
          {/* Total Reportes */}
          <div className="bg-dark-bg-secondary/50 rounded-lg p-3 sm:p-4 border border-dark-border-primary/10">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-dark-text-muted uppercase tracking-wide">Total</span>
              <Package className="w-4 h-4 text-dark-text-muted" />
            </div>
            <p className="text-xl sm:text-2xl font-bold text-dark-text-primary">{stats.total_reports}</p>
            <p className="text-xs text-dark-text-muted mt-1">reportes analizados</p>
          </div>

          {/* Tasa de Éxito */}
          <div className="bg-dark-bg-secondary/50 rounded-lg p-3 sm:p-4 border border-dark-border-primary/10">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-dark-text-muted uppercase tracking-wide">Éxito</span>
              <TrendingUp className="w-4 h-4 text-green-400" />
            </div>
            <p className="text-xl sm:text-2xl font-bold text-green-400">{stats.success_rate || 0}%</p>
            <p className="text-xs text-dark-text-muted mt-1">{totalSuccess} exitosos</p>
          </div>

          {/* Fallos */}
          <div className="bg-dark-bg-secondary/50 rounded-lg p-3 sm:p-4 border border-dark-border-primary/10">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-dark-text-muted uppercase tracking-wide">Fallos</span>
              <XCircle className="w-4 h-4 text-red-400" />
            </div>
            <p className="text-xl sm:text-2xl font-bold text-red-400">{failedCount}</p>
            <p className="text-xs text-dark-text-muted mt-1">reportes fallidos</p>
          </div>

          {/* Última Captura */}
          <div className="bg-dark-bg-secondary/50 rounded-lg p-3 sm:p-4 border border-dark-border-primary/10">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-dark-text-muted uppercase tracking-wide">Última</span>
              <Clock className="w-4 h-4 text-dark-text-muted" />
            </div>
            <p className="text-sm font-semibold text-dark-text-primary">
              {formatDate(stats.last_capture)}
            </p>
            <p className="text-xs text-dark-text-muted mt-1">captura analizada</p>
          </div>
        </div>

        {/* Distribución de Veredictos - Gráfico de Barras Simple */}
        <div className="space-y-3">
          <h4 className="text-sm font-semibold text-dark-text-primary flex items-center gap-2">
            <BarChart3 className="w-4 h-4" />
            Distribución de Veredictos
          </h4>
          <div className="space-y-2">
            {/* Barra de Éxitos */}
            {totalSuccess > 0 && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />
                    <span className="text-xs text-dark-text-primary font-medium">Éxitos</span>
                  </div>
                  <span className="text-xs text-dark-text-muted">{totalSuccess} ({successPercent.toFixed(1)}%)</span>
                </div>
                <div className="h-2 bg-dark-bg-secondary rounded-full overflow-hidden">
                  <div
                    className="h-full bg-green-500/30 rounded-full transition-all"
                    style={{ width: `${successPercent}%` }}
                  />
                </div>
              </div>
            )}

            {/* Barra de Fallos */}
            {failedCount > 0 && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <XCircle className="w-3.5 h-3.5 text-red-400" />
                    <span className="text-xs text-dark-text-primary font-medium">Fallos</span>
                  </div>
                  <span className="text-xs text-dark-text-muted">{failedCount} ({failedPercent.toFixed(1)}%)</span>
                </div>
                <div className="h-2 bg-dark-bg-secondary rounded-full overflow-hidden">
                  <div
                    className="h-full bg-red-500/30 rounded-full transition-all"
                    style={{ width: `${failedPercent}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Top 3 Marcas */}
        {stats.top_vendors && stats.top_vendors.length > 0 && (
          <div className="space-y-3">
            <h4 className="text-sm font-semibold text-dark-text-primary">Top 3 Marcas</h4>
            <div className="space-y-2">
              {stats.top_vendors.map((item, index) => {
                const percentage = (item.count / stats.total_reports) * 100
                return (
                  <div key={item.vendor} className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-6 h-6 rounded-full bg-dark-accent-primary/20 text-dark-accent-primary text-xs font-bold">
                      {index + 1}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm text-dark-text-primary font-medium">{item.vendor}</span>
                        <span className="text-xs text-dark-text-muted">{item.count} reportes</span>
                      </div>
                      <div className="h-1.5 bg-dark-bg-secondary rounded-full overflow-hidden">
                        <div
                          className="h-full bg-dark-accent-primary/30 rounded-full transition-all"
                          style={{ width: `${percentage}%` }}
                        />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
