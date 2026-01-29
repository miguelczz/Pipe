import React, { useMemo } from 'react'
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler } from 'chart.js'
import { Line } from 'react-chartjs-2'
import { Activity, Radio, ShieldAlert } from 'lucide-react'

// Registrar componentes de Chart.js
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

/**
 * Componente de gráfica rediseñado para "Storytelling".
 * No solo muestra dBm, muestra la HISTORIA de la transición del usuario.
 */
export function BandSteeringChart({ btmEvents = [], transitions = [], signalSamples = [], rawStats = {} }) {
  
  const chartData = useMemo(() => {
    if (!signalSamples.length && !btmEvents.length && !transitions.length) {
      return { datasets: [] }
    }

    const timelineEvents = []
    
    // Inyectar muestras de señal
    signalSamples.forEach(s => timelineEvents.push({ 
        timestamp: s.timestamp, type: 'signal', rssi: s.rssi, band: s.band 
    }))

    // Inyectar eventos BTM
    btmEvents.forEach(e => timelineEvents.push({
        timestamp: e.timestamp, type: 'btm', label: e.event_type === 'request' ? 'Sugerencia AP 📡' : 'Respuesta Cliente 📱',
        sub: e.status_code === 0 ? 'Aceptado ✅' : (e.status_code ? `Rechazo (Code ${e.status_code}) ❌` : ''),
        rssi: e.rssi
    }))

    // Inyectar Transiciones (El "Salto")
    transitions.forEach(t => {
        timelineEvents.push({
            timestamp: t.start_time, type: 'transition', 
            label: t.steering_type === 'aggressive' ? 'Destierro AP (Deauth) ⚠️' : 'Inicio Salto 🚀',
            band: t.from_band
        })
        if (t.end_time) {
            timelineEvents.push({
                timestamp: t.end_time, type: 'connected', 
                label: 'Conectado ✅', 
                sub: `A ${t.to_band}`,
                band: t.to_band
            })
        }
    })

    timelineEvents.sort((a, b) => a.timestamp - b.timestamp)
    const firstTimestamp = timelineEvents[0]?.timestamp || 0
    
    const band24Data = []
    const band5Data = []
    const milestoneMarkers = []
    
    // Lógica de "Connected Band" para el sombreado de fondo
    let currentBand = null
    const backgrounds = []

    timelineEvents.forEach((ev, idx) => {
      const relX = parseFloat((ev.timestamp - firstTimestamp).toFixed(2))
      
      // Actualizar banda actual
      if (ev.band) currentBand = ev.band
      
      // Crear punto de datos
      const point = { x: relX, y: ev.rssi || -60, band: ev.band || currentBand }

      if (point.band?.includes('2.4')) {
        band24Data.push(point)
      } else {
        band5Data.push(point)
      }

      // Si es un hito importante (BTM, Transition, Deauth), crear marcador
      if (ev.type !== 'signal') {
        milestoneMarkers.push({
          x: relX,
          y: ev.rssi || -40, // Colocar arriba para visibilidad
          label: ev.label,
          sub: ev.sub,
          type: ev.type
        })
      }
    })

    return {
      datasets: [
        {
          label: 'Señal 2.4 GHz',
          data: band24Data,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          pointRadius: 0,
          borderWidth: 3,
          tension: 0.4,
          fill: 'origin',
        },
        {
          label: 'Señal 5 GHz',
          data: band5Data,
          borderColor: '#10b981',
          backgroundColor: 'rgba(16, 185, 129, 0.1)',
          pointRadius: 0,
          borderWidth: 3,
          tension: 0.4,
          fill: 'origin',
        },
        {
          label: 'Hitos del Flujo',
          data: milestoneMarkers,
          showLine: false,
          pointRadius: 8,
          pointHoverRadius: 12,
          pointStyle: 'rectRounded',
          backgroundColor: (context) => {
            const type = context.raw?.type
            if (type === 'btm') return '#f59e0b'
            if (type === 'transition') return '#ef4444'
            return '#10b981'
          }
        }
      ]
    }
  }, [btmEvents, transitions, signalSamples])

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    layout: { padding: { top: 20, bottom: 10 } },
    scales: {
      x: {
        type: 'linear',
        title: { display: true, text: 'Segundos del análisis', color: '#9ca3af', font: { weight: 'bold' } },
        ticks: { color: '#6b7280' },
        grid: { display: false }
      },
      y: {
        min: -95,
        max: -25,
        title: { display: true, text: 'Calidad de Señal (dBm)', color: '#9ca3af' },
        ticks: { color: '#6b7280' },
        grid: { color: 'rgba(255, 255, 255, 0.05)' }
      }
    },
    plugins: {
      legend: { position: 'bottom', labels: { color: '#e5e7eb', usePointStyle: true, padding: 20 } },
      tooltip: {
        enabled: true,
        backgroundColor: '#1f2937',
        titleFont: { size: 14, weight: 'bold' },
        padding: 12,
        cornerRadius: 8,
        callbacks: {
          label: (ctx) => {
            const p = ctx.raw
            if (p.label) return [`📢 ${p.label}`, `📝 ${p.sub || ''}`]
            return `📊 Señal: ${p.y} dBm (${p.band})`
          }
        }
      }
    }
  }

  if (!chartData.datasets || chartData.datasets.length === 0 || 
     (chartData.datasets[0].data.length === 0 && chartData.datasets[1].data.length === 0)) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[300px] text-dark-text-secondary">
        <Activity className="w-12 h-12 mb-2 opacity-20" />
        <p>No hay eventos de steering para graficar</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Mini Dashboard de la Gráfica */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-2">
        <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20">
          <p className="text-[10px] text-blue-400 uppercase font-bold tracking-wider mb-1">Zona Estabilidad</p>
          <p className="text-sm font-semibold text-dark-text-primary">&gt; -65 dBm</p>
        </div>
        <div className="p-3 rounded-xl bg-yellow-500/10 border border-yellow-500/20">
          <p className="text-[10px] text-yellow-400 uppercase font-bold tracking-wider mb-1">Zona Steering</p>
          <p className="text-sm font-semibold text-dark-text-primary">-65 a -75 dBm</p>
        </div>
        <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20">
          <p className="text-[10px] text-red-400 uppercase font-bold tracking-wider mb-1">Zona Crítica</p>
          <p className="text-sm font-semibold text-dark-text-primary">&lt; -80 dBm</p>
        </div>
        <div className="p-3 rounded-xl bg-green-500/10 border border-green-500/20">
          <p className="text-[10px] text-green-400 uppercase font-bold tracking-wider mb-1">Resultado</p>
          <p className="text-sm font-semibold text-dark-text-primary">Salto Exitoso ✅</p>
        </div>
      </div>

      <div className="relative w-full h-[300px] bg-dark-bg-secondary/30 rounded-2xl p-4 border border-dark-border-primary/50 overflow-hidden">
        {/* Línea de umbral crítica visual (SVG superpuesto para máxima nitidez) */}
        <div className="absolute left-0 right-0 border-t border-dashed border-red-500/30 z-0" style={{ top: '75%' }}>
            <span className="absolute right-4 -top-5 text-[10px] text-red-500/50 font-bold uppercase">Umbral Crítico (-75dBm)</span>
        </div>
        
        <Line 
          key={rawStats?.diagnostics?.client_mac || 'initial'} 
          data={chartData} 
          options={options} 
        />
      </div>

      {/* Tabla Explicativa de Elementos Visuales */}
      <div className="bg-dark-surface-primary rounded-xl border border-dark-border-primary p-4">
        <h4 className="text-sm font-semibold text-dark-text-primary mb-3 flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-dark-accent-primary" />
          Guía de Elementos Visuales
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {/* Líneas de Señal */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-dark-text-muted uppercase tracking-wider mb-2">Líneas de Señal</p>
            <div className="flex items-center gap-2 text-xs">
              <div className="w-8 h-0.5 bg-blue-500"></div>
              <span className="text-dark-text-secondary">2.4 GHz</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <div className="w-8 h-0.5 bg-green-500"></div>
              <span className="text-dark-text-secondary">5 GHz</span>
            </div>
          </div>

          {/* Marcadores de Eventos */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-dark-text-muted uppercase tracking-wider mb-2">Marcadores de Eventos</p>
            <div className="flex items-center gap-2 text-xs">
              <div className="w-3 h-3 rounded bg-yellow-500"></div>
              <span className="text-dark-text-secondary">Sugerencia AP / Respuesta Cliente</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <div className="w-3 h-3 rounded bg-red-500"></div>
              <span className="text-dark-text-secondary">Inicio de Salto / Destierro</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <div className="w-3 h-3 rounded bg-green-500"></div>
              <span className="text-dark-text-secondary">Conectado Exitosamente</span>
            </div>
          </div>

          {/* Zonas de Señal */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-dark-text-muted uppercase tracking-wider mb-2">Zonas de Calidad</p>
            <div className="flex items-center gap-2 text-xs">
              <div className="w-3 h-3 rounded bg-blue-500/20 border border-blue-500/30"></div>
              <span className="text-dark-text-secondary"><strong>&gt; -65 dBm:</strong> Estabilidad</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <div className="w-3 h-3 rounded bg-yellow-500/20 border border-yellow-500/30"></div>
              <span className="text-dark-text-secondary"><strong>-65 a -75 dBm:</strong> Zona de Steering</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <div className="w-3 h-3 rounded bg-red-500/20 border border-red-500/30"></div>
              <span className="text-dark-text-secondary"><strong>&lt; -80 dBm:</strong> Crítica</span>
            </div>
          </div>

          {/* Interpretación */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-dark-text-muted uppercase tracking-wider mb-2">Interpretación</p>
            <div className="text-xs text-dark-text-secondary leading-relaxed">
              <p className="mb-1">Los marcadores muestran eventos clave del proceso de steering.</p>
              <p>Una secuencia <span className="text-red-400 font-semibold">rojo</span> → <span className="text-green-400 font-semibold">verde</span> indica un salto exitoso entre bandas.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default BandSteeringChart
