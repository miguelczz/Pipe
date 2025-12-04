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
        console.error('Error al cargar historial de sesión:', err)
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
   * Envía un mensaje al agente
   * @param {string} content - Contenido del mensaje
   */
  const sendMessage = useCallback(async (content) => {
    if (!content.trim() || isLoading) return

    // Cancelar petición anterior si existe
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
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

    // Crear nuevo AbortController para esta petición
    abortControllerRef.current = new AbortController()

    try {
      // Enviar TODOS los mensajes de la conversación (incluyendo el nuevo) para garantizar 
      // que el backend tenga acceso completo al contexto, similar a cómo funciona LangGraph Dev.
      // El backend validará y evitará duplicados (líneas 93-102 de agent.py)
      // Nota: messages es el estado antes de agregar userMessage, así que incluimos ambos
      const allMessages = [...messages, userMessage]
      const messagesForAPI = allMessages.map((msg) => ({
        role: msg.role,
        content: msg.content,
      }))

      const response = await agentService.sendQuery({
        session_id: sessionId,
        messages: messagesForAPI,
      })

      // Crear mensaje del asistente
      const assistantMessage = {
        id: `msg-${Date.now()}-assistant`,
        role: 'assistant',
        content: response.new_messages[0]?.content || 'Sin respuesta disponible',
        timestamp: new Date().toISOString(),
        decision: response.decision,
        tool: response.decision?.tool || 'none',
      }

      setMessages((prev) => [...prev, assistantMessage])
    } catch (err) {
      // No mostrar error si fue cancelado
      if (err.name === 'AbortError' || err.message?.includes('canceled')) {
        return
      }

      // Mensaje de error más descriptivo
      let errorMessage = 'No se pudo procesar la solicitud'
      if (err.message) {
        errorMessage = err.message
      } else if (err.status === 0) {
        errorMessage = 'No se pudo conectar con el servidor. Verifica que el backend esté corriendo en http://localhost:8000'
      }

      const errorMsg = {
        id: `msg-${Date.now()}-error`,
        role: 'assistant',
        content: errorMessage,
        timestamp: new Date().toISOString(),
        isError: true,
      }

      setMessages((prev) => [...prev, errorMsg])
      setError(errorMessage)
    } finally {
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
      console.error('Error al limpiar sesión en el backend:', error)
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
      console.error('Error al limpiar cache de mensajes:', err)
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
      abortControllerRef.current.abort()
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

