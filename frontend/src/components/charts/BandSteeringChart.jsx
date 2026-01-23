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
import { Activity, Radio } from 'lucide-react'

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
 * Componente de gráfica para visualizar cambios de banda en el tiempo.
 * Muestra: Tiempo, MAC, Frecuencia, RSSI, eventos BTM y cambios de canal.
 */
export function BandSteeringChart({ btmEvents = [], transitions = [], signalSamples = [], rawStats = {} }) {
  
  // Procesar datos para la gráfica
  const chartData = useMemo(() => {
    // Helper para media móvil simple (suavizado)
    const smoothData = (data, windowSize = 5) => {
      return data.map((val, index, arr) => {
        if (val === null) return null
        
        let sum = 0
        let count = 0
        // Tomar ventana alrededor del punto
        for (let i = Math.max(0, index - Math.floor(windowSize / 2)); 
             i < Math.min(arr.length, index + Math.floor(windowSize / 2) + 1); 
             i++) {
          if (arr[i] !== null && arr[i].y !== undefined && arr[i].y !== null) {
            sum += arr[i].y
            count++
          }
        }
        return count > 0 ? { ...val, y: sum / count } : val
      })
    }

    // Combinar todos los tipos de eventos en una línea de tiempo unificada
    const timelineEvents = []
    
    // 1. Muestras de Señal (Base principal de la gráfica)
    signalSamples.forEach(sample => {
      timelineEvents.push({
        timestamp: sample.timestamp,
        type: 'signal',
        rssi: sample.rssi,
        band: sample.band,
        frequency: sample.frequency,
        mac: sample.sa // Normalmente usamos Source Address como referencia
      })
    })

    // 2. Eventos BTM
    btmEvents.forEach(event => {
      // Intentar encontrar una muestra de señal cercana para asignar RSSI si no tiene
      const fallbackRssi = event.rssi || null
      
      timelineEvents.push({
        timestamp: event.timestamp,
        type: 'btm',
        eventType: event.event_type,
        frequency: event.frequency,
        band: event.band,
        mac: event.client_mac,
        bssid: event.ap_bssid,
        statusCode: event.status_code,
        rssi: fallbackRssi 
      })
    })
    
    // 3. Transiciones
    transitions.forEach(transition => {
      timelineEvents.push({
        timestamp: transition.start_time,
        type: 'transition_start',
        frequency: null,
        band: transition.from_band,
        mac: transition.client_mac,
        bssid: transition.from_bssid,
        steeringType: transition.steering_type,
        rssi: null // Se interpolará o usará default
      })
      
      if (transition.end_time) {
        timelineEvents.push({
          timestamp: transition.end_time,
          type: 'transition_end',
          frequency: null,
          band: transition.to_band,
          mac: transition.client_mac,
          bssid: transition.to_bssid,
          isSuccess: transition.is_successful,
          duration: transition.duration,
          steeringType: transition.steering_type,
          rssi: null
        })
      }
    })
    
    // Ordenar por timestamp
    timelineEvents.sort((a, b) => a.timestamp - b.timestamp)
    
    // Si no hay eventos, retornar datos vacíos
    if (timelineEvents.length === 0) {
      return { labels: [], datasets: [] }
    }
    
    // Normalizar timestamps
    const firstTimestamp = timelineEvents[0].timestamp
    
    // Crear labels (tiempo relativo)
    const labels = timelineEvents.map(event => (event.timestamp - firstTimestamp).toFixed(3) + 's')
    
    // Helper de frecuencia
    const frequencyToValue = (freq, band) => {
      if (freq) return freq
      if (band) {
        if (band.includes('2.4')) return 2437
        if (band.includes('5')) return 5180
      }
      return 2437
    }
    
    const band24DataRaw = []
    const band5DataRaw = []
    const btmMarkers = []
    
    timelineEvents.forEach((event, index) => {
      const freqValue = frequencyToValue(event.frequency, event.band)
      
      // Lógica de RSSI robusta
      let rssiValue = event.rssi
      
      // Si el evento no tiene RSSI (ej. una transición), intentar usar el valor anterior (Hold)
      // o simular si no hay nada.
      if (!rssiValue) {
         // Buscar el RSSI más cercano anterior
         for (let i = index - 1; i >= 0; i--) {
             if (timelineEvents[i].rssi) {
                 rssiValue = timelineEvents[i].rssi
                 break
             }
         }
      }
      
      // Si aún no hay RSSI (ej. al inicio), usar default visual
      if (!rssiValue) {
          const noise = (index % 5) * 2 
          rssiValue = -60 + noise 
      }
      
      // Clasificar banda
      const is24GHz = (event.band && event.band.includes('2.4')) || (freqValue >= 2400 && freqValue < 2500)
      const is5GHz = (event.band && event.band.includes('5')) || (freqValue >= 5000 && freqValue < 6000)
      
      const dataPoint = {
          x: index,
          y: rssiValue,
          timestamp: event.timestamp,
          relativeTime: (event.timestamp - firstTimestamp).toFixed(3),
          mac: event.mac,
          bssid: event.bssid,
          band: is24GHz ? '2.4GHz' : (is5GHz ? '5GHz' : 'Unknown'),
          frequency: freqValue,
          eventType: event.type,
          statusCode: event.statusCode,
          rssi: event.rssi,
          duration: event.duration,
          steeringType: event.steeringType
      }
      
      // Asignar al dataset correcto
      if (is24GHz) {
        band24DataRaw.push(dataPoint)
        band5DataRaw.push(null)
      } else if (is5GHz) {
        band5DataRaw.push(dataPoint)
        band24DataRaw.push(null)
      } else {
        band24DataRaw.push(dataPoint)
        band5DataRaw.push(null)
      }
      
      // Marcadores especiales
      if (event.type === 'btm' && event.eventType === 'request') {
        btmMarkers.push({ ...dataPoint, eventType: 'BTM Request' })
      }
    })
    
    // Aplicar suavizado a los datos (reduce ruido visual)
    const band24Data = smoothData(band24DataRaw)
    const band5Data = smoothData(band5DataRaw)
    
    return {
      labels,
      datasets: [
        {
          label: '2.4 GHz (RSSI)',
          data: band24Data,
          borderColor: 'rgb(59, 130, 246)',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          pointBackgroundColor: 'rgb(59, 130, 246)',
          pointBorderColor: '#fff',
          pointBorderWidth: 1,
          pointRadius: 0, // Ocultar puntos para línea limpia
          pointHoverRadius: 6,
          borderWidth: 2,
          tension: 0.4, // Curvas más suaves
          spanGaps: true,
          fill: false
        },
        {
          label: '5 GHz (RSSI)',
          data: band5Data,
          borderColor: 'rgb(16, 185, 129)',
          backgroundColor: 'rgba(16, 185, 129, 0.1)',
          pointBackgroundColor: 'rgb(16, 185, 129)',
          pointBorderColor: '#fff',
          pointBorderWidth: 1,
          pointRadius: 0, // Ocultar puntos
          pointHoverRadius: 6,
          borderWidth: 2,
          tension: 0.4,
          spanGaps: true,
          fill: false
        },
        {
          label: 'Eventos BTM',
          data: btmMarkers,
          borderColor: 'rgb(239, 68, 68)',
          backgroundColor: 'rgba(239, 68, 68, 0.9)',
          pointBackgroundColor: 'rgb(239, 68, 68)',
          pointBorderColor: '#fff',
          pointBorderWidth: 2,
          pointRadius: 8,
          pointHoverRadius: 10,
          pointStyle: 'triangle',
          showLine: false
        }
      ]
    }
  }, [btmEvents, transitions, signalSamples])
  
  // Opciones de configuración de la gráfica
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index',
      intersect: false,
    },
    plugins: {
      legend: {
        position: 'top',
        labels: {
          color: '#e5e7eb',
          font: {
            size: 12,
            weight: '600'
          },
          padding: 15,
          usePointStyle: true
        }
      },
      title: {
        display: true,
        text: 'Evolución de Intensidad de Señal (RSSI) y Band Steering',
        color: '#f9fafb',
        font: {
          size: 16,
          weight: 'bold'
        },
        padding: {
          top: 10,
          bottom: 20
        }
      },
      tooltip: {
        backgroundColor: 'rgba(17, 24, 39, 0.95)',
        titleColor: '#f9fafb',
        bodyColor: '#e5e7eb',
        borderColor: '#4b5563',
        borderWidth: 1,
        padding: 12,
        displayColors: true,
        callbacks: {
          title: (context) => {
            const dataPoint = context[0].raw
            if (!dataPoint) return ''
            return `⏱️ Tiempo: +${dataPoint.relativeTime}s`
          },
          label: (context) => {
            const dataPoint = context.raw
            if (!dataPoint) return ''
            
            const labels = []
            
            // Información Principal: Signal Strength
            labels.push(`📊 RSSI: ${dataPoint.y} dBm`)
            
            // Banda y Frecuencia
            labels.push(`📡 Banda: ${dataPoint.band || 'Desconocida'}`)
            if (dataPoint.frequency) {
               labels.push(`📶 Frecuencia: ${dataPoint.frequency} MHz`)
            }
            
            // MAC addresses
            if (dataPoint.mac) {
              labels.push(`💻 MAC Cliente: ${dataPoint.mac}`)
            }
            
            if (dataPoint.bssid) {
              labels.push(`🔌 BSSID AP: ${dataPoint.bssid}`)
            }
            
            // Tipo de evento
            if (dataPoint.eventType === 'BTM Request') {
              labels.push(`🔔 Evento: BTM Request enviado`)
            } else if (dataPoint.eventType === 'transition_start') {
              labels.push(`🚀 Inicio de transición`)
              if (dataPoint.steeringType) {
                const typeLabels = {
                  'aggressive': 'Agresivo (Deauth/Disassoc)',
                  'assisted': 'Asistido (BTM/802.11v)',
                  'preventive': 'Preventivo',
                  'unknown': 'Desconocido'
                }
                labels.push(`   Tipo: ${typeLabels[dataPoint.steeringType] || dataPoint.steeringType}`)
              }
            } else if (dataPoint.eventType === 'transition_end') {
              labels.push(`✅ Fin de transición`)
            }
            
            return labels
          }
        }
      }
    },
    scales: {
      x: {
        display: true,
        title: {
          display: true,
          text: 'Tiempo Relativo (s)',
          color: '#9ca3af',
          font: {
            size: 13,
            weight: '600'
          }
        },
        ticks: {
          color: '#9ca3af',
          maxRotation: 45,
          minRotation: 45,
          autoSkip: true,
          maxTicksLimit: 15
        },
        grid: {
          color: 'rgba(75, 85, 99, 0.2)',
          drawBorder: false
        }
      },
      y: {
        display: true,
        title: {
          display: true,
          text: 'Intensidad de Señal (dBm)',
          color: '#9ca3af',
          font: {
            size: 13,
            weight: '600'
          }
        },
        ticks: {
          color: '#9ca3af',
          callback: function(value) {
            return `${value} dBm`
          }
        },
        grid: {
          color: 'rgba(75, 85, 99, 0.2)',
          drawBorder: false
        },
        // Escala típica de WiFi RSSI: -30 (excelente) a -90 (muy mala)
        min: -95,
        max: -30,
        reverse: false // RSSI es negativo, -30 es "más alto" visualmente en chartjs si no inverse? 
        // En chartjs lineal, -30 está arriba y -95 abajo por defecto (mayor valor arriba). 
        // Como -30 > -95, esto está correcto para mostrar "mejor señal" arriba.
      }
    }
  }
  
  // Si no hay datos, mostrar mensaje
  if (chartData.labels.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center p-8">
        <div className="p-4 rounded-full bg-dark-accent-primary/10 mb-4">
          <Radio className="w-12 h-12 text-dark-accent-primary opacity-50" />
        </div>
        <h3 className="text-lg font-semibold text-dark-text-primary mb-2">
          Sin datos de banda disponibles
        </h3>
        <p className="text-sm text-dark-text-secondary max-w-md">
          No se detectaron eventos BTM o transiciones de banda en esta captura.
          La gráfica se mostrará cuando haya datos disponibles.
        </p>
      </div>
    )
  }
  
  return (
    <div className="w-full h-full min-h-[400px]">
      <Line data={chartData} options={options} />
    </div>
  )
}

export default BandSteeringChart
