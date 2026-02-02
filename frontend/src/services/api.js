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
   * Descarga el PDF del reporte de un análisis
   * @param {string} analysisId - ID del análisis
   * @returns {Promise} - Blob del archivo HTML (que se puede convertir a PDF)
   */
  async downloadPDF(analysisId) {
    const response = await apiClient.get(`/reports/${analysisId}/pdf`, {
      responseType: 'blob',
    })
    return response.data
  },
}

export default apiClient

