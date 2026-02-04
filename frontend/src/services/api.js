import axios from 'axios'
import { API_URL, API_ENDPOINTS } from '../config/constants'

/**
 * Cliente API configurado para comunicarse con el backend FastAPI
 */
const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 120000, // 120 segundos (2 minutos) - el grafo puede tardar más
})

// Interceptor para manejar errores globalmente
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      // El servidor respondió con un código de error
      return Promise.reject({
        message: error.response.data?.detail || 'Error en la petición',
        status: error.response.status,
        data: error.response.data,
      })
    } else if (error.request) {
      // La petición se hizo pero no hubo respuesta
      return Promise.reject({
        message: `No se pudo conectar con el servidor en ${error.config?.baseURL || API_URL}. Verifica que el backend esté corriendo.`,
        status: 0,
        originalError: error,
      })
    } else {
      // Algo más causó el error
      return Promise.reject({
        message: error.message || 'Error desconocido',
        status: 0,
      })
    }
  }
)

/**
 * Servicio para interactuar con el agente
 */
export const agentService = {
  /**
   * Obtiene el historial de mensajes de una sesión
   * @param {string} sessionId - ID de sesión
   * @returns {Promise} - Historial de mensajes
   */
  async getSessionHistory(sessionId) {
    try {
      const response = await apiClient.get(`${API_ENDPOINTS.AGENT_SESSION}/${sessionId}`)
      return response.data
    } catch (error) {
      // Si la sesión no existe o hay error, retornar historial vacío
      if (error.status === 404) {
        return { session_id: sessionId, messages: [], context_length: 0 }
      }
      return { session_id: sessionId, messages: [], context_length: 0 }
    }
  },

  /**
   * Limpia el historial de mensajes de una sesión
   * @param {string} sessionId - ID de sesión
   * @returns {Promise} - Respuesta de limpieza
   */
  async clearSession(sessionId) {
    try {
      const response = await apiClient.delete(`${API_ENDPOINTS.AGENT_SESSION}/${sessionId}`)
      return response.data
    } catch (error) {
      throw error
    }
  },

  /**
   * Envía una consulta al agente
   * @param {Object} queryData - Datos de la consulta
   * @param {string} queryData.session_id - ID de sesión
   * @param {string} queryData.user_id - ID de usuario (opcional)
   * @param {Array} queryData.messages - Array de mensajes
   * @returns {Promise} - Respuesta del agente
   */
  async sendQuery({ session_id, user_id = null, messages }) {
    const response = await apiClient.post(API_ENDPOINTS.AGENT_QUERY, {
      session_id,
      user_id,
      messages: messages.map((msg) => ({
        role: msg.role,
        content: msg.content,
      })),
    })
    return response.data
  },

  /**
   * Envía una consulta al agente con streaming de respuesta
   * @param {Object} queryData - Datos de la consulta
   * @param {string} queryData.session_id - ID de sesión
   * @param {string} queryData.user_id - ID de usuario (opcional)
   * @param {Array} queryData.messages - Array de mensajes
   * @param {Function} onToken - Callback para cada token recibido
   * @param {Function} onComplete - Callback cuando se completa la respuesta
   * @param {Function} onError - Callback para errores
   * @returns {Function} - Función para cancelar el streaming
   */
  sendQueryStream({ session_id, user_id = null, messages }, onToken, onComplete, onError) {
    const controller = new AbortController()
    
    // Usar fetch con streaming en lugar de EventSource para poder enviar POST
    fetch(`${API_URL}${API_ENDPOINTS.AGENT_QUERY}/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        session_id,
        user_id,
        messages: messages.map((msg) => ({
          role: msg.role,
          content: msg.content,
        })),
      }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let finalResponse = null

        while (true) {
          const { done, value } = await reader.read()
          
          if (done) {
            break
          }

          // Decodificar el chunk
          buffer += decoder.decode(value, { stream: true })
          
          // Procesar líneas completas
          const lines = buffer.split('\n')
          buffer = lines.pop() || '' // Guardar la última línea incompleta

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                
                if (data.type === 'token') {
                  // Enviar token al callback
                  onToken(data.data.content)
                } else if (data.type === 'final_response') {
                  // Guardar respuesta final
                  finalResponse = data.data
                } else if (data.type === 'error') {
                  // Error del servidor
                  onError(new Error(data.data.message || 'Error desconocido'))
                  return
                } else if (data.type === 'done') {
                  // Streaming completado
                  if (finalResponse) {
                    onComplete(finalResponse)
                  } else {
                    onError(new Error('No se recibió respuesta final'))
                  }
                  return
                }
              } catch (e) {
              }
            }
          }
        }
      })
      .catch((error) => {
        if (error.name === 'AbortError') {
        } else {
          onError(error)
        }
      })

    // Retornar función para cancelar
    return () => controller.abort()
  },
}

/**
 * Servicio para gestionar archivos
 */
export const filesService = {
  /**
   * Sube un archivo al servidor
   * @param {File} file - Archivo a subir
   * @returns {Promise} - Respuesta con información del archivo
   */
  async uploadFile(file) {
    const formData = new FormData()
    formData.append('file', file)

    // Crear un cliente temporal sin el header Content-Type para que axios lo configure automáticamente
    const uploadClient = axios.create({
      baseURL: API_URL,
      timeout: 60000, // 60 segundos para archivos grandes
    })

    const response = await uploadClient.post(API_ENDPOINTS.FILES_UPLOAD, formData, {
      headers: {
        // No establecer Content-Type, axios lo hará automáticamente con el boundary correcto
      },
    })
    return response.data
  },

  /**
   * Obtiene la lista de archivos subidos
   * @returns {Promise} - Lista de archivos
   */
  async getFiles() {
    try {
      const response = await apiClient.get(API_ENDPOINTS.FILES_LIST)
      return response.data || []
    } catch (error) {
      // Si es un error 404 o la lista está vacía, retornar array vacío
      if (error.status === 404) {
        return []
      }
      throw error
    }
  },

  /**
   * Elimina un archivo
   * @param {string} documentId - ID del documento
   * @returns {Promise} - Respuesta de eliminación
   */
  async deleteFile(documentId) {
    const response = await apiClient.delete(
      `${API_ENDPOINTS.FILES_DELETE}/${documentId}`
    )
    return response.data
  },
}

/**
 * Servicio para análisis de capturas de red (Wireshark / PCAP)
 */
export const networkAnalysisService = {
  /**
   * Guarda el PDF del reporte de un análisis desde el HTML proporcionado
   * @param {string} analysisId - ID del análisis
   * @param {string} htmlContent - Contenido HTML del reporte
   * @returns {Promise} - Respuesta del servidor
   */
  async savePDF(analysisId, htmlContent) {
    const response = await apiClient.post(`/reports/${analysisId}/pdf`, htmlContent, {
      headers: {
        'Content-Type': 'text/plain',
      },
    })
    return response.data
  },

  /**
   * Descarga el PDF persistido del reporte de un análisis
   * @param {string} analysisId - ID del análisis
   * @returns {Promise} - Blob del archivo PDF
   */
  async downloadPDF(analysisId) {
    const response = await apiClient.get(`/reports/${analysisId}/pdf`, {
      responseType: 'blob',
    })
    return response.data
  },

  /**
   * Sube una captura de red (pcap/pcapng) y obtiene el análisis de la IA
   * @param {File} file - Archivo de captura
   * @returns {Promise} - Análisis y estadísticas básicas
   */
  async analyzeCapture(file, metadata = {}) {
    const formData = new FormData()
    formData.append('file', file)

    // Enviar metadata de usuario (SSID, MAC cliente) como JSON si existe
    try {
      const cleaned = {}
      if (metadata && typeof metadata === 'object') {
        if (metadata.ssid && metadata.ssid.trim()) cleaned.ssid = metadata.ssid.trim()
        if (metadata.client_mac && metadata.client_mac.trim()) cleaned.client_mac = metadata.client_mac.trim()
      }
      if (Object.keys(cleaned).length > 0) {
        formData.append('user_metadata', JSON.stringify(cleaned))
      }
    } catch (e) {
    }

    const uploadClient = axios.create({
      baseURL: API_URL,
      timeout: 120000,
    })

    const response = await uploadClient.post('/network-analysis/analyze', formData, {
      headers: {
        // Dejar que axios ponga el Content-Type con boundary
      },
    })

    return response.data
  },
}

/**
 * Servicio para navegar el historial de reportes AIDLC
 */
export const reportsService = {
  /**
   * Obtiene la lista de todos los reportes generados
   * @returns {Promise} - Lista de reportes resumidos
   */
  async getReports() {
    const response = await apiClient.get('/reports/')
    return response.data
  },

  /**
   * Obtiene el detalle de un reporte específico
   * @param {string} analysisId - ID del análisis
   * @returns {Promise} - Objeto BandSteeringAnalysis completo
   */
  async getReportDetail(analysisId) {
    const response = await apiClient.get(`/reports/${analysisId}`)
    return response.data
  },

  /**
   * Elimina un reporte del historial
   * @param {string} analysisId - ID del análisis
   * @returns {Promise} - Respuesta de éxito
   */
  async deleteReport(analysisId) {
    const response = await apiClient.delete(`/reports/${analysisId}`)
    return response.data
  },

  /**
   * Descarga el archivo pcap original de un análisis
   * @param {string} analysisId - ID del análisis
   * @returns {Promise} - Blob del archivo
   */
  async downloadCapture(analysisId) {
    const response = await apiClient.get(`/reports/${analysisId}/download`, {
      responseType: 'blob',
    })
    return response.data
  },

  /**
   * Guarda el PDF del reporte de un análisis desde el HTML proporcionado
   * @param {string} analysisId - ID del análisis
   * @param {string} htmlContent - Contenido HTML del reporte
   * @returns {Promise} - Respuesta del servidor
   */
  async savePDF(analysisId, htmlContent) {
    const response = await apiClient.post(`/reports/${analysisId}/pdf`, htmlContent, {
      headers: {
        'Content-Type': 'text/plain',
      },
    })
    return response.data
  },

  /**
   * Descarga el PDF persistido del reporte de un análisis
   * @param {string} analysisId - ID del análisis
   * @returns {Promise} - Blob del archivo PDF
   */
  async downloadPDF(analysisId) {
    const response = await apiClient.get(`/reports/${analysisId}/pdf`, {
      responseType: 'blob',
    })
    return response.data
  },

  /**
   * Elimina todos los reportes del sistema
   * @returns {Promise} - Respuesta con cantidad de reportes eliminados
   */
  async deleteAllReports() {
    const response = await apiClient.delete('/reports/all')
    return response.data
  },

  /**
   * Elimina todos los reportes de una marca específica
   * @param {string} vendor - Nombre de la marca
   * @returns {Promise} - Respuesta con cantidad de reportes eliminados
   */
  async deleteReportsByVendor(vendor) {
    const response = await apiClient.delete(`/reports/vendor/${encodeURIComponent(vendor)}`)
    return response.data
  },

  /**
   * Elimina múltiples reportes por sus IDs
   * @param {string[]} ids - Array de IDs de reportes a eliminar
   * @returns {Promise} - Respuesta con cantidad de reportes eliminados
   */
  async deleteMultipleReports(ids) {
    // axios.delete no acepta body directamente, usar request con method DELETE
    const response = await apiClient.request({
      method: 'DELETE',
      url: '/reports/batch',
      data: { ids },
    })
    return response.data
  },

  /**
   * Obtiene estadísticas agregadas de los reportes
   * @returns {Promise} - Estadísticas de los reportes
   */
  async getReportsStats() {
    const response = await apiClient.get('/reports/stats')
    return response.data
  },

  /**
   * Exporta reportes en formato JSON o CSV
   * @param {string[]} ids - Array de IDs de reportes a exportar (opcional, si no se proporciona exporta todos)
   * @param {string} format - Formato de exportación: 'json' o 'csv'
   * @returns {Promise} - Blob del archivo exportado
   */
      async exportReports(ids = null, format = 'html') {
    const params = new URLSearchParams()
    // Solo agregar IDs si hay elementos válidos
    if (ids && Array.isArray(ids) && ids.length > 0) {
      // Filtrar IDs válidos (no null, undefined, o vacíos)
      const validIds = ids.filter(id => id != null && id !== '')
      if (validIds.length > 0) {
        params.append('ids', validIds.join(','))
      }
    }
    params.append('format', format)
    
    const url = `/reports/export?${params.toString()}`
    console.log('🌐 [API] Llamando a exportReports:', { url, ids, format })
    
    try {
      const response = await apiClient.get(url, {
        responseType: 'blob',
        validateStatus: (status) => status < 500, // Permitir 4xx para manejar errores manualmente
      })
      
      console.log('✅ [API] Respuesta recibida:', { 
        status: response.status, 
        blobSize: response.data?.size,
        blobType: response.data?.type 
      })
      
      // Si la respuesta es un error (status >= 400), el blob contiene el mensaje de error
      if (response.status >= 400) {
        try {
          const text = await response.data.text()
          const errorData = JSON.parse(text)
          throw new Error(errorData.detail || errorData.message || `Error ${response.status}`)
        } catch (parseError) {
          // Si no es JSON válido, lanzar error genérico
          throw new Error(`Error ${response.status}: No se pudo exportar los reportes`)
        }
      }
      
      // Verificar que el blob tenga contenido
      if (!response.data || response.data.size === 0) {
        throw new Error('El archivo exportado está vacío')
      }
      
      // Obtener el tipo MIME desde los headers de la respuesta
      const contentType = response.headers['content-type'] || 
                          response.headers['Content-Type'] || 
                          'application/octet-stream'
      
      console.log('📋 [API] Content-Type desde headers:', contentType)
      
      // Asegurar que sea un Blob válido con el tipo MIME correcto
      let blob = response.data
      if (!(blob instanceof Blob)) {
        // Si no es un Blob, intentar crear uno
        blob = new Blob([response.data], { type: contentType })
      } else if (blob.type !== contentType && blob.type === 'application/octet-stream') {
        // Si el blob tiene el tipo incorrecto, crear uno nuevo con el tipo correcto
        const arrayBuffer = await blob.arrayBuffer()
        blob = new Blob([arrayBuffer], { type: contentType })
      }
      
      console.log('✅ [API] Blob final:', { 
        size: blob.size, 
        type: blob.type,
        isBlob: blob instanceof Blob,
        originalType: response.data?.type
      })
      
      return blob
    } catch (error) {
      console.error('❌ [API] Error en exportReports:', error)
      
      // Si el error tiene data que es un Blob, intentar leer el mensaje
      if (error.data instanceof Blob) {
        try {
          const text = await error.data.text()
          const errorData = JSON.parse(text)
          const errorMessage = errorData.detail || errorData.message || 'Error al exportar reportes'
          console.error('❌ [API] Mensaje de error del backend:', errorMessage)
          throw new Error(errorMessage)
        } catch (parseError) {
          console.error('❌ [API] Error al parsear blob de error:', parseError)
          // Si no se puede parsear, usar el mensaje del error original
        }
      }
      
      // Si el error tiene response.data que es un Blob
      if (error.response?.data instanceof Blob) {
        try {
          const text = await error.response.data.text()
          const errorData = JSON.parse(text)
          const errorMessage = errorData.detail || errorData.message || 'Error al exportar reportes'
          console.error('❌ [API] Mensaje de error del backend:', errorMessage)
          throw new Error(errorMessage)
        } catch (parseError) {
          console.error('❌ [API] Error al parsear blob de error:', parseError)
          // Si no se puede parsear, usar el mensaje del error original
        }
      }
      
      throw error
    }
  },
}

export default apiClient

