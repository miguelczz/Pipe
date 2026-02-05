import React from 'react'
import { Card } from '../components/ui/Card'
import {
    Activity, AlertTriangle, CheckCircle2, XCircle, ShieldCheck, Smartphone, Network
} from 'lucide-react'
import { NetworkAnalysisChartSection } from '../components/network/NetworkAnalysisChartSection'
import { NetworkAnalysisInsightsSection } from '../components/network/NetworkAnalysisInsightsSection'

function formatVerdict(verdict) {
  if (!verdict) return 'N/A'
  const mapping = {
    EXCELLENT: 'Excelente',
    GOOD: 'Bueno',
    PREVENTIVE_SUCCESS: 'Éxito Preventivo',
    FAILED_BTM_REJECT: 'Fallo: Rechazo BTM',
    FAILED_LOOP: 'Fallo: Bucle entre APs',
    FAILED_NO_REASSOC: 'Fallo: Sin reconexión',
    FAILED_ALGORITHM: 'Fallo de algoritmo',
    WARNING_INCONCLUSIVE: 'Inconcluso',
    NOT_EVALUABLE: 'No evaluable',
    FAILED: 'Fallido',
    ACCEPTABLE: 'Aceptable',
    SLOW_BUT_SUCCESSFUL: 'Lento pero Exitoso',
    NO_DATA: 'Sin Datos',
    NO_STEERING_EVENTS: 'Sin Eventos',
    PARTIAL: 'Éxito Parcial',
    SUCCESS: 'Éxito'
  }
  return mapping[verdict] || verdict.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (l) => l.toUpperCase())
}

export function ReportBodyContent({ result, fileMetadata, savedSsid, userSsid }) {
  return (
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
                        <NetworkAnalysisChartSection result={result} />

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
                            
                            // Cálculo de muestras válidas procesadas
                            
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
                            
                            // Datos básicos de rango temporal

                            if (sampleTimestamps.length > 1) {
                                // Usar solo signalSamples para minTime y maxTime (como la gráfica)
                                minTime = Math.min(...sampleTimestamps)
                                maxTime = Math.max(...sampleTimestamps)
                                totalTime = maxTime - minTime
                                // Usar solo signalSamples para minTime y maxTime (como la gráfica)
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
                                    // Usar transiciones como fallback para el rango temporal
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
                                // Sin datos suficientes, usar valores por defecto mínimos
                            }

                            // totalTime calculado para el análisis

                                if (totalTime > 0) {
                                    let time24 = 0
                                    let time5 = 0

                                    const bandTimeline = []
                                // Iniciar cálculo de tiempos por banda
                                
                                    if (validTransitions.length > 0) {
                                    // Usar transiciones válidas para construir la línea de tiempo de bandas
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

                                    // Línea de tiempo de bandas generada

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
                                    // Usar muestras de señal como fuente principal
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
                                
                            // bandTiming final calculado
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

                    <NetworkAnalysisInsightsSection
                        result={result}
                        fileMetadata={fileMetadata}
                        savedSsid={savedSsid}
                        userSsid={userSsid}
                    />
    </div>
  )
}
