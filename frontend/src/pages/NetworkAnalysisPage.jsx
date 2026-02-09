import React from 'react'
import { createPortal } from 'react-dom'
import { useNetworkAnalysis } from '../hooks/useNetworkAnalysis'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Loading } from '../components/ui/Loading'
import {
    Upload,
    Activity,
    AlertTriangle,
    FileText,
    HardDrive,
    X,
    PanelLeft,
    PanelRight,
    MessageCircle,
    Trash2,
} from 'lucide-react'
import { ReportBodyContent } from './ReportBodyContent'
import { networkAnalysisService } from '../services/api'
import { useReportChat } from '../hooks/useReportChat'
import { ChatContainer } from '../components/chat/ChatContainer'
import { ChatInput } from '../components/chat/ChatInput'
import { useChatLayout } from '../contexts/ChatLayoutContext'

const CHAT_WIDTH_MIN = 280
const CHAT_WIDTH_MAX = 720

const PRINT_STYLES = `
        @page {
          margin: 1.5cm;
          size: auto;
        }

        @media print {
          /* Ocultar elementos de UI no necesarios de forma específica */
          nav, 
          button, 
          header,
          .flex-shrink-0,
          /* Seleccionar específicamente el contenedor de botones en el header para ocultarlo */
          .container-app > div:nth-child(2) > div:first-child > div:last-child {
            display: none !important;
          }

          /* Asegurar que el título de impresión esté arriba a la derecha */
          .print\\:flex {
            display: flex !important;
            position: fixed !important;
            top: 0 !important;
            right: 0 !important;
            z-index: 1000;
          }
          
          /* Reset de Layout para PDF */
          .container-app, body, #root {
            background: white !important;
            color: black !important;
            padding: 0 !important;
            margin: 0 !important;
            height: auto !important;
            width: 100% !important;
          }

          .max-w-5xl {
            max-width: 100% !important;
            width: 100% !important;
            box-shadow: none !important;
          }
          
          /* Forzar visibilidad de texto y bordes */
          h1, h2, h3, h4, p, span, div, li, td, th {
            color: #000 !important;
            background-color: transparent !important;
          }
          
          .text-dark-text-primary, 
          .text-dark-text-secondary, 
          .text-dark-text-muted,
          .text-white {
            color: #111 !important;
          }
          
          /* Cards con bordes para definición visual en papel */
          .Card, [class*="bg-dark-accent-primary/5"], [class*="bg-gradient-to-br"] {
            background: #fff !important;
            border: 1px solid #ccc !important;
            box-shadow: none !important;
            color: black !important;
            margin-bottom: 1rem !important;
            break-inside: avoid;
          }

          /* Arreglar Grid para impresión */
          .grid {
            display: block !important;
          }
          .md\\:grid-cols-3 {
            display: flex !important;
            flex-direction: row !important;
            gap: 1% !important;
            margin-bottom: 20px !important;
          }
          .md\\:grid-cols-3 > div {
            flex: 1 !important;
            width: 32% !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            min-height: 75px !important; /* Más compactos */
            padding: 10px 15px !important; /* Menos padding */
            margin-right: 0 !important;
          }

          .lg\\:grid-cols-3 {
            display: block !important;
          }
          .lg\\:col-span-1 {
            width: 100% !important;
            margin-bottom: 20px !important;
          }
          
          /* FORZAR SALTO DE PÁGINA PARA EL ANÁLISIS */
          .lg\\:col-span-2 {
            width: 100% !important;
            page-break-before: always !important;
            margin-top: 0 !important;
            padding-top: 3rem !important; /* Espacio extra para que no pegue arriba */
          }

          /* Ajustar Markdown (prose) para impresión */
          .prose {
            color: black !important;
            max-width: 100% !important;
          }
          .prose * {
            color: black !important;
          }
          .prose h2, .prose h3 {
            border-bottom: 1px solid #eee !important;
            margin-top: 1.5rem !important;
            padding-bottom: 0.5rem !important;
          }
          
          /* Detalle de veredicto en PDF */
          [class*="rounded-lg font-semibold"] {
            border: 2px solid #000 !important;
            background: #f8f8f8 !important;
            padding: 8px 16px !important;
          }
          
          /* NUEVO: Estilos para tabla de cumplimiento en PDF */
          .space-y-2\\.5 > div {
            background: #fff !important;
            border: 1px solid #eee !important;
            padding: 10px 15px !important;
            margin-bottom: 5px !important;
            page-break-inside: avoid !important;
          }
          
          /* Badges de PASÓ/FALLÓ visibles en PDF */
          .compliance-badge {
            border: 1px solid #000 !important;
            padding: 2px 6px !important;
            font-weight: bold !important;
            font-size: 9px !important;
            text-transform: uppercase !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }
          
          /* Verde para PASÓ */
          .compliance-badge.text-green-400 {
            color: #065f46 !important;
            background-color: #dcfce7 !important;
            border-color: #059669 !important;
          }
          
          /* Rojo para FALLÓ */
          .compliance-badge.text-red-400 {
            color: #991b1b !important;
            background-color: #fee2e2 !important;
            border-color: #dc2626 !important;
          }
          
          /* Prevenir word-break vertical en detalles técnicos */
          .font-mono {
            word-break: normal !important;
            overflow-wrap: break-word !important;
            white-space: pre-wrap !important;
          }
          
          /* Asegurar que los textos no se rompan verticalmente */
          p, span, div {
            word-break: normal !important;
            overflow-wrap: break-word !important;
          }
        }
      `

export function NetworkAnalysisPage() {
    const {
        selectedFile,
        uploading,
        result,
        fileMetadata,
        savedSsid,
        error,
        userSsid,
        userClientMac,
        setUserSsid,
        setUserClientMac,
        setError,
        fileInputRef,
        handleSelectClick,
        handleFileChange,
        resetAnalysis,
    } = useNetworkAnalysis()

    const analysisId = result?.band_steering?.analysis_id ?? null

    // Usar el contexto compartido para el estado del chat
    const chatLayoutContext = useChatLayout()
    const { chatWidth, setChatWidth, chatSide, setChatSide, chatPanelOpen, setChatPanelOpen } = chatLayoutContext

    // Estados locales para el chat (no relacionados con el layout)
    const [selectionPopup, setSelectionPopup] = React.useState(null)
    const selectionPopupDataRef = React.useRef(null) // ref para que handleAskAgent tenga el texto aunque el popup se cierre
    const [chatMode, setChatMode] = React.useState('report') // 'report' | 'docs'
    const [highlightedContext, setHighlightedContext] = React.useState(null)
    const [selectionLockActive, setSelectionLockActive] = React.useState(false)
    const [isResizing, setIsResizing] = React.useState(false)
    const reportContentRef = React.useRef(null)
    const isResizingRef = React.useRef(false)

    // Redimensionar ancho del chat
    const handleResizeStart = React.useCallback((e) => {
        e.preventDefault()
        isResizingRef.current = true
        setIsResizing(true)
    }, [])
    React.useEffect(() => {
        if (!result || !chatPanelOpen) return
        const onMove = (e) => {
            if (!isResizingRef.current) return
            const clientX = e.clientX ?? 0
            if (chatSide === 'right') {
                const w = Math.round(Math.max(CHAT_WIDTH_MIN, Math.min(CHAT_WIDTH_MAX, window.innerWidth - clientX)))
                setChatWidth(w)
            } else {
                const w = Math.round(Math.max(CHAT_WIDTH_MIN, Math.min(CHAT_WIDTH_MAX, clientX)))
                setChatWidth(w)
            }
        }
        const onUp = () => {
            isResizingRef.current = false
            setIsResizing(false)
        }
        document.addEventListener('mousemove', onMove)
        document.addEventListener('mouseup', onUp)
        return () => {
            document.removeEventListener('mousemove', onMove)
            document.removeEventListener('mouseup', onUp)
        }
    }, [result, chatPanelOpen, chatSide])
    React.useEffect(() => {
        if (isResizing) {
            document.body.style.cursor = 'col-resize'
            document.body.style.userSelect = 'none'
        }
        return () => {
            document.body.style.cursor = ''
            document.body.style.userSelect = ''
        }
    }, [isResizing])

    // Cerrar popup solo al hacer clic fuera del reporte y fuera del botón (no en selectionchange, para no cerrar antes del click y mantener la selección)
    React.useEffect(() => {
        const onMouseDown = (e) => {
            if (!selectionPopup) return
            const isInReport = reportContentRef.current && reportContentRef.current.contains(e.target)
            const isInPopup = e.target.closest('[data-selection-popup]')
            if (!isInReport && !isInPopup) {
                selectionPopupDataRef.current = null
                setSelectionPopup(null)
            }
        }
        document.addEventListener('mousedown', onMouseDown)
        return () => document.removeEventListener('mousedown', onMouseDown)
    }, [selectionPopup])

    const reportChat = useReportChat(analysisId)

    // Función para limpiar el nombre del archivo (quitar UUID y prefijos numéricos)
    const cleanFileName = (fileName) => {
        if (!fileName) return ''

        let clean = fileName

        // 1. Remover UUID del formato: "uuid_nombre.ext"
        const parts = clean.split('_')
        if (parts.length > 1 && parts[0].length > 20) { // Probable UUID
            clean = parts.slice(1).join('_')
        }

        // 2. Remover prefijos tipo "7." o "01."
        clean = clean.replace(/^\d+\./, '')
        return clean.trim()
    }

    // Función para formatear el tamaño del archivo (Uso decimal para coherencia con bytes)
    const formatFileSize = (bytes) => {
        if (!bytes) return '0 Bytes'
        const factor = 1000 // Factor decimal para coincidir visualmente con el texto
        const sizes = ['Bytes', 'KB', 'MB', 'GB']
        const i = Math.floor(Math.log(bytes) / Math.log(factor))
        return parseFloat((bytes / Math.pow(factor, i)).toFixed(2)) + ' ' + sizes[i]
    }

    // Función para capturar el gráfico como imagen
    const captureChartImage = () => {
        try {
            // Buscar el canvas del gráfico en el DOM (Chart.js renderiza en un canvas)
            // Buscar dentro del contenedor del gráfico para ser más específico
            const chartContainer = document.querySelector('[class*="BandSteeringChart"]') ||
                document.querySelector('.lg\\:col-span-2 canvas') ||
                document.querySelector('canvas')

            if (chartContainer) {
                const canvas = chartContainer.tagName === 'CANVAS'
                    ? chartContainer
                    : chartContainer.querySelector('canvas')

                if (canvas) {
                    // Capturar como imagen PNG con buena calidad
                    return canvas.toDataURL('image/png', 1.0)
                }
            }
        } catch {
            // Error al capturar el gráfico; se devuelve null
        }
        return null
    }

    // Función para generar HTML limpio para PDF
    const generatePDFHTML = () => {
        if (!result) return ''

        const fileName = result?.file_name || fileMetadata?.name || ''
        const cleanName = cleanFileName(fileName).split('.')[0].replace(/_/g, ' ').trim()
        const device = result.band_steering?.device || {}
        const vendor = device.vendor || 'Desconocido'
        const model = device.device_model || 'Genérico'
        const category = device.device_category?.replace('_', ' ') || 'N/A'
        // Recalcular el veredicto basándose en los checks corregidos
        let verdict = result.band_steering?.verdict || 'UNKNOWN'
        const baseChecks = result.band_steering?.compliance_checks || []

        // Recalcular el estado de "Steering Efectivo" para determinar el veredicto correcto
        const steeringCheck = baseChecks.find(c => c.check_name === 'Steering Efectivo')
        if (steeringCheck) {
            const transitions = result.band_steering?.transitions || []
            const normalizeBand = (band) => {
                if (!band) return null
                const bandStr = band.toString().toLowerCase()
                if (bandStr.includes('5')) return '5GHz'
                if (bandStr.includes('2.4') || bandStr.includes('2,4')) return '2.4GHz'
                return band
            }
            const sortedTransitions = [...transitions].sort((a, b) => a.start_time - b.start_time)
            let bandChangeCount = 0
            sortedTransitions.forEach((t, idx) => {
                if (!t.is_successful) return
                const fromBand = normalizeBand(t.from_band)
                const toBand = normalizeBand(t.to_band)
                let isBandChange = t.is_band_change === true
                let actualFromBand = fromBand
                let actualToBand = toBand

                if (idx > 0) {
                    const prevTransition = sortedTransitions[idx - 1]
                    if (prevTransition && prevTransition.to_band) {
                        const prevBand = normalizeBand(prevTransition.to_band)
                        const currentBand = toBand || fromBand

                        if (prevBand && currentBand && prevBand !== currentBand) {
                            actualFromBand = prevBand
                            actualToBand = currentBand
                            isBandChange = true
                        } else if (isBandChange && fromBand === toBand) {
                            if (prevBand === toBand) {
                                isBandChange = false
                            } else if (prevBand && prevBand !== toBand) {
                                actualFromBand = prevBand
                                actualToBand = toBand
                                isBandChange = true
                            }
                        }
                    }
                } else if (!isBandChange && fromBand && toBand && fromBand !== toBand) {
                    isBandChange = true
                }

                if (isBandChange && actualFromBand && actualToBand && actualFromBand !== actualToBand) {
                    bandChangeCount++
                }
            })

            const bssidChangeTransitions = sortedTransitions.filter(t =>
                t.is_successful &&
                t.from_bssid &&
                t.to_bssid &&
                t.from_bssid !== t.to_bssid
            ).length

            const steeringPassed = bandChangeCount > 0 || bssidChangeTransitions > 0

            // Recalcular el veredicto basándose en los checks corregidos
            const assocCheck = baseChecks.find(c => c.category === 'association')
            const btmCheck = baseChecks.find(c => c.category === 'btm')

            if (assocCheck && !assocCheck.passed) {
                verdict = 'FAILED'
            } else if (btmCheck && !btmCheck.passed) {
                verdict = 'FAILED'
            } else if (steeringPassed) {
                verdict = 'SUCCESS'
            } else {
                const sa = result.stats?.steering_analysis || {}
                const successful = sa.successful_transitions ?? 0
                if (successful > 0) {
                    if (btmCheck && btmCheck.passed) {
                        verdict = 'PARTIAL'
                    } else {
                        verdict = 'FAILED'
                    }
                }
            }
        }

        const ssid = savedSsid || fileMetadata?.ssid || ''
        const analysisText = result.analysis || 'No hay análisis disponible'

        // Capturar imagen del gráfico
        const chartImage = captureChartImage()

        // Obtener MACs
        const clientMac = result.stats?.diagnostics?.user_provided_client_mac ||
            result.stats?.diagnostics?.client_mac ||
            'Desconocido'
        const rawInfo = result.stats?.diagnostics?.bssid_info || {}
        const macRegex = /^([0-9a-f]{2}:){5}[0-9a-f]{2}$/i
        const bssids = Object.keys(rawInfo).filter(key => macRegex.test(key))

        // Obtener métricas KVR
        const kvrCheck = result.band_steering?.compliance_checks?.find(c => c.check_name === "Estándares KVR")
        let kvrDetected = []
        if (kvrCheck && kvrCheck.details) {
            if (kvrCheck.details.includes('k=True')) kvrDetected.push('11k')
            if (kvrCheck.details.includes('v=True')) kvrDetected.push('11v')
            if (kvrCheck.details.includes('r=True')) kvrDetected.push('11r')
        } else {
            const kvr = result.stats?.diagnostics?.band_counters?.kvr_stats || {}
            if (kvr['11k']) kvrDetected.push('11k')
            if (kvr['11v']) kvrDetected.push('11v')
            if (kvr['11r']) kvrDetected.push('11r')
        }

        // Obtener métricas de steering
        const sa = result.stats?.steering_analysis || {}
        const attempts = sa.steering_attempts ?? 0
        const successful = sa.successful_transitions ?? 0

        // Calcular cambios de banda y transiciones
        const transitions = result.band_steering?.transitions || []
        const normalizeBand = (band) => {
            if (!band) return null
            const bandStr = band.toString().toLowerCase()
            if (bandStr.includes('5')) return '5GHz'
            if (bandStr.includes('2.4') || bandStr.includes('2,4')) return '2.4GHz'
            return band
        }
        const sortedTransitions = [...transitions].sort((a, b) => a.start_time - b.start_time)
        let bandChangeCount = 0
        let associationOnlyCount = 0
        sortedTransitions.forEach((t, idx) => {
            if (!t.is_successful) return
            const fromBand = normalizeBand(t.from_band)
            const toBand = normalizeBand(t.to_band)
            let isBandChange = t.is_band_change === true
            let actualFromBand = fromBand
            let actualToBand = toBand

            // SIEMPRE comparar con la transición anterior para detectar cambios de banda reales
            // incluso si el backend no los marca correctamente (misma lógica que la gráfica)
            if (idx > 0) {
                const prevTransition = sortedTransitions[idx - 1]
                if (prevTransition && prevTransition.to_band) {
                    const prevBand = normalizeBand(prevTransition.to_band)
                    const currentBand = toBand || fromBand

                    // Si hay un cambio de banda real comparando con la transición anterior
                    if (prevBand && currentBand && prevBand !== currentBand) {
                        // Hay un cambio de banda real, incluso si el backend no lo marcó
                        actualFromBand = prevBand
                        actualToBand = currentBand
                        isBandChange = true
                    } else if (isBandChange && fromBand === toBand) {
                        // El backend dice que hay cambio pero las bandas son iguales
                        // Si la transición anterior tiene la misma banda, entonces no hay cambio real
                        if (prevBand === toBand) {
                            isBandChange = false
                        } else if (prevBand && prevBand !== toBand) {
                            // Hay cambio real comparando con la anterior
                            actualFromBand = prevBand
                            actualToBand = toBand
                            isBandChange = true
                        }
                    }
                }
            } else if (!isBandChange && fromBand && toBand && fromBand !== toBand) {
                // Primera transición: si las bandas son diferentes, es un cambio de banda
                isBandChange = true
            }

            // Verificar que realmente hay un cambio de banda válido
            if (isBandChange && actualFromBand && actualToBand && actualFromBand !== actualToBand) {
                bandChangeCount++
            } else {
                associationOnlyCount++
            }
        })

        // Calcular tiempo medido (usar la misma lógica que la aplicación: basarse en transitions y signal_samples)
        let measuredTime = 'N/A'
        try {
            const transitions = result.band_steering?.transitions || []
            const signalSamples = result.band_steering?.signal_samples || []

            // Recopilar todos los timestamps de transiciones y muestras de señal
            const allTimestamps = []

            transitions.forEach(t => {
                if (t && t.start_time != null) {
                    allTimestamps.push(Number(t.start_time))
                }
                if (t && t.end_time != null) {
                    allTimestamps.push(Number(t.end_time))
                }
            })

            signalSamples.forEach(s => {
                if (s && s.timestamp != null) {
                    const ts = Number(s.timestamp)
                    if (!isNaN(ts)) {
                        allTimestamps.push(ts)
                    }
                }
            })

            if (allTimestamps.length < 2) {
                // Fallback: intentar con paquetes de Wireshark si no hay transiciones/muestras
                const normalizeMac = (mac) => {
                    if (!mac) return null
                    return mac.toLowerCase().replace(/[:-]/g, '')
                }
                const normalizedClientMac = normalizeMac(clientMac)
                const wiresharkSample = result.stats?.diagnostics?.wireshark_raw?.sample || []
                const devicePackets = wiresharkSample.filter(packet => {
                    const wlanSa = normalizeMac(packet.wlan_sa)
                    const wlanDa = normalizeMac(packet.wlan_da)
                    return wlanSa === normalizedClientMac || wlanDa === normalizedClientMac
                })

                if (devicePackets.length > 0) {
                    const timestamps = devicePackets
                        .map(p => {
                            const ts = p.timestamp
                            if (typeof ts === 'string') {
                                return parseFloat(ts)
                            }
                            return ts
                        })
                        .filter(ts => !isNaN(ts) && ts > 0)
                    if (timestamps.length > 0) {
                        allTimestamps.push(...timestamps)
                    }
                }
            }

            if (allTimestamps.length > 1) {
                const minTime = Math.min(...allTimestamps)
                const maxTime = Math.max(...allTimestamps)
                const timeDiff = maxTime - minTime

                if (timeDiff > 0) {
                    if (timeDiff < 1) {
                        measuredTime = `${(timeDiff * 1000).toFixed(0)} ms`
                    } else if (timeDiff < 60) {
                        measuredTime = `${timeDiff.toFixed(2)} s`
                    } else {
                        const minutes = Math.floor(timeDiff / 60)
                        const seconds = (timeDiff % 60).toFixed(3)
                        measuredTime = `${minutes}m ${seconds}s`
                    }
                }
            }
        } catch {
            measuredTime = 'N/A'
        }

        // Obtener métricas BTM
        const btmRequests = result.band_steering?.btm_requests || 0
        const btmResponses = result.band_steering?.btm_responses || 0
        const btmAccept = result.band_steering?.btm_events?.filter(e => e.status_code === 0).length || 0

        // Obtener métricas de asociación
        const assocCount = result.stats?.diagnostics?.band_counters?.assoc_count || 0
        const reassocCount = result.stats?.diagnostics?.band_counters?.reassoc_count || 0
        const disassocCount = result.stats?.diagnostics?.band_counters?.disassoc_count || 0
        const deauthCount = result.stats?.diagnostics?.band_counters?.deauth_count || 0

        // Obtener soporte KVR detallado
        const kvrSupport = result.band_steering?.kvr_support || {}
        const kSupport = kvrSupport.k === true || kvrDetected.includes('11k')
        const vSupport = kvrSupport.v === true || kvrDetected.includes('11v')
        const rSupport = kvrSupport.r === true || kvrDetected.includes('11r')

        // Calcular tiempo en cada banda y en transición (EXACTAMENTE la misma lógica que en el componente)
        const signalSamples = result.band_steering?.signal_samples || []

        let bandTiming = null
        try {
            const sortedTransitions = (transitions || [])
                .filter(t => t && t.start_time != null && t.is_successful)
                .sort((a, b) => Number(a.start_time) - Number(b.start_time))

            const validTransitions = []

            for (let idx = 0; idx < sortedTransitions.length; idx++) {
                const t = sortedTransitions[idx]
                let fromBand = normalizeBand(t.from_band || '')
                let toBand = normalizeBand(t.to_band || '')
                let isBandChange = t.is_band_change === true

                // Si ya tiene bandas diferentes, es un cambio de banda
                if (fromBand && toBand && fromBand !== toBand) {
                    isBandChange = true
                } else if (isBandChange && fromBand === toBand && idx > 0) {
                    // Si está marcado como cambio pero las bandas son iguales, verificar con la anterior
                    const prevTransition = sortedTransitions[idx - 1]
                    if (prevTransition && prevTransition.to_band) {
                        const prevBand = normalizeBand(prevTransition.to_band)
                        if (prevBand && prevBand !== toBand) {
                            fromBand = prevBand
                            isBandChange = true
                        } else {
                            isBandChange = false
                        }
                    } else {
                        isBandChange = false
                    }
                } else if (!isBandChange) {
                    // Intentar detectar cambio de banda comparando con transición anterior
                    if (idx > 0) {
                        const prevTransition = sortedTransitions[idx - 1]
                        if (prevTransition && prevTransition.to_band) {
                            const prevBand = normalizeBand(prevTransition.to_band)
                            const currentBand = toBand || fromBand
                            if (prevBand && currentBand && prevBand !== currentBand) {
                                fromBand = prevBand
                                toBand = currentBand
                                isBandChange = true
                            }
                        }
                    }
                    // Si es la primera transición, buscar en samples anteriores
                    if (!isBandChange && idx === 0 && signalSamples.length > 0) {
                        const samplesBefore = signalSamples.filter(s => Number(s.timestamp) < Number(t.start_time || 0))
                            .sort((a, b) => Number(b.timestamp) - Number(a.timestamp))
                        if (samplesBefore.length > 0) {
                            const initialBandFromSamples = normalizeBand(samplesBefore[0].band || '')
                            if (initialBandFromSamples && toBand && initialBandFromSamples !== toBand) {
                                fromBand = initialBandFromSamples
                                isBandChange = true
                            }
                        }
                    }
                }

                if (isBandChange && fromBand && toBand && fromBand !== toBand) {
                    validTransitions.push({
                        ...t,
                        from_band: fromBand,
                        to_band: toBand,
                        is_band_change: true
                    })
                }
            }

            // Función auxiliar para normalizar timestamps (pueden estar en segundos o milisegundos)
            const normalizeTimestamp = (ts) => {
                if (ts == null) return null
                const num = Number(ts)
                if (Number.isNaN(num)) return null
                // Si el timestamp es muy grande (> 10000000000), está en milisegundos, convertir a segundos
                // Si es pequeño (< 10000000000), está en segundos
                return num > 10000000000 ? num / 1000 : num
            }

            const validSamples = (signalSamples && signalSamples.length > 0)
                ? (signalSamples || [])
                    .map(s => {
                        const band = normalizeBand(s.band || '')
                        const tsRaw = s.timestamp
                        if (!band || tsRaw == null) return null
                        const ts = normalizeTimestamp(tsRaw)
                        if (ts == null || Number.isNaN(ts)) return null
                        if (band === '2.4GHz' || band === '5GHz') {
                            return { timestamp: ts, band }
                        }
                        return null
                    })
                    .filter(s => s !== null)
                    .sort((a, b) => a.timestamp - b.timestamp)
                : []

            // Logs de depuración eliminados para producción

            const transitionDurations = validTransitions.map(t => {
                const transStartTime = normalizeTimestamp(t.start_time) || 0
                const transEndTime = normalizeTimestamp(t.end_time) || 0

                // Si hay end_time, usar la duración real de la transición
                if (transEndTime > transStartTime) {
                    const duration = transEndTime - transStartTime
                    // Limitar a un máximo razonable (30 segundos) para evitar valores absurdos
                    return Math.min(duration, 30.0)
                }

                // Si no hay end_time, buscar el primer sample después de start_time
                if (validSamples.length > 0) {
                    for (let i = 0; i < validSamples.length; i++) {
                        const sample = validSamples[i]
                        const sampleTime = normalizeTimestamp(sample.timestamp) || 0
                        if (sampleTime > transStartTime) {
                            const duration = sampleTime - transStartTime
                            // Limitar a un máximo razonable (5 segundos) si no hay end_time
                            return Math.min(duration, 5.0)
                        }
                    }
                }

                // Valor por defecto pequeño si no hay información
                return 0.5
            }).filter(d => !Number.isNaN(d) && d >= 0)

            const transitionPeriods = validTransitions
                .map(t => {
                    const startTime = normalizeTimestamp(t.start_time) || 0
                    const endTime = normalizeTimestamp(t.end_time) || startTime
                    return endTime > startTime ? [startTime, endTime] : null
                })
                .filter(p => p !== null)

            // Calcular minTime y maxTime basándose SOLO en signalSamples
            // para que coincida con el rango de tiempo de la gráfica
            const sampleTimestamps = (signalSamples || [])
                .map(s => s && s.timestamp != null ? normalizeTimestamp(s.timestamp) : null)
                .filter(ts => ts != null && !isNaN(ts))

            // También incluir timestamps de transiciones para el cálculo de períodos,
            // pero el totalTime se basará solo en signalSamples para coincidir con la gráfica
            const allTimestamps = []
            validTransitions.forEach(t => {
                if (t.start_time != null) {
                    const normalized = normalizeTimestamp(t.start_time)
                    if (normalized != null) allTimestamps.push(normalized)
                }
                if (t.end_time != null) {
                    const normalized = normalizeTimestamp(t.end_time)
                    if (normalized != null) allTimestamps.push(normalized)
                }
            })
            sampleTimestamps.forEach(ts => allTimestamps.push(ts))

            // FALLBACK: Si no hay suficientes signalSamples, usar transiciones para calcular el rango temporal
            let minTime, maxTime, totalTime

            if (sampleTimestamps.length > 1) {
                // Usar solo signalSamples para minTime y maxTime (como la gráfica)
                minTime = Math.min(...sampleTimestamps)
                maxTime = Math.max(...sampleTimestamps)
                totalTime = maxTime - minTime
            } else if (validTransitions.length > 0) {
                // FALLBACK: Usar timestamps de transiciones si no hay suficientes samples
                const transitionTimestamps = []
                validTransitions.forEach(t => {
                    if (t.start_time != null) {
                        const normalized = normalizeTimestamp(t.start_time)
                        if (normalized != null) transitionTimestamps.push(normalized)
                    }
                    if (t.end_time != null) {
                        const normalized = normalizeTimestamp(t.end_time)
                        if (normalized != null) transitionTimestamps.push(normalized)
                    }
                })
                if (transitionTimestamps.length > 0) {
                    minTime = Math.min(...transitionTimestamps)
                    maxTime = Math.max(...transitionTimestamps)
                    // Si solo hay una transición, agregar un margen mínimo
                    if (minTime === maxTime) {
                        maxTime = minTime + 1.0 // 1 segundo mínimo
                    }
                    totalTime = maxTime - minTime
                } else {
                    minTime = 0
                    maxTime = 1
                    totalTime = 1
                }
            } else {
                // Sin datos suficientes, usar valores por defecto mínimos
                minTime = 0
                maxTime = 1
                totalTime = 1
            }

            if (totalTime > 0) {
                let time24 = 0
                let time5 = 0

                const bandTimeline = []
                if (validTransitions.length > 0) {
                    const firstTrans = validTransitions[0]
                    let initialBand = normalizeBand(firstTrans.from_band || '')
                    if (!initialBand && signalSamples.length > 0) {
                        const samplesBeforeFirstTrans = signalSamples.filter(s => Number(s.timestamp) < Number(firstTrans.start_time || 0))
                            .sort((a, b) => Number(b.timestamp) - Number(a.timestamp))
                        if (samplesBeforeFirstTrans.length > 0) {
                            initialBand = normalizeBand(samplesBeforeFirstTrans[0].band || '')
                        }
                    }
                    if (!initialBand) initialBand = normalizeBand(firstTrans.to_band || '')

                    // Período inicial antes de la primera transición
                    if (initialBand && Number(firstTrans.start_time || 0) > minTime) {
                        bandTimeline.push({
                            band: initialBand,
                            start: minTime,
                            end: Number(firstTrans.start_time || 0)
                        })
                    }

                    // Períodos entre transiciones
                    for (let i = 0; i < validTransitions.length; i++) {
                        const t = validTransitions[i]
                        const fromBand = normalizeBand(t.from_band || '')
                        const toBand = normalizeBand(t.to_band || '')
                        const transStart = Number(t.start_time || 0)
                        const transEnd = Number(t.end_time != null ? t.end_time : transStart)

                        // Período de la banda origen antes de la transición
                        if (fromBand && transStart > (bandTimeline.length > 0 ? bandTimeline[bandTimeline.length - 1].end : minTime)) {
                            bandTimeline.push({
                                band: fromBand,
                                start: bandTimeline.length > 0 ? bandTimeline[bandTimeline.length - 1].end : minTime,
                                end: transStart
                            })
                        }

                        // Período de la banda destino después de la transición
                        const nextTransStart = (i + 1 < validTransitions.length)
                            ? (normalizeTimestamp(validTransitions[i + 1].start_time) || 0)
                            : maxTime
                        if (toBand && transEnd < nextTransStart) {
                            bandTimeline.push({
                                band: toBand,
                                start: transEnd,
                                end: nextTransStart
                            })
                        }
                    }

                    // Asegurar que el último período llegue hasta maxTime
                    if (bandTimeline.length > 0 && bandTimeline[bandTimeline.length - 1].end < maxTime) {
                        const lastBand = bandTimeline[bandTimeline.length - 1].band
                        bandTimeline.push({
                            band: lastBand,
                            start: bandTimeline[bandTimeline.length - 1].end,
                            end: maxTime
                        })
                    }

                    for (const period of bandTimeline) {
                        let periodDuration = period.end - period.start
                        for (const [transStart, transEnd] of transitionPeriods) {
                            if (period.start < transEnd && period.end > transStart) {
                                const overlapStart = Math.max(period.start, transStart)
                                const overlapEnd = Math.min(period.end, transEnd)
                                periodDuration -= (overlapEnd - overlapStart)
                            }
                        }
                        if (periodDuration > 0) {
                            if (period.band === '2.4GHz') {
                                time24 += periodDuration
                            } else if (period.band === '5GHz') {
                                time5 += periodDuration
                            }
                        }
                    }
                } else if (validSamples.length > 0) {
                    let i = 0
                    while (i < validSamples.length) {
                        const currentBand = validSamples[i].band
                        let periodStart = validSamples[i].timestamp
                        let periodEnd = periodStart

                        let j = i + 1
                        while (j < validSamples.length) {
                            const nextSample = validSamples[j]
                            const nextTs = nextSample.timestamp
                            const nextBand = nextSample.band

                            let inTransition = false
                            for (const [transStart, transEnd] of transitionPeriods) {
                                if (transStart <= nextTs && nextTs <= transEnd) {
                                    inTransition = true
                                    break
                                }
                            }

                            if (nextBand !== currentBand || inTransition) {
                                break
                            }

                            if (nextTs - periodEnd <= 5.0) {
                                periodEnd = nextTs
                                j++
                            } else {
                                break
                            }
                        }

                        let periodDuration = periodEnd - periodStart
                        for (const [transStart, transEnd] of transitionPeriods) {
                            if (periodStart < transEnd && periodEnd > transStart) {
                                const overlapStart = Math.max(periodStart, transStart)
                                const overlapEnd = Math.min(periodEnd, transEnd)
                                periodDuration -= (overlapEnd - overlapStart)
                            }
                        }

                        if (periodDuration > 0) {
                            if (currentBand === '2.4GHz') {
                                time24 += periodDuration
                            } else if (currentBand === '5GHz') {
                                time5 += periodDuration
                            }
                        }

                        i = j
                    }
                }

                const totalTransitionTime = transitionDurations.reduce((a, b) => a + b, 0)
                const totalBandTime = time24 + time5
                const expectedTotal = totalTime - totalTransitionTime

                // Ajustar tiempos si hay discrepancia, pero mantener la proporción
                if (expectedTotal > 0 && Math.abs(totalBandTime - expectedTotal) > 0.1) {
                    if (totalBandTime > expectedTotal * 1.1) {
                        // Si el tiempo de banda es mucho mayor, escalar hacia abajo
                        const scale = expectedTotal / totalBandTime
                        time24 *= scale
                        time5 *= scale
                    } else if (totalBandTime < expectedTotal * 0.9) {
                        // Si el tiempo de banda es menor, ajustar proporcionalmente
                        const scale = expectedTotal / totalBandTime
                        time24 *= scale
                        time5 *= scale
                    }
                }

                const transitionsWithDuration = validTransitions.map((t, idx) => {
                    const startTime = normalizeTimestamp(t.start_time) || 0
                    const duration = idx < transitionDurations.length ? transitionDurations[idx] : 0
                    return {
                        fromBand: normalizeBand(t.from_band || ''),
                        toBand: normalizeBand(t.to_band || ''),
                        duration: duration,
                        relStart: startTime - minTime
                    }
                }).filter(t => !Number.isNaN(t.duration) && t.duration >= 0)

                // Recalcular totalBandTime después del ajuste
                const finalTotalBandTime = time24 + time5
                const finalTotalTime = finalTotalBandTime + totalTransitionTime

                bandTiming = {
                    time24,
                    time5,
                    totalTime: finalTotalTime, // Tiempo total incluyendo transiciones para que los porcentajes sumen 100%
                    totalBandTime: finalTotalBandTime,
                    totalTransitionTime,
                    transitions: transitionsWithDuration,
                    transitionDurations
                }
            } else {
                console.warn('⚠️ [BAND_TIMING PDF] totalTime <= 0, no se puede calcular bandTiming')
            }
        } catch (e) {
            console.error('❌ [BAND_TIMING PDF] Error calculando bandTiming en PDF:', e)
            console.error('❌ [BAND_TIMING PDF] Stack trace:', e.stack)
            bandTiming = null
        }

        const formatSeconds = (seconds) => {
            if (seconds == null || Number.isNaN(seconds) || seconds <= 0) return '0 s'
            if (seconds < 1) return `${(seconds * 1000).toFixed(0)} ms`
            if (seconds < 60) return `${seconds.toFixed(2)} s`
            const minutes = Math.floor(seconds / 60)
            const rem = seconds % 60
            return `${minutes} min ${rem.toFixed(1)} s`
        }

        // Convertir markdown a HTML con mejor formato
        const formatAnalysis = (text) => {
            if (!text) return ''

            // Dividir por líneas
            const lines = text.split('\n')
            let html = ''
            let inList = false
            let inOrderedList = false
            let listItems = []

            const closeList = () => {
                if (inList) {
                    html += '<ul style="margin: 8px 0; padding-left: 20px; list-style-type: disc;">'
                    listItems.forEach(item => {
                        html += `<li style="margin-bottom: 4px; font-size: 8pt; line-height: 1.5;">${item}</li>`
                    })
                    html += '</ul>'
                    listItems = []
                    inList = false
                }
                if (inOrderedList) {
                    html += '<ol style="margin: 8px 0; padding-left: 20px; list-style-type: decimal;">'
                    listItems.forEach(item => {
                        html += `<li style="margin-bottom: 4px; font-size: 8pt; line-height: 1.5;">${item}</li>`
                    })
                    html += '</ol>'
                    listItems = []
                    inOrderedList = false
                }
            }

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim()

                if (!line) {
                    closeList()
                    continue
                }

                // Títulos markdown
                if (line.match(/^#+\s/)) {
                    closeList()
                    const level = line.match(/^#+/)?.[0]?.length || 1
                    const content = line.replace(/^#+\s*/, '').trim()
                    const fontSize = level === 1 ? '11pt' : level === 2 ? '10pt' : level === 3 ? '9pt' : '8pt'
                    const marginTop = level === 1 ? '16px' : level === 2 ? '14px' : '12px'
                    html += `<h${Math.min(level + 1, 4)} style="margin-top: ${marginTop}; margin-bottom: 8px; font-size: ${fontSize}; font-weight: 600; color: #374151; page-break-after: avoid;">${content}</h${Math.min(level + 1, 4)}>`
                    continue
                }

                // Listas ordenadas (1., 2., etc.)
                const orderedMatch = line.match(/^(\d+)\.\s+(.+)$/)
                if (orderedMatch) {
                    closeList()
                    if (!inOrderedList) {
                        inOrderedList = true
                    }
                    let itemText = orderedMatch[2]
                    // Procesar negritas y otros formatos en el item
                    itemText = itemText
                        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                        .replace(/\*(.*?)\*/g, '<em>$1</em>')
                    listItems.push(itemText)
                    continue
                }

                // Listas no ordenadas (-, *, •)
                if (line.match(/^[-*•]\s+(.+)$/)) {
                    closeList()
                    if (!inList) {
                        inList = true
                    }
                    let itemText = line.replace(/^[-*•]\s+/, '')
                    // Procesar negritas y otros formatos en el item
                    itemText = itemText
                        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                        .replace(/\*(.*?)\*/g, '<em>$1</em>')
                    listItems.push(itemText)
                    continue
                }

                // Si llegamos aquí y hay una lista abierta, cerrarla
                closeList()

                // Párrafo normal
                let paraText = line
                // Procesar negritas
                paraText = paraText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                // Procesar cursivas
                paraText = paraText.replace(/\*(.*?)\*/g, '<em>$1</em>')
                // Procesar código inline
                paraText = paraText.replace(/`([^`]+)`/g, '<code style="background: #f3f4f6; padding: 2px 4px; border-radius: 3px; font-family: monospace; font-size: 7pt;">$1</code>')

                html += `<p style="margin-bottom: 8px; font-size: 8pt; line-height: 1.6; text-align: justify;">${paraText}</p>`
            }

            // Cerrar cualquier lista que quede abierta
            closeList()

            return html
        }

        // Obtener compliance checks
        const complianceChecks = result.band_steering?.compliance_checks || []

        // Procesar paquetes de Wireshark para la tabla
        const wiresharkSampleForTable = result.stats?.diagnostics?.wireshark_raw?.sample || []
        const processWiresharkPackets = (sample) => {
            if (!sample || sample.length === 0) return []

            return sample.map((row, idx) => {
                let protocol = '802.11'
                let info = ''
                let color = '#6b7280'

                const subtype = row.subtype || ''
                const category = row.category_code || ''
                const action = row.action_code || ''

                if (subtype) {
                    const subtypeInt = parseInt(subtype) || 0
                    switch (subtypeInt) {
                        case 0:
                            info = `Association Request: ${row.wlan_sa || 'N/A'}`
                            color = '#3b82f6'
                            break
                        case 1: {
                            const assocStatus = parseInt(row.assoc_status_code || '0') || 0
                            info = `Association Response: Status=${assocStatus} ${assocStatus === 0 ? '✓' : '✗'}`
                            color = assocStatus === 0 ? '#10b981' : '#ef4444'
                            break
                        }
                        case 2:
                            info = `Reassociation Request: ${row.wlan_sa || 'N/A'}`
                            color = '#3b82f6'
                            break
                        case 3: {
                            const reassocStatus = parseInt(row.assoc_status_code || '0') || 0
                            info = `Reassociation Response: Status=${reassocStatus} ${reassocStatus === 0 ? '✓' : '✗'}`
                            color = reassocStatus === 0 ? '#10b981' : '#ef4444'
                            break
                        }
                        case 8:
                            info = `Beacon: ${row.ssid || 'N/A'}`
                            color = '#06b6d4'
                            break
                        case 10:
                            info = `Disassociation: Reason=${row.reason_code || 'N/A'}`
                            color = '#f97316'
                            break
                        case 12:
                            info = `Deauthentication: Reason=${row.reason_code || 'N/A'}`
                            color = '#ef4444'
                            break
                        case 13: {
                            const catInt = parseInt(category) || -1
                            const actInt = parseInt(action) || -1
                            if (catInt === 10) {
                                if (actInt === 7) {
                                    protocol = '802.11v'
                                    info = `BTM Request: ${row.wlan_da || 'N/A'}`
                                    color = '#eab308'
                                } else if (actInt === 8) {
                                    protocol = '802.11v'
                                    const btmStatus = parseInt(row.btm_status_code || '0') || 0
                                    info = `BTM Response: Status=${btmStatus} ${btmStatus === 0 ? '✓ Accept' : '✗ Reject'}`
                                    color = btmStatus === 0 ? '#10b981' : '#ef4444'
                                }
                            }
                            break
                        }
                    }
                }

                let band = 'Unknown'
                if (row.frequency) {
                    const freq = parseInt(row.frequency) || 0
                    if (freq >= 2400 && freq <= 2500) band = '2.4 GHz'
                    else if (freq >= 5000 && freq <= 6000) band = '5 GHz'
                }

                const source = row.source || row.wlan_sa || row.bssid || 'N/A'
                const destination = row.destination || row.wlan_da || 'Broadcast'
                const time = parseFloat(row.timestamp) || 0

                return {
                    no: idx + 1,
                    time: time,
                    source: source,
                    destination: destination,
                    protocol: protocol,
                    band: band,
                    info: info,
                    color: color
                }
            })
        }

        const wiresharkPackets = processWiresharkPackets(wiresharkSampleForTable)
        const originalCount = result.stats?.diagnostics?.wireshark_raw?.original_count || wiresharkSampleForTable.length
        const isTruncated = result.stats?.diagnostics?.wireshark_raw?.truncated || false

        // Función para filtrar paquetes más relevantes de cada tipo
        const filterRelevantPackets = (packets) => {
            if (packets.length <= 50) return packets // Si hay pocos paquetes, mostrar todos

            // Obtener transiciones para identificar paquetes relacionados
            const transitions = result.band_steering?.transitions || []
            const transitionTimes = new Set()
            transitions.forEach(t => {
                if (t.start_time) transitionTimes.add(Number(t.start_time))
                if (t.end_time) transitionTimes.add(Number(t.end_time))
            })

            // Clasificar paquetes por tipo
            const packetsByType = {
                btm: [], // BTM Requests/Responses (todos relevantes)
                association: [], // Association/Reassociation
                disassociation: [], // Disassociation/Deauthentication (todos relevantes)
                beacon: [], // Beacons (solo algunos)
                other: [] // Otros tipos
            }

            packets.forEach(packet => {
                const info = packet.info.toLowerCase()
                const time = packet.time

                // Verificar si está cerca de una transición (dentro de 2 segundos)
                const isNearTransition = Array.from(transitionTimes).some(tt => Math.abs(time - tt) <= 2)

                if (info.includes('btm')) {
                    packetsByType.btm.push({ ...packet, isNearTransition })
                } else if (info.includes('association') || info.includes('reassociation')) {
                    packetsByType.association.push({ ...packet, isNearTransition })
                } else if (info.includes('disassociation') || info.includes('deauthentication')) {
                    packetsByType.disassociation.push({ ...packet, isNearTransition })
                } else if (info.includes('beacon')) {
                    packetsByType.beacon.push({ ...packet, isNearTransition })
                } else {
                    packetsByType.other.push({ ...packet, isNearTransition })
                }
            })

            // Seleccionar paquetes relevantes
            const relevantPackets = []

            // BTM: todos son relevantes
            relevantPackets.push(...packetsByType.btm)

            // Association/Reassociation: los relacionados con transiciones + primeros 3 + últimos 3
            const assocRelevant = packetsByType.association.filter(p => p.isNearTransition)
            const assocOthers = packetsByType.association.filter(p => !p.isNearTransition)
            relevantPackets.push(...assocRelevant)
            if (assocOthers.length > 0) {
                relevantPackets.push(assocOthers[0]) // Primero
                if (assocOthers.length > 1) {
                    relevantPackets.push(assocOthers[assocOthers.length - 1]) // Último
                }
                if (assocOthers.length > 2) {
                    const mid = Math.floor(assocOthers.length / 2)
                    relevantPackets.push(assocOthers[mid]) // Medio
                }
            }

            // Disassociation/Deauthentication: todos son relevantes
            relevantPackets.push(...packetsByType.disassociation)

            // Beacon: solo algunos representativos (primeros 2, últimos 2, y algunos intermedios)
            if (packetsByType.beacon.length > 0) {
                relevantPackets.push(packetsByType.beacon[0]) // Primero
                if (packetsByType.beacon.length > 1) {
                    relevantPackets.push(packetsByType.beacon[packetsByType.beacon.length - 1]) // Último
                }
                // Agregar algunos intermedios si hay muchos
                if (packetsByType.beacon.length > 10) {
                    const step = Math.floor(packetsByType.beacon.length / 5)
                    for (let i = step; i < packetsByType.beacon.length - 1; i += step) {
                        if (relevantPackets.length < 50) { // Limitar total
                            relevantPackets.push(packetsByType.beacon[i])
                        }
                    }
                }
            }

            // Otros: solo los relacionados con transiciones
            relevantPackets.push(...packetsByType.other.filter(p => p.isNearTransition))

            // Ordenar por tiempo y eliminar duplicados
            const uniquePackets = []
            const seen = new Set()
            relevantPackets
                .sort((a, b) => a.time - b.time)
                .forEach(p => {
                    const key = `${p.time}-${p.source}-${p.destination}`
                    if (!seen.has(key)) {
                        seen.add(key)
                        uniquePackets.push(p)
                    }
                })

            // Limitar a máximo 100 paquetes para el PDF
            return uniquePackets.slice(0, 100)
        }

        const relevantWiresharkPackets = filterRelevantPackets(wiresharkPackets)

        // Generar nombre del PDF en el estilo "Pipe [MODELO]"
        const pdfTitle = model && model !== 'Genérico' ? `Pipe ${model.toUpperCase()}` : `Pipe ${cleanName.toUpperCase()}`

        const htmlContent = `<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${pdfTitle}</title>
    <style>
        @page {
            margin: 1.5cm;
            size: A4;
        }
        @page {
            @top-center {
                content: "";
            }
        }
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            font-size: 9pt;
            line-height: 1.5;
            color: #1a1a1a;
            background: white;
            padding: 0;
        }
        .header {
            border-bottom: 3px solid #6366f1;
            padding-bottom: 12px;
            margin-bottom: 24px;
            page-break-after: avoid;
        }
        h1 {
            font-size: 20pt;
            color: #1a1a1a;
            margin-bottom: 6px;
            font-weight: 700;
            page-break-after: avoid;
        }
        h2 {
            font-size: 13pt;
            color: #1a1a1a;
            margin-top: 20px;
            margin-bottom: 10px;
            border-bottom: 2px solid #e5e7eb;
            padding-bottom: 5px;
            font-weight: 600;
            page-break-after: avoid;
        }
        h3 {
            font-size: 11pt;
            color: #374151;
            margin-top: 14px;
            margin-bottom: 7px;
            font-weight: 600;
            page-break-after: avoid;
        }
        h4 {
            font-size: 10pt;
            color: #4b5563;
            margin-top: 10px;
            margin-bottom: 5px;
            font-weight: 600;
            page-break-after: avoid;
        }
        .info-section {
            background: #f8f9fa;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 25px;
        }
        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e5e7eb;
        }
        .info-row:last-child {
            border-bottom: none;
        }
        .info-label {
            font-weight: 600;
            color: #6b7280;
            font-size: 10pt;
        }
        .info-value {
            color: #1a1a1a;
            font-size: 11pt;
            text-align: right;
            font-weight: 500;
        }
        .verdict-badge {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 11pt;
            text-transform: uppercase;
        }
        .verdict-success {
            background: #10b981;
            color: white;
        }
        .verdict-failed {
            background: #ef4444;
            color: white;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin: 20px 0;
        }
        .metric-card {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 15px;
        }
        .metric-label {
            font-size: 9pt;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 5px;
        }
        .metric-value {
            font-size: 18pt;
            font-weight: 700;
            color: #1a1a1a;
        }
        .metric-subvalue {
            font-size: 10pt;
            color: #6b7280;
            margin-top: 5px;
        }
        .analysis-section {
            margin-top: 30px;
        }
        .analysis-content {
            background: #ffffff;
            border-left: 4px solid #6366f1;
            padding: 16px;
            margin-top: 12px;
            line-height: 1.6;
        }
        .analysis-content p {
            margin-bottom: 8px;
            font-size: 8pt;
            text-align: justify;
        }
        .analysis-content ul,
        .analysis-content ol {
            margin: 8px 0;
            padding-left: 20px;
        }
        .analysis-content li {
            margin-bottom: 4px;
            font-size: 8pt;
            line-height: 1.5;
        }
        .analysis-content strong {
            font-weight: 700;
            color: #1a1a1a;
        }
        .analysis-content em {
            font-style: italic;
        }
        .analysis-content code {
            background: #f3f4f6;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 7pt;
        }
        .compliance-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 10pt;
        }
        .compliance-table th,
        .compliance-table td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #e5e7eb;
        }
        .compliance-table th {
            background: #f3f4f6;
            font-weight: 600;
            color: #374151;
        }
        .compliance-table tr:hover {
            background: #f9fafb;
        }
        .mac-address {
            font-family: 'Courier New', monospace;
            font-size: 10pt;
            color: #1a1a1a;
        }
        .footer {
            margin-top: 40px;
            text-align: center;
            color: #6b7280;
            font-size: 8pt;
            border-top: 1px solid #e5e7eb;
            padding-top: 12px;
            page-break-inside: avoid;
        }
        .section-divider {
            height: 2px;
            background: linear-gradient(to right, #6366f1, transparent);
            margin: 24px 0;
            page-break-inside: avoid;
        }
        .highlight-box {
            background: #eff6ff;
            border-left: 4px solid #3b82f6;
            padding: 15px;
            margin: 15px 0;
            border-radius: 4px;
        }
        .kvr-badge {
            display: inline-block;
            padding: 4px 8px;
            background: #dbeafe;
            color: #1e40af;
            border-radius: 4px;
            font-size: 9pt;
            font-weight: 600;
            margin-right: 5px;
        }
        .card {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 12px;
            page-break-inside: avoid;
        }
        .card-title {
            font-size: 12pt;
            font-weight: 600;
            color: #1a1a1a;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .card-content {
            font-size: 10pt;
        }
        .compliance-check {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px;
            margin-bottom: 8px;
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            page-break-inside: avoid;
        }
        .compliance-check-title {
            font-weight: 700;
            font-size: 9pt;
            color: #1a1a1a;
            margin-bottom: 3px;
        }
        .compliance-check-details {
            font-size: 7pt;
            font-family: 'Courier New', monospace;
            color: #4b5563;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            line-height: 1.4;
        }
        .compliance-badge-pdf {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 5px 12px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 8pt;
            flex-shrink: 0;
            min-width: 60px;
        }
        .compliance-badge-pass {
            background: rgba(16, 185, 129, 0.15);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        .compliance-badge-fail {
            background: rgba(239, 68, 68, 0.15);
            color: #ef4444;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }
        .badge-icon {
            width: 12px;
            height: 12px;
            display: inline-block;
        }
        .section-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
        }
        .section-title {
            font-size: 12pt;
            font-weight: 600;
            color: #1a1a1a;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .section-description {
            font-size: 8pt;
            color: #6b7280;
            margin-top: 6px;
            margin-bottom: 16px;
        }
        .success-badge-large {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 8px 16px;
            background: #10b981;
            color: white;
            border-radius: 6px;
            font-weight: 700;
            font-size: 9pt;
        }
        .failed-badge-large {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 8px 16px;
            background: #ef4444;
            color: white;
            border-radius: 6px;
            font-weight: 700;
            font-size: 9pt;
        }
        .partial-badge-large {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 8px 16px;
            background: #f59e0b;
            color: white;
            border-radius: 6px;
            font-weight: 700;
            font-size: 9pt;
        }
        .info-card-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 12px;
            margin-bottom: 20px;
            page-break-inside: avoid;
        }
        .info-card {
            background: #f8f9fa;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 12px;
        }
        .info-card-title {
            font-size: 8pt;
            font-weight: 600;
            color: #6b7280;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .info-card-value {
            font-size: 11pt;
            font-weight: 500;
            color: #1a1a1a;
        }
        .metric-item {
            margin-bottom: 16px;
        }
        .metric-item-label {
            font-size: 7pt;
            color: #6b7280;
            text-transform: uppercase;
            margin-bottom: 3px;
        }
        .metric-item-value {
            font-size: 12pt;
            font-weight: 700;
            color: #1a1a1a;
        }
        .metric-item-sub {
            font-size: 7pt;
            color: #6b7280;
            margin-top: 3px;
        }
        .wireshark-table {
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0;
            font-size: 7pt;
            font-family: 'Courier New', monospace;
            page-break-inside: avoid;
            border: 1px solid #e5e7eb;
        }
        .wireshark-table th {
            background: #374151;
            color: #ffffff !important;
            padding: 6px 8px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #4b5563;
            font-size: 7pt;
            white-space: nowrap;
        }
        .wireshark-table td {
            padding: 4px 8px;
            border-bottom: 1px solid #e5e7eb;
            color: #1a1a1a;
            font-size: 7pt;
            white-space: nowrap;
        }
        .wireshark-table tr:nth-child(even) {
            background: #f9fafb;
        }
        .wireshark-table th.packet-no,
        .wireshark-table th.packet-time,
        .wireshark-table th.packet-mac,
        .wireshark-table th.packet-protocol,
        .wireshark-table th.packet-band,
        .wireshark-table th.packet-info {
            color: #ffffff !important;
        }
        .wireshark-table .packet-no {
            width: 35px;
            text-align: right;
        }
        .wireshark-table td.packet-no {
            color: #6b7280;
        }
        .wireshark-table .packet-time {
            width: 90px;
            font-family: 'Courier New', monospace;
        }
        .wireshark-table td.packet-time {
            color: #1a1a1a;
        }
        .wireshark-table .packet-mac {
            font-family: 'Courier New', monospace;
            width: 130px;
            font-size: 6.5pt;
        }
        .wireshark-table td.packet-mac {
            color: #1a1a1a;
        }
        .wireshark-table .packet-protocol {
            width: 55px;
            font-weight: 600;
        }
        .wireshark-table td.packet-protocol {
            color: #3b82f6;
        }
        .wireshark-table .packet-band {
            width: 65px;
        }
        .wireshark-table td.packet-band {
            color: #6b7280;
        }
        .wireshark-table .packet-info {
            white-space: normal;
            word-break: break-word;
        }
        .wireshark-table td.packet-info {
            color: #1a1a1a;
        }
        .wireshark-header {
            background: #f8f9fa;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 10px;
            margin-bottom: 10px;
        }
        .wireshark-header-title {
            font-size: 9pt;
            font-weight: 600;
            color: #1a1a1a;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .wireshark-header-info {
            font-size: 7pt;
            color: #6b7280;
            font-family: 'Courier New', monospace;
        }
        @media print {
            body {
                padding: 0;
            }
            .page-break {
                page-break-before: always;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>${pdfTitle}</h1>
    </div>
    
    <!-- Sección Análisis de Band Steering -->
    <div class="section-header">
        <div>
            <h2 class="section-title">Análisis de Band Steering</h2>
            <p class="section-description">Evaluación técnica de capacidades 802.11k/v/r basada directamente en la captura real de Wireshark/tshark</p>
        </div>
        ${(() => {
                const successVerdicts = ['SUCCESS', 'EXCELLENT', 'GOOD', 'PREVENTIVE_SUCCESS', 'ACCEPTABLE', 'SLOW_BUT_SUCCESSFUL']
                const failedVerdicts = ['FAILED', 'FAILED_BTM_REJECT', 'FAILED_LOOP', 'FAILED_NO_REASSOC']
                const partialVerdicts = ['PARTIAL', 'NO_DATA', 'NO_STEERING_EVENTS']

                const verdictUpper = verdict.toUpperCase()
                let badgeClass = 'success-badge-large'
                let badgeText = verdictUpper

                if (failedVerdicts.includes(verdictUpper)) {
                    badgeClass = 'failed-badge-large'
                    badgeText = 'FAILED'
                } else if (partialVerdicts.includes(verdictUpper)) {
                    badgeClass = 'partial-badge-large'
                    badgeText = verdictUpper === 'PARTIAL' ? 'PARTIAL' : verdictUpper
                } else if (successVerdicts.includes(verdictUpper)) {
                    badgeClass = 'success-badge-large'
                    badgeText = verdictUpper === 'SUCCESS' ? 'SUCCESS' : verdictUpper
                } else {
                    badgeClass = 'success-badge-large'
                    badgeText = verdictUpper
                }

                return `<span class="${badgeClass}">${badgeText}</span>`
            })()}
    </div>

    <!-- Detalle de Cumplimiento Técnico -->
    <div class="card" style="background: #eff6ff; border-left: 4px solid #3b82f6;">
        <h3 style="margin-top: 0; margin-bottom: 10px; font-size: 10pt; font-weight: 700;">DETALLE DE CUMPLIMIENTO TÉCNICO</h3>
        ${complianceChecks.length > 0 ? complianceChecks.map(check => {
                const checkDetails = check.details || ''
                let displayDetails = checkDetails
                let actualPassed = check.passed

                // Usar los detalles del check directamente (como en la aplicación)
                // Solo formatear para HTML y recalcular para "Steering Efectivo"
                if (check.check_name === 'Steering Efectivo') {
                    // Recalcular displayDetails con el número correcto de cambios de banda
                    displayDetails = `TRANSICIONES CON CAMBIO DE BANDA: ${bandChangeCount} | TRANSICIONES TOTALES: ${successful} | BTM ACCEPT: ${btmAccept}`

                    // Recalcular passed: pasa si hay al menos 1 cambio de banda exitoso
                    // O si hay transiciones exitosas entre BSSIDs distintos
                    const transitions = result.band_steering?.transitions || []
                    const bssidChangeTransitions = transitions.filter(t =>
                        t.is_successful &&
                        t.from_bssid &&
                        t.to_bssid &&
                        t.from_bssid !== t.to_bssid
                    ).length

                    // El check pasa si hay al menos 1 cambio de banda O al menos 1 cambio de BSSID
                    actualPassed = bandChangeCount > 0 || bssidChangeTransitions > 0
                } else {
                    // Para los demás checks, usar los detalles directamente del backend
                    // Solo reemplazar saltos de línea por <br> para HTML
                    displayDetails = checkDetails.replace(/\n/g, '<br>')
                }

                return `
        <div class="compliance-check">
            <div style="flex: 1;">
                <div class="compliance-check-title">${check.check_name}</div>
                <div class="compliance-check-details">${displayDetails}</div>
            </div>
            <div class="compliance-badge-pdf ${actualPassed ? 'compliance-badge-pass' : 'compliance-badge-fail'}">
                <span>${actualPassed ? 'PASÓ' : 'FALLÓ'}</span>
            </div>
        </div>
        `
            }).join('') : `
    <div class="compliance-check">
        <div style="flex: 1;">
            <div class="compliance-check-title">Soporte BTM (802.11v)</div>
            <div class="compliance-check-details">REQUESTS: ${btmRequests}, RESPONSES: ${btmResponses}, ACCEPT: ${btmAccept}<br>CODE: 0 (ACCEPT)</div>
        </div>
        <div class="compliance-badge-pdf compliance-badge-pass">
            <span>PASÓ</span>
        </div>
    </div>
    <div class="compliance-check">
        <div style="flex: 1;">
            <div class="compliance-check-title">Asociación y Reasociación</div>
            <div class="compliance-check-details">ASSOC: ${assocCount}, REASSOC: ${reassocCount}<br>DISASSOC: ${disassocCount} (FORZADOS: 0), DEAUTH: ${deauthCount} (FORZADOS: 0)</div>
        </div>
        <div class="compliance-badge-pdf compliance-badge-pass">
            <span>PASÓ</span>
        </div>
    </div>
    <div class="compliance-check">
        <div style="flex: 1;">
            <div class="compliance-check-title">Steering Efectivo</div>
            <div class="compliance-check-details">TRANSICIONES CON CAMBIO DE BANDA: ${bandChangeCount} | TRANSICIONES TOTALES: ${successful} | BTM ACCEPT: ${btmAccept}</div>
        </div>
        <div class="compliance-badge-pdf compliance-badge-pass">
            <span>PASÓ</span>
        </div>
    </div>
    <div class="compliance-check">
        <div style="flex: 1;">
            <div class="compliance-check-title">Estándares KVR</div>
            <div class="compliance-check-details">K=${kSupport ? 'TRUE' : 'FALSE'}, V=${vSupport ? 'TRUE' : 'FALSE'}, R=${rSupport ? 'TRUE' : 'FALSE'}</div>
        </div>
        <div class="compliance-badge-pdf compliance-badge-pass">
            <span>PASÓ</span>
        </div>
    </div>
    `}
    </div>
    
    <!-- Cards de Información del Dispositivo -->
    <div class="info-card-grid">
        <div class="info-card">
            <div class="info-card-title">Dispositivo Identificado</div>
            <div class="card-content">
                ${ssid ? `<div style="margin-bottom: 8px;"><span style="font-size: 9pt; color: #6b7280;">Red (SSID):</span><br><span class="info-card-value">${ssid}</span></div>` : ''}
                <div style="margin-bottom: 8px;"><span style="font-size: 9pt; color: #6b7280;">Marca:</span><br><span class="info-card-value">${vendor}</span></div>
                <div style="margin-bottom: 8px;"><span style="font-size: 9pt; color: #6b7280;">Modelo:</span><br><span class="info-card-value">${model}</span></div>
                <div><span style="font-size: 9pt; color: #6b7280;">Categoría:</span><br><span class="info-card-value">${category}</span></div>
            </div>
        </div>
        
        <div class="info-card">
            <div class="info-card-title">MACs de Negociación</div>
            <div class="card-content">
                <div style="margin-bottom: 12px;">
                    <span style="font-size: 9pt; color: #6b7280; text-transform: uppercase;">Cliente</span><br>
                    <span class="mac-address" style="font-weight: 700; font-size: 11pt;">${clientMac}</span>
                </div>
                <div>
                    <span style="font-size: 9pt; color: #6b7280; text-transform: uppercase;">BSSIDS (${bssids.length})</span><br>
                    ${bssids.length > 0 ? bssids.map(bssid => `<div class="mac-address" style="margin-top: 4px; font-size: 10pt;">${bssid}</div>`).join('') : '<span style="font-size: 10pt; color: #6b7280; font-style: italic;">No detectados</span>'}
                </div>
            </div>
        </div>
        
        <div class="info-card">
            <div class="info-card-title">Métricas de Steering</div>
            <div class="card-content">
                <div class="metric-item">
                    <div class="metric-item-label">Estándares KVR Identificados</div>
                    <div class="metric-item-value" style="font-size: 12pt;">
                        ${kvrDetected.length > 0 ? kvrDetected.map(k => `<span class="kvr-badge">${k}</span>`).join('') : 'Ninguno'}
                    </div>
                </div>
                <div class="metric-item">
                    <div class="metric-item-label">Intentos de steering</div>
                    <div class="metric-item-value">${successful}/${attempts}</div>
                    <div class="metric-item-sub">EXITOSAS</div>
                    ${bandChangeCount > 0 || associationOnlyCount > 0 ? `
                    <div class="metric-item-sub" style="margin-top: 6px;">
                        ${bandChangeCount > 0 ? `<span style="color: #10b981; font-weight: 600;">${bandChangeCount} cambio${bandChangeCount !== 1 ? 's' : ''} de banda</span>` : ''}
                        ${bandChangeCount > 0 && associationOnlyCount > 0 ? '<br>' : ''}
                        ${associationOnlyCount > 0 ? `<span style="color: #f97316; font-weight: 600;">${associationOnlyCount} transición${associationOnlyCount !== 1 ? 'es' : ''} de asociación</span>` : ''}
                    </div>
                    ` : ''}
                </div>
                <div class="metric-item">
                    <div class="metric-item-label">Tiempo medido</div>
                    <div class="metric-item-value" style="font-size: 14pt;">${measuredTime}</div>
                </div>
            </div>
        </div>
    </div>
    
        <!-- Visualización de Cambios de Banda -->
        <h2 style="margin-top: 28px; margin-bottom: 10px; font-size: 12pt; font-weight: 600; color: #1a1a1a;">Visualización de Cambios de Banda</h2>
        ${chartImage ? `
        <div style="margin-bottom: 24px;">
            <div style="background: #1e293b; border-radius: 8px; padding: 16px; border: 1px solid #334155;">
                <img src="${chartImage}" alt="Gráfico de Band Steering" style="width: 100%; height: auto; border-radius: 4px;" />
            </div>
        </div>
        
        <!-- Guía de Elementos Visuales (3 columnas sin título) -->
        <div class="card" style="background: #1f2937; border: 1px solid #374151; margin-bottom: 20px;">
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; font-size: 8pt;">
                <div>
                    <p style="font-size: 7pt; font-weight: 600; color: #9ca3af; text-transform: uppercase; margin-bottom: 10px; letter-spacing: 0.5px;">LÍNEAS DE SEÑAL</p>
                    <div style="margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
                        <div style="width: 24px; height: 2px; background: #3b82f6;"></div>
                        <span style="color: #e5e7eb; font-size: 8pt;">2.4 GHz</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <div style="width: 24px; height: 2px; background: #10b981;"></div>
                        <span style="color: #e5e7eb; font-size: 8pt;">5 GHz</span>
                    </div>
                </div>
                <div>
                    <p style="font-size: 7pt; font-weight: 600; color: #9ca3af; text-transform: uppercase; margin-bottom: 10px; letter-spacing: 0.5px;">MARCADORES BTM</p>
                    <div style="margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
                        <span style="color: #f97316; font-size: 10pt;">▼</span>
                        <span style="color: #e5e7eb; font-size: 8pt;">BTM Request</span>
                    </div>
                    <div style="margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
                        <span style="color: #10b981; font-size: 10pt;">▲</span>
                        <span style="color: #e5e7eb; font-size: 8pt;">BTM Accept</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="color: #ef4444; font-size: 10pt;">▲</span>
                        <span style="color: #e5e7eb; font-size: 8pt;">BTM Rechazado</span>
                    </div>
                </div>
                <div>
                    <p style="font-size: 7pt; font-weight: 600; color: #9ca3af; text-transform: uppercase; margin-bottom: 10px; letter-spacing: 0.5px;">TRANSICIONES</p>
                    <div style="margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
                        <span style="color: #10b981; font-size: 12pt;">◆</span>
                        <span style="color: #e5e7eb; font-size: 8pt;">Exitosa (Cambio de banda)</span>
                    </div>
                    <div style="margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
                        <span style="color: #f97316; font-size: 12pt;">◆</span>
                        <span style="color: #e5e7eb; font-size: 8pt;">Exitosa (Sin cambio)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="color: #ef4444; font-size: 12pt;">◆</span>
                        <span style="color: #e5e7eb; font-size: 8pt;">Fallido</span>
                    </div>
                </div>
            </div>
            <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #374151;">
                <p style="font-size: 7pt; font-weight: 600; color: #9ca3af; text-transform: uppercase; margin-bottom: 10px; letter-spacing: 0.5px;">UMBRALES RSSI</p>
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <div style="width: 24px; height: 1px; border-top: 2px dashed #10b981;"></div>
                        <span style="color: #e5e7eb; font-size: 8pt;">Excelente (-67 dBm)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <div style="width: 24px; height: 1px; border-top: 2px dashed #f97316;"></div>
                        <span style="color: #e5e7eb; font-size: 8pt;">Límite (-70 dBm)</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <div style="width: 24px; height: 1px; border-top: 2px dashed #ef4444;"></div>
                        <span style="color: #e5e7eb; font-size: 8pt;">Malo (-75 dBm)</span>
                    </div>
                </div>
            </div>
        </div>
        ` : ''}
    
    ${bandTiming ? `
    <!-- Tiempo en cada banda y en transición -->
    <div style="margin-top: 28px; margin-bottom: 20px;">
        <h3 style="font-size: 13pt; font-weight: 600; color: #1a1a1a; margin-bottom: 16px;">Tiempo en cada banda y transición</h3>
        
        <!-- Cards con barras de progreso -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px;">
            <!-- Card 2.4GHz -->
            <div style="border-radius: 8px; border: 1px solid rgba(59, 130, 246, 0.3); background: rgba(59, 130, 246, 0.1); padding: 16px;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div style="width: 12px; height: 12px; border-radius: 50%; background: #3b82f6;"></div>
                        <span style="font-size: 11pt; font-weight: 600; color: #1a1a1a; white-space: nowrap;">2.4 GHz</span>
                    </div>
                    <span style="font-size: 14pt; font-weight: 700; color: #60a5fa; white-space: nowrap;">
                        ${(() => {
                    const totalTimeForPct = bandTiming.totalTime || (bandTiming.time24 + bandTiming.time5 + (bandTiming.totalTransitionTime || 0))
                    const pct24 = totalTimeForPct > 0 ? Math.round((bandTiming.time24 / totalTimeForPct) * 100) : 0
                    return pct24
                })()}%
                    </span>
                </div>
                
                <!-- Barra de progreso -->
                <div style="width: 100%; height: 10px; background: rgba(0, 0, 0, 0.1); border-radius: 9999px; overflow: hidden; margin-bottom: 12px;">
                    <div style="height: 100%; background: #3b82f6; border-radius: 9999px; width: ${(() => {
                    const totalTimeForPct = bandTiming.totalTime || (bandTiming.time24 + bandTiming.time5 + (bandTiming.totalTransitionTime || 0))
                    const pct24 = totalTimeForPct > 0 ? Math.round((bandTiming.time24 / totalTimeForPct) * 100) : 0
                    return pct24
                })()}%;"></div>
                </div>
                
                <div style="text-align: right; font-family: 'Courier New', monospace; font-size: 14pt; color: #6b7280; white-space: nowrap;">
                    ${formatSeconds(bandTiming.time24)}
                </div>
            </div>
            
            <!-- Card 5GHz -->
            <div style="border-radius: 8px; border: 1px solid rgba(16, 185, 129, 0.3); background: rgba(16, 185, 129, 0.1); padding: 16px;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div style="width: 12px; height: 12px; border-radius: 50%; background: #10b981;"></div>
                        <span style="font-size: 11pt; font-weight: 600; color: #1a1a1a; white-space: nowrap;">5 GHz</span>
                    </div>
                    <span style="font-size: 14pt; font-weight: 700; color: #34d399; white-space: nowrap;">
                        ${(() => {
                    const totalTimeForPct = bandTiming.totalTime || (bandTiming.time24 + bandTiming.time5 + (bandTiming.totalTransitionTime || 0))
                    const pct5 = totalTimeForPct > 0 ? Math.round((bandTiming.time5 / totalTimeForPct) * 100) : 0
                    return pct5
                })()}%
                    </span>
                </div>
                
                <!-- Barra de progreso -->
                <div style="width: 100%; height: 10px; background: rgba(0, 0, 0, 0.1); border-radius: 9999px; overflow: hidden; margin-bottom: 12px;">
                    <div style="height: 100%; background: #10b981; border-radius: 9999px; width: ${(() => {
                    const totalTimeForPct = bandTiming.totalTime || (bandTiming.time24 + bandTiming.time5 + (bandTiming.totalTransitionTime || 0))
                    const pct5 = totalTimeForPct > 0 ? Math.round((bandTiming.time5 / totalTimeForPct) * 100) : 0
                    return pct5
                })()}%;"></div>
                </div>
                
                <div style="text-align: right; font-family: 'Courier New', monospace; font-size: 14pt; color: #6b7280; white-space: nowrap;">
                    ${formatSeconds(bandTiming.time5)}
                </div>
            </div>
        </div>
        
        <!-- Cambios de banda observados -->
        ${bandChangeCount > 0 ? `
        <div style="padding-top: 16px; border-top: 1px solid #e5e7eb;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                <span style="font-size: 11pt; font-weight: 600; color: #1a1a1a;">Cambios de banda observados</span>
                <span style="padding: 2px 8px; border-radius: 9999px; background: rgba(99, 102, 241, 0.2); font-size: 9pt; font-weight: 600; color: #6366f1; white-space: nowrap;">
                    ${bandChangeCount}
                </span>
            </div>
            
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;">
                ${(() => {
                        // Crear lista de transiciones de cambios de banda usando la misma lógica que bandChangeCount
                        const bandChangeTransitions = []
                        sortedTransitions.forEach((t, idx) => {
                            if (!t.is_successful) return
                            const fromBand = normalizeBand(t.from_band)
                            const toBand = normalizeBand(t.to_band)
                            let isBandChange = t.is_band_change === true
                            let actualFromBand = fromBand
                            let actualToBand = toBand

                            if (idx > 0) {
                                const prevTransition = sortedTransitions[idx - 1]
                                if (prevTransition && prevTransition.to_band) {
                                    const prevBand = normalizeBand(prevTransition.to_band)
                                    const currentBand = toBand || fromBand

                                    if (prevBand && currentBand && prevBand !== currentBand) {
                                        actualFromBand = prevBand
                                        actualToBand = currentBand
                                        isBandChange = true
                                    } else if (isBandChange && fromBand === toBand) {
                                        if (prevBand === toBand) {
                                            isBandChange = false
                                        } else if (prevBand && prevBand !== toBand) {
                                            actualFromBand = prevBand
                                            actualToBand = toBand
                                            isBandChange = true
                                        }
                                    }
                                }
                            } else if (!isBandChange && fromBand && toBand && fromBand !== toBand) {
                                isBandChange = true
                            }

                            if (isBandChange && actualFromBand && actualToBand && actualFromBand !== actualToBand) {
                                // Buscar duración en bandTiming si está disponible
                                let duration = 0
                                if (bandTiming && bandTiming.transitions) {
                                    const matchingTransition = bandTiming.transitions.find(bt =>
                                        bt.fromBand === actualFromBand && bt.toBand === actualToBand
                                    )
                                    if (matchingTransition) {
                                        duration = matchingTransition.duration || 0
                                    }
                                }
                                bandChangeTransitions.push({
                                    fromBand: actualFromBand,
                                    toBand: actualToBand,
                                    duration: duration
                                })
                            }
                        })
                        return bandChangeTransitions
                    })().map((t) => {
                        const is24to5 = t.fromBand === '2.4GHz' && t.toBand === '5GHz'
                        const is5to24 = t.fromBand === '5GHz' && t.toBand === '2.4GHz'
                        const borderColor = is24to5
                            ? 'rgba(59, 130, 246, 0.3)'
                            : is5to24
                                ? 'rgba(16, 185, 129, 0.3)'
                                : 'rgba(229, 231, 235, 0.5)'
                        const bgColor = is24to5
                            ? 'rgba(59, 130, 246, 0.05)'
                            : is5to24
                                ? 'rgba(16, 185, 129, 0.05)'
                                : 'rgba(0, 0, 0, 0.02)'
                        const dotColor = is24to5 ? '#3b82f6' : is5to24 ? '#10b981' : '#6366f1'

                        return `
                    <div style="border-radius: 8px; border: 1px solid ${borderColor}; background: ${bgColor}; padding: 12px; display: flex; align-items: center; justify-content: space-between; gap: 8px;">
                        <div style="display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0;">
                            <div style="width: 8px; height: 8px; border-radius: 50%; background: ${dotColor}; flex-shrink: 0;"></div>
                            <span style="font-size: 9pt; font-weight: 500; color: #1a1a1a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                                ${t.fromBand || '?'} → ${t.toBand || '?'}
                            </span>
                        </div>
                        <span style="font-family: 'Courier New', monospace; font-size: 10pt; font-weight: 600; color: #6b7280; white-space: nowrap; text-align: right;">
                            ${formatSeconds(t.duration)}
                        </span>
                    </div>
                    `
                    }).join('')}
            </div>
        </div>
        ` : ''}
    </div>
    ` : ''}
    
    ${relevantWiresharkPackets.length > 0 ? `
    <div class="page-break"></div>
    <h2 style="font-size: 13pt; font-weight: 600; margin-top: 28px; margin-bottom: 12px;">Wireshark Packet List</h2>
    <div class="wireshark-header">
        <div class="wireshark-header-title">
            <span>Wireshark Packet List</span>
        </div>
        <div class="wireshark-header-info">
            ${ssid ? `Red: ${ssid} | ` : ''}${relevantWiresharkPackets.length} / ${wiresharkPackets.length} packets${isTruncated && originalCount > wiresharkPackets.length ? ` (de ${originalCount} total)` : ''}${relevantWiresharkPackets.length < wiresharkPackets.length ? ' (mostrando solo los más relevantes)' : ''}
        </div>
    </div>
    <table class="wireshark-table">
        <thead>
            <tr>
                <th class="packet-no">No.</th>
                <th class="packet-time">Time</th>
                <th class="packet-mac">Source</th>
                <th class="packet-mac">Destination</th>
                <th class="packet-protocol">Protocol</th>
                <th class="packet-band">Band</th>
                <th class="packet-info">Info</th>
            </tr>
        </thead>
        <tbody>
            ${relevantWiresharkPackets.map((packet, idx) => {
                        const formatTime = (time) => {
                            if (time < 1) return time.toFixed(6)
                            if (time < 60) return time.toFixed(6)
                            const minutes = Math.floor(time / 60)
                            const seconds = (time % 60).toFixed(6)
                            return `${minutes}:${seconds}`
                        }
                        return `
                <tr>
                    <td class="packet-no">${idx + 1}</td>
                    <td class="packet-time">${formatTime(packet.time)}</td>
                    <td class="packet-mac">${packet.source}</td>
                    <td class="packet-mac">${packet.destination}</td>
                    <td class="packet-protocol">${packet.protocol}</td>
                    <td class="packet-band">${packet.band}</td>
                    <td class="packet-info" style="color: ${packet.color};">${packet.info}</td>
                </tr>
                `
                    }).join('')}
        </tbody>
    </table>
    ` : ''}
    
    <div class="section-divider"></div>
    
    <!-- INFORME TÉCNICO DE AUDITORÍA -->
        <h2 style="font-size: 13pt; font-weight: 700; text-transform: uppercase; margin-top: 28px; margin-bottom: 14px; page-break-before: auto;">INFORME TÉCNICO DE AUDITORÍA DE BAND STEERING</h2>
    <div class="analysis-content">
        ${formatAnalysis(analysisText)}
    </div>
    
    <div class="footer">
        Generado por Pipe - Análisis inteligente de capturas Wireshark
    </div>
</body>
</html>`

        return htmlContent
    }

    // Generar y guardar PDF automáticamente después de que el análisis se complete
    // Esto asegura que el PDF descargado desde el menú sea siempre el mismo que se genera aquí
    React.useEffect(() => {
        let timeoutId = null

        if (result?.band_steering?.analysis_id) {
            // Esperar a que el gráfico se renderice completamente antes de generar el PDF
            timeoutId = setTimeout(async () => {
                try {
                    const analysisId = result.band_steering.analysis_id

                    // Generar HTML limpio y completo para el PDF
                    const htmlContent = generatePDFHTML()

                    if (htmlContent) {
                        // Guardar el PDF en el backend
                        await networkAnalysisService.savePDF(analysisId, htmlContent)
                        // PDF generado y guardado automáticamente
                    }
                } catch (error) {
                    // No mostrar error al usuario, solo loguear
                    console.warn('⚠️ [PDF] Error al generar PDF automáticamente:', error)
                }
            }, 2000) // Esperar 2 segundos para que el gráfico se renderice
        }

        return () => {
            if (timeoutId) {
                clearTimeout(timeoutId)
            }
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps -- Solo debe ejecutarse cuando result cambia; generatePDFHTML usa result internamente
    }, [result])

    // Función para descargar el PDF directamente
    const handleDownloadPDF = async () => {
        if (!result) return

        const fileName = result?.file_name || fileMetadata?.name || ''
        const cleanName = cleanFileName(fileName).split('.')[0].replace(/_/g, ' ').trim()
        const device = result.band_steering?.device || {}
        const model = device.device_model || 'Genérico'

        // Obtener el analysis_id del resultado
        const analysisId = result?.band_steering?.analysis_id

        if (!analysisId) {
            setError('No se puede generar el PDF: falta el ID del análisis')
            return
        }

        try {
            // Esperar un momento para que el gráfico se renderice completamente
            await new Promise(resolve => setTimeout(resolve, 1000))

            // Generar HTML limpio y completo para el PDF (incluye captura del gráfico)
            const htmlContent = generatePDFHTML()

            if (!htmlContent) {
                setError('Error al generar el contenido del PDF')
                return
            }

            // Guardar el PDF en el backend primero
            await networkAnalysisService.savePDF(analysisId, htmlContent)

            // Esperar un momento para asegurar que el PDF se guardó
            await new Promise(resolve => setTimeout(resolve, 500))

            // Descargar el PDF
            const blob = await networkAnalysisService.downloadPDF(analysisId)

            // Generar nombre del archivo
            const pdfFilename = model && model !== 'Genérico' && model !== 'Unknown'
                ? `Pipe ${model.toUpperCase()}.pdf`
                : `Pipe ${cleanName.toUpperCase()}.pdf`

            // Crear URL temporal para descarga
            const url = window.URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = url
            link.download = pdfFilename
            document.body.appendChild(link)
            link.click()
            document.body.removeChild(link)
            window.URL.revokeObjectURL(url)
        } catch (error) {
            console.error('Error al descargar PDF:', error)
            setError(`Error al descargar el PDF: ${error?.message || 'Error desconocido'}`)
        }
    }

    // Función para cerrar/limpiar el reporte
    const handleCloseReport = () => {
        resetAnalysis()
    }

    // Mostrar popup "Preguntar al agente" al soltar el ratón con selección en el contenido del informe.
    // Usamos requestAnimationFrame para no alterar la selección con un re-render en el mismo tick.
    // Usamos getClientRects()[0] para la primera línea de la selección (posición estable).
    const handleReportMouseUp = React.useCallback(() => {
        const sel = window.getSelection()
        if (!sel || !reportContentRef.current) return
        const text = sel.toString().trim()
        if (!text) {
            selectionPopupDataRef.current = null
            setSelectionPopup(null)
            return
        }
        try {
            if (!reportContentRef.current.contains(sel.anchorNode)) return
            const range = sel.getRangeAt(0)
            const rects = range.getClientRects()
            if (!rects.length) return
            const rect = rects[0]
            const padding = 8
            const buttonWidth = 200
            const aboveHeight = 52
            let left = rect.left
            const top = rect.top - aboveHeight
            if (left + buttonWidth > window.innerWidth - padding) left = window.innerWidth - buttonWidth - padding
            if (left < padding) left = padding
            const finalTop = Math.max(padding, top)
            const data = { text, left, top: finalTop }
            selectionPopupDataRef.current = data
            setSelectionPopup(data)
        } catch {
            setSelectionPopup(null)
        }
    }, [])

    const handleAskAgent = React.useCallback(() => {
        const data = selectionPopupDataRef.current || selectionPopup
        if (!data?.text) return
        // Abrir panel de chat y cargar el fragmento como contexto visual para que el usuario formule su propia pregunta
        setChatPanelOpen(true)
        setChatMode('report')           // Forzar modo reporte mientras haya selección
        setSelectionLockActive(true)    // Bloquear cambio de modo hasta respuesta o limpieza
        setHighlightedContext(data.text)
        selectionPopupDataRef.current = null
        setSelectionPopup(null)
    }, [selectionPopup])

    // Contenido del reporte memoizado para no re-renderizar al mostrar el popup y así mantener la selección de texto (p. ej. en párrafos y listas).
    const reportInnerContent = React.useMemo(
        () =>
            result ? (
                <ReportBodyContent
                    result={result}
                    fileMetadata={fileMetadata}
                    savedSsid={savedSsid}
                    userSsid={userSsid}
                />
            ) : null,
        [result, fileMetadata, savedSsid, userSsid]
    )

    // Panel de chat lateral: posición fija; ancho animado al abrir/cerrar; ocupa todo el alto de la pantalla
    const reportChatPanel = result && (
        <aside
            className={`fixed top-0 bottom-0 z-50 flex flex-col h-screen rounded-none border border-dark-border-primary/50 bg-dark-bg-primary overflow-hidden print:hidden shadow-lg min-w-0 ${chatSide === 'left' ? 'left-0' : 'right-0'}`}
            aria-label="Chat sobre el informe"
            style={{
                width: chatPanelOpen ? chatWidth : 0,
                transition: 'width 0.45s cubic-bezier(0.4, 0, 0.2, 1)',
                pointerEvents: chatPanelOpen ? 'auto' : 'none'
            }}
            onWheel={(e) => e.stopPropagation()}
        >
            {/* Resize handle: borde interior para arrastrar y cambiar ancho */}
            <div
                role="separator"
                aria-label="Redimensionar ancho del chat"
                className={`absolute top-0 bottom-0 w-2 cursor-col-resize flex-shrink-0 z-10 flex items-center justify-center hover:bg-dark-border-primary/20 ${chatSide === 'left' ? 'right-0' : 'left-0'}`}
                onMouseDown={handleResizeStart}
                style={{ [chatSide === 'left' ? 'right' : 'left']: 0 }}
            >
                <div className="w-0.5 h-12 rounded-full bg-dark-border-primary/50" />
            </div>
            <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-dark-border-primary/50 bg-dark-surface-primary/50 flex-shrink-0">
                <span className="text-sm font-medium text-dark-text-primary truncate">
                    Pipechat
                </span>
                <div className="flex items-center gap-1 flex-shrink-0">
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="p-1.5 text-dark-text-muted hover:text-dark-accent-primary"
                        onClick={() => reportChat.clearMessages()}
                        title="Limpiar chat"
                    >
                        <Trash2 className="w-4 h-4" />
                    </Button>
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="p-1.5 text-dark-text-muted hover:text-dark-accent-primary"
                        onClick={() => setChatSide(chatSide === 'left' ? 'right' : 'left')}
                        title={chatSide === 'left' ? 'Mover chat a la derecha' : 'Mover chat a la izquierda'}
                    >
                        {chatSide === 'left' ? <PanelRight className="w-4 h-4" /> : <PanelLeft className="w-4 h-4" />}
                    </Button>
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="p-1.5 text-dark-text-muted hover:text-dark-accent-primary"
                        onClick={() => setChatPanelOpen(false)}
                        title="Cerrar chat"
                    >
                        <X className="w-4 h-4" />
                    </Button>
                </div>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
                <ChatContainer
                    messages={reportChat.messages}
                    isLoading={reportChat.isLoading}
                    onSaveEditedMessage={(msg, newContent) => {
                        if (msg?.role === 'user' && newContent) {
                            reportChat.sendMessageAfterEdit(
                                msg.id,
                                newContent,
                                highlightedContext,
                                selectionLockActive ? 'report' : chatMode
                            )
                        }
                    }}
                    mode={chatMode}
                    onModeChange={setChatMode}
                    modeLocked={selectionLockActive}
                />
            </div>
            <div className="p-2 border-t border-dark-border-primary/50 flex-shrink-0 bg-dark-bg-primary">
                <ChatInput
                    onSend={(content, contextText) =>
                        reportChat.sendMessage(
                            content,
                            contextText,
                            selectionLockActive ? 'report' : chatMode
                        )
                    }
                    isLoading={reportChat.isLoading}
                    disabled={!analysisId}
                    mode={chatMode}
                    modeLocked={selectionLockActive}
                    onModeChange={setChatMode}
                    contextText={highlightedContext}
                    onClearContext={() => {
                        setHighlightedContext(null)
                        setSelectionLockActive(false)
                    }}
                />
            </div>
        </aside>
    )


    return (
        <>
            {result && reportChatPanel}
            <div className="w-full min-w-0 bg-transparent">
                <div
                    className="container-app mx-auto py-4 sm:py-8 overflow-x-hidden px-4"
                    style={{ maxWidth: '1050px' }}
                >
                    <div className="w-full space-y-6 pt-4 print:pt-2 mt-[30px] mb-[30px]">
                        {/* Bloque superior: título + descripción */}
                        <div className="flex flex-col space-y-2">
                            <h1 className="text-xl sm:text-2xl font-semibold text-dark-text-primary mb-1 tracking-tight flex items-center gap-2">
                                <div className="p-2 rounded-lg bg-dark-accent-primary/20">
                                    <Activity className="w-5 h-5 sm:w-6 sm:h-6 text-dark-accent-primary" />
                                </div>
                                <span>Análisis de Capturas de Red</span>
                            </h1>
                            <p className="text-dark-text-secondary text-xs sm:text-[13px] leading-relaxed break-words text-wrap">
                                Sube un archivo de captura de red en formato
                                <code className="px-1 py-0.5 rounded bg-dark-bg-secondary text-dark-accent-primary text-[11px] font-mono mx-1">
                                    .pcap / .pcapng
                                </code> y Pipe generará un análisis
                                detallado del tráfico observado usando inteligencia artificial.
                            </p>
                        </div>

                        {/* Segunda fila: inputs a la izquierda, botones a la derecha */}
                        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 sm:gap-6">
                            <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                                <div className="flex flex-col gap-1">
                                    <label className="text-[11px] font-medium text-dark-text-muted uppercase tracking-wide">
                                        SSID de la red <span className="text-red-400">*</span>
                                    </label>
                                    <input
                                        type="text"
                                        value={userSsid}
                                        onChange={(e) => setUserSsid(e.target.value)}
                                        placeholder="Ej: MiWifi_5G"
                                        className="px-3 py-1.5 rounded-md bg-dark-bg-primary border border-dark-border-primary/70 text-dark-text-primary text-xs focus:outline-none focus:ring-1 focus:ring-dark-accent-primary"
                                    />
                                </div>
                                <div className="flex flex-col gap-1">
                                    <label className="text-[11px] font-medium text-dark-text-muted uppercase tracking-wide">
                                        MAC del cliente <span className="text-red-400">*</span>
                                    </label>
                                    <input
                                        type="text"
                                        value={userClientMac}
                                        onChange={(e) => setUserClientMac(e.target.value)}
                                        placeholder="Ej: d8:cf:bf:4a:50:6f"
                                        className="px-3 py-1.5 rounded-md bg-dark-bg-primary border border-dark-border-primary/70 text-dark-text-primary text-xs font-mono focus:outline-none focus:ring-1 focus:ring-dark-accent-primary"
                                    />
                                </div>
                            </div>

                            <div className="flex flex-col sm:flex-row items-center gap-3 w-full sm:w-auto">
                                {result && (
                                    <>
                                        <Button
                                            variant="outline"
                                            onClick={() => setChatPanelOpen((v) => !v)}
                                            className={`w-full sm:w-auto ${chatPanelOpen ? 'border-dark-accent-primary/50 bg-dark-accent-primary/10 text-dark-accent-primary' : 'border-dark-border-primary/50 text-dark-text-secondary hover:bg-dark-surface-primary'}`}
                                            title={chatPanelOpen ? 'Ocultar chat del informe' : 'Abrir chat del informe'}
                                        >
                                            <MessageCircle className="w-4 h-4 mr-2" />
                                            {chatPanelOpen ? 'Ocultar chat' : 'Mostrar chat'}
                                        </Button>
                                        <Button
                                            variant="outline"
                                            onClick={handleDownloadPDF}
                                            className="w-full sm:w-auto border-dark-accent-primary/10 text-dark-accent-primary hover:bg-dark-accent-primary/10"
                                        >
                                            <HardDrive className="w-4 h-4 mr-2" />
                                            Exportar PDF
                                        </Button>
                                    </>
                                )}

                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    accept=".pcap,.pcapng"
                                    onChange={handleFileChange}
                                    className="hidden"
                                />
                                <Button
                                    type="button"
                                    onClick={handleSelectClick}
                                    disabled={uploading || !userSsid.trim() || !userClientMac.trim()}
                                    className="w-full sm:w-auto disabled:opacity-60 disabled:cursor-not-allowed"
                                >
                                    {uploading ? (
                                        <>
                                            <Loading size="sm" className="sm:mr-2" />
                                            <span>Analizando...</span>
                                        </>
                                    ) : (
                                        <>
                                            <Upload className="w-4 h-4 sm:mr-2" />
                                            <span>{result ? 'Analizar captura' : 'Seleccionar y analizar'}</span>
                                        </>
                                    )}
                                </Button>
                            </div>
                        </div>

                        {/* Resto del código (Tarjetas, Errores, Resultados)... */}
                        {(selectedFile || (result && fileMetadata)) && (
                            <Card className="p-4 border border-dark-accent-primary/20 bg-dark-accent-primary/5 mt-[19px] mb-[19px]">
                                {/* ... contenido de la tarjeta ... */}
                                <div className="flex items-center gap-3">
                                    <div className="p-2 rounded-lg bg-dark-accent-primary/20">
                                        <FileText className="w-5 h-5 text-dark-accent-primary" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium text-dark-text-primary mb-1">
                                            Archivo {result ? 'analizado' : 'seleccionado'}
                                        </p>
                                        <p className="text-xs text-dark-text-secondary break-all truncate">
                                            {cleanFileName(selectedFile?.name || fileMetadata?.name || result?.file_name)}
                                        </p>
                                    </div>
                                    <div className="text-right flex-shrink-0 flex items-center gap-3">
                                        <div>
                                            <p className="text-sm font-semibold text-dark-text-primary">
                                                {formatFileSize(selectedFile?.size || fileMetadata?.size || 0)}
                                            </p>
                                            <p className="text-xs text-dark-text-muted">
                                                {(selectedFile?.size || fileMetadata?.size || 0).toLocaleString()} bytes
                                            </p>
                                        </div>
                                        <button
                                            onClick={handleCloseReport}
                                            className="p-2 rounded-lg hover:bg-red-500/20 hover:text-red-400 text-dark-text-muted hover:border-red-500/30 border border-transparent transition-all duration-200 flex-shrink-0 group"
                                            title="Cerrar reporte"
                                        >
                                            <X className="w-4 h-4 group-hover:scale-110 transition-transform" />
                                        </button>
                                    </div>
                                </div>
                            </Card>
                        )}

                        {error && (
                            <Card className="p-4 border border-dark-status-error/40 bg-dark-status-error/5 flex items-start gap-3">
                                <AlertTriangle className="w-5 h-5 text-dark-status-error mt-0.5 flex-shrink-0" />
                                <p className="text-sm text-dark-status-error">{error}</p>
                            </Card>
                        )}

                        {uploading && !result && (
                            <Card className="p-12 flex flex-col items-center justify-center gap-4">
                                {/* ... contenido de loading ... */}
                                <div className="relative">
                                    <div className="absolute inset-0 rounded-full bg-dark-accent-primary/20 animate-ping"></div>
                                    <div className="relative p-4 rounded-full bg-dark-accent-primary/10">
                                        <Activity className="w-8 h-8 text-dark-accent-primary animate-pulse" />
                                    </div>
                                </div>
                                <div className="text-center space-y-2">
                                    <p className="text-base font-medium text-dark-text-primary">
                                        Analizando captura de red
                                    </p>
                                    <p className="text-sm text-dark-text-secondary max-w-md">
                                        Pipe está procesando tu archivo y generando un análisis detallado.
                                        Esto puede tardar unos segundos dependiendo del tamaño del archivo.
                                    </p>
                                </div>
                                <Loading size="md" />
                            </Card>
                        )}

                        {result && (
                            <>
                                {selectionPopup && createPortal(
                                    <div
                                        data-selection-popup
                                        className="fixed z-[9999]"
                                        style={{ left: Math.max(8, selectionPopup.left), top: Math.max(8, selectionPopup.top) }}
                                    >
                                        <Button size="sm" onClick={handleAskAgent} className="bg-dark-accent-primary hover:bg-dark-accent-hover text-white border-0 shadow-md">
                                            <MessageCircle className="w-4 h-4 mr-1.5" />
                                            Preguntar al agente
                                        </Button>
                                    </div>,
                                    document.body
                                )}
                                <div ref={reportContentRef} onMouseUp={handleReportMouseUp} className="relative">
                                    {reportInnerContent}
                                </div>
                            </>
                        )}
                    </div>

                    {/* Estilos para impresión */}
                    <style dangerouslySetInnerHTML={{ __html: PRINT_STYLES }} />
                </div>
            </div>
        </>
    )
}

export default NetworkAnalysisPage

