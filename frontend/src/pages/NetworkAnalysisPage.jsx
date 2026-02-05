import React, { useState, useRef } from 'react'
import { networkAnalysisService } from '../services/api'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Loading } from '../components/ui/Loading'
import {
    Upload,
    Activity,
    AlertTriangle,
    FileText,
    HardDrive,
    Network,
    Smartphone,
    ShieldCheck,
    CheckCircle2,
    XCircle,
    X
} from 'lucide-react'
import { MarkdownRenderer } from '../components/chat/MarkdownRenderer'
import { BandSteeringChart } from '../components/charts/BandSteeringChart_v2'
import { WiresharkTruthPanel } from '../components/WiresharkTruthPanel'

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
    const [selectedFile, setSelectedFile] = useState(null)
    const [uploading, setUploading] = useState(false)

    // Inicializar estado desde localStorage si existe
    const [result, setResult] = useState(() => {
        try {
            const savedResult = localStorage.getItem('networkAnalysisResult')
            if (!savedResult) return null

            console.log('🔍 [DATA] Cargando resultado desde localStorage')

            const parsed = JSON.parse(savedResult)
            // Validar estructura básica
            if (!parsed?.stats) {
                console.warn('⚠️ [DATA] Resultado en localStorage no tiene estructura válida')
                localStorage.removeItem('networkAnalysisResult')
                return null
            }
            
            console.log('🔍 [DATA] Resultado cargado desde localStorage')
            console.log('🔍 [DATA] band_steering existe:', !!parsed.band_steering)
            console.log('🔍 [DATA] signal_samples:', parsed.band_steering?.signal_samples?.length || 0)
            console.log('🔍 [DATA] transitions:', parsed.band_steering?.transitions?.length || 0)
            
            return parsed
        } catch (e) {
            return null
        }
    })

    const [fileMetadata, setFileMetadata] = useState(() => {
        try {
            const savedMetadata = localStorage.getItem('networkAnalysisFileMeta')
            return savedMetadata ? JSON.parse(savedMetadata) : null
        } catch (e) {
            return null
        }
    })

    // Sincronizar result y fileMetadata cuando se carga la página (para cuando se carga desde reportes)
    // Esto asegura que se lean los valores más recientes de localStorage después de la navegación
    React.useEffect(() => {
        try {
            const savedResult = localStorage.getItem('networkAnalysisResult')
            if (savedResult) {
                const parsed = JSON.parse(savedResult)
                if (parsed?.stats) {
                    setResult(parsed)
                }
            }
            const savedMetadata = localStorage.getItem('networkAnalysisFileMeta')
            if (savedMetadata) {
                const meta = JSON.parse(savedMetadata)
                setFileMetadata(meta)
            }
        } catch (e) {
            // Ignorar errores
        }
    }, []) // Solo ejecutar una vez al montar

    // Inicializar SSID desde localStorage si existe (buscar en metadatos y en resultado)
    const [savedSsid, setSavedSsid] = useState(() => {
        try {
            // Primero intentar desde networkAnalysisFileMeta
            const savedMetadata = localStorage.getItem('networkAnalysisFileMeta')
            if (savedMetadata) {
                const meta = JSON.parse(savedMetadata)
                if (meta?.ssid) {
                    return meta.ssid
                }
            }
            // Si no está en metadatos, buscar en el resultado guardado
            const savedResult = localStorage.getItem('networkAnalysisResult')
            if (savedResult) {
                const parsed = JSON.parse(savedResult)
                if (parsed?.stats?.diagnostics?.user_metadata?.ssid) {
                    return parsed.stats.diagnostics.user_metadata.ssid
                }
            }
            return ''
        } catch (e) {
            return ''
        }
    })

    // Función para limpiar datos antes de guardar en localStorage (evitar QuotaExceededError)
    const sanitizeResultForStorage = (data) => {
        if (!data) return null

        const sanitized = JSON.parse(JSON.stringify(data)) // Deep clone

        // Limitar wireshark_raw.sample a máximo 200 paquetes para evitar exceder localStorage
        if (sanitized?.stats?.diagnostics?.wireshark_raw?.sample) {
            const sample = sanitized.stats.diagnostics.wireshark_raw.sample
            if (sample.length > 200) {
                sanitized.stats.diagnostics.wireshark_raw.sample = sample.slice(0, 200)
                sanitized.stats.diagnostics.wireshark_raw.truncated = true
                sanitized.stats.diagnostics.wireshark_raw.original_count = sample.length
            }
        }

        return sanitized
    }

    // Sincronizar persistencia cada vez que result cambia (redundancia de seguridad)
    React.useEffect(() => {
        if (result) {
            try {
                const sanitized = sanitizeResultForStorage(result)
                localStorage.setItem('networkAnalysisResult', JSON.stringify(sanitized))
            } catch (err) {
                // Si falla, intentar guardar sin los datos raw
                try {
                    const minimal = sanitizeResultForStorage(result)
                    if (minimal?.stats?.diagnostics?.wireshark_raw) {
                        delete minimal.stats.diagnostics.wireshark_raw.sample
                        minimal.stats.diagnostics.wireshark_raw.storage_limited = true
                    }
                    localStorage.setItem('networkAnalysisResult', JSON.stringify(minimal))
                } catch (err2) {
                }
            }
        }
    }, [result])

    // Sincronizar savedSsid y userClientMac cuando cambian los metadatos o el resultado (para cuando se carga desde reportes)
    // También verificar localStorage directamente para capturar cambios recientes
    React.useEffect(() => {
        // Siempre leer directamente de localStorage para obtener el valor más reciente
        try {
            // 1. Intentar desde networkAnalysisFileMeta (prioridad más alta)
            const savedMetadata = localStorage.getItem('networkAnalysisFileMeta')
            if (savedMetadata) {
                const meta = JSON.parse(savedMetadata)
                if (meta?.ssid && meta.ssid.trim() !== '') {
                    setSavedSsid(meta.ssid)
                }
                if (meta?.client_mac && meta.client_mac.trim() !== '') {
                    setUserClientMac(meta.client_mac)
                }
            }
            // 2. Si no está en metadatos, buscar en el resultado guardado
            const savedResult = localStorage.getItem('networkAnalysisResult')
            if (savedResult) {
                const parsed = JSON.parse(savedResult)
                if (parsed?.stats?.diagnostics?.user_metadata) {
                    if (parsed.stats.diagnostics.user_metadata.ssid) {
                        setSavedSsid(parsed.stats.diagnostics.user_metadata.ssid)
                    }
                    if (parsed.stats.diagnostics.user_metadata.client_mac) {
                        setUserClientMac(parsed.stats.diagnostics.user_metadata.client_mac)
                    }
                }
            }
        } catch (e) {
            // Ignorar errores de parsing
        }
    }, [fileMetadata, result])

    const [error, setError] = useState('')
    const fileInputRef = useRef(null)

    // Inputs del usuario para ayudar a la identificación precisa
    const [userSsid, setUserSsid] = useState('')
    const [userClientMac, setUserClientMac] = useState(() => {
        try {
            // Intentar obtener desde networkAnalysisFileMeta
            const savedMetadata = localStorage.getItem('networkAnalysisFileMeta')
            if (savedMetadata) {
                const meta = JSON.parse(savedMetadata)
                if (meta?.client_mac) {
                    return meta.client_mac
                }
            }
            // Si no está en metadatos, buscar en el resultado guardado
            const savedResult = localStorage.getItem('networkAnalysisResult')
            if (savedResult) {
                const parsed = JSON.parse(savedResult)
                if (parsed?.stats?.diagnostics?.user_metadata?.client_mac) {
                    return parsed.stats.diagnostics.user_metadata.client_mac
                }
            }
            return ''
        } catch (e) {
            return ''
        }
    })

    const handleSelectClick = () => {
        // Resetear el valor para permitir seleccionar el mismo archivo y que dispare onChange
        if (fileInputRef.current) {
            fileInputRef.current.value = ''
        }

        // Validar que el usuario haya completado SSID y MAC antes de permitir seleccionar archivo
        if (!userSsid.trim() || !userClientMac.trim()) {
            setError('Debes ingresar el SSID de la red y la MAC del cliente antes de analizar una captura.')
            return
        }

        fileInputRef.current?.click()
    }

    const handleFileChange = (e) => {
        const file = e.target.files?.[0]
        if (!file) return

        const lowerName = file.name.toLowerCase()
        if (!lowerName.endsWith('.pcap') && !lowerName.endsWith('.pcapng')) {
            setError('Solo se permiten archivos de captura .pcap o .pcapng.')
            setSelectedFile(null)
            e.target.value = ''
            return
        }

        // Limpiar TODA persistencia anterior al cambiar archivo
        localStorage.removeItem('networkAnalysisResult')
        localStorage.removeItem('networkAnalysisFileMeta')

        setError('')
        setSelectedFile(file)
        const meta = {
            name: file.name,
            size: file.size,
            ssid: userSsid.trim() || '',
            client_mac: userClientMac.trim() || ''
        }
        setFileMetadata(meta)
        setSavedSsid(userSsid.trim() || '')
        setResult(null)

        // Disparar análisis automáticamente
        performAnalysis(file, meta)
    }

    const performAnalysis = async (file, meta) => {
        setUploading(true)
        setError('')
        setResult(null)

        try {
            console.log('🔍 [DATA] Iniciando análisis de captura')
            console.log('🔍 [DATA] userSsid:', userSsid)
            console.log('🔍 [DATA] userClientMac:', userClientMac)
            
            const res = await networkAnalysisService.analyzeCapture(file, {
                ssid: userSsid || null,
                client_mac: userClientMac || null,
            })

            // Debug: Ver estructura de datos
            console.log('🔍 [DATA] Resultado recibido del backend')
            console.log('🔍 [DATA] band_steering existe:', !!res.band_steering)
            console.log('🔍 [DATA] signal_samples:', res.band_steering?.signal_samples?.length || 0)
            console.log('🔍 [DATA] transitions:', res.band_steering?.transitions?.length || 0)
            console.log('🔍 [DATA] btm_events:', res.band_steering?.btm_events?.length || 0)
            
            if (res.band_steering?.signal_samples?.length > 0) {
                console.log('🔍 [DATA] Primer signalSample:', res.band_steering.signal_samples[0])
                console.log('🔍 [DATA] Último signalSample:', res.band_steering.signal_samples[res.band_steering.signal_samples.length - 1])
            }
            
            if (res.band_steering?.transitions?.length > 0) {
                console.log('🔍 [DATA] Primer transition:', res.band_steering.transitions[0])
                console.log('🔍 [DATA] Último transition:', res.band_steering.transitions[res.band_steering.transitions.length - 1])
            }

            // Guardar en persistencia (con sanitización para evitar QuotaExceededError)
            setResult(res)
            // Incluir SSID y client_mac en los metadatos y en el resultado
            const ssidValue = userSsid.trim() || ''
            const clientMacValue = userClientMac.trim() || ''
            const metaWithSsid = {
                ...meta,
                ssid: ssidValue,
                client_mac: clientMacValue
            }
            setSavedSsid(ssidValue)
            try {
                const sanitized = sanitizeResultForStorage(res)
                // Guardar SSID y client_mac también en el resultado para que esté disponible cuando se carga desde reportes
                if (sanitized.stats?.diagnostics) {
                    if (!sanitized.stats.diagnostics.user_metadata) {
                        sanitized.stats.diagnostics.user_metadata = {}
                    }
                    if (ssidValue) {
                        sanitized.stats.diagnostics.user_metadata.ssid = ssidValue
                    } else {
                    }
                    if (clientMacValue) {
                        sanitized.stats.diagnostics.user_metadata.client_mac = clientMacValue
                    } else {
                    }
                } else {
                }
                localStorage.setItem('networkAnalysisResult', JSON.stringify(sanitized))
                localStorage.setItem('networkAnalysisFileMeta', JSON.stringify(metaWithSsid))
            } catch (err) {
                // Guardar versión mínima sin sample completo
                try {
                    const minimal = sanitizeResultForStorage(res)
                    if (minimal?.stats?.diagnostics?.wireshark_raw) {
                        delete minimal.stats.diagnostics.wireshark_raw.sample
                        minimal.stats.diagnostics.wireshark_raw.storage_limited = true
                    }
                    // Guardar SSID y client_mac también en el resultado mínimo
                    if (minimal.stats?.diagnostics) {
                        if (!minimal.stats.diagnostics.user_metadata) {
                            minimal.stats.diagnostics.user_metadata = {}
                        }
                        if (ssidValue) {
                            minimal.stats.diagnostics.user_metadata.ssid = ssidValue
                        }
                        if (clientMacValue) {
                            minimal.stats.diagnostics.user_metadata.client_mac = clientMacValue
                        }
                    }
                    localStorage.setItem('networkAnalysisResult', JSON.stringify(minimal))
                    localStorage.setItem('networkAnalysisFileMeta', JSON.stringify(metaWithSsid))
                } catch (err2) {
                }
            }

        } catch (err) {
            const message =
                err?.message ||
                err?.data?.detail ||
                'Ocurrió un error al analizar la captura de red.'
            setError(message)
        } finally {
            setUploading(false)
        }
    }

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

    // Función para formatear el veredicto técnico a español
    const formatVerdict = (verdict) => {
        if (!verdict) return 'N/A'

        const mapping = {
            'EXCELLENT': 'Excelente',
            'GOOD': 'Bueno',
            'PREVENTIVE_SUCCESS': 'Éxito Preventivo',
            'FAILED_BTM_REJECT': 'Fallo: Rechazo BTM',
            'FAILED_LOOP': 'Fallo: Bucle entre APs',
            'FAILED_NO_REASSOC': 'Fallo: Sin reconexión',
            'FAILED_ALGORITHM': 'Fallo de algoritmo',
            'WARNING_INCONCLUSIVE': 'Inconcluso',
            'NOT_EVALUABLE': 'No evaluable',
            'FAILED': 'Fallido',
            'ACCEPTABLE': 'Aceptable',
            'SLOW_BUT_SUCCESSFUL': 'Lento pero Exitoso',
            'NO_DATA': 'Sin Datos',
            'NO_STEERING_EVENTS': 'Sin Eventos',
            'PARTIAL': 'Éxito Parcial'
        }

        return mapping[verdict] || verdict.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase())
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
        } catch (error) {
            console.error('Error al capturar el gráfico:', error)
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
        } catch (e) {
            console.error('Error calculando tiempo medido en PDF:', e)
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
        console.log('🔍 [BAND_TIMING PDF] Iniciando cálculo de bandTiming para PDF')
        console.log('🔍 [BAND_TIMING PDF] signalSamples recibidos:', signalSamples?.length || 0)
        console.log('🔍 [BAND_TIMING PDF] transitions recibidas:', transitions?.length || 0)
        if (signalSamples.length > 0) {
            console.log('🔍 [BAND_TIMING PDF] Primer signalSample:', signalSamples[0])
            console.log('🔍 [BAND_TIMING PDF] Último signalSample:', signalSamples[signalSamples.length - 1])
        }
        if (transitions.length > 0) {
            console.log('🔍 [BAND_TIMING PDF] Primer transition:', transitions[0])
            console.log('🔍 [BAND_TIMING PDF] Último transition:', transitions[transitions.length - 1])
        }
        
        let bandTiming = null
        try {
            const sortedTransitions = (transitions || [])
                .filter(t => t && t.start_time != null && t.is_successful)
                .sort((a, b) => Number(a.start_time) - Number(b.start_time))
            
            console.log('🔍 [BAND_TIMING PDF] sortedTransitions filtradas:', sortedTransitions.length)

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
            
            console.log('🔍 [BAND_TIMING PDF] validSamples procesados:', validSamples.length)
            if (validSamples.length > 0) {
                console.log('🔍 [BAND_TIMING PDF] Primer validSample:', validSamples[0])
                console.log('🔍 [BAND_TIMING PDF] Último validSample:', validSamples[validSamples.length - 1])
            }
            
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
            
            console.log('🔍 [BAND_TIMING PDF] sampleTimestamps.length:', sampleTimestamps.length)
            console.log('🔍 [BAND_TIMING PDF] validTransitions.length:', validTransitions.length)

            if (sampleTimestamps.length > 1) {
                // Usar solo signalSamples para minTime y maxTime (como la gráfica)
                minTime = Math.min(...sampleTimestamps)
                maxTime = Math.max(...sampleTimestamps)
                totalTime = maxTime - minTime
                console.log('🔍 [BAND_TIMING PDF] Usando signalSamples - minTime:', minTime, 'maxTime:', maxTime, 'totalTime:', totalTime)
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
                console.log('🔍 [BAND_TIMING PDF] transitionTimestamps:', transitionTimestamps)
                if (transitionTimestamps.length > 0) {
                    minTime = Math.min(...transitionTimestamps)
                    maxTime = Math.max(...transitionTimestamps)
                    // Si solo hay una transición, agregar un margen mínimo
                    if (minTime === maxTime) {
                        maxTime = minTime + 1.0 // 1 segundo mínimo
                    }
                    totalTime = maxTime - minTime
                    console.log('🔍 [BAND_TIMING PDF] Usando transiciones - minTime:', minTime, 'maxTime:', maxTime, 'totalTime:', totalTime)
                } else {
                    minTime = 0
                    maxTime = 1
                    totalTime = 1
                    console.log('🔍 [BAND_TIMING PDF] Sin timestamps válidos en transiciones, usando valores por defecto')
                }
            } else {
                // Sin datos suficientes, usar valores por defecto mínimos
                minTime = 0
                maxTime = 1
                totalTime = 1
                console.log('🔍 [BAND_TIMING PDF] Sin datos suficientes, usando valores por defecto mínimos')
            }

            console.log('🔍 [BAND_TIMING PDF] totalTime calculado:', totalTime)

                if (totalTime > 0) {
                console.log('🔍 [BAND_TIMING PDF] Iniciando cálculo de time24 y time5')
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
                } else if (validTransitions.length > 0) {
                    // FALLBACK: Calcular tiempo en cada banda basándose solo en transiciones
                    // cuando no hay suficientes signalSamples
                    let currentBand = null
                    let lastTime = minTime
                    
                    for (let i = 0; i < validTransitions.length; i++) {
                        const t = validTransitions[i]
                        const fromBand = normalizeBand(t.from_band || '')
                        const toBand = normalizeBand(t.to_band || '')
                        const transStart = Number(t.start_time || 0)
                        const transEnd = Number(t.end_time != null ? t.end_time : transStart)
                        
                        // Determinar banda inicial si es la primera transición
                        if (i === 0 && fromBand) {
                            currentBand = fromBand
                            // Tiempo antes de la primera transición
                            if (transStart > minTime) {
                                const periodDuration = transStart - minTime
                                if (currentBand === '2.4GHz') {
                                    time24 += periodDuration
                                } else if (currentBand === '5GHz') {
                                    time5 += periodDuration
                                }
                            }
                        }
                        
                        // Tiempo en la banda destino después de la transición
                        if (toBand) {
                            const nextTransStart = (i + 1 < validTransitions.length) 
                                ? Number(validTransitions[i + 1].start_time || 0) 
                                : maxTime
                            const periodDuration = nextTransStart - transEnd
                            
                            if (periodDuration > 0) {
                                if (toBand === '2.4GHz') {
                                    time24 += periodDuration
                                } else if (toBand === '5GHz') {
                                    time5 += periodDuration
                                }
                            }
                            currentBand = toBand
                        }
                    }
                    
                    // Si no hay transiciones pero hay una banda conocida, asignar todo el tiempo a esa banda
                    if (validTransitions.length === 0 && signalSamples.length > 0) {
                        const firstSample = signalSamples[0]
                        const band = normalizeBand(firstSample.band || '')
                        if (band === '2.4GHz') {
                            time24 = totalTime
                        } else if (band === '5GHz') {
                            time5 = totalTime
                        }
                    }
                    }

                    const totalTransitionTime = transitionDurations.reduce((a, b) => a + b, 0)
                    const totalBandTime = time24 + time5
                    const expectedTotal = totalTime - totalTransitionTime

                console.log('🔍 [BAND_TIMING PDF] ANTES de ajuste - time24:', time24, 'time5:', time5)
                console.log('🔍 [BAND_TIMING PDF] totalTransitionTime:', totalTransitionTime)
                console.log('🔍 [BAND_TIMING PDF] totalBandTime:', totalBandTime)
                console.log('🔍 [BAND_TIMING PDF] expectedTotal:', expectedTotal)
                console.log('🔍 [BAND_TIMING PDF] totalTime:', totalTime)

                    // Ajustar tiempos si hay discrepancia, pero mantener la proporción
                    if (expectedTotal > 0 && Math.abs(totalBandTime - expectedTotal) > 0.1) {
                    console.log('🔍 [BAND_TIMING PDF] Aplicando ajuste de tiempos - discrepancia detectada')
                        if (totalBandTime > expectedTotal * 1.1) {
                            // Si el tiempo de banda es mucho mayor, escalar hacia abajo
                            const scale = expectedTotal / totalBandTime
                            time24 *= scale
                            time5 *= scale
                        console.log('🔍 [BAND_TIMING PDF] Escalando hacia abajo - scale:', scale)
                        } else if (totalBandTime < expectedTotal * 0.9) {
                            // Si el tiempo de banda es menor, ajustar proporcionalmente
                            const scale = expectedTotal / totalBandTime
                            time24 *= scale
                            time5 *= scale
                        console.log('🔍 [BAND_TIMING PDF] Escalando hacia arriba - scale:', scale)
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
                
                console.log('🔍 [BAND_TIMING PDF] DESPUÉS de ajuste - time24:', time24, 'time5:', time5)
                console.log('🔍 [BAND_TIMING PDF] finalTotalBandTime:', finalTotalBandTime)
                console.log('🔍 [BAND_TIMING PDF] finalTotalTime:', finalTotalTime)
                console.log('🔍 [BAND_TIMING PDF] transitionsWithDuration:', transitionsWithDuration.length)
                    
                    bandTiming = {
                        time24,
                        time5,
                        totalTime: finalTotalTime, // Tiempo total incluyendo transiciones para que los porcentajes sumen 100%
                        totalBandTime: finalTotalBandTime,
                        totalTransitionTime,
                        transitions: transitionsWithDuration,
                        transitionDurations
                    }
                
                console.log('🔍 [BAND_TIMING PDF] bandTiming final:', bandTiming)
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
                        console.log('✅ [PDF] PDF generado y guardado automáticamente')
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
    }, [result]) // Se ejecuta cuando result cambia

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
            alert('No se puede generar el PDF: falta el ID del análisis')
            return
        }

        try {
            // Esperar un momento para que el gráfico se renderice completamente
            await new Promise(resolve => setTimeout(resolve, 1000))
            
            // Generar HTML limpio y completo para el PDF (incluye captura del gráfico)
            const htmlContent = generatePDFHTML()
            
            if (!htmlContent) {
                alert('Error al generar el contenido del PDF')
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
            alert(`Error al descargar el PDF: ${error?.message || 'Error desconocido'}`)
        }
    }

    // Función para manejar la impresión/PDF (mantener para compatibilidad)
    const handlePrint = async () => {
        const fileName = result?.file_name || fileMetadata?.name || ''
        const cleanName = cleanFileName(fileName).split('.')[0].replace(/_/g, ' ').trim()
        const device = result.band_steering?.device || {}
        const model = device.device_model || 'Genérico'
        
        // El título del documento influye en el nombre del archivo al guardar
        // Usar el modelo del dispositivo si está disponible, similar al PDF
        const originalTitle = document.title
        const pdfTitle = model && model !== 'Genérico' && model !== 'Unknown' 
            ? `Pipe ${model.toUpperCase()}` 
            : `Pipe ${cleanName.toUpperCase()}`
        document.title = pdfTitle

        // Obtener el analysis_id del resultado
        const analysisId = result?.band_steering?.analysis_id
        
        // Si hay un analysis_id, persistir el PDF antes de imprimir
        if (analysisId) {
            try {
                // Generar HTML limpio y completo para el PDF
                const htmlContent = generatePDFHTML()
                
                if (htmlContent) {
                    // Enviar al backend para persistir el PDF
                    await networkAnalysisService.savePDF(analysisId, htmlContent)
                }
            } catch (error) {
                // Continuar con la impresión aunque falle la persistencia
            }
        }

        window.print()
        document.title = originalTitle
    }

    // Función para cerrar/limpiar el reporte
    const handleCloseReport = () => {
        setResult(null)
        setSelectedFile(null)
        setFileMetadata(null)
        setSavedSsid('')
        setError('')
        localStorage.removeItem('networkAnalysisResult')
        localStorage.removeItem('networkAnalysisFileMeta')
        if (fileInputRef.current) {
            fileInputRef.current.value = ''
        }
    }

    return (
        <div className="container-app py-4 sm:py-8 overflow-x-hidden min-w-0 px-4" style={{ width: '1050px' }}>


            <div className="max-w-5xl mx-auto w-full min-w-0 space-y-6 pt-4 print:pt-2 mt-[30px] mb-[30px]">
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
                        <code className="px-1 py-0.5 rounded bg-dark-bg-secondary text-dark-accent-primary text-[11px] font-mono">
                            .pcap / .pcapng
                        </code> y Pipe generará un análisis
                        detallado del tráfico observado usando inteligencia artificial.

                        
                        .
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
                            <Button
                                variant="outline"
                                onClick={handleDownloadPDF}
                                className="w-full sm:w-auto border-dark-accent-primary/10 text-dark-accent-primary hover:bg-dark-accent-primary/10"
                            >
                                <HardDrive className="w-4 h-4 mr-2" />
                                Exportar PDF
                            </Button>
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


            </div>

            {(selectedFile || (result && fileMetadata)) && (
                <Card className="p-4 border border-dark-accent-primary/20 bg-dark-accent-primary/5 mt-[19px] mb-[19px]">
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
                <div className="space-y-6">

                    {/* 1. Análisis de Band Steering y Detalle de Cumplimiento Técnico (Unificado) */}
                    <Card className="p-6">
                        <div className="space-y-6">
                            {/* Header con Veredicto Visual */}
                            <div className="flex items-start justify-between gap-4 pb-4 border-b border-dark-border-primary/100">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 rounded-lg bg-dark-accent-primary/20">
                                        <Activity className="w-5 h-5 text-dark-accent-primary" />
                                    </div>
                                    <div>
                                        <h2 className="text-lg font-semibold text-dark-text-primary">
                                            Análisis de Band Steering
                                        </h2>
                                        <p className="text-sm text-dark-text-secondary mt-1">
                                            Evaluación técnica de capacidades 802.11k/v/r basada directamente en la captura real de Wireshark/tshark
                                        </p>
                                    </div>
                                </div>

                                {/* Badge de Veredicto */}
                                {(() => {
                                    // Recalcular el veredicto basándose en los checks corregidos
                                    const baseChecks = result.band_steering?.compliance_checks || []
                                    
                                    // Recalcular el estado de "Steering Efectivo" si existe
                                    let correctedChecks = baseChecks.map(check => {
                                        if (check.check_name === 'Steering Efectivo') {
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
                                            
                                            const actualPassed = bandChangeCount > 0 || bssidChangeTransitions > 0
                                            
                                            return { ...check, passed: actualPassed }
                                        }
                                        return check
                                    })
                                    
                                    // Recalcular el veredicto basándose en los checks corregidos
                                    // Usar la misma lógica que el backend
                                    const assocCheck = correctedChecks.find(c => c.category === 'association')
                                    const btmCheck = correctedChecks.find(c => c.category === 'btm')
                                    const performanceCheck = correctedChecks.find(c => c.category === 'performance')
                                    
                                    let correctedVerdict = result.band_steering?.verdict || result.stats?.steering_analysis?.verdict || 'UNKNOWN'
                                    
                                    // Si el check de asociación falla, es FAILED
                                    if (assocCheck && !assocCheck.passed) {
                                        correctedVerdict = 'FAILED'
                                    }
                                    // Si el check de BTM falla explícitamente, es FAILED
                                    else if (btmCheck && !btmCheck.passed) {
                                        correctedVerdict = 'FAILED'
                                    }
                                    // Si el check de performance (Steering Efectivo) pasa, es SUCCESS
                                    else if (performanceCheck && performanceCheck.passed) {
                                        correctedVerdict = 'SUCCESS'
                                    }
                                    // Si hay transiciones exitosas pero no hay steering efectivo, puede ser PARTIAL
                                    else {
                                        const sa = result.stats?.steering_analysis || {}
                                        const successful = sa.successful_transitions ?? 0
                                        if (successful > 0) {
                                            if (btmCheck && btmCheck.passed) {
                                                correctedVerdict = 'PARTIAL'
                                            } else {
                                                correctedVerdict = 'FAILED'
                                            }
                                        }
                                    }
                                    
                                    const verdictUpper = correctedVerdict.toUpperCase()
                                    const successVerdicts = ['SUCCESS', 'EXCELLENT', 'GOOD', 'PREVENTIVE_SUCCESS', 'ACCEPTABLE', 'SLOW_BUT_SUCCESSFUL']
                                    const partialVerdicts = ['PARTIAL']
                                    const isSuccess = successVerdicts.includes(verdictUpper)
                                    const isPartial = partialVerdicts.includes(verdictUpper)

                                    return (
                                        <div className={`px-4 py-2 rounded-lg font-semibold text-sm flex items-center gap-2 ${isSuccess
                                                ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                                                : isPartial
                                                    ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
                                                    : 'bg-red-500/20 text-red-400 border border-red-500/30'
                                            }`}>
                                            {isSuccess ? '✅' : isPartial ? '⚠️' : '❌'}
                                            <span>{formatVerdict(verdictUpper).toUpperCase()}</span>
                                        </div>
                                    )
                                })()}
                            </div>

                            {/* Detalle de Cumplimiento Técnico */}
                            {result.band_steering?.compliance_checks && (
                                <div>
                                    <h3 className="text-base font-semibold text-dark-text-primary mb-4 flex items-center gap-2">
                                        <ShieldCheck className="w-5 h-5 text-dark-accent-primary" />
                                        Detalle de Cumplimiento Técnico
                                    </h3>
                                    <div className="space-y-2.5">
                                        {(() => {
                                            const baseChecks = result.band_steering?.compliance_checks || []
                                            return (
                                                <>
                                                    {baseChecks.map((check, idx) => {
                                                        // Recalcular el estado passed para "Steering Efectivo" basándose en el número correcto de cambios de banda
                                                        let actualPassed = check.passed
                                                        let displayDetails = check.details || ''
                                                        
                                                        if (check.check_name === 'Steering Efectivo') {
                                                            // Calcular bandChangeCount usando la misma lógica que el PDF
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
                                                            
                                                            const sa = result.stats?.steering_analysis || {}
                                                            const successful = sa.successful_transitions ?? 0
                                                            const btmAccept = result.band_steering?.btm_events?.filter(e => e.status_code === 0).length || 0
                                                            
                                                            displayDetails = `TRANSICIONES CON CAMBIO DE BANDA: ${bandChangeCount} | TRANSICIONES TOTALES: ${successful} | BTM ACCEPT: ${btmAccept}`
                                                            
                                                            // Recalcular passed: pasa si hay al menos 1 cambio de banda exitoso
                                                            // O si hay transiciones exitosas entre BSSIDs distintos
                                                            const bssidChangeTransitions = sortedTransitions.filter(t => 
                                                                t.is_successful && 
                                                                t.from_bssid && 
                                                                t.to_bssid && 
                                                                t.from_bssid !== t.to_bssid
                                                            ).length
                                                            
                                                            // El check pasa si hay al menos 1 cambio de banda O al menos 1 cambio de BSSID
                                                            actualPassed = bandChangeCount > 0 || bssidChangeTransitions > 0
                                                        }
                                                        
                                                        return (
                                                            <div
                                                                key={idx}
                                                                className="bg-dark-bg-secondary/30 rounded-lg py-2.5 px-4 border border-dark-border-primary/10 hover:border-dark-accent-primary/20 transition-all"
                                                            >
                                                                <div className="flex items-center justify-between gap-4">
                                                                    {/* Contenido (Título + Detalles) */}
                                                                    <div className="flex-1 min-w-0">
                                                                        <h4 className="font-bold text-dark-text-primary text-base tracking-tight">
                                                                            {check.check_name}
                                                                        </h4>

                                                                        {/* Detalles técnicos (Justo debajo del título) */}
                                                                        {displayDetails ? (
                                                                            <div className="mt-0.5">
                                                                                <p className="text-[11px] text-dark-text-primary/90 font-mono leading-tight uppercase tracking-tight">
                                                                                    {displayDetails}
                                                                                </p>
                                                                            </div>
                                                                        ) : null}
                                                                    </div>

                                                                    {/* Badge de Estado Centrado Verticalmente */}
                                                                    <div
                                                                        className={`compliance-badge flex-shrink-0 px-3 py-1.5 rounded-md font-bold text-xs flex items-center gap-1.5 ${
                                                                            actualPassed
                                                                                ? 'bg-green-500/15 text-green-400 border border-green-500/30'
                                                                                : 'bg-red-500/15 text-red-400 border border-red-500/30'
                                                                        }`}
                                                                    >
                                                                        {actualPassed ? (
                                                                            <>
                                                                                <CheckCircle2 className="w-4 h-4" />
                                                                                <span>PASÓ</span>
                                                                            </>
                                                                        ) : (
                                                                            <>
                                                                                <XCircle className="w-4 h-4" />
                                                                                <span>FALLÓ</span>
                                                                            </>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        )
                                                    })}
                                                </>
                                            )
                                        })()}
                                    </div>
                                </div>
                            )}
                        </div>
                    </Card>


                    {/* 4. Fila Superior: Estadísticas (3 cards) + Gráfica de Band Steering */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch">
                        {/* Panel lateral izquierdo: 3 Cards de estadísticas */}
                        <div className="lg:col-span-1 flex flex-col space-y-4 h-full">

                            {/* Identidad del Dispositivo*/}
                            {result.band_steering?.device && (
                                <Card className="p-4 border-dark-accent-primary/20 bg-dark-accent-primary/5">
                                    <div className="flex items-center gap-2 mb-3">
                                        <Smartphone className="w-4 h-4 text-dark-accent-primary" />
                                        <h3 className="text-sm font-semibold text-dark-text-primary">
                                            Dispositivo Identificado
                                        </h3>
                                    </div>
                                    <div className="space-y-2">
                                        {(savedSsid || userSsid) && (
                                            <div className="flex justify-between items-center">
                                                <p className="text-xs text-dark-text-muted">Red (SSID)</p>
                                                <p className="text-sm font-medium text-dark-text-primary truncate max-w-[60%] text-right" title={savedSsid || userSsid}>
                                                    {savedSsid || userSsid || 'N/A'}
                                                </p>
                                            </div>
                                        )}
                                        <div className="flex justify-between items-center">
                                            <p className="text-xs text-dark-text-muted">Marca</p>
                                            <p className="text-sm font-medium text-dark-text-primary">{result.band_steering.device.vendor || 'Desconocido'}</p>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <p className="text-xs text-dark-text-muted">Modelo</p>
                                            <p className="text-sm font-medium text-dark-text-primary">{result.band_steering.device.device_model || 'Genérico'}</p>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <p className="text-xs text-dark-text-muted">Categoría</p>
                                            <p className="text-sm font-medium text-dark-text-primary capitalize">{result.band_steering.device.device_category?.replace('_', ' ') || 'N/A'}</p>
                                        </div>
                                    </div>
                                </Card>
                            )}
                            {/* MACs de Negociación */}
                            <Card className="p-4">
                                <div className="flex items-center gap-2 mb-3">
                                    <Network className="w-4 h-4 text-dark-accent-primary" />
                                    <h3 className="text-sm font-semibold text-dark-text-primary">
                                        MACs de Negociación
                                    </h3>
                                </div>
                                <div className="space-y-3">
                                    <div>
                                        <p className="text-xs text-dark-text-muted mb-1 uppercase">Cliente</p>
                                        <p className="text-sm font-mono font-bold text-dark-text-primary break-all">
                                            {result.stats?.diagnostics?.user_provided_client_mac || result.stats?.diagnostics?.client_mac || 'Desconocido'}
                                        </p>
                                        {result.stats?.diagnostics?.client_mac_warning && (
                                            <div className="mt-2 p-2 rounded-lg bg-orange-500/10 border border-orange-500/30">
                                                <p className="text-xs text-orange-400 font-medium">
                                                    ⚠️ {result.stats.diagnostics.client_mac_warning}
                                                </p>
                                            </div>
                                        )}
                                    </div>
                                    <div>
                                        <p className="text-xs text-dark-text-muted mb-1 uppercase">
                                            {(() => {
                                                const rawInfo = result.stats?.diagnostics?.bssid_info || {}
                                                const macRegex = /^([0-9a-f]{2}:){5}[0-9a-f]{2}$/i
                                                const onlyBssids = Object.keys(rawInfo).filter(key => macRegex.test(key))
                                                return `BSSIDs (${onlyBssids.length})`
                                            })()}
                                        </p>
                                        <div className="space-y-1">
                                            {(() => {
                                                const rawInfo = result.stats?.diagnostics?.bssid_info || {}
                                                const macRegex = /^([0-9a-f]{2}:){5}[0-9a-f]{2}$/i
                                                const onlyBssids = Object.keys(rawInfo).filter(key => macRegex.test(key))

                                                if (onlyBssids.length === 0) {
                                                    return (
                                                        <p className="text-xs text-dark-text-muted italic">
                                                            No detectados
                                                        </p>
                                                    )
                                                }

                                                return onlyBssids.map((bssid, idx) => {
                                                    return (
                                                        <p key={idx} className="text-xs font-mono text-dark-text-secondary">
                                                            {bssid}
                                                        </p>
                                                    )
                                                })
                                            })()}
                                        </div>
                                    </div>
                                </div>
                            </Card>

                            {/* Métricas de Band Steering */}
                            <Card className="p-4 flex-1 flex flex-col">
                                <div className="flex items-center gap-2 mb-3">
                                    <Activity className="w-4 h-4 text-dark-accent-primary" />
                                    <h3 className="text-sm font-semibold text-dark-text-primary">
                                        Métricas de Steering
                                    </h3>
                                </div>
                                <div className="space-y-5 flex-1">
                                    <div className="p-2 rounded-lg bg-dark-bg-secondary/50">
                                        <p className="text-xs text-dark-text-muted mb-1">Estándares KVR Identificados</p>
                                        <p className="text-sm font-semibold text-dark-text-primary">
                                            {(() => {
                                                const kvrCheck = result.band_steering?.compliance_checks?.find(c => c.check_name === "Estándares KVR")
                                                if (kvrCheck && kvrCheck.details) {
                                                    // Extrae solo los verdaderos de los detalles (k=True, v=True, r=False)
                                                    const detected = []
                                                    if (kvrCheck.details.includes('k=True')) detected.push('11k')
                                                    if (kvrCheck.details.includes('v=True')) detected.push('11v')
                                                    if (kvrCheck.details.includes('r=True')) detected.push('11r')
                                                    return detected.length > 0 ? detected.join(', ') : 'Ninguno'
                                                }

                                                const kvr = result.stats?.diagnostics?.band_counters?.kvr_stats || {}
                                                const detected = []
                                                if (kvr['11k']) detected.push('11k')
                                                if (kvr['11v']) detected.push('11v')
                                                if (kvr['11r']) detected.push('11r')
                                                return detected.length > 0 ? detected.join(', ') : 'Ninguno'
                                            })()}
                                        </p>
                                    </div>
                                    <div className="p-2 rounded-lg bg-dark-bg-secondary/50 min-h-[60px] flex flex-col justify-between">
                                        <p className="text-xs text-dark-text-muted mb-1">Intentos de steering</p>
                                        <div className="space-y-2">
                                            {(() => {
                                                const sa = result.stats?.steering_analysis || {}
                                                const attempts = sa.steering_attempts ?? 0
                                                const successful = sa.successful_transitions ?? 0

                                                // Función para normalizar bandas
                                                const normalizeBand = (band) => {
                                                    if (!band) return null
                                                    const bandStr = band.toString().toLowerCase()
                                                    if (bandStr.includes('5')) return '5GHz'
                                                    if (bandStr.includes('2.4') || bandStr.includes('2,4')) return '2.4GHz'
                                                    return band
                                                }

                                                const transitions = result.band_steering?.transitions || []

                                                // Ordenar transiciones por tiempo para comparar consecutivas
                                                const sortedTransitions = [...transitions].sort((a, b) => a.start_time - b.start_time)

                                                // Analizar cada transición exitosa
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

                                                return (
                                                    <>
                                                        <div className="flex items-baseline gap-2">
                                                            <p className="text-sm font-semibold text-dark-text-primary">
                                                                {successful}/{attempts}
                                                            </p>
                                                            <p className="text-[10px] text-dark-text-muted uppercase">
                                                                Exitosas
                                                            </p>
                                                        </div>
                                                        <div className="flex flex-col gap-1.5">
                                                            {bandChangeCount > 0 && (
                                                                <div className="flex items-center gap-2">
                                                                    <div className="w-2 h-2 bg-emerald-500 rounded-full"></div>
                                                                    <span className="text-xs text-dark-text-secondary">
                                                                        <span className="font-semibold text-emerald-400">{bandChangeCount}</span> cambio de banda
                                                                    </span>
                                                                </div>
                                                            )}
                                                            {associationOnlyCount > 0 && (
                                                                <div className="flex items-center gap-2">
                                                                    <div className="w-2 h-2 bg-orange-500 rounded-full"></div>
                                                                    <span className="text-xs text-dark-text-secondary">
                                                                        <span className="font-semibold text-orange-400">{associationOnlyCount}</span> transición de asociación
                                                                    </span>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </>
                                                )
                                            })()}
                                        </div>
                                    </div>
                                    <div className="p-2 rounded-lg bg-dark-bg-secondary/50 min-h-[60px] flex flex-col justify-between">
                                        <p className="text-xs text-dark-text-muted mb-1">Tiempo medido</p>
                                        <p className="text-sm font-semibold text-dark-text-primary">
                                            {(() => {
                                                // Usar la misma lógica que el bloque de "Tiempo en cada banda y en transición"
                                                // para que sea consistente con la gráfica: basarse en transitions y signal_samples
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
                                                        allTimestamps.push(Number(s.timestamp))
                                                    }
                                                })

                                                if (allTimestamps.length < 2) {
                                                    // Fallback: intentar con paquetes de Wireshark si no hay transiciones/muestras
                                                    const clientMac = result.stats?.diagnostics?.user_provided_client_mac ||
                                                        result.stats?.diagnostics?.client_mac ||
                                                        result.band_steering?.devices?.[0]?.mac_address

                                                    if (!clientMac) {
                                                        return 'N/A'
                                                    }

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

                                                    if (devicePackets.length === 0) {
                                                        return 'N/A'
                                                    }

                                                    const timestamps = devicePackets
                                                        .map(p => {
                                                            const ts = p.timestamp
                                                            if (typeof ts === 'string') {
                                                                return parseFloat(ts)
                                                            }
                                                            return ts
                                                        })
                                                        .filter(ts => !isNaN(ts) && ts > 0)

                                                    if (timestamps.length === 0) {
                                                        return 'N/A'
                                                    }

                                                    const minTime = Math.min(...timestamps)
                                                    const maxTime = Math.max(...timestamps)
                                                    const measuredTime = maxTime - minTime

                                                    if (measuredTime <= 0) {
                                                        return 'N/A'
                                                    }

                                                    // Formatear tiempo
                                                    if (measuredTime < 1) {
                                                        return `${(measuredTime * 1000).toFixed(2)}ms`
                                                    } else if (measuredTime < 60) {
                                                        return `${measuredTime.toFixed(3)}s`
                                                    } else {
                                                        const minutes = Math.floor(measuredTime / 60)
                                                        const seconds = (measuredTime % 60).toFixed(3)
                                                        return `${minutes}m ${seconds}s`
                                                    }
                                                }

                                                // Calcular tiempo medido (diferencia entre primer y último timestamp)
                                                const minTime = Math.min(...allTimestamps)
                                                const maxTime = Math.max(...allTimestamps)
                                                const measuredTime = maxTime - minTime

                                                if (measuredTime <= 0) {
                                                    return 'N/A'
                                                }

                                                // Formatear tiempo (mismo formato que el bloque de tiempo en bandas)
                                                if (measuredTime < 1) {
                                                    return `${(measuredTime * 1000).toFixed(2)}ms`
                                                } else if (measuredTime < 60) {
                                                    return `${measuredTime.toFixed(3)}s`
                                                } else {
                                                    const minutes = Math.floor(measuredTime / 60)
                                                    const seconds = (measuredTime % 60).toFixed(3)
                                                    return `${minutes}m ${seconds}s`
                                                }
                                            })()}
                                        </p>
                                    </div>
                                </div>
                            </Card>

                        </div>

                        {/* Panel derecho: Gráfica de Band Steering */}
                        <Card className="lg:col-span-2 p-6 flex flex-col h-full">
                            <div className="flex items-center gap-2 mb-4">
                                <Activity className="w-5 h-5 text-dark-accent-primary" />
                                <h3 className="text-lg font-semibold text-dark-text-primary">
                                    Visualización de Cambios de Banda
                                </h3>
                            </div>
                            <div className="flex-1 min-h-[300px]">
                                <BandSteeringChart
                                    btmEvents={result.band_steering?.btm_events || []}
                                    transitions={result.band_steering?.transitions || []}
                                    signalSamples={result.band_steering?.signal_samples || []}
                                    rawStats={result.stats || {}}
                                />
                            </div>
                        </Card>

                    </div>

                    {/* 3. Tiempo en cada banda y en transición */}
                    {(() => {
                        const transitions = result.band_steering?.transitions || []
                        const signalSamples = result.band_steering?.signal_samples || []

                        const normalizeBand = (band) => {
                            if (!band) return ''
                            const b = band.toString().toLowerCase()
                            if (b.includes('2.4') || b.includes('2,4')) return '2.4GHz'
                            if (b.includes('5')) return '5GHz'
                            return band
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

                        const formatSeconds = (seconds) => {
                            if (seconds == null || Number.isNaN(seconds) || seconds <= 0) return '0 s'
                            if (seconds < 1) return `${(seconds * 1000).toFixed(0)} ms`
                            if (seconds < 60) return `${seconds.toFixed(2)} s`
                            const minutes = Math.floor(seconds / 60)
                            const rem = seconds % 60
                            return `${minutes} min ${rem.toFixed(1)} s`
                        }

                        // Cálculo del tiempo en cada banda y en transición
                        let bandTiming = null
                        try {
                            console.log('🔍 [BAND_TIMING] Iniciando cálculo de bandTiming')
                            console.log('🔍 [BAND_TIMING] signalSamples recibidos:', signalSamples?.length || 0)
                            console.log('🔍 [BAND_TIMING] transitions recibidas:', transitions?.length || 0)
                            
                            const sortedTransitions = (transitions || [])
                                .filter(t => t && t.start_time != null && t.is_successful)
                                .sort((a, b) => Number(a.start_time) - Number(b.start_time))
                            
                            console.log('🔍 [BAND_TIMING] sortedTransitions filtradas:', sortedTransitions.length)

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
                                        const transStart = normalizeTimestamp(t.start_time) || 0
                                        const samplesBefore = signalSamples
                                            .filter(s => {
                                                const sTs = normalizeTimestamp(s.timestamp)
                                                return sTs != null && sTs < transStart
                                            })
                                            .sort((a, b) => {
                                                const aTs = normalizeTimestamp(a.timestamp) || 0
                                                const bTs = normalizeTimestamp(b.timestamp) || 0
                                                return bTs - aTs
                                            })
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
                            
                            console.log('🔍 [BAND_TIMING] validSamples procesados:', validSamples.length)
                            if (validSamples.length > 0) {
                                console.log('🔍 [BAND_TIMING] Primer sample:', validSamples[0])
                                console.log('🔍 [BAND_TIMING] Último sample:', validSamples[validSamples.length - 1])
                            }
                            
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
                            
                            console.log('🔍 [BAND_TIMING] sampleTimestamps.length:', sampleTimestamps.length)
                            console.log('🔍 [BAND_TIMING] validTransitions.length:', validTransitions.length)

                            if (sampleTimestamps.length > 1) {
                                // Usar solo signalSamples para minTime y maxTime (como la gráfica)
                                minTime = Math.min(...sampleTimestamps)
                                maxTime = Math.max(...sampleTimestamps)
                                totalTime = maxTime - minTime
                                console.log('🔍 [BAND_TIMING] Usando signalSamples - minTime:', minTime, 'maxTime:', maxTime, 'totalTime:', totalTime)
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
                                console.log('🔍 [BAND_TIMING] transitionTimestamps:', transitionTimestamps)
                                if (transitionTimestamps.length > 0) {
                                    minTime = Math.min(...transitionTimestamps)
                                    maxTime = Math.max(...transitionTimestamps)
                                    // Si solo hay una transición, agregar un margen mínimo
                                    if (minTime === maxTime) {
                                        maxTime = minTime + 1.0 // 1 segundo mínimo
                                    }
                                    totalTime = maxTime - minTime
                                    console.log('🔍 [BAND_TIMING] Usando transiciones - minTime:', minTime, 'maxTime:', maxTime, 'totalTime:', totalTime)
                                } else {
                                    minTime = 0
                                    maxTime = 1
                                    totalTime = 1
                                    console.log('🔍 [BAND_TIMING] Sin timestamps válidos en transiciones, usando valores por defecto')
                                }
                            } else {
                                // Sin datos suficientes, usar valores por defecto mínimos
                                minTime = 0
                                maxTime = 1
                                totalTime = 1
                                console.log('🔍 [BAND_TIMING] Sin datos suficientes, usando valores por defecto mínimos')
                            }

                            console.log('🔍 [BAND_TIMING] totalTime calculado:', totalTime)

                                if (totalTime > 0) {
                                    let time24 = 0
                                    let time5 = 0

                                    const bandTimeline = []
                                console.log('🔍 [BAND_TIMING] Iniciando cálculo de time24 y time5')
                                console.log('🔍 [BAND_TIMING] validTransitions.length:', validTransitions.length)
                                console.log('🔍 [BAND_TIMING] validSamples.length:', validSamples.length)
                                
                                    if (validTransitions.length > 0) {
                                    console.log('🔍 [BAND_TIMING] Usando lógica de validTransitions')
                                        const firstTrans = validTransitions[0]
                                        let initialBand = normalizeBand(firstTrans.from_band || '')
                                        if (!initialBand && signalSamples.length > 0) {
                                        const firstTransStart = normalizeTimestamp(firstTrans.start_time) || 0
                                        const samplesBeforeFirstTrans = signalSamples
                                            .filter(s => {
                                                const sTs = normalizeTimestamp(s.timestamp)
                                                return sTs != null && sTs < firstTransStart
                                            })
                                            .sort((a, b) => {
                                                const aTs = normalizeTimestamp(a.timestamp) || 0
                                                const bTs = normalizeTimestamp(b.timestamp) || 0
                                                return bTs - aTs
                                            })
                                            if (samplesBeforeFirstTrans.length > 0) {
                                                initialBand = normalizeBand(samplesBeforeFirstTrans[0].band || '')
                                            }
                                        }
                                        if (!initialBand) initialBand = normalizeBand(firstTrans.to_band || '')

                                        // Período inicial antes de la primera transición
                                    const firstTransStart = normalizeTimestamp(firstTrans.start_time) || 0
                                    if (initialBand && firstTransStart > minTime) {
                                            bandTimeline.push({
                                                band: initialBand,
                                                start: minTime,
                                            end: firstTransStart
                                            })
                                        }

                                        // Períodos entre transiciones
                                        for (let i = 0; i < validTransitions.length; i++) {
                                            const t = validTransitions[i]
                                            const fromBand = normalizeBand(t.from_band || '')
                                            const toBand = normalizeBand(t.to_band || '')
                                        const transStart = normalizeTimestamp(t.start_time) || 0
                                        const transEnd = normalizeTimestamp(t.end_time) || transStart

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

                                    console.log('🔍 [BAND_TIMING] bandTimeline generada:', bandTimeline.length, 'períodos')
                                    console.log('🔍 [BAND_TIMING] bandTimeline:', bandTimeline)

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
                                    
                                    console.log('🔍 [BAND_TIMING] Después de procesar bandTimeline - time24:', time24, 'time5:', time5)
                                    } else if (validSamples.length > 0) {
                                    console.log('🔍 [BAND_TIMING] Usando lógica de validSamples')
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
                                    console.log('🔍 [BAND_TIMING] Después de procesar validSamples - time24:', time24, 'time5:', time5)
                                } else if (validTransitions.length > 0) {
                                    // FALLBACK: Calcular tiempo en cada banda basándose solo en transiciones
                                    // cuando no hay suficientes signalSamples
                                    console.log('🔍 [BAND_TIMING] Usando FALLBACK: solo transiciones')
                                    let currentBand = null
                                    let lastTime = minTime
                                    
                                    for (let i = 0; i < validTransitions.length; i++) {
                                        const t = validTransitions[i]
                                        const fromBand = normalizeBand(t.from_band || '')
                                        const toBand = normalizeBand(t.to_band || '')
                                        const transStart = normalizeTimestamp(t.start_time) || 0
                                        const transEnd = normalizeTimestamp(t.end_time) || transStart
                                        
                                        // Determinar banda inicial si es la primera transición
                                        if (i === 0 && fromBand) {
                                            currentBand = fromBand
                                            // Tiempo antes de la primera transición
                                            if (transStart > minTime) {
                                                const periodDuration = transStart - minTime
                                                if (currentBand === '2.4GHz') {
                                                    time24 += periodDuration
                                                } else if (currentBand === '5GHz') {
                                                    time5 += periodDuration
                                                }
                                            }
                                        }
                                        
                                        // Tiempo en la banda destino después de la transición
                                        if (toBand) {
                                            const nextTransStart = (i + 1 < validTransitions.length) 
                                                ? Number(validTransitions[i + 1].start_time || 0) 
                                                : maxTime
                                            const periodDuration = nextTransStart - transEnd
                                            
                                            if (periodDuration > 0) {
                                                if (toBand === '2.4GHz') {
                                                    time24 += periodDuration
                                                } else if (toBand === '5GHz') {
                                                    time5 += periodDuration
                                                }
                                            }
                                            currentBand = toBand
                                        }
                                    }
                                    
                                    // Si no hay transiciones pero hay una banda conocida, asignar todo el tiempo a esa banda
                                    if (validTransitions.length === 0 && signalSamples.length > 0) {
                                        const firstSample = signalSamples[0]
                                        const band = normalizeBand(firstSample.band || '')
                                        if (band === '2.4GHz') {
                                            time24 = totalTime
                                        } else if (band === '5GHz') {
                                            time5 = totalTime
                                        }
                                    }
                                    }

                                    const totalTransitionTime = transitionDurations.reduce((a, b) => a + b, 0)
                                    const totalBandTime = time24 + time5
                                    const expectedTotal = totalTime - totalTransitionTime

                                console.log('🔍 [BAND_TIMING] ANTES de ajuste - time24:', time24, 'time5:', time5)
                                console.log('🔍 [BAND_TIMING] totalTransitionTime:', totalTransitionTime)
                                console.log('🔍 [BAND_TIMING] totalBandTime:', totalBandTime)
                                console.log('🔍 [BAND_TIMING] expectedTotal:', expectedTotal)
                                console.log('🔍 [BAND_TIMING] totalTime:', totalTime)

                                    // Ajustar tiempos si hay discrepancia, pero mantener la proporción
                                    if (expectedTotal > 0 && Math.abs(totalBandTime - expectedTotal) > 0.1) {
                                    console.log('🔍 [BAND_TIMING] Aplicando ajuste de tiempos - discrepancia detectada')
                                        if (totalBandTime > expectedTotal * 1.1) {
                                            // Si el tiempo de banda es mucho mayor, escalar hacia abajo
                                            const scale = expectedTotal / totalBandTime
                                            time24 *= scale
                                            time5 *= scale
                                        console.log('🔍 [BAND_TIMING] Escalando hacia abajo - scale:', scale)
                                        } else if (totalBandTime < expectedTotal * 0.9) {
                                            // Si el tiempo de banda es menor, ajustar proporcionalmente
                                            const scale = expectedTotal / totalBandTime
                                            time24 *= scale
                                            time5 *= scale
                                        console.log('🔍 [BAND_TIMING] Escalando hacia arriba - scale:', scale)
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
                                
                                console.log('🔍 [BAND_TIMING] DESPUÉS de ajuste - time24:', time24, 'time5:', time5)
                                console.log('🔍 [BAND_TIMING] finalTotalBandTime:', finalTotalBandTime)
                                console.log('🔍 [BAND_TIMING] finalTotalTime:', finalTotalTime)
                                console.log('🔍 [BAND_TIMING] transitionsWithDuration:', transitionsWithDuration.length)
                                    
                                    bandTiming = {
                                        time24,
                                        time5,
                                        totalTime: finalTotalTime, // Tiempo total incluyendo transiciones para que los porcentajes sumen 100%
                                        totalBandTime: finalTotalBandTime,
                                        totalTransitionTime,
                                        transitions: transitionsWithDuration,
                                        transitionDurations
                                    }
                                
                                console.log('🔍 [BAND_TIMING] bandTiming final:', bandTiming)
                            } else {
                                console.warn('⚠️ [BAND_TIMING] totalTime <= 0, no se puede calcular bandTiming')
                            }
                        } catch (e) {
                            console.error('❌ [BAND_TIMING] Error calculando bandTiming:', e)
                            console.error('❌ [BAND_TIMING] Stack trace:', e.stack)
                            bandTiming = null
                        }

                        if (bandTiming) {
                            // Calcular porcentajes basándose en el tiempo total (bandas + transiciones)
                            // para que sumen 100%
                            const totalTimeForPct = bandTiming.totalTime || (bandTiming.time24 + bandTiming.time5 + (bandTiming.totalTransitionTime || 0))
                            const pct24 =
                                totalTimeForPct > 0
                                    ? Math.round(
                                          (bandTiming.time24 / totalTimeForPct) *
                                              100
                                      )
                                    : 0
                            const pct5 =
                                totalTimeForPct > 0
                                    ? Math.round(
                                          (bandTiming.time5 / totalTimeForPct) *
                                              100
                                      )
                                    : 0

                            return (
                                <Card className="p-6">
                                    <div className="space-y-5">
                                        {/* Header */}
                                        <div className="flex items-center gap-2">
                                            <h3 className="text-lg font-semibold text-dark-text-primary">
                                                Tiempo en cada banda y transición
                                            </h3>
                                        </div>

                                        {/* Distribución por banda con barras de progreso */}
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            {/* 2.4GHz Card */}
                                            <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 p-4 space-y-3">
                                                <div className="flex items-center justify-between">
                                                    <div className="flex items-center gap-2">
                                                        <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                                                        <span className="text-sm font-semibold text-dark-text-primary">
                                                            2.4 GHz
                                                        </span>
                                                    </div>
                                                    <span className="text-lg font-bold text-blue-400">
                                                        {pct24}%
                                                    </span>
                                                </div>
                                                
                                                {/* Barra de progreso */}
                                                <div className="w-full h-2.5 bg-dark-bg-secondary/50 rounded-full overflow-hidden">
                                                    <div 
                                                        className="h-full bg-blue-500 rounded-full transition-all duration-500"
                                                        style={{ width: `${pct24}%` }}
                                                    ></div>
                                                </div>
                                                
                                                <div className="text-md text-dark-text-secondary font-mono text-end">
                                                    {formatSeconds(bandTiming.time24)}
                                                </div>
                                            </div>

                                            {/* 5GHz Card */}
                                            <div className="rounded-lg border border-green-500/30 bg-green-500/10 p-4 space-y-3">
                                                <div className="flex items-center justify-between">
                                                    <div className="flex items-center gap-2">
                                                        <div className="w-3 h-3 rounded-full bg-green-500"></div>
                                                        <span className="text-sm font-semibold text-dark-text-primary">
                                                            5 GHz
                                                        </span>
                                                    </div>
                                                    <span className="text-lg font-bold text-green-400">
                                                        {pct5}%
                                                    </span>
                                                </div>
                                                
                                                {/* Barra de progreso */}
                                                <div className="w-full h-2.5 bg-dark-bg-secondary/50 rounded-full overflow-hidden">
                                                    <div 
                                                        className="h-full bg-green-500 rounded-full transition-all duration-500"
                                                        style={{ width: `${pct5}%` }}
                                                    ></div>
                                                </div>
                                                
                                                <div className="text-md text-dark-text-secondary font-mono text-end">
                                                    {formatSeconds(bandTiming.time5)}
                                                </div>
                                            </div>
                                        </div>

                                        {/* Lista de cambios de banda individuales */}
                                        {bandTiming.transitions &&
                                            bandTiming.transitions.length > 0 && (
                                                <div className="space-y-3 pt-2 border-t border-dark-border-primary/20">
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-sm font-semibold text-dark-text-primary">
                                                            Cambios de banda observados
                                                        </span>
                                                        <span className="px-2 py-0.5 rounded-full bg-dark-accent-primary/20 text-xs font-semibold text-dark-accent-primary">
                                                            {bandTiming.transitions.length}
                                                        </span>
                                                    </div>
                                                    
                                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
                                                        {bandTiming.transitions.map((t, idx) => {
                                                            const is24to5 = t.fromBand === '2.4GHz' && t.toBand === '5GHz'
                                                            const is5to24 = t.fromBand === '5GHz' && t.toBand === '2.4GHz'
                                                            const borderColor = is24to5 
                                                                ? 'border-blue-500/30 bg-blue-500/5' 
                                                                : is5to24 
                                                                    ? 'border-green-500/30 bg-green-500/5'
                                                                    : 'border-dark-border-primary/20 bg-dark-bg-secondary/30'
                                                            
                                                            return (
                                                                <div
                                                                    key={idx}
                                                                    className={`rounded-lg border ${borderColor} p-3 flex items-center justify-between gap-2 transition-all hover:scale-[1.02]`}
                                                                >
                                                                    <div className="flex items-center gap-2 flex-1 min-w-0">
                                                                        <div className={`w-2 h-2 rounded-full ${is24to5 ? 'bg-blue-500' : is5to24 ? 'bg-green-500' : 'bg-dark-accent-primary'}`}></div>
                                                                        <span className="text-xs font-medium text-dark-text-primary truncate">
                                                                            {t.fromBand || '?'} → {t.toBand || '?'}
                                                                        </span>
                                                                    </div>
                                                                    <span className="text-md font-mono font-semibold text-dark-text-secondary whitespace-nowrap">
                                                                        {formatSeconds(t.duration)}
                                                                    </span>
                                                                </div>
                                                            )
                                                        })}
                                                    </div>
                                                </div>
                                            )}
                                    </div>
                                </Card>
                            )
                        }
                        return null
                    })()}

                    {/* 4. Panel de Wireshark Source of Truth */}
                    {result.stats?.diagnostics?.wireshark_raw && (
                        <Card className="p-6">
                            <WiresharkTruthPanel
                                wiresharkRaw={result.stats.diagnostics.wireshark_raw}
                                wiresharkCompare={result.stats.diagnostics.wireshark_compare}
                                ssid={savedSsid || fileMetadata?.ssid || userSsid}
                            />
                        </Card>
                    )}

                    {/* 6. Contenido del Análisis (Markdown) */}
                    {result.analysis && (
                        <Card className="p-6">
                            <div className="max-w-none">
                                <div className="text-dark-text-primary leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                                    <MarkdownRenderer content={result.analysis || ''} />
                                </div>
                            </div>
                        </Card>
                    )}

                </div>
            )}

            {/* Estilos para impresión */}
            <style dangerouslySetInnerHTML={{ __html: PRINT_STYLES }} />
        </div>
    )
}

export default NetworkAnalysisPage

