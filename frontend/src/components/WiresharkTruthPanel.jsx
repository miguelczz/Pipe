import React, { useState, useMemo } from 'react'
import { 
  Search,
  ChevronRight,
  ChevronDown,
  Wifi,
  CheckCircle2,
  AlertCircle
} from 'lucide-react'

// eslint-disable-next-line no-unused-vars
export function WiresharkTruthPanel({ wiresharkRaw, wiresharkCompare, ssid }) {
  const [selectedPacket, setSelectedPacket] = useState(null)
  const [filterText, setFilterText] = useState('')
  const [filterType, setFilterType] = useState('all') // 'all', 'btm', 'assoc', 'deauth', 'beacon'
  const [expandedDetails, setExpandedDetails] = useState({})

  // Procesar muestras para crear paquetes estilo Wireshark
  const packets = useMemo(() => {
    if (!wiresharkRaw) {
      return []
    }
    const sample = wiresharkRaw.sample || []

    // Si no tenemos muestra de paquetes, igual queremos renderizar el panel
    // para que el usuario vea los contadores de Wireshark; en ese caso,
    // simplemente no habrá filas en la tabla.
    if (!sample.length) return []

    return sample.map((row, idx) => {
      // Determinar tipo de frame y protocolo
      let frameType = 'Unknown'
      let protocol = '802.11'
      let info = ''
      let color = 'text-gray-400'
      
      const subtype = row.subtype || ''
      const category = row.category_code || ''
      const action = row.action_code || ''
      
      // Determinar tipo de frame (subtype ya viene normalizado del backend)
      if (subtype) {
        const subtypeInt = parseInt(subtype) || 0
        
        switch (subtypeInt) {
          case 0:
            frameType = 'Association Request'
            protocol = '802.11'
            info = `Association Request: ${row.wlan_sa || 'N/A'}`
            color = 'text-blue-400'
            break
          case 1: {
            frameType = 'Association Response'
            protocol = '802.11'
            const assocStatus = row.assoc_status_code || '0'
            const assocStatusInt = parseInt(assocStatus) || 0
            info = `Association Response: Status=${assocStatusInt} ${assocStatusInt === 0 ? '✓' : '✗'}`
            color = assocStatusInt === 0 ? 'text-green-400' : 'text-red-400'
            break
          }
          case 2:
            frameType = 'Reassociation Request'
            protocol = '802.11'
            info = `Reassociation Request: ${row.wlan_sa || 'N/A'}`
            color = 'text-blue-400'
            break
          case 3: {
            frameType = 'Reassociation Response'
            protocol = '802.11'
            const reassocStatus = row.assoc_status_code || '0'
            const reassocStatusInt = parseInt(reassocStatus) || 0
            info = `Reassociation Response: Status=${reassocStatusInt} ${reassocStatusInt === 0 ? '✓' : '✗'}`
            color = reassocStatusInt === 0 ? 'text-green-400' : 'text-red-400'
            break
          }
          case 8:
            frameType = 'Beacon'
            protocol = '802.11'
            info = `Beacon: ${row.ssid || 'N/A'}`
            color = 'text-cyan-400'
            break
          case 10:
            frameType = 'Disassociation'
            protocol = '802.11'
            info = `Disassociation: Reason=${row.reason_code || 'N/A'}`
            color = 'text-orange-400'
            break
          case 12:
            frameType = 'Deauthentication'
            protocol = '802.11'
            info = `Deauthentication: Reason=${row.reason_code || 'N/A'}`
            color = 'text-red-400'
            break
          case 13: {
            // Action Frame (category y action ya vienen normalizados del backend)
            const catInt = parseInt(category) || -1
            const actInt = parseInt(action) || -1
            
            if (catInt === 10) { // WNM (802.11v)
              if (actInt === 7) {
                frameType = 'BTM Request'
                protocol = '802.11v'
                info = `BTM Request: ${row.wlan_da || 'N/A'}`
                color = 'text-yellow-400'
              } else if (actInt === 8) {
                frameType = 'BTM Response'
                protocol = '802.11v'
                const btmStatus = row.btm_status_code || '0'
                const btmStatusInt = parseInt(btmStatus) || 0
                info = `BTM Response: Status=${btmStatusInt} ${btmStatusInt === 0 ? '✓ Accept' : '✗ Reject'}`
                color = btmStatusInt === 0 ? 'text-green-400' : 'text-red-400'
              } else {
                frameType = 'Action Frame (WNM)'
                protocol = '802.11v'
                info = `WNM Action: ${actInt}`
                color = 'text-purple-400'
              }
            } else {
              frameType = 'Action Frame'
              protocol = '802.11'
              info = `Action: Category=${catInt}`
              color = 'text-gray-400'
            }
            break
          }
          default:
            frameType = `802.11 (Subtype ${subtypeInt})`
            protocol = '802.11'
            info = `Frame Type: ${subtypeInt}`
        }
      }
      
      // Calcular banda desde frecuencia
      let band = 'Unknown'
      if (row.frequency) {
        const freq = parseInt(row.frequency) || 0
        if (freq >= 2400 && freq <= 2500) band = '2.4 GHz'
        else if (freq >= 5000 && freq <= 6000) band = '5 GHz'
      }
      
      // Usar source/destination normalizados si están disponibles, sino usar wlan_sa/wlan_da
      const source = row.source || row.wlan_sa || row.bssid || 'N/A'
      const destination = row.destination || row.wlan_da || 'Broadcast'
      
      return {
        no: idx + 1,
        time: parseFloat(row.timestamp) || 0,
        source: source,
        destination: destination,
        protocol,
        length: parseInt(row.frame_len) || 0,
        info,
        frameType,
        color,
        band,
        frequency: row.frequency || 'N/A',
        rssi: row.signal_strength || 'N/A',
        bssid: row.bssid || 'N/A',
        ssid: row.ssid || 'N/A',
        subtype: row.subtype || 'N/A',
        category_code: row.category_code || 'N/A',
        action_code: row.action_code || 'N/A',
        btm_status_code: row.btm_status_code || 'N/A',
        assoc_status_code: row.assoc_status_code || 'N/A',
        reason_code: row.reason_code || 'N/A',
        frame_len: row.frame_len || 'N/A',
        ip_src: row.ip_src || 'N/A',
        ip_dst: row.ip_dst || 'N/A',
        protocols: row.protocols || 'N/A',
        client_mac: row.client_mac || 'N/A',
        ap_mac: row.ap_mac || 'N/A',
        raw: row
      }
    })
  }, [wiresharkRaw])

  // Filtrar paquetes
  const filteredPackets = useMemo(() => {
    let filtered = packets

    // Filtro por tipo
    if (filterType !== 'all') {
      filtered = filtered.filter(p => {
        switch (filterType) {
          case 'btm':
            return p.frameType.includes('BTM')
          case 'assoc':
            return p.frameType.includes('Association') || p.frameType.includes('Reassociation')
          case 'deauth':
            return p.frameType.includes('Deauth') || p.frameType.includes('Disassoc')
          case 'beacon':
            return p.frameType.includes('Beacon')
          default:
            return true
        }
      })
    }

    // Filtro por texto
    if (filterText) {
      const searchLower = filterText.toLowerCase()
      filtered = filtered.filter(p => 
        p.source.toLowerCase().includes(searchLower) ||
        p.destination.toLowerCase().includes(searchLower) ||
        p.info.toLowerCase().includes(searchLower) ||
        p.frameType.toLowerCase().includes(searchLower) ||
        p.bssid.toLowerCase().includes(searchLower)
      )
    }

    return filtered
  }, [packets, filterText, filterType])

  if (!wiresharkRaw) {
    return null
  }

  // Formatear tiempo relativo
  const formatTime = (timestamp) => {
    if (!timestamp || timestamp === 0) return '0.000000'
    const firstTime = packets[0]?.time || timestamp
    const relative = timestamp - firstTime
    return relative.toFixed(6)
  }

  const toggleDetail = (key) => {
    setExpandedDetails(prev => ({
      ...prev,
      [key]: !prev[key]
    }))
  }

  const isTruncated = wiresharkRaw.truncated || wiresharkRaw.storage_limited
  const originalCount = wiresharkRaw.original_count || wiresharkRaw.sample?.length || packets.length

  return (
    <div className="bg-[#1e1e1e] rounded-lg border border-gray-700 overflow-hidden">
      {/* Header estilo Wireshark */}
      <div className="bg-[#2d2d2d] border-b border-gray-700 px-4 py-2 flex flex-col gap-2">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Wifi className="w-5 h-5 text-blue-400" />
            <div className="flex flex-col">
              <h3 className="text-sm font-semibold text-gray-200">Wireshark Packet List</h3>
              {ssid && (
                <span className="text-[10px] text-gray-400 mt-0.5">Red: {ssid}</span>
              )}
            </div>
            <span className="text-xs text-gray-400 bg-gray-700 px-2 py-1 rounded">
              {filteredPackets.length} / {packets.length} packets
              {isTruncated && originalCount > packets.length && (
                <span className="ml-1 text-yellow-400">(de {originalCount} total)</span>
              )}
            </span>
            {isTruncated && (
              <span className="text-xs text-yellow-400 bg-yellow-500/20 px-2 py-1 rounded flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {wiresharkRaw.storage_limited ? 'Limitado por almacenamiento' : 'Truncado'}
              </span>
            )}
          </div>
          
          {/* Filtros */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-4 h-4 text-gray-400 absolute left-2 top-1/2 transform -translate-y-1/2" />
              <input
                type="text"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                placeholder="Filter packets..."
                className="bg-[#1e1e1e] border border-gray-600 rounded px-8 py-1.5 text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500 w-48"
              />
            </div>
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="bg-[#1e1e1e] border border-gray-600 rounded px-3 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-blue-500"
            >
              <option value="all">All</option>
              <option value="btm">BTM</option>
              <option value="assoc">Association</option>
              <option value="deauth">Deauth/Disassoc</option>
              <option value="beacon">Beacon</option>
            </select>
          </div>
        </div>

        {/* Resumen de coherencia con datos procesados */}
        {/* {wiresharkCompare?.enabled && wiresharkCompare?.total_mismatches > 0 && (
          <div className="flex items-center justify-between gap-3 text-[11px] text-gray-300 bg-[#1e293b]/60 px-3 py-1.5 rounded border border-gray-700/70">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-3.5 h-3.5 text-yellow-400" />
              <span className="font-semibold">
                Fuente de verdad: captura Wireshark
              </span>
              <span className="text-gray-400">
                Se detectaron pequeñas diferencias entre los contadores crudos y las métricas procesadas. 
                La UI prioriza siempre los valores de Wireshark como referencia.
              </span>
            </div>
            <div className="flex items-center gap-3 text-[10px] text-gray-400">
              <span>
                BTM raw: {wiresharkCompare.summary?.raw_btm_requests ?? 0} req / {wiresharkCompare.summary?.raw_btm_accept ?? 0} accept
              </span>
              <span>
                Steering procesado: {wiresharkCompare.summary?.processed_successful_transitions ?? 0} / {wiresharkCompare.summary?.processed_steering_attempts ?? 0}
              </span>
            </div>
          </div>
        )} */}
      </div>

      {/* Tabla de paquetes estilo Wireshark */}
      <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
        {packets.length === 0 ? (
          <div className="px-4 py-6 text-xs text-gray-400">
            No hay muestra de paquetes (`sample`) disponible, pero todos los contadores de esta vista
            provienen directamente del resumen de la captura (`wireshark_raw.summary`).
          </div>
        ) : (
          <table className="w-full text-xs font-mono">
            <thead className="bg-[#2d2d2d] sticky top-0 z-10">
              <tr className="border-b border-gray-700">
                <th className="text-left px-3 py-2 text-gray-300 font-semibold w-16">No.</th>
                <th className="text-left px-3 py-2 text-gray-300 font-semibold w-32">Time</th>
                <th className="text-left px-3 py-2 text-gray-300 font-semibold w-40">Source</th>
                <th className="text-left px-3 py-2 text-gray-300 font-semibold w-40">Destination</th>
                <th className="text-left px-3 py-2 text-gray-300 font-semibold w-24">Protocol</th>
                <th className="text-left px-3 py-2 text-gray-300 font-semibold w-20">Band</th>
                <th className="text-left px-3 py-2 text-gray-300 font-semibold">Info</th>
              </tr>
            </thead>
            <tbody>
              {filteredPackets.map((packet) => (
                <React.Fragment key={packet.no}>
                  <tr
                    onClick={() => setSelectedPacket(selectedPacket?.no === packet.no ? null : packet)}
                    className={`border-b border-gray-800 hover:bg-[#2d2d2d] cursor-pointer transition-colors ${
                      selectedPacket?.no === packet.no ? 'bg-[#2d4a5a]' : ''
                    }`}
                  >
                    <td className="px-3 py-2 text-gray-400">{packet.no}</td>
                    <td className="px-3 py-2 text-gray-300">{formatTime(packet.time)}</td>
                    <td className="px-3 py-2 text-gray-300">{packet.source}</td>
                    <td className="px-3 py-2 text-gray-300">{packet.destination}</td>
                    <td className="px-3 py-2 text-blue-400">{packet.protocol}</td>
                    <td className="px-3 py-2 text-gray-400">{packet.band}</td>
                    <td className={`px-3 py-2 ${packet.color}`}>{packet.info}</td>
                  </tr>
                  
                  {/* Panel de detalles del paquete seleccionado */}
                  {selectedPacket?.no === packet.no && (
                    <tr>
                      <td colSpan="7" className="px-0 py-0 bg-[#1e1e1e]">
                        <div className="border-t border-gray-700">
                          <div className="grid grid-cols-2 gap-0">
                            {/* Panel izquierdo: Tree view de campos */}
                            <div className="border-r border-gray-700 p-3 max-h-[400px] overflow-y-auto">
                              <div className="space-y-1 text-xs">
                                <PacketDetailSection
                                  title="Frame"
                                  data={{
                                    "Frame Number": packet.no,
                                    "Arrival Time": new Date(packet.time * 1000).toISOString(),
                                    "Time Delta": formatTime(packet.time),
                                    "Length": packet.length || packet.frame_len || 'N/A',
                                    "Protocols": packet.protocols || 'N/A',
                                    "Band": packet.band,
                                    "Frequency": packet.frequency,
                                    "RSSI": packet.rssi
                                  }}
                                  expanded={expandedDetails[`frame-${packet.no}`]}
                                  onToggle={() => toggleDetail(`frame-${packet.no}`)}
                                />
                                
                                {(packet.ip_src && packet.ip_src !== 'N/A') && (
                                  <PacketDetailSection
                                    title="Internet Protocol"
                                    data={{
                                      "Source": packet.ip_src,
                                      "Destination": packet.ip_dst || 'N/A'
                                    }}
                                    expanded={expandedDetails[`ip-${packet.no}`]}
                                    onToggle={() => toggleDetail(`ip-${packet.no}`)}
                                  />
                                )}
                                
                                <PacketDetailSection
                                  title="IEEE 802.11"
                                  data={{
                                    "Type": packet.frameType,
                                    "Subtype": packet.subtype,
                                    "BSSID": packet.bssid,
                                    "Source": packet.source,
                                    "Destination": packet.destination,
                                    "SSID": packet.ssid || "N/A"
                                  }}
                                  expanded={expandedDetails[`80211-${packet.no}`]}
                                  onToggle={() => toggleDetail(`80211-${packet.no}`)}
                                />
                                
                                {packet.frameType.includes('BTM') && (
                                  <PacketDetailSection
                                    title="802.11v BTM"
                                    data={{
                                      "Category": packet.category_code,
                                      "Action": packet.action_code,
                                      "Status Code": packet.btm_status_code,
                                      "Status": packet.btm_status_code === '0' || packet.btm_status_code === 0 
                                        ? "Accept ✓" 
                                        : `Reject (Code: ${packet.btm_status_code})`
                                    }}
                                    expanded={expandedDetails[`btm-${packet.no}`]}
                                    onToggle={() => toggleDetail(`btm-${packet.no}`)}
                                  />
                                )}
                                
                                {(packet.frameType.includes('Association') || packet.frameType.includes('Reassociation')) && (
                                  <PacketDetailSection
                                    title="Association"
                                    data={{
                                      "Status Code": packet.assoc_status_code,
                                      "Status": packet.assoc_status_code === '0' || packet.assoc_status_code === 0
                                        ? "Success ✓"
                                        : `Failed (Code: ${packet.assoc_status_code})`
                                    }}
                                    expanded={expandedDetails[`assoc-${packet.no}`]}
                                    onToggle={() => toggleDetail(`assoc-${packet.no}`)}
                                  />
                                )}
                                
                                {(packet.frameType.includes('Deauth') || packet.frameType.includes('Disassoc')) && (
                                  <PacketDetailSection
                                    title="Disconnection"
                                    data={{
                                      "Reason Code": packet.reason_code,
                                      "Type": packet.frameType
                                    }}
                                    expanded={expandedDetails[`deauth-${packet.no}`]}
                                    onToggle={() => toggleDetail(`deauth-${packet.no}`)}
                                  />
                                )}
                              </div>
                            </div>
                            
                            {/* Panel derecho: Hex dump (simulado) */}
                            <div className="p-3 bg-[#1a1a1a] max-h-[400px] overflow-y-auto">
                              <div className="text-xs text-gray-400 mb-2 font-semibold">Raw Data (JSON)</div>
                              <pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap break-all">
                                {JSON.stringify(packet.raw, null, 2)}
                              </pre>
                            </div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer con estadísticas */}
      <div className="bg-[#2d2d2d] border-t border-gray-700 px-4 py-2 flex items-center justify-between text-xs text-gray-400">
        <div className="flex items-center gap-4">
          <span>Displayed: {filteredPackets.length}</span>
        </div>
        <div className="flex items-center gap-2">
          {wiresharkRaw.summary?.btm?.requests > 0 && (
            <span className="flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3 text-green-400" />
              BTM: {wiresharkRaw.summary.btm.requests} req, {wiresharkRaw.summary.btm.responses_accept} accept
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

// Componente auxiliar para secciones expandibles de detalles
function PacketDetailSection({ title, data, expanded, onToggle }) {
  return (
    <div className="border-l-2 border-gray-600 pl-2">
      <button
        onClick={onToggle}
        className="flex items-center gap-1 text-gray-300 hover:text-white transition-colors w-full text-left"
      >
        {expanded ? (
          <ChevronDown className="w-3 h-3" />
        ) : (
          <ChevronRight className="w-3 h-3" />
        )}
        <span className="font-semibold">{title}</span>
      </button>
      {expanded && (
        <div className="ml-4 mt-1 space-y-0.5">
          {Object.entries(data).map(([key, value]) => (
            <div key={key} className="flex gap-2">
              <span className="text-gray-500 min-w-[120px]">{key}:</span>
              <span className="text-gray-300">{String(value)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
