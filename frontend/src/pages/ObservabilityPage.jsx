import React, { useState, useEffect } from 'react'
import { ExternalLink, TrendingUp, Clock, DollarSign, Zap, AlertCircle, Activity, CheckCircle, XCircle, RefreshCw, Tag, FileText } from 'lucide-react'

export default function ObservabilityPage() {
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)

  const langfuseUrl = `http://${window.location.hostname}:3000/project/cmljlef020006e364mymjb65y`

  const fetchMetrics = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await fetch('/observability/metrics')
      
      if (!response.ok) {
        throw new Error(`Error ${response.status}: ${response.statusText}`)
      }
      
      const contentType = response.headers.get('content-type')
      if (!contentType || !contentType.includes('application/json')) {
        throw new Error('La respuesta del servidor no es JSON válido (posible error 404/500 HTML)')
      }
      
      const data = await response.json()
      setMetrics(data)
      setLastUpdate(new Date())
    } catch (err) {
      console.error('Error fetching metrics:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchMetrics()
    
    // Auto-refresh cada 30 segundos
    const interval = setInterval(fetchMetrics, 30000)
    return () => clearInterval(interval)
  }, [])

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 4,
      maximumFractionDigits: 6
    }).format(value)
  }

  const formatTimestamp = (isoString) => {
    if (!isoString) return 'N/A'
    const date = new Date(isoString)
    return date.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  const MetricCard = ({ title, value, subtitle, icon: Icon, trend, color = 'blue' }) => {
    const colorClasses = {
      blue: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
      green: 'bg-green-500/10 text-green-400 border-green-500/20',
      purple: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
      orange: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
      red: 'bg-red-500/10 text-red-400 border-red-500/20',
    }

    return (
      <div className={`rounded-xl border ${colorClasses[color]} p-6 transition-all hover:scale-[1.02]`}>
        <div className="flex items-start justify-between mb-4">
          <div className={`p-3 rounded-lg ${colorClasses[color]}`}>
            <Icon className="w-6 h-6" />
          </div>
          {trend && (
            <div className={`flex items-center gap-1 text-xs font-medium ${trend > 0 ? 'text-green-400' : 'text-red-400'}`}>
              <TrendingUp className={`w-3 h-3 ${trend < 0 ? 'rotate-180' : ''}`} />
              {Math.abs(trend)}%
            </div>
          )}
        </div>
        <div>
          <p className="text-sm text-dark-text-secondary mb-1">{title}</p>
          <p className="text-2xl font-bold text-dark-text-primary mb-1">{value}</p>
          {subtitle && <p className="text-xs text-dark-text-muted">{subtitle}</p>}
        </div>
      </div>
    )
  }


  const TraceItem = ({ trace }) => {
    const isError = trace.status === 'error';
    
    return (
      <div className="flex items-center justify-between p-3 rounded-lg bg-dark-surface-hover border border-dark-border-primary/30 hover:border-dark-accent-primary/30 transition-colors">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {isError ? (
            <XCircle className="w-4 h-4 text-red-400 shrink-0" />
          ) : (
            <CheckCircle className="w-4 h-4 text-green-400 shrink-0" />
          )}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-dark-text-primary truncate" title={trace.name}>{trace.name}</p>
            <p className="text-xs text-dark-text-muted">{formatTimestamp(trace.timestamp)}</p>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-dark-text-secondary">
          <div className="flex items-center gap-1 min-w-[60px] justify-end">
            <Clock className="w-3 h-3 text-dark-text-muted" />
            <span>{trace.latency_ms}ms</span>
          </div>
          <div className="flex items-center gap-1 min-w-[70px] justify-end">
            <DollarSign className="w-3 h-3 text-green-400" />
            <span className="font-mono">{formatCurrency(trace.cost_usd)}</span>
          </div>
        </div>
      </div>
    )
  }

  if (loading && !metrics) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-dark-bg-primary">
        <RefreshCw className="w-12 h-12 text-dark-accent-primary animate-spin mb-4" />
        <p className="text-lg font-medium text-dark-text-primary">Cargando métricas...</p>
      </div>
    )
  }

  if (error && !metrics) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-dark-bg-primary">
        <AlertCircle className="w-12 h-12 text-red-400 mb-4" />
        <p className="text-lg font-medium text-dark-text-primary mb-2">Error al cargar métricas</p>
        <p className="text-sm text-dark-text-secondary mb-4">{error}</p>
        <button
          onClick={fetchMetrics}
          className="px-4 py-2 bg-dark-accent-primary text-white rounded-lg hover:bg-dark-accent-primary/80 transition-colors"
        >
          Reintentar
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full w-full bg-dark-bg-primary overflow-auto">
      {/* Header */}
      <div className="mt-10">
        <div className="container-app py-4 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-dark-text-primary flex items-center gap-2">
              <Activity className="w-5 h-5 text-dark-accent-primary" />
              Observabilidad en Tiempo Real
            </h2>
            <p className="text-sm text-dark-text-secondary mt-1">
              Monitoreo de trazas, costos y latencia con Langfuse
              {lastUpdate && (
                <span className="ml-2 text-xs text-dark-text-muted">
                  • Actualizado: {lastUpdate.toLocaleTimeString('es-ES')}
                </span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={fetchMetrics}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-2 bg-dark-surface-hover hover:bg-dark-surface-active text-dark-text-primary rounded-lg transition-colors text-sm font-medium border border-dark-border-primary/30 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Actualizar
            </button>
            <a 
              href={langfuseUrl} 
              target="_blank" 
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 bg-dark-accent-primary/10 hover:bg-dark-accent-primary/20 text-dark-accent-primary rounded-lg transition-colors text-sm font-medium border border-dark-accent-primary/20"
            >
              <ExternalLink className="w-4 h-4" />
              Dashboard Completo
            </a>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="container-app flex-1 py-6 space-y-6 w-full">
        {/* Métricas principales */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            title="Trazas Totales"
            value={metrics?.total_traces || 0}
            subtitle="Últimas 24 horas"
            icon={Activity}
            color="blue"
          />
          <MetricCard
            title="Costo Total"
            value={formatCurrency(metrics?.total_cost_usd || 0)}
            subtitle="Últimas 24 horas"
            icon={DollarSign}
            color="green"
          />
          <MetricCard
            title="Latencia Promedio"
            value={`${metrics?.avg_latency_ms || 0}ms`}
            subtitle="Tiempo de respuesta"
            icon={Zap}
            color="purple"
          />
          <MetricCard
            title="Tasa de Errores"
            value={`${metrics?.error_rate || 0}%`}
            subtitle="Errores detectados"
            icon={AlertCircle}
            color={metrics?.error_rate > 5 ? 'red' : 'orange'}
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Trazas recientes con Scroll */}
          <div className="lg:col-span-2 bg-dark-bg-secondary/30 rounded-xl border border-dark-border-primary/50 flex flex-col h-[520px]">
            <div className="p-6 border-b border-dark-border-primary/50 shrink-0">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-dark-text-primary flex items-center gap-2">
                  <Clock className="w-5 h-5 text-dark-accent-primary" />
                  Trazas Recientes
                </h3>
                <span className="text-xs text-dark-text-muted">
                  {metrics?.recent_traces?.length || 0} trazas
                </span>
              </div>
            </div>
            
            <div className="flex-1 overflow-y-auto p-4 space-y-2 scrollbar-thin scrollbar-thumb-dark-border-secondary scrollbar-track-transparent">
              {metrics?.recent_traces && metrics.recent_traces.length > 0 ? (
                metrics.recent_traces.map((trace, index) => (
                  <TraceItem key={trace.id || index} trace={trace} />
                ))
              ) : (
                <div className="text-center py-20 text-dark-text-muted flex flex-col items-center">
                  <Activity className="w-12 h-12 mb-4 opacity-20" />
                  <p className="text-sm">No hay trazas recientes disponibles</p>
                </div>
              )}
            </div>
          </div>

            {/* Panel de Modelos y Estado */}
          <div className="space-y-6">
             {/* Uso de Modelos */}
            <div className="bg-dark-bg-secondary/30 rounded-xl border border-dark-border-primary/50 p-6">
              <h3 className="text-lg font-semibold text-dark-text-primary mb-4 flex items-center gap-2">
                <Zap className="w-5 h-5 text-dark-accent-primary" />
                Uso por Modelo
              </h3>
              <div className="space-y-4">
                {metrics?.models_used && Object.keys(metrics.models_used).length > 0 ? (
                  Object.entries(metrics.models_used).map(([modelName, stats]) => (
                    <div key={modelName} className="p-3 rounded-lg bg-dark-bg-primary/50 border border-dark-border-primary/30">
                      <div className="flex justify-between items-start mb-2">
                        <span className="text-sm font-medium text-dark-text-primary truncate max-w-[180px]" title={modelName}>
                          {modelName.split('/').pop()}
                        </span>
                        <span className="text-xs font-mono text-green-400 bg-green-500/10 px-1.5 py-0.5 rounded">
                           {formatCurrency(stats.cost)}
                        </span>
                      </div>
                      <div className="flex justify-between text-xs text-dark-text-secondary">
                        <span>{stats.count} llamadas</span>
                        <span>{stats.tokens.toLocaleString()} toks</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-dark-text-muted text-center py-4">No hay datos de modelos</p>
                )}
              </div>
              </div>

            {/* Estado del Sistema (Compacto) */}
            <div className="bg-dark-bg-secondary/30 rounded-xl border border-dark-border-primary/50 p-6">
              <h3 className="text-sm font-semibold text-dark-text-primary mb-3 uppercase tracking-wider text-dark-text-muted">
                Estado
              </h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-dark-text-secondary">Langfuse API</span>
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
                    <span className="text-xs font-medium text-green-400">Conectado</span>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-dark-text-secondary">Tokens 24h</span>
                  <span className="text-sm font-medium text-dark-text-primary">
                    {(metrics?.total_tokens || 0).toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-dark-text-muted">Actualizado</span>
                  <span className="text-xs text-dark-text-primary">
                    {lastUpdate ? lastUpdate.toLocaleTimeString('es-ES') : '--:--'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
