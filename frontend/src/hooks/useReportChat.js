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
 * Hook para el chat en contexto de un reporte (página de Análisis).
 * Usa una sesión por report_id y envía report_id y opcionalmente selected_text al backend.
 * Persiste la conversación en localStorage por report_id.
 * @param {string} reportId - analysis_id del reporte actual
 * @param {() => string} getSelectedText - función que devuelve el texto seleccionado al enviar (opcional)
 */
export function useReportChat(reportId, getSelectedText = null) {
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

  const sendMessage = useCallback(
    async (content) => {
      if (!content?.trim() || isLoading || !reportId || !sessionId) return

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

      const selectedText = typeof getSelectedText === 'function' ? getSelectedText() : null
      const trimmedSelected = selectedText?.trim() || null

      try {
        const allMessages = [...messages, userMessage]
        const messagesForAPI = allMessages.map((msg) => ({
          role: msg.role,
          content: msg.content,
        }))

        let accumulatedContent = ''

        const cancelStream = agentService.sendQueryStream(
          {
            session_id: sessionId,
            messages: messagesForAPI,
            report_id: reportId,
            selected_text: trimmedSelected,
          },
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
      }
    },
    [messages, isLoading, reportId, sessionId, getSelectedText]
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
    isLoading,
    error,
    clearMessages,
    sessionId,
  }
}
