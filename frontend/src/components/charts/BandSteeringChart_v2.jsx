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

export function BandSteeringChart({ btmEvents = [], transitions = [], signalSamples = []}) {
    // Estados para toggles de visualización
    const [showBTMEvents, setShowBTMEvents] = useState(true)
    const [showTransitions, setShowTransitions] = useState(true)
    const [showRSSIThresholds, setShowRSSIThresholds] = useState(true)
    const [showBandZones, setShowBandZones] = useState(true)
    const chartRef = useRef(null)


    const chartData = useMemo(() => {
        // -------------------------------------------------------------------------
        // 1. PROCESAMIENTO Y SUAVIZADO DE SEÑAL
        // -------------------------------------------------------------------------

        // Función para detectar si son ms o segundos y normalizar a MS
        const toMs = (ts) => (Number(ts) < 10000000000 ? Number(ts) * 1000 : Number(ts))

        // Función auxiliar para normalizar bandas (debe estar definida antes de usarse)
        const normalizeBand = (band) => {
            if (!band) return null
            const bandStr = band.toString().toLowerCase()
            if (bandStr.includes('5')) return '5GHz'
            if (bandStr.includes('2.4') || bandStr.includes('2,4')) return '2.4GHz'
            return band
        }

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
            return { datasets: [], bandZones: [], xMax: 0 }
        }

        let startTime = rawSamples[0].ts
        let endTime = rawSamples[rawSamples.length - 1].ts
        let totalDuration = endTime - startTime

        // Determinar ventana de suavizado dinámicamente (moderado-alto para reducir picos)
        // Usar ventanas moderadas para reducir picos pero mantener algo de variación
        const WINDOW_SIZE_MS = totalDuration > 60000 ? 1500 : 800

        // Función para normalizar tiempo (debe estar definida después de startTime)
        const normalizeTime = (tsRaw) => parseFloat(((toMs(tsRaw) - startTime) / 1000).toFixed(2))

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
        transitions.forEach((t) => {
            // CUALQUIER transición exitosa nos confirma en qué banda está el dispositivo.
            // Incluso si es 5GHz -> 5GHz, nos confirma que está en 5GHz.
            // Usamos esto para corregir el color de la línea.
            if (t.is_successful && t.to_band) {
                // Para cambios de banda, usar end_time porque el cambio real ocurre
                // cuando se completa la reassociation. Para otras transiciones, usar start_time.
                const timestampForState = (t.is_band_change && t.end_time) ? t.end_time : t.start_time

                // Normalizar la banda para consistencia
                const normalizedBand = normalizeBand(t.to_band)

                stateChanges.push({ ts: toMs(timestampForState), band: normalizedBand || t.to_band })
            }
        })

        stateChanges.sort((a, b) => a.ts - b.ts)

        // Construir lista de cambios de banda desde transiciones
        // IMPORTANTE: Procesar las transiciones PRIMERO para detectar cambios de banda corregidos
        // antes de generar smoothedPoints, para que getBandFromTransitions funcione correctamente
        let transitionBandChanges = []
        
        
        // Procesar transiciones primero para construir transitionBandChanges con correcciones
        const sortedTransitionsForBandChanges = [...(transitions || [])].sort((a, b) => a.start_time - b.start_time)
        
        sortedTransitionsForBandChanges.forEach((t, idx) => {
            if (!t || !t.start_time) return
            
            const fromBandNorm = normalizeBand(t.from_band)
            const toBandNorm = normalizeBand(t.to_band)
            let actualFromBand = fromBandNorm
            let actualToBand = toBandNorm
            let isBandChange = t.is_band_change === true
            
            // SIEMPRE comparar con la transición anterior para detectar cambios de banda reales
            // incluso si el backend no los marca correctamente
            if (idx > 0) {
                const prevTransition = sortedTransitionsForBandChanges[idx - 1]
                if (prevTransition && prevTransition.to_band) {
                    const prevBandNorm = normalizeBand(prevTransition.to_band)
                    const currentBandNorm = toBandNorm || fromBandNorm
                    
                    // Si hay un cambio de banda real comparando con la transición anterior
                    if (prevBandNorm && currentBandNorm && prevBandNorm !== currentBandNorm) {
                        // Hay un cambio de banda real, incluso si el backend no lo marcó
                        actualFromBand = prevBandNorm
                        actualToBand = currentBandNorm
                        isBandChange = true
                    } else if (isBandChange && fromBandNorm === toBandNorm) {
                        // El backend dice que hay cambio pero las bandas son iguales
                        // Si la transición anterior tiene la misma banda, entonces no hay cambio real
                        if (prevBandNorm === toBandNorm) {
                            isBandChange = false
                        } else if (prevBandNorm && prevBandNorm !== toBandNorm) {
                            // Hay cambio real comparando con la anterior
                            actualFromBand = prevBandNorm
                            actualToBand = toBandNorm
                        }
                    }
                }
            }
            
            // Agregar a transitionBandChanges si es un cambio de banda exitoso con bandas corregidas
            if (isBandChange && t.is_successful && actualFromBand && actualToBand && actualFromBand !== actualToBand) {
                const timestampToUse = (t.end_time) ? t.end_time : t.start_time
                const tRel = normalizeTime(timestampToUse)
                transitionBandChanges.push({
                    time: tRel,
                    fromBand: actualFromBand,
                    toBand: actualToBand
                })
            }
        })
        
        transitionBandChanges.sort((a, b) => a.time - b.time)

        // Función para obtener la banda basándose en transiciones (misma lógica que zonas de banda)
        const getBandFromTransitions = (timeInSeconds, fallbackBand = null) => {
            if (transitionBandChanges.length === 0) {
                return fallbackBand // No hay cambios de banda conocidos, usar fallback
            }
            
            // Determinar la banda inicial (antes del primer cambio)
            // Si el tiempo es anterior al primer cambio, usar fromBand del primer cambio
            if (timeInSeconds < transitionBandChanges[0].time) {
                const initialBand = transitionBandChanges[0].fromBand || fallbackBand
                return initialBand
            }
            
            // Encontrar el último cambio de banda que ocurrió antes o en este momento
            let currentBand = transitionBandChanges[0].fromBand // Banda inicial (fromBand del primer cambio)
            for (const change of transitionBandChanges) {
                if (change.time <= timeInSeconds) {
                    currentBand = change.toBand
                } else {
                    break
                }
            }
            
            return currentBand
        }

        // Función para obtener la banda lógica en un momento dado
    const getLogicalBand = (currentTs, rawBand) => {
        // Buscar el último cambio de estado válido ANTES de este momento
        // IMPORTANTE: Usar <= para incluir cambios de estado que ocurren exactamente en este momento
        const lastChange = stateChanges.filter(c => c.ts <= currentTs).pop()
        
        // CORRECCIÓN: Usar el último cambio de estado que ocurrió ANTES del momento actual
        // Los cambios de estado son persistentes hasta que haya un nuevo cambio de estado.
        // No limitar a 5 segundos - los cambios de banda son permanentes hasta el siguiente cambio.
        if (lastChange) {
            return lastChange.band
        }
        
        // Si no hay cambio de estado previo, usar la banda cruda
        return rawBand
    }

    // CRÍTICO: Si hay muy pocas muestras pero hay cambios de banda, generar puntos sintéticos adicionales
    // para asegurar que la línea se pinte correctamente en todo el rango temporal
    const MIN_SAMPLES_FOR_GOOD_COVERAGE = 10
    if (rawSamples.length < MIN_SAMPLES_FOR_GOOD_COVERAGE && transitionBandChanges.length > 0) {
        
        // Calcular el rango temporal completo
        const allTimestamps = [
            ...rawSamples.map(s => s.ts),
            ...transitions.map(t => toMs(t.start_time)),
            ...transitions.map(t => t.end_time ? toMs(t.end_time) : null).filter(Boolean),
            ...btmEvents.map(e => toMs(e.timestamp))
        ].filter(ts => ts && ts > 0).sort((a, b) => a - b)
        
        const minTime = allTimestamps[0]
        const maxTime = allTimestamps[allTimestamps.length - 1]
        const rangeDuration = maxTime - minTime
        
        // Generar puntos cada segundo (o más frecuente si el rango es pequeño)
        const stepMs = rangeDuration > 300000 ? 5000 : (rangeDuration > 60000 ? 2000 : 1000) // 5s, 2s o 1s según duración
        const syntheticSamples = []
        
        // Función auxiliar para obtener la banda en un tiempo dado (antes de actualizar startTime)
        const getBandAtTime = (timestampMs) => {
            if (transitionBandChanges.length === 0) {
                return '2.4GHz'
            }
            // Convertir timestamp a segundos relativos al startTime original
            const timeInSeconds = (timestampMs - startTime) / 1000
            
            // Determinar la banda inicial (antes del primer cambio)
            if (timeInSeconds < transitionBandChanges[0].time) {
                return transitionBandChanges[0].fromBand || '2.4GHz'
            }
            
            // Encontrar el último cambio de banda que ocurrió antes o en este momento
            let currentBand = transitionBandChanges[0].fromBand || '2.4GHz'
            for (const change of transitionBandChanges) {
                if (change.time <= timeInSeconds) {
                    currentBand = change.toBand
                } else {
                    break
                }
            }
            
            return currentBand
        }
        
        // Asegurar puntos alrededor de cada cambio de banda
        const criticalTimes = new Set()
        transitionBandChanges.forEach(change => {
            const changeTimeMs = startTime + (change.time * 1000)
            // Agregar puntos 2 segundos antes y después de cada cambio
            for (let offset = -2000; offset <= 2000; offset += 500) {
                criticalTimes.add(changeTimeMs + offset)
            }
        })
        
        // Generar puntos en todo el rango
        for (let t = minTime; t <= maxTime; t += stepMs) {
            if (!rawSamples.some(s => Math.abs(s.ts - t) < stepMs / 2)) {
                // No hay muestra cerca de este tiempo, crear una sintética con la banda correcta
                const correctBand = getBandAtTime(t)
                syntheticSamples.push({
                    ts: t,
                    rssi: -60, // RSSI por defecto
                    band: correctBand // Usar la banda correcta desde el inicio
                })
            }
        }
        
        // Agregar puntos críticos alrededor de cambios de banda
        criticalTimes.forEach(t => {
            if (t >= minTime && t <= maxTime && !rawSamples.some(s => Math.abs(s.ts - t) < 500)) {
                const correctBand = getBandAtTime(t)
                syntheticSamples.push({
                    ts: t,
                    rssi: -60,
                    band: correctBand // Usar la banda correcta desde el inicio
                })
            }
        })
        
        // Combinar muestras reales con sintéticas y ordenar
        rawSamples = [...rawSamples, ...syntheticSamples].sort((a, b) => a.ts - b.ts)
        
        // Actualizar startTime y endTime después de agregar muestras sintéticas
        startTime = rawSamples[0].ts
        endTime = rawSamples[rawSamples.length - 1].ts
        totalDuration = endTime - startTime
        
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

                const tiempoSegundos = parseFloat(((currentWindowStart - startTime) / 1000).toFixed(2))
                
                // CRÍTICO: Si hay cambios de banda en transiciones, usar EXACTAMENTE la misma lógica que las zonas de banda
                // Esto asegura que la línea se pinte con los mismos valores que las zonas de fondo
                let finalBand
                if (transitionBandChanges.length > 0) {
                    // Usar SOLO getBandFromTransitions cuando hay cambios de banda conocidos
                    // Esto garantiza que la línea coincida con las zonas de banda
                    finalBand = getBandFromTransitions(tiempoSegundos, rawDominant)
                    // Normalizar para asegurar formato consistente
                    if (finalBand && finalBand.includes('5')) {
                        finalBand = '5GHz'
                    } else if (finalBand && (finalBand.includes('2.4') || finalBand.includes('2,4'))) {
                        finalBand = '2.4GHz'
                    } else if (!finalBand || finalBand === '') {
                        // Si getBandFromTransitions retorna null/vacío pero hay cambios, usar la banda del último cambio
                        const lastChange = transitionBandChanges[transitionBandChanges.length - 1]
                        finalBand = lastChange ? lastChange.toBand : rawDominant
                    }
                } else {
                    // Solo usar fallbacks si NO hay cambios de banda en transiciones
                    const logicalBand = getLogicalBand(currentWindowStart, rawDominant)
                    finalBand = logicalBand ? (logicalBand.includes('5') ? '5GHz' : '2.4GHz') : rawDominant
                }
                
                smoothedPoints.push({
                    x: parseFloat(((currentWindowStart - startTime) / 1000).toFixed(2)),
                    y: Math.round(avgRssi * 10) / 10,
                    band: finalBand,
                    count: bucket.length
                })
            }
            currentWindowStart += WINDOW_SIZE_MS
        }

        // 1b. SUAVIZADO SECUNDARIO (Reducido - Solo vecinos inmediatos)
        // Si no hay puntos suavizados, crear puntos mínimos desde rawSamples
        let finalPoints = []


        if (smoothedPoints.length > 0) {
            finalPoints = smoothedPoints.map((p, i, arr) => {
                // Suavizado secundario moderado-alto para reducir picos
                // Aplicar suavizado si hay suficientes puntos
                let finalY = p.y
                if (arr.length > 50) {
                    // Usar vecinos inmediatos con pesos moderados-alto
                    const p1_prev = arr[i - 1] || p
                    const p1_next = arr[i + 1] || p

                    // Promedio moderado-alto (preserva ~60% del valor original, suaviza ~40%)
                    finalY = (
                        (p1_prev.y * 0.2) +
                        (p.y * 0.6) +
                        (p1_next.y * 0.2)
                    )
                }
                
                // CRÍTICO: Recalcular la banda después del suavizado usando EXACTAMENTE la misma lógica que las zonas de banda
                // Esto asegura que la línea se pinte correctamente incluso después del suavizado
                let correctedBand
                if (transitionBandChanges.length > 0) {
                    // Usar SOLO getBandFromTransitions cuando hay cambios de banda conocidos
                    correctedBand = getBandFromTransitions(p.x, p.band)
                    // Normalizar para asegurar formato consistente
                    if (correctedBand && correctedBand.includes('5')) {
                        correctedBand = '5GHz'
                    } else if (correctedBand && (correctedBand.includes('2.4') || correctedBand.includes('2,4'))) {
                        correctedBand = '2.4GHz'
                    } else if (!correctedBand || correctedBand === '') {
                        // Si getBandFromTransitions retorna null/vacío pero hay cambios, usar la banda del último cambio
                        const lastChange = transitionBandChanges[transitionBandChanges.length - 1]
                        correctedBand = lastChange ? lastChange.toBand : p.band
                    }
                } else {
                    // Si no hay cambios de banda, mantener la banda original del punto
                    correctedBand = p.band
                }
                
                return { 
                    ...p, 
                    y: Number(finalY.toFixed(2)),
                    band: correctedBand
                }
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
        // normalizeTime ya está definida arriba, después de startTime

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
            if (finalPoints.length > 0 && tRel > finalPoints[finalPoints.length - 1].x + 5) return
            // Si no hay puntos pero hay eventos, incluirlos de todas formas 

            const yPos = findRssiAt(tRel) // Poner marcador sobre la línea suavizada
            const isRequest = e.event_type === 'request'
            const isSuccess = !isRequest && e.status_code === 0

            const statusInfo = !isRequest
                ? (BTM_STATUS_CODES[e.status_code] || { label: `Código ${e.status_code}`, desc: 'Estado desconocido', color: '#9ca3af' })
                : null

            // SI ES UN ÉXITO DE BTM, LO TRATAMOS COMO EL "ROAMING COMPLETADO" VISUALMENTE
            // Esto resuelve el caso donde la "Transición" no se reporta pero el BTM sí.

            // Colores distintivos para cada tipo de BTM
            let btmColor, btmBorderColor, btmBgColor
            if (isRequest) {
                // BTM Request: Naranja/Amber
                btmColor = '#f59e0b'
                btmBorderColor = '#854d0e'
                btmBgColor = '#f59e0b'
            } else if (isSuccess) {
                // BTM Accept: Verde
                btmColor = '#10b981'
                btmBorderColor = '#fff'
                btmBgColor = '#10b981'
            } else {
                // BTM Rechazado: Rojo
                btmColor = '#ef4444'
                btmBorderColor = '#ef4444'
                btmBgColor = 'rgba(239, 68, 68, 0.3)'
            }

            markers.push({
                x: tRel,
                y: yPos,
                type: 'btm',
                // Títulos y descripciones técnicas precisas
                label: isRequest
                    ? 'BTM Request (Enviado por AP)'
                    : (isSuccess ? 'BTM Accept (Cliente acepta)' : 'BTM Rechazado (Cliente rechaza)'),
                description: isRequest
                    ? 'AP sugiere transición mediante gestión 802.11v'
                    : `Decisión: ${statusInfo?.label?.toUpperCase()} - ${statusInfo?.desc}`,
                color: btmColor,

                // FORMAS: Todos los BTM son triángulos (requests hacia abajo, responses hacia arriba)
                shape: 'triangle',
                rotation: isRequest ? 180 : 0,
                radius: isRequest ? 7 : (isSuccess ? 7 : 6),
                borderWidth: 2,
                borderColor: btmBorderColor,
                backgroundColor: btmBgColor
            })
        })

        // Primero, ordenar transiciones por tiempo para poder comparar consecutivas
        const sortedTransitions = [...filteredTransitions].sort((a, b) => a.start_time - b.start_time)

        // transitionBandChanges ya está construido arriba, no necesitamos reconstruirlo
        // pero podemos agregar cambios adicionales si se detectan durante el procesamiento de marcadores

        sortedTransitions.forEach((t, idx) => {
            if (!t || !t.start_time) return

            // Normalizar bandas para comparación consistente
            const fromBandNorm = normalizeBand(t.from_band)
            const toBandNorm = normalizeBand(t.to_band)

            // PROBLEMA DETECTADO: El backend marca is_band_change=true pero from_band y to_band son iguales
            // Esto ocurre cuando el cambio de banda se detecta comparando transiciones consecutivas
            // en el post-procesamiento, pero no se actualizan los campos from_band/to_band de la transición individual.
            // 
            // SOLUCIÓN: Si is_band_change es true pero las bandas son iguales, buscar la transición anterior
            // para obtener el from_band real, o calcularlo comparando con la transición anterior.
            // TAMBIÉN: Detectar cambios de banda incluso si el backend no los marca, comparando transiciones consecutivas.
            let actualFromBand = fromBandNorm
            let actualToBand = toBandNorm
            let isBandChange = t.is_band_change === true

            // SIEMPRE comparar con la transición anterior para detectar cambios de banda reales
            // incluso si el backend no los marca correctamente
            if (idx > 0) {
                const prevTransition = sortedTransitions[idx - 1]
                if (prevTransition && prevTransition.to_band) {
                    const prevBandNorm = normalizeBand(prevTransition.to_band)
                    const currentBandNorm = toBandNorm || fromBandNorm
                    
                    // Si hay un cambio de banda real comparando con la transición anterior
                    if (prevBandNorm && currentBandNorm && prevBandNorm !== currentBandNorm) {
                        // Hay un cambio de banda real, incluso si el backend no lo marcó
                        actualFromBand = prevBandNorm
                        actualToBand = currentBandNorm
                        isBandChange = true
                    } else if (isBandChange && fromBandNorm === toBandNorm) {
                        // El backend dice que hay cambio pero las bandas son iguales
                        // Si la transición anterior tiene la misma banda, entonces no hay cambio real
                        if (prevBandNorm === toBandNorm) {
                            isBandChange = false
                        } else if (prevBandNorm && prevBandNorm !== toBandNorm) {
                            // Hay cambio real comparando con la anterior
                            actualFromBand = prevBandNorm
                            actualToBand = toBandNorm
                        }
                    }
                }
            }


            // IMPORTANTE: Para cambios de banda, usar end_time porque el cambio real ocurre
            // cuando se completa la reassociation, no cuando se inicia el steering.
            // Para otras transiciones, usar start_time.
            const timestampToUse = (isBandChange && t.end_time) ? t.end_time : t.start_time
            const tRel = normalizeTime(timestampToUse)
            
            // Verificar si este cambio de banda ya está en transitionBandChanges
            // Si no está, agregarlo (puede pasar si se detecta una corrección adicional durante la creación de marcadores)
            // IMPORTANTE: Si el marcador es verde (cambio de banda exitoso), DEBE estar en transitionBandChanges
            if (isBandChange && t.is_successful && actualFromBand && actualToBand && actualFromBand !== actualToBand) {
                const alreadyExists = transitionBandChanges.some(c => 
                    Math.abs(c.time - tRel) < 0.1 && c.fromBand === actualFromBand && c.toBand === actualToBand
                )
                if (!alreadyExists) {
                    transitionBandChanges.push({
                        time: tRel,
                        fromBand: actualFromBand,
                        toBand: actualToBand
                    })
                    transitionBandChanges.sort((a, b) => a.time - b.time)
                }
            }
            
            const yPos = findRssiAt(tRel)


            // Separar claramente cambio de banda vs cambio de BSSID
            const hasBssidChange =
                t.is_successful &&
                t.from_bssid &&
                t.to_bssid &&
                t.from_bssid !== t.to_bssid

            const label = isBandChange && t.is_successful
                ? 'Roaming Completado (Cambio de Banda)'
                : (hasBssidChange && t.is_successful
                    ? 'Roaming Completado (Entre BSSIDs)'
                    : (t.is_successful
                        ? 'Transición de Asociación (sin cambio de banda/BSSID)'
                        : 'Intento Fallido'))

            // Usar las bandas corregidas en la descripción
            const descriptionFromBand = actualFromBand || t.from_band || '?'
            const descriptionToBand = actualToBand || t.to_band || '?'

            // Colores distintivos para cada tipo de transición
            let transColor, transBorderColor, transBgColor
            if (isBandChange && t.is_successful) {
                // Cambio de banda exitoso: Verde esmeralda
                transColor = '#10b981'
                transBorderColor = '#fff'
                transBgColor = '#10b981'
            } else if (hasBssidChange && t.is_successful) {
                // Cambio de BSSID exitoso (sin cambio de banda): Azul
                transColor = '#3b82f6'
                transBorderColor = '#fff'
                transBgColor = '#3b82f6'
            } else if (t.is_successful) {
                // Transición exitosa sin cambio: Naranja
                transColor = '#f97316'
                transBorderColor = '#f97316'
                transBgColor = 'rgba(249,115,22,0.95)'
            } else {
                // Transición fallida: Rojo
                transColor = '#ef4444'
                transBorderColor = '#ef4444'
                transBgColor = 'rgba(239, 68, 68, 0.8)'
            }


            // Traducir steering_type a español
            // Normalizar el valor a minúsculas para asegurar la comparación
            const steeringTypeNormalized = (t.steering_type || '').toLowerCase()
            const steeringTypeLabel = {
                'aggressive': 'Agresivo (Deauth)',
                'assisted': 'Asistido (BTM)',
                'preventive': 'Preventivo',
                'unknown': 'Espontáneo'
            }[steeringTypeNormalized] || (t.steering_type || 'Espontáneo')

            const finalDescription = `Transición: ${descriptionFromBand} ➡ ${descriptionToBand} (${steeringTypeLabel})`
            
            markers.push({
                x: tRel, y: yPos,
                type: 'transition',
                label: label,
                description: finalDescription,

                color: transColor,

                // Forma: Todos los rombos (rectRot) para transiciones
                shape: 'rectRot',
                radius: 7,
                borderWidth: 2,
                borderColor: transBorderColor,
                backgroundColor: transBgColor
            })
        })


        // -------------------------------------------------------------------------
        // 3. AGRUPACIÓN VISUAL INTELIGENTE (Smart Clustering)
        // -------------------------------------------------------------------------
        // Ordenar marcadores por tiempo (sin clustering - mantener posiciones originales)
        const clusteredMarkers = markers.sort((a, b) => a.x - b.x)

        // -------------------------------------------------------------------------
        // 4. GENERAR ZONAS DE BANDA EN EL TIEMPO (Background bands)
        // -------------------------------------------------------------------------
        // MEJORA: Usar transiciones con cambio de banda para determinar zonas,
        // no solo las muestras de RSSI (que pueden no tener frecuencia en el momento del cambio)
        const bandZones = []

        // Usar la lista de cambios de banda ya construida anteriormente (transitionBandChanges)
        // No necesitamos reconstruirla aquí

        // Calcular rangos dinámicos para los ejes basados en los datos reales
        // Primero calcular yMin y yMax para RSSI
        let yMin = -90
        let yMax = -40
        if (finalPoints.length > 0) {
            const rssiValues = finalPoints.map(p => p.y).filter(v => v != null && !isNaN(v))
            if (rssiValues.length > 0) {
                const minRssi = Math.min(...rssiValues)
                const maxRssi = Math.max(...rssiValues)
                const rssiRange = maxRssi - minRssi
                // Agregar márgenes del 10% arriba y abajo, pero mantener límites razonables
                yMin = Math.max(-100, Math.floor(minRssi - (rssiRange * 0.1)))
                yMax = Math.min(-20, Math.ceil(maxRssi + (rssiRange * 0.1)))
            }
        } else if (rawSamples.length > 0) {
            const rssiValues = rawSamples.map(s => s.rssi).filter(v => v != null && !isNaN(v))
            if (rssiValues.length > 0) {
                const minRssi = Math.min(...rssiValues)
                const maxRssi = Math.max(...rssiValues)
                const rssiRange = maxRssi - minRssi
                yMin = Math.max(-100, Math.floor(minRssi - (rssiRange * 0.1)))
                yMax = Math.min(-20, Math.ceil(maxRssi + (rssiRange * 0.1)))
            }
        }

        // Calcular xMax antes de crear zonas para extenderlas hasta el final completo
        let calculatedXMax = 0
        if (finalPoints.length > 0) {
            calculatedXMax = finalPoints[finalPoints.length - 1].x + 5 // Márgen de 5 segundos
        } else if (clusteredMarkers.length > 0) {
            const eventTimes = clusteredMarkers.map(m => m.x).sort((a, b) => a - b)
            calculatedXMax = eventTimes[eventTimes.length - 1] + 5
        } else if (rawSamples.length > 0) {
            const lastSample = rawSamples[rawSamples.length - 1]
            calculatedXMax = parseFloat(((lastSample.ts - startTime) / 1000).toFixed(2)) + 5
        }

        // Si hay cambios de banda en transiciones, usarlos para crear zonas
        if (transitionBandChanges.length > 0 && finalPoints.length > 0) {
            // Usar fromBand del primer cambio como banda inicial (no finalPoints[0]?.band que puede estar mal)
            let currentBand = transitionBandChanges[0].fromBand || finalPoints[0]?.band || '2.4GHz'
            let zoneStart = 0

            for (const change of transitionBandChanges) {
                // Cerrar zona anterior
                if (zoneStart < change.time) {
                    bandZones.push({
                        band: currentBand,
                        xStart: zoneStart,
                        xEnd: change.time,
                        yMin: yMin,
                        yMax: yMax
                    })
                }
                // Iniciar nueva zona con la banda destino
                currentBand = change.toBand
                zoneStart = change.time
            }

            // Cerrar última zona hasta el final completo de la gráfica
            if (zoneStart < calculatedXMax) {
                bandZones.push({
                    band: currentBand,
                    xStart: zoneStart,
                    xEnd: calculatedXMax,
                    yMin: yMin,
                    yMax: yMax
                })
            }
            
        } else if (finalPoints.length > 0) {
            // Fallback: usar solo puntos de RSSI si no hay transiciones con cambio de banda
            let currentZone = null
            for (let i = 0; i < finalPoints.length; i++) {
                const point = finalPoints[i]
                const band = point.band || '2.4GHz'
                const xStart = point.x
                // Usar calculatedXMax para la última zona, o el siguiente punto si no es el último
                const xEnd = i < finalPoints.length - 1 ? finalPoints[i + 1].x : (calculatedXMax || point.x)

                if (!currentZone || currentZone.band !== band) {
                    if (currentZone) {
                        currentZone.xEnd = xStart
                        bandZones.push(currentZone)
                    }
                    currentZone = {
                        band: band,
                        xStart: xStart,
                        xEnd: xEnd,
                        yMin: yMin,
                        yMax: yMax
                    }
                } else {
                    currentZone.xEnd = xEnd
                }
            }
            if (currentZone) {
                // Asegurar que la última zona llegue hasta el final completo de la gráfica
                currentZone.xEnd = calculatedXMax || currentZone.xEnd
                bandZones.push(currentZone)
            }
        }
        
        // Si no hay puntos pero hay eventos, crear una zona por defecto desde 0 hasta el final
        if (bandZones.length === 0 && calculatedXMax > 0) {
            bandZones.push({
                band: '2.4GHz',
                xStart: 0,
                xEnd: calculatedXMax,
                yMin: yMin,
                yMax: yMax
            })
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
                data: finalPoints, // Usamos data con suavizado mínimo
                borderWidth: 3,
                tension: 0, // Sin suavizado de curva para mostrar cambios más precisos
                fill: false,
                pointRadius: 0,
                pointHoverRadius: 6,
                spanGaps: true,
                // Eliminado cubicInterpolationMode para que los cambios de color sean más visibles
                // cubicInterpolationMode: 'monotone' puede ocultar cambios de color en segmentos
                segment: {
                    borderColor: (ctx) => {
                        // IMPORTANTE: En Chart.js, raw contiene el objeto original del data array
                        const p0Raw = ctx.p0?.raw
                        const p1Raw = ctx.p1?.raw
                        const p0Band = p0Raw?.band || ''
                        const p1Band = p1Raw?.band || ''
                        
                        // Si el segmento cruza un cambio de banda (p0.band !== p1.band),
                        // usar la banda del punto destino porque el cambio ocurre durante el segmento
                        // y al final del segmento el dispositivo ya está en la nueva banda
                        const currentBand = (p0Band && p1Band && p0Band !== p1Band) ? p1Band : (p0Band || p1Band || '');
                        const is5GHz = currentBand.includes('5') || currentBand === '5GHz';
                        const color = is5GHz ? '#10b981' : '#3b82f6';
                        return color;
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

        // Calcular rangos dinámicos para los ejes basados en los datos reales
        // xMax y xMin para ajustar el eje temporal al rango real de la captura
        let xMin = 0
        let xMax = 0
        if (finalPoints.length > 0) {
            xMin = Math.max(0, finalPoints[0].x - 2) // Márgen de 2 segundos antes
            xMax = finalPoints[finalPoints.length - 1].x + 5 // Márgen de 5 segundos después
        } else if (clusteredMarkers.length > 0) {
            const eventTimes = clusteredMarkers.map(m => m.x).sort((a, b) => a - b)
            xMin = Math.max(0, eventTimes[0] - 2)
            xMax = eventTimes[eventTimes.length - 1] + 5
        } else if (rawSamples.length > 0) {
            // Fallback: usar rawSamples si no hay nada más
            const firstSample = rawSamples[0]
            const lastSample = rawSamples[rawSamples.length - 1]
            xMin = Math.max(0, parseFloat(((firstSample.ts - startTime) / 1000).toFixed(2)) - 2)
            xMax = parseFloat(((lastSample.ts - startTime) / 1000).toFixed(2)) + 5
        }


        return {
            datasets,
            bandZones, // Zonas de banda para annotations dinámicas
            xMin,
            xMax,
            yMin,
            yMax
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
                // Ajustar el eje X al rango real de la captura para evitar zonas vacías
                min: chartData.xMin !== undefined && chartData.xMin >= 0 ? chartData.xMin : 0,
                max: chartData.xMax && chartData.xMax > 0 ? chartData.xMax : undefined
            },
            y: {
                // Ajustar el eje Y al rango real de RSSI con márgenes
                min: chartData.yMin !== undefined ? chartData.yMin : -90,
                max: chartData.yMax !== undefined ? chartData.yMax : -40,
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
    }), [showBandZones, showRSSIThresholds, chartData.bandZones, chartData.xMax, chartData.xMin, chartData.yMin, chartData.yMax])

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
    }, [chartData, chartData.xMin, chartData.xMax, chartData.yMin, chartData.yMax]) // Re-ejecutar cuando cambien los datos del gráfico


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
                            return Array.isArray(d.data) && d.data.length > 0
                        })
                    }

                    if (validData.datasets.length === 0) {
                        return (
                            <div className="h-full flex items-center justify-center text-gray-500">
                                <p>No hay datos válidos para mostrar en la gráfica</p>
                            </div>
                        )
                    }

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
                        <p className="text-xs font-semibold text-dark-text-muted uppercase tracking-wider mb-2">Marcadores BTM</p>
                        <div className="space-y-1.5">
                            <div className="flex items-center gap-2 text-xs">
                                <div className="w-0 h-0 border-l-[4px] border-l-transparent border-r-[4px] border-r-transparent border-t-[7px] border-t-amber-500"></div>
                                <span className="text-dark-text-secondary">BTM Request</span>
                            </div>
                            <div className="flex items-center gap-2 text-xs">
                                <div className="w-0 h-0 border-l-[4px] border-l-transparent border-r-[4px] border-r-transparent border-b-[7px] border-b-emerald-500"></div>
                                <span className="text-dark-text-secondary">BTM Accept</span>
                            </div>
                            <div className="flex items-center gap-2 text-xs">
                                <div className="w-0 h-0 border-l-[4px] border-l-transparent border-r-[4px] border-r-transparent border-b-[7px] border-b-red-500"></div>
                                <span className="text-dark-text-secondary">BTM Rechazado</span>
                            </div>

                        </div>
                    </div>

                    {/* Resumen de Métricas */}
                    <div className="space-y-2">
                        <p className="text-xs font-semibold text-dark-text-muted uppercase tracking-wider mb-2">Transiciones</p>
                        <div className="space-y-1.5 text-xs text-dark-text-secondary">
                            <div className="flex items-center gap-2 text-xs">
                                <div className="w-2 h-2 bg-green-500 rotate-45"></div>
                                <span className="text-dark-text-secondary">Exitosa (Cambio de banda)</span>
                            </div>
                            <div className="flex items-center gap-2 text-xs">
                                <div className="w-2 h-2 bg-orange-500 rotate-45"></div>
                                <span className="text-dark-text-secondary">Exitosa (Sin cambio)</span>
                            </div>
                            <div className="flex items-center gap-2 text-xs">
                                <div className="w-2 h-2 bg-red-500 rotate-45"></div>
                                <span className="text-dark-text-secondary">Fallido</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Umbrales RSSI */}
                <div className="mt-4 pt-4 border-t border-dark-border-primary">
                    <p className="text-xs font-semibold text-dark-text-muted uppercase tracking-wider mb-3">Umbrales RSSI</p>
                    <div className="flex items-center gap-4 flex-wrap mb-2">
                        <div className="flex items-center gap-2 text-xs">
                            <div className="w-8 h-0.5 border-t border-t-emerald-500 border-dashed" style={{ borderTopWidth: '1px', borderTopStyle: 'dashed' }}></div>
                            <span className="text-dark-text-secondary">Excelente (-67 dBm)</span>
                        </div>
                        <div className="flex items-center gap-2 text-xs">
                            <div className="w-8 h-0.5 border-t border-t-amber-500 border-dashed" style={{ borderTopWidth: '2px', borderTopStyle: 'dashed' }}></div>
                            <span className="text-dark-text-secondary">Límite (-70 dBm)</span>
                        </div>
                        <div className="flex items-center gap-2 text-xs">
                            <div className="w-8 h-0.5 border-t border-t-red-500 border-dashed" style={{ borderTopWidth: '1px', borderTopStyle: 'dashed' }}></div>
                            <span className="text-dark-text-secondary">Malo (-75 dBm)</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default BandSteeringChart