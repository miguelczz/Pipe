import { useState, useCallback, useRef, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
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
  const location = useLocation()
  const [sessionId] = useState(() => 
    getOrCreateSessionId(SESSION_CONFIG.STORAGE_KEY)
  )
  const abortControllerRef = useRef(null)
  const [isLoadingHistory, setIsLoadingHistory] = useState(true)
  const hasLoadedRef = useRef(false)

  // Guardar sessionId en localStorage cuando cambia
  useEffect(() => {
    setStorageItem(SESSION_CONFIG.STORAGE_KEY, sessionId)
  }, [sessionId])

  // Guardar mensajes en localStorage como respaldo
  useEffect(() => {
    if (messages.length > 0) {
      const messagesKey = `${SESSION_CONFIG.STORAGE_KEY}_messages`
      setStorageItem(messagesKey, messages)
    }
  }, [messages])

  // Guardar mensajes cuando se sale de la página de chat
  useEffect(() => {
    if (location.pathname !== '/' && messages.length > 0) {
      const messagesKey = `${SESSION_CONFIG.STORAGE_KEY}_messages`
      setStorageItem(messagesKey, messages)
      // Resetear el flag cuando salimos de la página
      hasLoadedRef.current = false
    }
  }, [location.pathname, messages])

  // Cargar historial de sesión al montar el componente o cuando se vuelve a la página de chat
  useEffect(() => {
    // Solo cargar si estamos en la página de chat
    if (location.pathname !== '/') {
      return
    }

    const loadSessionHistory = async () => {
      // Evitar cargar múltiples veces en la misma sesión de página
      if (hasLoadedRef.current) {
        return
      }

      try {
        setIsLoadingHistory(true)
        
        // Primero intentar cargar desde localStorage como respaldo rápido
        const messagesKey = `${SESSION_CONFIG.STORAGE_KEY}_messages`
        const cachedMessages = getStorageItem(messagesKey, [])
        if (cachedMessages.length > 0) {
          setMessages(cachedMessages)
        }
        
        // Luego cargar desde el backend (más actualizado)
        const history = await agentService.getSessionHistory(sessionId)
        
        if (history.messages && history.messages.length > 0) {
          // Convertir mensajes del backend al formato del frontend
          const formattedMessages = history.messages.map((msg, idx) => ({
            id: `msg-${sessionId}-${idx}-${msg.role}`,
            role: msg.role === 'assistant' ? 'assistant' : 'user',
            content: msg.content,
            timestamp: new Date().toISOString(),
          }))
          // Actualizar con los mensajes del backend (más actualizados)
          setMessages(formattedMessages)
        } else if (cachedMessages.length === 0) {
          // Si no hay mensajes en backend ni en cache, limpiar
          setMessages([])
        }
      } catch (err) {
        // Si falla el backend, usar cache de localStorage si existe
        const messagesKey = `${SESSION_CONFIG.STORAGE_KEY}_messages`
        const cachedMessages = getStorageItem(messagesKey, [])
        if (cachedMessages.length > 0) {
          setMessages(cachedMessages)
        }
      } finally {
        setIsLoadingHistory(false)
        hasLoadedRef.current = true
      }
    }

    // Recargar cada vez que se monta el componente o se vuelve a la página
    loadSessionHistory()
  }, [sessionId, location.pathname])

  /**
   * Envía un mensaje al agente con streaming
   * @param {string} content - Contenido del mensaje
   */
  const sendMessage = useCallback(async (content) => {
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
      isStreaming: true, // Indicador de que está en streaming
    }

    // Agregar burbuja vacía del asistente
    setMessages((prev) => [...prev, assistantMessage])

    try {
      // Enviar TODOS los mensajes de la conversación (incluyendo el nuevo) para garantizar 
      // que el backend tenga acceso completo al contexto
      const allMessages = [...messages, userMessage]
      const messagesForAPI = allMessages.map((msg) => ({
        role: msg.role,
        content: msg.content,
      }))

      // Variable para acumular el contenido
      let accumulatedContent = ''

      // Función para cancelar el streaming
      const cancelStream = agentService.sendQueryStream(
        {
          session_id: sessionId,
          messages: messagesForAPI,
        },
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
   * Limpia la conversación actual
   */
  const clearMessages = useCallback(async () => {
    try {
      // Limpiar sesión en el backend
      await agentService.clearSession(sessionId)
    } catch (error) {
      // Continuar limpiando el frontend aunque falle el backend
    }
    
    // Limpiar mensajes del frontend
    setMessages([])
    setError(null)
    
    // Limpiar cache de localStorage
    const messagesKey = `${SESSION_CONFIG.STORAGE_KEY}_messages`
    try {
      localStorage.removeItem(messagesKey)
    } catch (err) {
    }
    
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
    isLoading,
    error,
    clearMessages,
    cancelRequest,
    sessionId,
  }
}

