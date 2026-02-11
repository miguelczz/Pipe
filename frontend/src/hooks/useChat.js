import { useState, useCallback, useRef, useEffect } from 'react'
import { agentService } from '../services/api'
import { getOrCreateSessionId, setStorageItem, getStorageItem } from '../utils/storage'
import { SESSION_CONFIG } from '../config/constants'

/**
 * Hook personalizado para manejar conversaciones con el agente
 * Gestiona mensajes, sesiones, estados de carga y errores
 */
export function useChat() {
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [sessionId] = useState(() => 
    getOrCreateSessionId(SESSION_CONFIG.STORAGE_KEY)
  )
  const abortControllerRef = useRef(null)
  const [, setIsLoadingHistory] = useState(true)
  const hasLoadedRef = useRef(false)

  // Guardar sessionId en localStorage cuando cambia
  useEffect(() => {
    setStorageItem(SESSION_CONFIG.STORAGE_KEY, sessionId)
  }, [sessionId])

  // Guardar mensajes en localStorage cada vez que cambian
  useEffect(() => {
    const messagesKey = `${SESSION_CONFIG.STORAGE_KEY}_messages`
    if (messages.length > 0) {
      setStorageItem(messagesKey, messages)
    }
  }, [messages])

  // Cargar historial al montar el componente (una sola vez)
  useEffect(() => {
    if (hasLoadedRef.current) return

    const loadSessionHistory = async () => {
      try {
        setIsLoadingHistory(true)
        
        // Primero cargar desde localStorage (instantáneo)
        const messagesKey = `${SESSION_CONFIG.STORAGE_KEY}_messages`
        const cachedMessages = getStorageItem(messagesKey, [])
        if (cachedMessages.length > 0) {
          setMessages(cachedMessages)
        }
        
        // Luego intentar sincronizar con el backend
        const history = await agentService.getSessionHistory(sessionId)
        
        if (history.messages && history.messages.length > 0) {
          const formattedMessages = history.messages.map((msg, idx) => ({
            id: `msg-${sessionId}-${idx}-${msg.role}`,
            role: msg.role === 'assistant' ? 'assistant' : 'user',
            content: msg.content,
            timestamp: new Date().toISOString(),
          }))
          setMessages(formattedMessages)
        }
      } catch (err) {
        // Si falla el backend, los mensajes de localStorage ya están cargados
      } finally {
        setIsLoadingHistory(false)
        hasLoadedRef.current = true
      }
    }

    loadSessionHistory()
  }, [sessionId])

  /**
   * Envía un mensaje al agente con streaming
   * @param {string} content - Contenido del mensaje
   * @param {string} [contextText] - Texto de contexto seleccionado (opcional)
   * @param {Object} [extra] - Campos extra para el payload (report_id, selected_text, etc.)
   */
  const sendMessage = useCallback(async (content, contextText = null, extra = {}) => {
    if (!content.trim() || isLoading) return

    // Cancelar petición anterior si existe
    if (abortControllerRef.current) {
      abortControllerRef.current()
    }

    const userMessage = {
      id: `msg-${Date.now()}-user`,
      role: 'user',
      content: content.trim(),
      timestamp: new Date().toISOString(),
    }

    // Agregar mensaje del usuario inmediatamente
    setMessages((prev) => [...prev, userMessage])
    setIsLoading(true)
    setError(null)

    // Crear mensaje del asistente vacío que se irá llenando
    const assistantMessageId = `msg-${Date.now()}-assistant`
    const assistantMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      isStreaming: true,
    }

    // Agregar burbuja vacía del asistente
    setMessages((prev) => [...prev, assistantMessage])

    try {
      const allMessages = [...messages, userMessage]
      const messagesForAPI = allMessages.map((msg) => ({
        role: msg.role,
        content: msg.content,
      }))

      // Variable para acumular el contenido
      let accumulatedContent = ''

      // Construir payload con campos extra opcionales (report_id, selected_text)
      const payload = {
        session_id: sessionId,
        messages: messagesForAPI,
        ...extra,
      }
      if (contextText?.trim()) {
        payload.selected_text = contextText.trim()
      }

      // Función para cancelar el streaming
      const cancelStream = agentService.sendQueryStream(
        payload,
        // onToken: se llama por cada token recibido
        (token) => {
          accumulatedContent += token
          // Actualizar el mensaje del asistente con el contenido acumulado
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? { ...msg, content: accumulatedContent }
                : msg
            )
          )
        },
        // onComplete: se llama cuando termina el streaming
        (finalData) => {
          // Actualizar con la respuesta final completa y marcar como completado
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? {
                    ...msg,
                    content: finalData.content,
                    isStreaming: false,
                    executed_tools: finalData.executed_tools,
                    executed_steps: finalData.executed_steps,
                  }
                : msg
            )
          )
          setIsLoading(false)
          abortControllerRef.current = null
        },
        // onError: se llama si hay un error
        (err) => {
          // No mostrar error si fue cancelado
          if (err.name === 'AbortError' || err.message?.includes('canceled')) {
            return
          }

          // Mensaje de error más descriptivo
          let errorMessage = 'No se pudo procesar la solicitud'
          if (err.message) {
            errorMessage = err.message
          }

          // Actualizar el mensaje del asistente con el error
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? {
                    ...msg,
                    content: errorMessage,
                    isStreaming: false,
                    isError: true,
                  }
                : msg
            )
          )
          setError(errorMessage)
          setIsLoading(false)
          abortControllerRef.current = null
        }
      )

      // Guardar la función de cancelación
      abortControllerRef.current = cancelStream
    } catch (err) {
        // Manejo de errores síncronos (no debería ocurrir con el nuevo enfoque)
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMessageId
            ? {
                ...msg,
                content: 'Error inesperado al procesar la solicitud',
                isStreaming: false,
                isError: true,
              }
            : msg
        )
      )
      setError('Error inesperado')
      setIsLoading(false)
      abortControllerRef.current = null
    }
  }, [messages, isLoading, sessionId])

  /**
   * Edita un mensaje de usuario y genera una nueva respuesta del asistente (paginado).
   * Mantiene las respuestas anteriores para permitir navegar entre ellas.
   * @param {Object} message - Mensaje original a editar (necesita message.id)
   * @param {string} newContent - Nuevo contenido del mensaje
   * @param {string} [contextText] - Texto de contexto seleccionado (opcional)
   * @param {Object} [extra] - Campos extra para el payload (report_id, selected_text, etc.)
   */
  const sendMessageAfterEdit = useCallback(async (message, newContent, contextText = null, extra = {}) => {
    const trimmed = newContent?.trim()
    if (!trimmed || isLoading) return

    if (abortControllerRef.current) {
      abortControllerRef.current()
    }

    const assistantMessageId = `msg-${Date.now()}-assistant`

    // Actualizar el mensaje editado y agregar nueva respuesta vacía al grupo
    setMessages((prev) => {
      const index = prev.findIndex((m) => m.id === message.id)
      if (index === -1) return prev

      // Actualizar contenido del mensaje de usuario
      const upToEdited = prev.slice(0, index + 1).map((m) =>
        m.id === message.id ? { ...m, content: trimmed } : m
      )

      // Mantener las respuestas del asistente que siguen (para el paginado)
      let j = index + 1
      while (j < prev.length && prev[j].role === 'assistant') j++
      const existingReplies = prev.slice(index + 1, j)

      // Nueva respuesta vacía que se irá llenando con streaming
      const assistantMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        isStreaming: true,
      }

      // Resto de mensajes después del grupo actual
      const rest = prev.slice(j)

      return [...upToEdited, ...existingReplies, assistantMessage, ...rest]
    })

    setIsLoading(true)
    setError(null)

    // Construir mensajes para la API (solo hasta el mensaje editado, con el nuevo contenido)
    const currentMessages = messages
    const index = currentMessages.findIndex((m) => m.id === message.id)
    const messagesUpToEdited = index >= 0
      ? currentMessages.slice(0, index).concat({ ...currentMessages[index], content: trimmed })
      : currentMessages
    const messagesForAPI = messagesUpToEdited.map((msg) => ({
      role: msg.role,
      content: msg.content,
    }))

    const payload = {
      session_id: sessionId,
      messages: messagesForAPI,
      ...extra,
    }
    if (contextText?.trim()) {
      payload.selected_text = contextText.trim()
    }

    let accumulatedContent = ''

    try {
      const cancelStream = agentService.sendQueryStream(
        payload,
        (token) => {
          accumulatedContent += token
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId ? { ...msg, content: accumulatedContent } : msg
            )
          )
        },
        (finalData) => {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? {
                    ...msg,
                    content: finalData?.content ?? accumulatedContent,
                    isStreaming: false,
                    executed_tools: finalData?.executed_tools,
                    executed_steps: finalData?.executed_steps,
                  }
                : msg
            )
          )
          setIsLoading(false)
          abortControllerRef.current = null
        },
        (err) => {
          if (err?.name === 'AbortError' || err?.message?.includes('canceled')) return
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? { ...msg, content: err?.message || 'Error', isStreaming: false, isError: true }
                : msg
            )
          )
          setError(err?.message || 'Error')
          setIsLoading(false)
          abortControllerRef.current = null
        }
      )
      abortControllerRef.current = cancelStream
    } catch (err) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMessageId
            ? { ...msg, content: 'Error inesperado', isStreaming: false, isError: true }
            : msg
        )
      )
      setError('Error inesperado')
      setIsLoading(false)
      abortControllerRef.current = null
    }
  }, [messages, isLoading, sessionId])

  /**
   * Limpia la conversación actual
   */
  const clearMessages = useCallback(async () => {
    try {
      // Limpiar sesión en el backend
      await agentService.clearSession(sessionId)
    } catch (error) {
      // Continuar limpiando el frontend aunque falle el backend
    }
    
    // Limpiar mensajes del frontend y del localStorage
    setMessages([])
    setError(null)
    const messagesKey = `${SESSION_CONFIG.STORAGE_KEY}_messages`
    try { localStorage.removeItem(messagesKey) } catch (e) { /* ignore */ }
    
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
  }, [sessionId])

  /**
   * Cancela la petición en curso
   */
  const cancelRequest = useCallback(() => {
    if (abortControllerRef.current) {
      // Llamar a la función de cancelación (es una función, no un AbortController)
      if (typeof abortControllerRef.current === 'function') {
        abortControllerRef.current()
      }
      setIsLoading(false)
    }
  }, [])

  return {
    messages,
    sendMessage,
    sendMessageAfterEdit,
    isLoading,
    error,
    clearMessages,
    cancelRequest,
    sessionId,
  }
}

