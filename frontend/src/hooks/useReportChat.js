import { useState, useCallback, useRef, useEffect } from 'react'
import { agentService } from '../services/api'

const REPORT_CHAT_SESSION_PREFIX = 'report_chat_'
const REPORT_CHAT_STORAGE_PREFIX = 'pipe_report_chat_messages_'
const MAX_PERSISTED_MESSAGES = 100

function getStorageKey(reportId) {
  return reportId ? `${REPORT_CHAT_STORAGE_PREFIX}${reportId}` : null
}

function loadPersistedMessages(reportId) {
  const key = getStorageKey(reportId)
  if (!key) return []
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.slice(-MAX_PERSISTED_MESSAGES) : []
  } catch {
    return []
  }
}

function savePersistedMessages(reportId, messages) {
  const key = getStorageKey(reportId)
  if (!key || !Array.isArray(messages) || messages.length === 0) return
  try {
    const toSave = messages.slice(-MAX_PERSISTED_MESSAGES)
    localStorage.setItem(key, JSON.stringify(toSave))
  } catch {
    // quota o no soportado
  }
}

/**
 * Hook para el chat unificado en contexto de un reporte (página de Análisis).
 * Usa una sesión por report_id y permite operar en:
 *   - modo "report": preguntas sobre ESTE análisis (incluye report_id y selected_text).
 *   - modo "docs": preguntas de documentación general (sin report_id, pero puede usar selected_text como contexto).
 * Persiste la conversación en localStorage por report_id.
 *
 * @param {string} reportId - analysis_id del reporte actual
 */
export function useReportChat(reportId) {
  const [messages, setMessages] = useState(() => loadPersistedMessages(reportId))
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const abortControllerRef = useRef(null)

  const sessionId = reportId ? `${REPORT_CHAT_SESSION_PREFIX}${reportId}` : null

  // Cargar mensajes persistidos al cambiar de reporte
  useEffect(() => {
    setMessages(loadPersistedMessages(reportId))
  }, [reportId])

  const lastPersistRef = useRef(0)
  const PERSIST_THROTTLE_MS = 2000

  // Persistir mensajes: al terminar de cargar siempre; durante streaming como máximo cada 2s
  useEffect(() => {
    if (!reportId || messages.length === 0) return
    const now = Date.now()
    const shouldSave = !isLoading || now - lastPersistRef.current >= PERSIST_THROTTLE_MS
    if (shouldSave) {
      lastPersistRef.current = now
      savePersistedMessages(reportId, messages)
    }
  }, [reportId, messages, isLoading])

  const runStream = useCallback(
    (messagesForAPI, assistantMessageId, payloadExtra = {}) => {
      let accumulatedContent = ''
      const payload = {
        session_id: sessionId,
        messages: messagesForAPI,
        ...payloadExtra,
      }
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
          if (err?.name === 'AbortError' || err?.message?.includes('cancel')) return
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? { ...msg, content: err?.message || 'Error', isStreaming: false, isError: true }
                : msg
            )
          )
          setError(err?.message || null)
          setIsLoading(false)
          abortControllerRef.current = null
        }
      )
      return cancelStream
    },
    [sessionId]
  )

  const sendMessage = useCallback(
    async (content, contextText = null, mode = 'report') => {
      if (!content?.trim() || isLoading || !sessionId) return

      if (abortControllerRef.current) {
        abortControllerRef.current()
      }

      const userMessage = {
        id: `msg-${Date.now()}-user`,
        role: 'user',
        content: content.trim(),
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, userMessage])
      setIsLoading(true)
      setError(null)

      const assistantMessageId = `msg-${Date.now()}-assistant`
      const assistantMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        isStreaming: true,
      }
      setMessages((prev) => [...prev, assistantMessage])

      const trimmedSelected = contextText?.trim() || null
      const messagesForAPI = [...messages, userMessage].map((msg) => ({
        role: msg.role,
        content: msg.content,
      }))
      const payloadExtra = {}
      if (mode === 'report' && reportId) {
        payloadExtra.report_id = reportId
        if (trimmedSelected) payloadExtra.selected_text = trimmedSelected
      } else if (trimmedSelected) {
        payloadExtra.selected_text = trimmedSelected
      }

      try {
        abortControllerRef.current = runStream(messagesForAPI, assistantMessageId, payloadExtra)
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
      }
    },
    [messages, isLoading, reportId, sessionId, runStream]
  )

  /** Edita el contenido de un mensaje de usuario, mantiene las respuestas ya existentes y añade una nueva (paginado). */
  const sendMessageAfterEdit = useCallback(
    async (messageId, newContent, contextText = null, mode = 'report') => {
      const trimmed = newContent?.trim()
      if (!trimmed || isLoading || !sessionId) return
      if (abortControllerRef.current) abortControllerRef.current()

      setMessages((prev) => {
        const index = prev.findIndex((m) => m.id === messageId)
        if (index === -1) return prev
        // Actualizar contenido del mensaje de usuario
        const upToEdited = prev.slice(0, index + 1).map((m) =>
          m.id === messageId ? { ...m, content: trimmed } : m
        )
        // Mantener las respuestas del agente que ya seguían a este mensaje (para el paginado)
        let j = index + 1
        while (j < prev.length && prev[j].role === 'assistant') j++
        const existingReplies = prev.slice(index + 1, j)
        const assistantMessageId = `msg-${Date.now()}-assistant`
        const assistantMessage = {
          id: assistantMessageId,
          role: 'assistant',
          content: '',
          timestamp: new Date().toISOString(),
          isStreaming: true,
        }
        const next = [...upToEdited, ...existingReplies, assistantMessage]
        setIsLoading(true)
        setError(null)
        const messagesForAPI = upToEdited.map((m) => ({ role: m.role, content: m.content }))
        const trimmedSelected = contextText?.trim() || null
        const payloadExtra = {}
        if (mode === 'report' && reportId) {
          payloadExtra.report_id = reportId
          if (trimmedSelected) payloadExtra.selected_text = trimmedSelected
        } else if (trimmedSelected) {
          payloadExtra.selected_text = trimmedSelected
        }
        setTimeout(() => {
          try {
            abortControllerRef.current = runStream(
              messagesForAPI,
              assistantMessageId,
              payloadExtra
            )
          } catch (err) {
            setMessages((p) =>
              p.map((msg) =>
                msg.id === assistantMessageId
                  ? { ...msg, content: 'Error inesperado', isStreaming: false, isError: true }
                  : msg
              )
            )
            setError('Error inesperado')
            setIsLoading(false)
          }
        }, 0)
        return next
      })
    },
    [isLoading, reportId, sessionId, runStream]
  )

  const clearMessages = useCallback(async () => {
    if (sessionId) {
      try {
        await agentService.clearSession(sessionId)
      } catch {
        // ignore
      }
    }
    const key = getStorageKey(reportId)
    if (key) {
      try {
        localStorage.removeItem(key)
      } catch {
        // ignore
      }
    }
    setMessages([])
    setError(null)
    if (abortControllerRef.current) {
      if (typeof abortControllerRef.current === 'function') abortControllerRef.current()
    }
  }, [sessionId, reportId])

  return {
    messages,
    sendMessage,
    sendMessageAfterEdit,
    isLoading,
    error,
    clearMessages,
    sessionId,
  }
}
