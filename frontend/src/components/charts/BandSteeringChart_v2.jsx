import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  ScatterController
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import annotationPlugin from 'chartjs-plugin-annotation'
import { ShieldAlert } from 'lucide-react'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ScatterController,
  Title,
  Tooltip,
  Legend,
  Filler,
  annotationPlugin
)

// Códigos de estado BTM (802.11v) para descripciones legibles
const BTM_STATUS_CODES = {
  0: { label: 'Aceptada', desc: 'Cliente aceptó la transición', color: '#10b981' }, 
  1: { label: 'Rechazada', desc: 'Razón no especificada', color: '#ef4444' }, 
  2: { label: 'Rechazada', desc: 'Beacons insuficientes', color: '#ef4444' },
  3: { label: 'Rechazada', desc: 'Capacidad insuficiente', color: '#ef4444' },
  4: { label: 'Rechazada', desc: 'Terminación no deseada', color: '#ef4444' },
  5: { label: 'Rechazada', desc: 'Retraso solicitado', color: '#ef4444' },
  6: { label: 'Rechazada', desc: 'Lista de candidatos provista', color: '#ef4444' },
  7: { label: 'Rechazada', desc: 'Sin candidatos aptos', color: '#ef4444' },
  8: { label: 'Rechazada', desc: 'Saliendo del ESS', color: '#ef4444' }
}

export function BandSteeringChart({ btmEvents = [], transitions = [], signalSamples = [], rawStats = {} }) {
  // Estados para toggles de visualización
  const [showBTMEvents, setShowBTMEvents] = useState(true)
  const [showTransitions, setShowTransitions] = useState(true)
  const [showRSSIThresholds, setShowRSSIThresholds] = useState(true)
  const [showBandZones, setShowBandZones] = useState(true)
  const chartRef = useRef(null)


  // Resumen compacto para la tabla/leyenda inferior (sincronizado con métricas globales)
  const steeringSummary = useMemo(() => {
    const sa = rawStats?.steering_analysis || {}
    const wiresharkBtm = rawStats?.diagnostics?.wireshark_raw?.summary?.btm || {}

    // Función auxiliar para normalizar bandas (debe ser la misma que usamos en el chartData)
    const normalizeBand = (band) => {
      if (!band) return null
      const bandStr = band.toString().toLowerCase()
      if (bandStr.includes('5')) return '5GHz'
      if (bandStr.includes('2.4') || bandStr.includes('2,4')) return '2.4GHz'
      return band
    }

    // Las métricas agregadas de steering (attempts / successful) vienen del
    // backend ya sincronizadas con `wireshark_raw.summary`. La UI no debe
    // recontar estos valores; sólo puede derivar vistas adicionales como
    // “cuántas de esas transiciones exitosas implicaron cambio de banda”.
    const attempts = sa.steering_attempts ?? 0
    const successful = sa.successful_transitions ?? 0

    const successfulTransitions = (transitions || []).filter(t => t.is_successful).length
    
    // Calcular cambios de banda solo como métrica derivada visual
    const bandChangeTransitions = (transitions || []).filter(t => {
      if (!t.is_successful) return false
      const fromBandNorm = normalizeBand(t.from_band)
      const toBandNorm = normalizeBand(t.to_band)
      return fromBandNorm && toBandNorm && fromBandNorm !== toBandNorm
    }).length

    return {
      attempts,
      successful,
      bandChanges: bandChangeTransitions,
      transitionSuccess: successfulTransitions,
      btmRequests: wiresharkBtm.requests ?? 0,
      btmAccept: wiresharkBtm.responses_accept ?? 0
    }
  }, [rawStats, transitions])
  
  const chartData = useMemo(() => {
    // -------------------------------------------------------------------------
    // 1. PROCESAMIENTO Y SUAVIZADO DE SEÑAL
    // -------------------------------------------------------------------------
    
    // Función para detectar si son ms o segundos y normalizar a MS
    const toMs = (ts) => (Number(ts) < 10000000000 ? Number(ts) * 1000 : Number(ts))

    // Declarar rawSamples una sola vez
    let rawSamples

    // Si no hay signalSamples, crear timeline desde eventos
    if (!signalSamples?.length) {
      // Crear puntos mínimos desde eventos BTM y transiciones
      const eventTimestamps = [
        ...btmEvents.map(e => toMs(e.timestamp)),
        ...transitions.map(t => toMs(t.start_time))
      ].filter(ts => ts && ts > 0).sort((a, b) => a - b)
      
      if (eventTimestamps.length === 0) {
        return { datasets: [], bandZones: [], xMax: 0 }
      }
      
      // Crear timeline mínimo para mostrar eventos
      const syntheticStartTime = eventTimestamps[0]
      const syntheticEndTime = eventTimestamps[eventTimestamps.length - 1]
      const syntheticDuration = syntheticEndTime - syntheticStartTime
      
      // Asegurar un mínimo de duración para la gráfica
      const minDuration = 5000 // 5 segundos mínimo
      const finalEndTime = syntheticDuration < minDuration 
        ? syntheticStartTime + minDuration 
        : syntheticEndTime
      
      // Crear puntos sintéticos para la línea de señal (RSSI promedio -60 dBm)
      // Dividir en ventanas de 1 segundo, pero asegurar que cubran todo el rango
      const syntheticSamples = []
      const SYNTHETIC_WINDOW_MS = 1000
      let currentTime = syntheticStartTime
      
      // Asegurar que siempre haya al menos algunos puntos
      const totalDuration = finalEndTime - syntheticStartTime
      const numPoints = Math.max(5, Math.ceil(totalDuration / SYNTHETIC_WINDOW_MS))
      const step = totalDuration / numPoints
      
      while (currentTime <= finalEndTime) {
        syntheticSamples.push({
          ts: Math.round(currentTime), // Redondear para evitar problemas de precisión
          rssi: -60, // RSSI promedio por defecto
          band: '2.4GHz' // Banda por defecto
        })
        currentTime += step
      }
      
      // Asegurar que el último punto esté incluido
      if (syntheticSamples.length === 0 || syntheticSamples[syntheticSamples.length - 1].ts < finalEndTime) {
        syntheticSamples.push({
          ts: Math.round(finalEndTime),
          rssi: -60,
          band: '2.4GHz'
        })
      }
      
      // Usar muestras sintéticas para continuar con el flujo normal
      rawSamples = syntheticSamples
    } else {
      // Ordenar muestras por tiempo real
      const processedSamples = [...signalSamples]
        .filter(s => s.rssi && s.timestamp)
        .map(s => ({
          ts: toMs(s.timestamp),
          rssi: Number(s.rssi),
          band: (s.band || '').toString()
        }))
        .sort((a, b) => a.ts - b.ts)

      if (processedSamples.length === 0) {
        return { datasets: [], bandZones: [], xMax: 0 }
      }
      
      rawSamples = processedSamples
    }

    // Validar que rawSamples tenga datos
    if (!rawSamples || rawSamples.length === 0) {
      console.error('BandSteeringChart: rawSamples está vacío después del procesamiento')
      return { datasets: [], bandZones: [], xMax: 0 }
    }

    const startTime = rawSamples[0].ts
    const endTime = rawSamples[rawSamples.length - 1].ts
    const totalDuration = endTime - startTime
    
    console.log('BandSteeringChart: Timeline calculado', {
      startTime,
      endTime,
      totalDuration,
      rawSamplesCount: rawSamples.length
    })

    // Determinar ventana de suavizado dinámicamente (aumentada para más suavizado)
    const WINDOW_SIZE_MS = totalDuration > 60000 ? 2000 : 1000 

    // -------------------------------------------------------------------------
    // CALCULAR ESTADO LÓGICO DE LA BANDA (State Machine)
    // -------------------------------------------------------------------------
    const stateChanges = []
    
    // 1. Agregar cambios por Respuestas BTM Exitosas
    btmEvents.forEach(e => {
        if (e.event_type === 'response' && e.status_code === 0) {
            stateChanges.push({ ts: toMs(e.timestamp), band: e.band })
        }
    })

    // 2. Agregar cambios por Transiciones Reales
    transitions.forEach(t => {
        // CUALQUIER transición exitosa nos confirma en qué banda está el dispositivo.
        // Incluso si es 5GHz -> 5GHz, nos confirma que está en 5GHz.
        // Usamos esto para corregir el color de la línea.
        if (t.is_successful && t.to_band) {
            stateChanges.push({ ts: toMs(t.start_time), band: t.to_band })
        }
    })

    stateChanges.sort((a,b) => a.ts - b.ts)

    // Función para obtener la banda lógica en un momento dado
    const getLogicalBand = (currentTs, rawBand) => {
        // Buscar el último cambio de estado válido ANTES de este momento
        const lastChange = stateChanges.filter(c => c.ts <= currentTs).pop()
        
        // Si hubo un cambio de estado EXITOSO reciente (ej. en los últimos 5 segundos),
        // le hacemos caso ciegamente para mostrar el éxito visualmente.
        // PERO después, volvemos a confiar en los datos crudos para ver si se cayó o cambió.
        if (lastChange && (currentTs - lastChange.ts) < 5000) {
            return lastChange.band
        }
        
        // Si no hay evento reciente mandatorio, somos fieles a lo que dicen los paquetes (Realidad)
        return rawBand
    }

    const smoothedPoints = []
    let currentWindowStart = startTime

    while (currentWindowStart <= endTime) {
      const windowEnd = currentWindowStart + WINDOW_SIZE_MS
      // Incluir muestras que estén en el rango [currentWindowStart, windowEnd)
      // Usar <= en lugar de < para windowEnd para incluir el último punto
      const bucket = rawSamples.filter(s => s.ts >= currentWindowStart && s.ts <= windowEnd)

      if (bucket.length > 0) {
        const avgRssi = bucket.reduce((sum, s) => sum + s.rssi, 0) / bucket.length
        
        // Banda Dominante Cruda
        const bandCounts = bucket.reduce((acc, s) => {
          const b = s.band.includes('5') ? '5GHz' : '2.4GHz'
          acc[b] = (acc[b] || 0) + 1
          return acc
        }, {})
        const rawDominant = (bandCounts['5GHz'] || 0) >= (bandCounts['2.4GHz'] || 0) ? '5GHz' : '2.4GHz'

        // Decisión Final: Lógica vs Cruda
        const logicalBand = getLogicalBand(currentWindowStart, rawDominant)
        const finalBand = logicalBand.includes('5') ? '5GHz' : '2.4GHz'

        smoothedPoints.push({
          x: parseFloat(((currentWindowStart - startTime) / 1000).toFixed(2)),
          y: Math.round(avgRssi * 10) / 10,
          band: finalBand,
          count: bucket.length 
        })
      }
      currentWindowStart += WINDOW_SIZE_MS
    }

    // 1b. SUAVIZADO SECUNDARIO (Gaussiano de 7 puntos - Más suavizado)
    // Si no hay puntos suavizados, crear puntos mínimos desde rawSamples
    let finalPoints = []
    if (smoothedPoints.length > 0) {
      finalPoints = smoothedPoints.map((p, i, arr) => {
        // Tomamos vecinos más lejanos para una curva más "cremosa"
        const p3_prev = arr[i - 3] || arr[i - 2] || arr[i - 1] || p
        const p2_prev = arr[i - 2] || arr[i - 1] || p
        const p1_prev = arr[i - 1] || p
        const p1_next = arr[i + 1] || p
        const p2_next = arr[i + 2] || arr[i + 1] || p
        const p3_next = arr[i + 3] || arr[i + 2] || arr[i + 1] || p
        
        // Peso gaussiano extendido: 1-2-4-6-4-2-1 (más peso al centro)
        const weightedAvg = (
          p3_prev.y + 
          (p2_prev.y * 2) + 
          (p1_prev.y * 4) + 
          (p.y * 6) + 
          (p1_next.y * 4) + 
          (p2_next.y * 2) + 
          p3_next.y
        ) / 20
        return { ...p, y: Number(weightedAvg.toFixed(2)) }
      })
    } else if (rawSamples.length > 0) {
      // Fallback: crear puntos mínimos desde rawSamples si smoothedPoints está vacío
      // Esto puede pasar si los buckets no coinciden exactamente con las muestras sintéticas
      finalPoints = rawSamples.map((s) => ({
        x: parseFloat(((s.ts - startTime) / 1000).toFixed(2)),
        y: s.rssi,
        band: s.band && s.band.includes('5') ? '5GHz' : '2.4GHz',
        count: 1
      }))
    }

    // -------------------------------------------------------------------------
    // 2. PROCESAMIENTO DE EVENTOS
    // -------------------------------------------------------------------------
    const normalizeTime = (tsRaw) => parseFloat(((toMs(tsRaw) - startTime) / 1000).toFixed(2))
    
    // Función auxiliar para normalizar bandas (disponible en todo el scope)
    const normalizeBand = (band) => {
      if (!band) return null
      const bandStr = band.toString().toLowerCase()
      if (bandStr.includes('5')) return '5GHz'
      if (bandStr.includes('2.4') || bandStr.includes('2,4')) return '2.4GHz'
      return band
    }

    // Función para encontrar el RSSI PROMEDIO más cercano al evento
    const findRssiAt = (evTimeNormalized) => {
      // Si no hay puntos, retornar RSSI por defecto
      if (!finalPoints || finalPoints.length === 0) {
        return -60
      }
      // Buscar en los puntos finales ya suavizados
      const closest = finalPoints.reduce((prev, curr) => {
        return (Math.abs(curr.x - evTimeNormalized) < Math.abs(prev.x - evTimeNormalized) ? curr : prev)
      }, finalPoints[0])
      return closest ? closest.y : -60
    }

    const markers = []

    // Filtrar eventos según toggles
    const filteredBTMEvents = showBTMEvents ? (btmEvents || []) : []
    const filteredTransitions = showTransitions ? (transitions || []) : []

    filteredBTMEvents.forEach(e => {
      if (!e || !e.timestamp) return
      let tRel = normalizeTime(e.timestamp)
      // Clampear eventos anteriores al inicio para que se vean al inicio del eje X
      if (tRel < 0) tRel = 0
      // Filtrar eventos muy fuera del rango final de la gráfica (solo si hay puntos)
      if (finalPoints.length > 0 && tRel > finalPoints[finalPoints.length-1].x + 5) return
      // Si no hay puntos pero hay eventos, incluirlos de todas formas 

      const yPos = findRssiAt(tRel) // Poner marcador sobre la línea suavizada
      const isRequest = e.event_type === 'request'
      const isSuccess = !isRequest && e.status_code === 0
      
      const statusInfo = !isRequest 
        ? (BTM_STATUS_CODES[e.status_code] || { label: `Código ${e.status_code}`, desc: 'Estado desconocido', color: '#9ca3af' }) 
        : null
      
      // SI ES UN ÉXITO DE BTM, LO TRATAMOS COMO EL "ROAMING COMPLETADO" VISUALMENTE
      // Esto resuelve el caso donde la "Transición" no se reporta pero el BTM sí.
      
      markers.push({
        x: tRel,
        y: yPos,
        type: 'btm',
        // Títulos y descripciones técnicas precisas
        label: isRequest 
          ? 'BTM Request (Enviado por AP)' 
          : (isSuccess ? 'Roaming Completado (vía BTM)' : 'BTM Response (Enviado por Cliente)'),
        description: isRequest 
          ? 'AP sugiere transición mediante gestión 802.11v' 
          : `Decisión: ${statusInfo?.label?.toUpperCase()} - ${statusInfo?.desc}`,
        color: isRequest ? '#f59e0b' : (isSuccess ? '#10b981' : '#ef4444'),
        
        // FORMAS: Requests (triángulo amarillo), Responses éxito (círculo verde), Responses fallo (rombo rojo)
        shape: isRequest ? 'triangle' : (isSuccess ? 'circle' : 'rectRot'), 
        rotation: isRequest ? 180 : 45,
        radius: isRequest ? 7 : (isSuccess ? 7 : 6),
        borderWidth: 2,
        borderColor: isRequest ? '#854d0e' : (isSuccess ? '#fff' : '#ef4444'),
        backgroundColor: isRequest ? '#f59e0b' : (isSuccess ? '#10b981' : 'rgba(239, 68, 68, 0.2)')
      })
    })

    filteredTransitions.forEach(t => {
      if (!t || !t.start_time) return
      // Normalizar bandas para comparación consistente (función ya definida arriba)
      const fromBandNorm = normalizeBand(t.from_band)
      const toBandNorm = normalizeBand(t.to_band)
      
      // Analizar si hubo cambio real de banda (comparando bandas normalizadas)
      const isBandChange = fromBandNorm && toBandNorm && fromBandNorm !== toBandNorm
      const tRel = normalizeTime(t.start_time)
      const yPos = findRssiAt(tRel)

      // CRITERIO SINCRONIZADO CON COMPLIANCE CHECKS (versión visual):
      // Consideramos "steering efectivo" solo cuando:
      // - Hay cambio de banda, o
      // - Hay cambio de BSSID con éxito.
      const hasBssidChange =
        t.is_successful &&
        t.from_bssid &&
        t.to_bssid &&
        t.from_bssid !== t.to_bssid

      const isEffectiveSuccess = t.is_successful && (isBandChange || hasBssidChange)
      
      const label = isEffectiveSuccess
        ? (isBandChange ? 'Roaming Completado (Cambio de Banda)' : 'Roaming Completado (Entre BSSIDs)')
        : (t.is_successful ? 'Transición de Asociación (sin cambio de banda/BSSID)' : 'Intento Fallido')

      markers.push({
        x: tRel, y: yPos,
        type: 'transition',
        label: label,
        description: `Transición: ${fromBandNorm || t.from_band || '?'} ➡ ${toBandNorm || t.to_band || '?'} (${t.steering_type})`,
        
        // Color: VERDE solo si es steering efectivo, NARANJA llamativo para reassoc "normal",
        // ROJO si falló.
        color: isEffectiveSuccess ? '#10b981' : (t.is_successful ? '#f97316' : '#ef4444'),
        
        // Forma: Cuadrado para steering efectivo, rombo naranja grande para transiciones neutras,
        // círculo rojo para fallos.
        shape: isEffectiveSuccess ? 'rect' : (t.is_successful ? 'rectRot' : 'circle'),
        radius: isEffectiveSuccess ? 7 : 7,
        borderWidth: 2,
        borderColor: isEffectiveSuccess ? '#fff' : (t.is_successful ? '#f97316' : '#ef4444'),
        backgroundColor: isEffectiveSuccess ? '#10b981' : (t.is_successful ? 'rgba(249,115,22,0.95)' : 'rgba(239, 68, 68, 0.8)')
      })
    })

    // -------------------------------------------------------------------------
    // 3. AGRUPACIÓN VISUAL INTELIGENTE (Smart Clustering)
    // -------------------------------------------------------------------------
    // NOTA: desactivamos el clustering agresivo para que el usuario siempre
    // pueda ver TODOS los eventos (BTM Request/Response y transiciones),
    // incluso cuando ocurren muy cerca en el tiempo. Esto hace más densa la
    // gráfica, pero evita que un éxito visual oculte un Request importante.
    const clusteredMarkers = markers.sort((a, b) => a.x - b.x)

    // -------------------------------------------------------------------------
    // 4. GENERAR ZONAS DE BANDA EN EL TIEMPO (Background bands)
    // -------------------------------------------------------------------------
    // MEJORA: Usar transiciones con cambio de banda para determinar zonas,
    // no solo las muestras de RSSI (que pueden no tener frecuencia en el momento del cambio)
    const bandZones = []
    
    // Primero: construir zonas desde transiciones con cambio de banda
    const transitionBandChanges = []
    transitions.forEach(t => {
      if (t.is_successful && t.is_band_change && t.from_band && t.to_band) {
        const tRel = normalizeTime(t.start_time)
        transitionBandChanges.push({
          time: tRel,
          fromBand: normalizeBand(t.from_band),
          toBand: normalizeBand(t.to_band)
        })
      }
    })
    transitionBandChanges.sort((a, b) => a.time - b.time)
    
    // Si hay cambios de banda en transiciones, usarlos para crear zonas
    if (transitionBandChanges.length > 0 && finalPoints.length > 0) {
      let currentBand = finalPoints[0]?.band || '2.4GHz'
      let zoneStart = 0
      
      for (const change of transitionBandChanges) {
        // Cerrar zona anterior
        if (zoneStart < change.time) {
          bandZones.push({
            band: currentBand,
            xStart: zoneStart,
            xEnd: change.time,
            yMin: -90,
            yMax: -40
          })
        }
        // Iniciar nueva zona con la banda destino
        currentBand = change.toBand
        zoneStart = change.time
      }
      
      // Cerrar última zona hasta el final
      const lastX = finalPoints[finalPoints.length - 1]?.x || 0
      if (zoneStart < lastX) {
        bandZones.push({
          band: currentBand,
          xStart: zoneStart,
          xEnd: lastX,
          yMin: -90,
          yMax: -40
        })
      }
    } else if (finalPoints.length > 0) {
      // Fallback: usar solo puntos de RSSI si no hay transiciones con cambio de banda
      let currentZone = null
      for (let i = 0; i < finalPoints.length; i++) {
        const point = finalPoints[i]
        const band = point.band || '2.4GHz'
        const xStart = point.x
        const xEnd = i < finalPoints.length - 1 ? finalPoints[i + 1].x : point.x
        
        if (!currentZone || currentZone.band !== band) {
          if (currentZone) {
            currentZone.xEnd = xStart
            bandZones.push(currentZone)
          }
          currentZone = {
            band: band,
            xStart: xStart,
            xEnd: xEnd,
            yMin: -90,
            yMax: -40
          }
        } else {
          currentZone.xEnd = xEnd
        }
      }
      if (currentZone) {
        bandZones.push(currentZone)
      }
    }

    // Asegurar que siempre haya al menos un dataset con datos para que Chart.js renderice
    const hasEvents = clusteredMarkers.length > 0
    const hasSignalData = finalPoints.length > 0
    
    const datasets = []
    
    // Dataset de eventos (siempre que haya eventos y estén habilitados)
    if (hasEvents && (showBTMEvents || showTransitions)) {
      datasets.push({
        type: 'scatter',
        label: 'Eventos',
        data: clusteredMarkers, 
        backgroundColor: (ctx) => ctx.raw?.color || '#fff',
        borderColor: (ctx) => ctx.raw?.borderColor || '#fff', 
        borderWidth: 1.5,
        pointStyle: (ctx) => ctx.raw?.shape || 'circle',
        pointRadius: (ctx) => ctx.raw?.radius || 4,
        pointRotation: (ctx) => ctx.raw?.rotation || 0,
        order: 0
      })
    }
    
    // Dataset de señal (solo si hay datos de señal)
    if (hasSignalData) {
      datasets.push({
        label: 'Señal Promedio',
        data: finalPoints, // Usamos data con doble suavizado
        borderWidth: 3,
        tension: 0.6, // Curva más suavizada y orgánica
        fill: false,
        pointRadius: 0,
        pointHoverRadius: 6,
        spanGaps: true,
        cubicInterpolationMode: 'monotone', // Suavizado cúbico monotónico para curvas más naturales
        segment: {
          borderColor: (ctx) => {
            const targetBand = ctx.p1.raw?.band || '';
            return targetBand.includes('5') ? '#10b981' : '#3b82f6';
          }
        },
        order: 1
      })
    } else if (hasEvents) {
      // Si no hay señal pero hay eventos, crear una línea base para el contexto visual
      // Usar el rango de tiempo de los eventos
      const eventTimes = clusteredMarkers.map(m => m.x).sort((a, b) => a - b)
      if (eventTimes.length > 0) {
        const minTime = eventTimes[0]
        const maxTime = eventTimes[eventTimes.length - 1]
        const timeRange = maxTime - minTime || 10 // Mínimo 10 segundos si no hay rango
        const baselinePoints = []
        for (let t = minTime; t <= maxTime + 5; t += Math.max(1, timeRange / 20)) {
          baselinePoints.push({ x: t, y: -60, band: '2.4GHz' })
        }
        datasets.push({
          label: 'Línea Base',
          data: baselinePoints,
          borderWidth: 2,
          borderColor: 'rgba(156, 163, 175, 0.3)',
          borderDash: [5, 5],
          pointRadius: 0,
          order: 1
        })
      }
    }

    // xMax para ajustar el eje temporal al rango real de la captura
    // Usar eventos si no hay puntos de señal
    let xMax = 0
    if (finalPoints.length > 0) {
      xMax = finalPoints[finalPoints.length - 1].x + 5
    } else if (clusteredMarkers.length > 0) {
      const eventTimes = clusteredMarkers.map(m => m.x).sort((a, b) => a - b)
      xMax = eventTimes[eventTimes.length - 1] + 5
    } else if (rawSamples.length > 0) {
      // Fallback: usar rawSamples si no hay nada más
      const lastSample = rawSamples[rawSamples.length - 1]
      xMax = parseFloat(((lastSample.ts - startTime) / 1000).toFixed(2)) + 5
    }

    // Debug: Log antes de retornar
    console.log('chartData useMemo returning:', {
      datasetsCount: datasets.length,
      datasetsInfo: datasets.map(d => ({ 
        label: d.label, 
        dataLength: Array.isArray(d.data) ? d.data.length : 0,
        type: d.type || 'line',
        firstDataPoint: Array.isArray(d.data) && d.data.length > 0 ? d.data[0] : null,
        lastDataPoint: Array.isArray(d.data) && d.data.length > 0 ? d.data[d.data.length - 1] : null
      })),
      xMax,
      bandZonesCount: bandZones.length,
      hasEvents: clusteredMarkers.length > 0,
      hasSignalData: finalPoints.length > 0,
      clusteredMarkersCount: clusteredMarkers.length,
      finalPointsCount: finalPoints.length
    })

    return {
      datasets,
      bandZones, // Zonas de banda para annotations dinámicas
      xMax
    }
  }, [signalSamples, btmEvents, transitions, showBTMEvents, showTransitions])

  const options = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'point',
      intersect: true,
    },
    scales: {
      x: {
        type: 'linear',
        title: { display: true, text: 'Tiempo (Segundos)', color: '#9ca3af', font: { size: 10 } },
        grid: { color: 'rgba(255,255,255,0.05)' },
        ticks: { color: '#9ca3af' },
        // Limitar el eje X al rango real de la captura para evitar zonas vacías artificiales
        max: chartData.xMax && chartData.xMax > 0 ? chartData.xMax : undefined
      },
      y: {
        min: -90, max: -40,
        title: { display: true, text: 'RSSI Promedio (dBm)', color: '#9ca3af', font: { size: 10 } },
        grid: { color: 'rgba(255,255,255,0.05)' },
        ticks: { color: '#9ca3af' }
      }
    },
    plugins: {
      tooltip: {
        backgroundColor: 'rgba(15, 23, 42, 0.95)',
        titleColor: '#f1f5f9',
        bodyColor: '#cbd5e1',
        padding: 10,
        borderColor: 'rgba(255,255,255,0.1)',
        borderWidth: 1,
        // Solo mostrar tooltips cuando el elemento tiene metadatos de evento (BTM / transición)
        filter: (ctx) => {
          if (!ctx || !ctx.raw) return false
          return !!ctx.raw.type
        },
        callbacks: {
          title: (items) => {
            if (!items || items.length === 0 || !items[0] || !items[0].parsed) {
              return 'Tiempo: N/A'
            }
            return `Tiempo: ${items[0].parsed.x.toFixed(2)}s`
          },
          label: (ctx) => {
            if (!ctx || !ctx.raw) return ''
            const raw = ctx.raw
            if (raw && raw.type) {
              return [
                `• ${raw.label || 'Evento'}`,
                raw.description ? `  ${raw.description}` : ''
              ].filter(Boolean)
            }
            // No mostrar tooltip para puntos de la línea de señal
            return ''
          }
        }
      },
      legend: { display: false },
      annotation: {
        annotations: (() => {
          const annotations = {}
          
          // Zonas de banda dinámicas (A)
          if (showBandZones && chartData.bandZones) {
            chartData.bandZones.forEach((zone, idx) => {
              const zoneId = `bandZone_${idx}`
              annotations[zoneId] = {
                type: 'box',
                xMin: zone.xStart,
                xMax: zone.xEnd,
                yMin: -90,
                yMax: -40,
                backgroundColor: zone.band.includes('5') 
                  ? 'rgba(16, 185, 129, 0.08)' 
                  : 'rgba(59, 130, 246, 0.08)',
                borderWidth: 0,
                drawTime: 'beforeDatasetsDraw'
              }
            })
          }
          
          // Umbrales RSSI (C)
          if (showRSSIThresholds) {
            // Umbral excelente (-67 dBm)
            annotations.rssi_excellent = {
              type: 'line',
              yMin: -67,
              yMax: -67,
              borderColor: 'rgba(16, 185, 129, 0.4)',
              borderWidth: 1,
              borderDash: [4, 4],
              label: {
                display: true,
                content: '',
                position: 'start',
                backgroundColor: 'rgba(16, 185, 129, 0.8)',
                color: '#fff',
                font: { size: 9 },
                xAdjust: 4,
                yAdjust: -6
              }
            }
            
            // Umbral límite (-70 dBm)
            annotations.rssi_threshold = {
              type: 'line',
              yMin: -70,
              yMax: -70,
              borderColor: 'rgba(255, 193, 7, 0.5)',
              borderWidth: 2,
              borderDash: [6, 4],
              label: {
                display: true,
                content: '',
                position: 'start',
                backgroundColor: 'rgba(255, 193, 7, 0.8)',
                color: '#000',
                font: { size: 9 },
                xAdjust: 4,
                yAdjust: -2
              }
            }
            
            // Umbral malo (-75 dBm)
            annotations.rssi_poor = {
              type: 'line',
              yMin: -75,
              yMax: -75,
              borderColor: 'rgba(239, 68, 68, 0.4)',
              borderWidth: 1,
              borderDash: [4, 4],
              label: {
                display: true,
                content: '',
                position: 'start',
                backgroundColor: 'rgba(239, 68, 68, 0.8)',
                color: '#fff',
                font: { size: 9 },
                xAdjust: 4,
                yAdjust: 2
              }
            }
            
            // Sombreado bajo -70 dBm (área de señal pobre)
            annotations.rssi_poor_area = {
              type: 'box',
              yMin: -90,
              yMax: -70,
              backgroundColor: 'rgba(239, 68, 68, 0.02)',
              borderWidth: 0,
              drawTime: 'beforeDatasetsDraw'
            }
          }
          
          return annotations
        })()
      }
    }
  }), [showBandZones, showRSSIThresholds, chartData.bandZones, chartData.xMax])

  // Solución robusta al bug de tooltip "pegado"
  // El problema ocurre cuando Chart.js no detecta correctamente que el mouse salió del área
  // o cuando hay eventos de mouse que no se propagan correctamente
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    const canvas = chart.canvas
    const container = canvas?.parentElement
    if (!canvas) return

    // Timeout para limpiar tooltip si no hay actividad
    let hideTimeout = null

    // Función para ocultar el tooltip de forma segura
    const hideTooltip = () => {
      if (chart && chart.tooltip) {
        try {
          // Limpiar elementos activos del tooltip
          chart.tooltip.setActiveElements([], { x: 0, y: 0 })
          // Actualizar sin animación para respuesta inmediata
          chart.update('none')
        } catch (e) {
          // Ignorar errores si el chart ya fue destruido
        }
      }
    }

    // Handler para cuando el mouse sale del canvas
    const handleCanvasLeave = () => {
      if (hideTimeout) {
        clearTimeout(hideTimeout)
        hideTimeout = null
      }
      // Ocultar inmediatamente al salir del canvas
      hideTooltip()
    }

    // Handler para cuando el mouse sale del contenedor completo
    // Esto captura casos donde el mouse sale rápidamente sin disparar mouseleave del canvas
    const handleContainerLeave = () => {
      if (hideTimeout) {
        clearTimeout(hideTimeout)
        hideTimeout = null
      }
      hideTooltip()
    }

    // Handler para mousemove - verificar si hay elementos activos
    const handleMouseMove = (e) => {
      if (!chart) return
      
      // Limpiar timeout anterior
      if (hideTimeout) {
        clearTimeout(hideTimeout)
        hideTimeout = null
      }

      // Obtener elementos bajo el cursor usando el evento nativo
      const elements = chart.getElementsAtEventForMode(e, 'point', { intersect: true }, true)
      
      // Si no hay elementos bajo el cursor, programar ocultar tooltip
      if (!elements || elements.length === 0) {
        hideTimeout = setTimeout(() => {
          // Verificar una última vez que no hay elementos activos
          if (chart && chart.tooltip) {
            const activeElements = chart.tooltip.getActiveElements()
            if (!activeElements || activeElements.length === 0) {
              hideTooltip()
            }
          }
        }, 200) // Delay de 200ms para evitar parpadeos pero asegurar limpieza
      }
    }

    // Agregar listeners al canvas y contenedor
    canvas.addEventListener('mouseleave', handleCanvasLeave)
    canvas.addEventListener('mousemove', handleMouseMove)
    if (container) {
      container.addEventListener('mouseleave', handleContainerLeave)
    }

    // Cleanup
    return () => {
      if (hideTimeout) {
        clearTimeout(hideTimeout)
      }
      canvas.removeEventListener('mouseleave', handleCanvasLeave)
      canvas.removeEventListener('mousemove', handleMouseMove)
      if (container) {
        container.removeEventListener('mouseleave', handleContainerLeave)
      }
    }
  }, [chartData]) // Re-ejecutar cuando cambien los datos del gráfico

  // Debug: Log para entender qué está pasando
  console.log('BandSteeringChart Debug:', {
    datasetsCount: chartData?.datasets?.length || 0,
    datasets: chartData?.datasets?.map(d => ({ 
      label: d.label, 
      dataLength: Array.isArray(d.data) ? d.data.length : 0,
      type: d.type || 'line'
    })) || [],
    btmEventsCount: btmEvents?.length || 0,
    transitionsCount: transitions?.length || 0,
    signalSamplesCount: signalSamples?.length || 0,
    xMax: chartData?.xMax || 0,
    showBTMEvents,
    showTransitions
  })

  if (!chartData?.datasets || chartData.datasets.length === 0) {
    // Mensajes específicos según qué datos faltan
    const hasBTMEvents = btmEvents?.length > 0
    const hasTransitions = transitions?.length > 0
    const hasSignalSamples = signalSamples?.length > 0
    
    let message = "No hay datos para mostrar"
    let suggestion = ""
    
    if (!hasSignalSamples && !hasBTMEvents && !hasTransitions) {
      message = "No se detectaron eventos en la captura"
      suggestion = "Verifica que la captura contenga tráfico 802.11 relacionado con band steering"
    } else if (!hasSignalSamples) {
      message = "No hay muestras de señal RSSI disponibles"
      suggestion = hasBTMEvents || hasTransitions 
        ? "La gráfica debería mostrar eventos BTM y transiciones, pero no se generaron datasets. Revisa la consola."
        : "Verifica que la captura incluya información de señal"
    } else {
      message = "Error: Hay datos pero no se generaron datasets"
      suggestion = "Revisa la consola del navegador para más detalles"
    }
    
    return (
      <div className="h-[300px] flex flex-col items-center justify-center text-gray-500 space-y-2">
        <p className="text-sm font-medium">{message}</p>
        {suggestion && <p className="text-xs text-gray-400">{suggestion}</p>}
        <p className="text-xs text-gray-500 mt-2">
          BTM: {hasBTMEvents ? btmEvents.length : 0} | 
          Transiciones: {hasTransitions ? transitions.length : 0} | 
          Señal: {hasSignalSamples ? signalSamples.length : 0}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Controles de Visualización */}
      <div className="flex flex-wrap gap-3 items-center bg-slate-800/40 p-3 rounded-lg border border-slate-700/50">
        <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider">Mostrar:</span>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={showBTMEvents}
            onChange={(e) => setShowBTMEvents(e.target.checked)}
            className="w-3.5 h-3.5 rounded border-slate-600 bg-slate-700 text-emerald-500 focus:ring-emerald-500"
          />
          <span className="text-xs text-gray-300">Eventos BTM</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={showTransitions}
            onChange={(e) => setShowTransitions(e.target.checked)}
            className="w-3.5 h-3.5 rounded border-slate-600 bg-slate-700 text-emerald-500 focus:ring-emerald-500"
          />
          <span className="text-xs text-gray-300">Transiciones</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={showBandZones}
            onChange={(e) => setShowBandZones(e.target.checked)}
            className="w-3.5 h-3.5 rounded border-slate-600 bg-slate-700 text-emerald-500 focus:ring-emerald-500"
          />
          <span className="text-xs text-gray-300">Zonas de Banda</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={showRSSIThresholds}
            onChange={(e) => setShowRSSIThresholds(e.target.checked)}
            className="w-3.5 h-3.5 rounded border-slate-600 bg-slate-700 text-emerald-500 focus:ring-emerald-500"
          />
          <span className="text-xs text-gray-300">Umbrales RSSI</span>
        </label>
      </div>
      
      <div className="h-[300px] bg-slate-900/50 rounded-xl p-4 border border-slate-800 shadow-xl relative">
        {(() => {
          // Validar que chartData tenga el formato correcto antes de renderizar
          const validData = {
            datasets: chartData.datasets.filter(d => {
              const hasData = Array.isArray(d.data) && d.data.length > 0
              if (!hasData) {
                console.warn(`Dataset "${d.label}" tiene datos vacíos, filtrando...`)
              }
              return hasData
            })
          }
          
          if (validData.datasets.length === 0) {
            return (
              <div className="h-full flex items-center justify-center text-gray-500">
                <p>No hay datos válidos para mostrar en la gráfica</p>
              </div>
            )
          }
          
          console.log('Rendering chart with data:', {
            datasetsCount: validData.datasets.length,
            datasets: validData.datasets.map(d => ({
              label: d.label,
              type: d.type || 'line',
              dataLength: d.data.length,
              firstPoint: d.data[0],
              lastPoint: d.data[d.data.length - 1]
            }))
          })
          
          return <Line ref={chartRef} data={validData} options={options} />
        })()}
      </div>


      {/* Tabla Explicativa Mejorada */}
      <div className="bg-dark-surface-primary rounded-xl border border-dark-border-primary p-4">
        <h4 className="text-sm font-semibold text-dark-text-primary mb-4 flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-dark-accent-primary" />
          Guía de Elementos Visuales
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Líneas de Señal */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-dark-text-muted uppercase tracking-wider mb-2">Líneas de Señal</p>
            <div className="space-y-1.5">
              <div className="flex items-center gap-2 text-xs">
                <div className="w-8 h-0.5 bg-blue-500"></div>
                <span className="text-dark-text-secondary">2.4 GHz</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <div className="w-8 h-0.5 bg-emerald-500"></div>
                <span className="text-dark-text-secondary">5 GHz</span>
              </div>
            </div>
          </div>

          {/* Marcadores de Eventos */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-dark-text-muted uppercase tracking-wider mb-2">Marcadores</p>
            <div className="space-y-1.5">
              <div className="flex items-center gap-2 text-xs">
                <div className="w-0 h-0 border-l-[4px] border-l-transparent border-r-[4px] border-r-transparent border-t-[7px] border-t-amber-500"></div>
                <span className="text-dark-text-secondary">BTM Request</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <div className="w-2.5 h-2.5 rounded-full bg-green-500"></div>
                <span className="text-dark-text-secondary">BTM Accept</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <div className="w-2.5 h-2.5 bg-red-500/20 border-2 border-red-500 rotate-45"></div>
                <span className="text-dark-text-secondary">BTM Rechazado</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <div className="w-3 h-3 bg-emerald-500 rounded"></div>
                <span className="text-dark-text-secondary">Transición Exitosa</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <div className="w-3 h-3 bg-orange-500 rotate-45"></div>
                <span className="text-dark-text-secondary">Transición Exitosa (sin cambio)</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <div className="w-2.5 h-2.5 rounded-full bg-red-500"></div>
                <span className="text-dark-text-secondary">Evento Fallido</span>
              </div>
            </div>
          </div>

          {/* Resumen de Métricas */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-dark-text-muted uppercase tracking-wider mb-2">Resumen</p>
            <div className="space-y-1.5 text-xs text-dark-text-secondary">
              <div>
                <span className="font-semibold text-dark-text-primary">Intentos:</span>{' '}
                <span className="text-emerald-400 font-bold">{steeringSummary.successful}</span>
                <span className="text-dark-text-muted"> / </span>
                <span className="text-dark-text-primary font-bold">{steeringSummary.attempts}</span>
              </div>
              <div>
                <span className="font-semibold text-dark-text-primary">BTM:</span>{' '}
                <span className="text-emerald-400 font-bold">{steeringSummary.btmAccept}</span>
                <span className="text-dark-text-muted"> de </span>
                <span className="text-dark-text-primary font-bold">{steeringSummary.btmRequests}</span>
              </div>
              <div>
                <span className="font-semibold text-dark-text-primary">Cambios de banda:</span>{' '}
                <span className="text-emerald-400 font-bold">{steeringSummary.bandChanges}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default BandSteeringChart