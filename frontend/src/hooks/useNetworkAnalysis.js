import React, { useState, useRef } from 'react'
import { networkAnalysisService } from '../services/api'

/**
 * Hook que centraliza la lógica de:
 * - estado de análisis de red
 * - sincronización con localStorage
 * - llamada a networkAnalysisService.analyzeCapture
 *
 * No cambia el comportamiento existente, solo encapsula la lógica.
 */
export function useNetworkAnalysis() {
  const [selectedFile, setSelectedFile] = useState(null)
  const [uploading, setUploading] = useState(false)

  const [result, setResult] = useState(() => {
    try {
      const savedResult = localStorage.getItem('networkAnalysisResult')
      if (!savedResult) return null

      const parsed = JSON.parse(savedResult)
      if (!parsed?.stats) {
        localStorage.removeItem('networkAnalysisResult')
        return null
      }

      return parsed
    } catch {
      return null
    }
  })

  const [fileMetadata, setFileMetadata] = useState(() => {
    try {
      const savedMetadata = localStorage.getItem('networkAnalysisFileMeta')
      return savedMetadata ? JSON.parse(savedMetadata) : null
    } catch {
      return null
    }
  })

  const [savedSsid, setSavedSsid] = useState(() => {
    try {
      const savedMetadata = localStorage.getItem('networkAnalysisFileMeta')
      if (savedMetadata) {
        const meta = JSON.parse(savedMetadata)
        if (meta?.ssid) return meta.ssid
      }
      const savedResult = localStorage.getItem('networkAnalysisResult')
      if (savedResult) {
        const parsed = JSON.parse(savedResult)
        if (parsed?.stats?.diagnostics?.user_metadata?.ssid) {
          return parsed.stats.diagnostics.user_metadata.ssid
        }
      }
      return ''
    } catch {
      return ''
    }
  })

  const [error, setError] = useState('')
  const fileInputRef = useRef(null)

  const [userSsid, setUserSsid] = useState('')
  const [userClientMac, setUserClientMac] = useState(() => {
    try {
      const savedMetadata = localStorage.getItem('networkAnalysisFileMeta')
      if (savedMetadata) {
        const meta = JSON.parse(savedMetadata)
        if (meta?.client_mac) {
          return meta.client_mac
        }
      }
      const savedResult = localStorage.getItem('networkAnalysisResult')
      if (savedResult) {
        const parsed = JSON.parse(savedResult)
        if (parsed?.stats?.diagnostics?.user_metadata?.client_mac) {
          return parsed.stats.diagnostics.user_metadata.client_mac
        }
      }
      return ''
    } catch {
      return ''
    }
  })

  const sanitizeResultForStorage = (data) => {
    if (!data) return null

    const sanitized = JSON.parse(JSON.stringify(data))

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

  React.useEffect(() => {
    if (result) {
      try {
        const sanitized = sanitizeResultForStorage(result)
        localStorage.setItem('networkAnalysisResult', JSON.stringify(sanitized))
      } catch {
        try {
          const minimal = sanitizeResultForStorage(result)
          if (minimal?.stats?.diagnostics?.wireshark_raw) {
            delete minimal.stats.diagnostics.wireshark_raw.sample
            minimal.stats.diagnostics.wireshark_raw.storage_limited = true
          }
          localStorage.setItem('networkAnalysisResult', JSON.stringify(minimal))
        } catch {
          // ignorar
        }
      }
    }
  }, [result])

  React.useEffect(() => {
    try {
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
    } catch {
      // ignorar
    }
  }, [fileMetadata, result])

  const handleSelectClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }

    if (!userSsid.trim() || !userClientMac.trim()) {
      setError(
        'Debes ingresar el SSID de la red y la MAC del cliente antes de analizar una captura.'
      )
      return
    }

    fileInputRef.current?.click()
  }

  const performAnalysis = async (file, meta) => {
    setUploading(true)
    setError('')
    setResult(null)

    try {
      const res = await networkAnalysisService.analyzeCapture(file, {
        ssid: userSsid || null,
        client_mac: userClientMac || null,
      })

      setResult(res)
      const ssidValue = userSsid.trim() || ''
      const clientMacValue = userClientMac.trim() || ''
      const metaWithSsid = {
        ...meta,
        ssid: ssidValue,
        client_mac: clientMacValue,
      }
      setSavedSsid(ssidValue)
      try {
        const sanitized = sanitizeResultForStorage(res)
        if (sanitized.stats?.diagnostics) {
          if (!sanitized.stats.diagnostics.user_metadata) {
            sanitized.stats.diagnostics.user_metadata = {}
          }
          if (ssidValue) {
            sanitized.stats.diagnostics.user_metadata.ssid = ssidValue
          }
          if (clientMacValue) {
            sanitized.stats.diagnostics.user_metadata.client_mac = clientMacValue
          }
        }
        localStorage.setItem(
          'networkAnalysisResult',
          JSON.stringify(sanitized)
        )
        localStorage.setItem(
          'networkAnalysisFileMeta',
          JSON.stringify(metaWithSsid)
        )
      } catch {
        try {
          const minimal = sanitizeResultForStorage(res)
          if (minimal?.stats?.diagnostics?.wireshark_raw) {
            delete minimal.stats.diagnostics.wireshark_raw.sample
            minimal.stats.diagnostics.wireshark_raw.storage_limited = true
          }
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
          localStorage.setItem(
            'networkAnalysisResult',
            JSON.stringify(minimal)
          )
          localStorage.setItem(
            'networkAnalysisFileMeta',
            JSON.stringify(metaWithSsid)
          )
        } catch {
          // ignorar
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

    localStorage.removeItem('networkAnalysisResult')
    localStorage.removeItem('networkAnalysisFileMeta')

    setError('')
    setSelectedFile(file)
    const meta = {
      name: file.name,
      size: file.size,
      ssid: userSsid.trim() || '',
      client_mac: userClientMac.trim() || '',
    }
    setFileMetadata(meta)
    setSavedSsid(userSsid.trim() || '')
    setResult(null)

    performAnalysis(file, meta)
  }

  const resetAnalysis = () => {
    setSelectedFile(null)
    setResult(null)
    setFileMetadata(null)
    setSavedSsid('')
    setError('')
    try {
      localStorage.removeItem('networkAnalysisResult')
      localStorage.removeItem('networkAnalysisFileMeta')
    } catch {
      // ignorar errores de localStorage
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  return {
    // estado
    selectedFile,
    uploading,
    result,
    fileMetadata,
    savedSsid,
    error,
    userSsid,
    userClientMac,
    // setters / refs
    setUserSsid,
    setUserClientMac,
    setError,
    fileInputRef,
    // handlers
    handleSelectClick,
    handleFileChange,
    resetAnalysis,
  }
}

