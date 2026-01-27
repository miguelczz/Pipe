import React, { useMemo } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import annotationPlugin from 'chartjs-plugin-annotation'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  annotationPlugin
)

// Códigos de estado BTM (802.11v) para descripciones legibles
const BTM_STATUS_CODES = {
  0: { label: 'Aceptada', desc: 'Cliente aceptó la transición', color: '#10b981' }, // Green
  1: { label: 'Rechazada', desc: 'Razón no especificada', color: '#ef4444' }, // Red
  2: { label: 'Rechazada', desc: 'Beacons insuficientes', color: '#ef4444' },
  3: { label: 'Rechazada', desc: 'Capacidad insuficiente', color: '#ef4444' },
  4: { label: 'Rechazada', desc: 'Terminación no deseada', color: '#ef4444' },
  5: { label: 'Rechazada', desc: 'Retraso solicitado', color: '#ef4444' },
  6: { label: 'Rechazada', desc: 'Lista de candidatos provista', color: '#ef4444' },
  7: { label: 'Rechazada', desc: 'Sin candidatos aptos', color: '#ef4444' },
  8: { label: 'Rechazada', desc: 'Saliendo del ESS', color: '#ef4444' }
}

export function BandSteeringChart({ btmEvents = [], transitions = [], signalSamples = [], rawStats = {} }) {
  
  // Umbral visual de steering (típicamente entre -65 y -75 dBm)
  // Usaremos -70 dBm como referencia estándar visual si no hay config
  const STEERING_THRESHOLD = -70

  const chartData = useMemo(() => {
    if (!signalSamples?.length) return { datasets: [] }

    // 1. Procesamiento de Señal
    let rawData = signalSamples
      .map(s => ({
        timestamp: new Date(s.timestamp).getTime(),
        rssi: Number(s.rssi),
        band: s.band || 'unknown'
      }))
      .filter(d => !isNaN(d.timestamp) && !isNaN(d.rssi))
      .sort((a, b) => a.timestamp - b.timestamp)

    if (rawData.length === 0) return { datasets: [] }

    const startTime = rawData[0].timestamp
    
    // Normalizar tiempo a segundos relativos
    const normalizeTime = (t) => parseFloat(((t - startTime) / 1000).toFixed(2))

    // Separar series por banda para colorear la línea
    const data24 = [] // Banda 2.4 GHz
    const data5 = []  // Banda 5 GHz
    
    // Diccionario para buscar RSSI por tiempo aproximado (para situar los marcadores verticalmente)
    const timeToRssi = {}

    rawData.forEach(d => {
      const x = normalizeTime(d.timestamp)
      const point = { x, y: d.rssi }
      
      // Guardar referencia de RSSI para usar en eventos cercanos
      // Usamos toFixed(0) como clave simple para agrupar segundos
      timeToRssi[Math.round(x)] = d.rssi

      if (d.band.includes('5')) {
        data24.push({ x, y: null }) // Hueco
        data5.push(point)
      } else {
        data24.push(point)
        data5.push({ x, y: null }) // Hueco
      }
    })

    // 2. Procesamiento de Eventos (BTM y Transiciones)
    const markers = []

    const findCloseRssi = (eventTimeRel) => {
      // Intentar encontrar el RSSI más cercano temporalmente
      const t = Math.round(eventTimeRel)
      // Buscar en un radio de 5 segundos
      for (let offset = 0; offset <= 5; offset++) {
        if (timeToRssi[t + offset] !== undefined) return timeToRssi[t + offset]
        if (timeToRssi[t - offset] !== undefined) return timeToRssi[t - offset]
      }
      return -60 // Default si no encuentra
    }

    // A. Eventos BTM
    btmEvents?.forEach(e => {
      const tRel = normalizeTime(new Date(e.timestamp).getTime())
      if (tRel < 0) return

      const isRequest = e.event_type === 'request'
      const statusInfo = !isRequest ? (BTM_STATUS_CODES[e.status_code] || { label: 'Desconocido', color: '#9ca3af' }) : null
      
      // Posición Y: Ajustar ligeramente para que no se solapen
      // Request un poco más arriba, Response sobre la línea o abajo
      const baseRssi = findCloseRssi(tRel)
      const y = isRequest ? baseRssi + 2 : baseRssi - 2

      markers.push({
        x: tRel,
        y: y,
        type: 'btm',
        subType: isRequest ? 'request' : 'response',
        label: isRequest ? 'Solicitud AP (BTM Request)' : `Respuesta Cliente: ${statusInfo?.label}`,
        description: isRequest ? 'AP sugiere cambio de banda' : statusInfo?.desc,
        color: isRequest ? '#f59e0b' : statusInfo?.color, // Ambar para Request, Color estado para Response
        shape: isRequest ? 'triangle' : 'circle',
        rotation: isRequest ? 180 : 0, // Triángulo hacia abajo indicando "Input" del AP
        radius: 8,
        borderWidth: 2
      })
    })

    // B. Transiciones (Roaming/Steering éxitos o fallos)
    transitions?.forEach(t => {
      const tStart = normalizeTime(new Date(t.start_time).getTime())
      if (tStart < 0) return

      const isSuccess = t.is_successful
      const y = findCloseRssi(tStart)

      markers.push({
        x: tStart,
        y: y,
        type: 'transition',
        subType: t.steering_type,
        label: isSuccess ? 'Transición Exitosa' : 'Intento Fallido',
        description: `De ${t.from_band || '?'} a ${t.to_band || '?'} (${t.steering_type})`,
        color: isSuccess ? '#10b981' : '#ef4444', 
        shape: 'rectRounded',
        radius: 10,
        rotation: 0,
        borderWidth: 2
      })
    })

    return {
      datasets: [
        // Marker Dataset (Debe ir encima visualmente, así que al final del array en Chart.js standard, 
        // pero con order menor se pinta encima? No, last in array = top layer)
        {
          type: 'scatter',
          label: 'Eventos',
          data: markers,
          backgroundColor: (ctx) => ctx.raw?.color || '#fff',
          borderColor: '#fff',
          borderWidth: 2,
          pointStyle: (ctx) => ctx.raw?.shape || 'circle',
          pointRadius: (ctx) => ctx.raw?.radius || 6,
          pointRotation: (ctx) => ctx.raw?.rotation || 0,
          order: 0 // Top layer
        },
        // 5 GHz Line
        {
          label: '5 GHz (Activo)',
          data: data5,
          borderColor: '#10b981', // Emerald 500
          backgroundColor: 'rgba(16, 185, 129, 0.1)',
          borderWidth: 2,
          tension: 0.3,
          fill: false, // No llenar individualmente para no ensuciar
          spanGaps: true,
          pointRadius: 0,
          order: 1
        },
        // 2.4 GHz Line
        {
          label: '2.4 GHz (Activo)',
          data: data24,
          borderColor: '#3b82f6', // Blue 500
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          borderWidth: 2,
          tension: 0.3,
          fill: false,
          spanGaps: true,
          pointRadius: 0,
          order: 2
        }
      ]
    }
  }, [signalSamples, btmEvents, transitions])

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'nearest',
      axis: 'x',
      intersect: false
    },
    scales: {
      x: {
        type: 'linear',
        title: { display: true, text: 'Tiempo (segundos)', color: '#6b7280' },
        grid: { color: 'rgba(255,255,255,0.05)' },
        ticks: { color: '#9ca3af' }
      },
      y: {
        min: -95,
        max: -30,
        title: { display: true, text: 'RSSI (dBm)', color: '#6b7280' },
        grid: { color: 'rgba(255,255,255,0.05)' },
        ticks: { color: '#9ca3af' }
      }
    },
    plugins: {
      tooltip: {
        backgroundColor: 'rgba(17, 24, 39, 0.9)',
        titleColor: '#f3f4f6',
        bodyColor: '#d1d5db',
        padding: 12,
        borderColor: 'rgba(255,255,255,0.1)',
        borderWidth: 1,
        callbacks: {
          label: (ctx) => {
            const raw = ctx.raw
            // Tooltip para marcadores
            if (raw.type) {
              return [
                `${raw.label}`,
                `${raw.description}`
              ]
            }
            // Tooltip para líneas de señal
            return `${ctx.dataset.label}: ${raw.y} dBm`
          }
        }
      },
      legend: {
        position: 'top',
        labels: { color: '#e5e7eb', usePointStyle: true, boxWidth: 8 }
      },
      annotation: {
        annotations: {
          // Línea divisoria de Steering (Threshold) - MÁS PROMINENTE
          steeringThreshold: {
            type: 'line',
            yMin: -70,
            yMax: -70,
            borderColor: 'rgba(255, 255, 255, 0.6)',
            borderWidth: 2,
            borderDash: [8, 4],
            label: {
              display: true,
              content: 'DIVISIÓN DE BANDAS (-70 dBm)',
              position: 'center',
              color: '#fff',
              backgroundColor: 'rgba(30, 41, 59, 0.8)',
              font: { size: 10, weight: 'bold' },
              padding: 4,
              borderRadius: 4
            }
          },
          // Zona 5GHz (Indicador visual superior)
          label5G: {
            type: 'label',
            xValue: 2, 
            yValue: -45,
            content: ['ZONA 5 GHz', '(Prioridad)'],
            color: '#10b981', 
            font: { size: 12, weight: 'bold' },
            position: 'start',
            textAlign: 'left'
          },
          // Zona 2.4GHz (Indicador visual inferior)
          label24G: {
            type: 'label',
            xValue: 2,
            yValue: -85,
            content: ['ZONA 2.4 GHz', '(Cobertura)'],
            color: '#3b82f6', 
            font: { size: 12, weight: 'bold' },
            position: 'start',
            textAlign: 'left'
          }
        }
      }
    }
  }

  if (!chartData.datasets.length) {
    return (
      <div className="h-[300px] flex flex-col items-center justify-center text-gray-500 bg-slate-900/50 rounded-xl border border-slate-800">
        <p>Esperando datos de señal...</p>
        <span className="text-xs opacity-50 mt-2">No se encontraron muestras RSSI en la captura</span>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Contenedor Gráfica */}
      <div className="h-[450px] bg-slate-900/50 rounded-xl p-4 border border-slate-800 relative">
        {/* Fondo sutil degradado para indicar zonas (CSS puro para performance) */}
        <div className="absolute inset-0 pointer-events-none rounded-xl overflow-hidden opacity-10">
          <div className="w-full h-[55%] bg-emerald-500/30 border-b border-white/20"></div> {/* Parte superior 5G */}
          <div className="w-full h-[45%] bg-blue-500/30"></div>    {/* Parte inferior 2.4G */}
        </div>
        
        <Line data={chartData} options={options} />
      </div>

      {/* Leyenda Personalizada Descriptiva */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
        
        {/* Guía de Bandas */}
        <div className="bg-slate-800/30 p-3 rounded-lg border border-slate-700/50 space-y-2">
          <p className="font-semibold text-gray-300 mb-1 border-b border-slate-700 pb-1">Comportamiento Esperado</p>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            <span className="text-gray-400">
              <strong className="text-gray-300">5 GHz:</strong> Prioridad para alto rendimiento. 
              Ideal cuando RSSI &gt; -70 dBm.
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-500"></span>
            <span className="text-gray-400">
              <strong className="text-gray-300">2.4 GHz:</strong> Cobertura extendida. 
              Fallback cuando señal &lt; -70 dBm.
            </span>
          </div>
        </div>

        {/* Guía de Eventos BTM */}
        <div className="bg-slate-800/30 p-3 rounded-lg border border-slate-700/50 space-y-2">
          <p className="font-semibold text-gray-300 mb-1 border-b border-slate-700 pb-1">Leyenda de Eventos</p>
          <div className="flex items-center gap-2">
            <div className="w-0 h-0 border-l-[5px] border-l-transparent border-r-[5px] border-r-transparent border-t-[8px] border-t-amber-500"></div>
            <span className="text-gray-400">
              <strong className="text-amber-500">Solicitud AP:</strong> El router sugiere cambiar de banda (BTM Request).
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-500"></div>
            <span className="text-gray-400">
              <strong className="text-green-500">Aceptada:</strong> El dispositivo obedece el cambio.
            </span>
            <div className="w-2 h-2 rounded-full bg-red-500 ml-2"></div>
            <span className="text-gray-400">
              <strong className="text-red-500">Rechazada:</strong> El dispositivo ignora la sugerencia.
            </span>
          </div>
        </div>

      </div>
    </div>
  )
}

export default BandSteeringChart