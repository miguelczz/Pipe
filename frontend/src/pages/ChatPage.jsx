import { useChat } from '../hooks/useChat'
import { ChatContainer } from '../components/chat/ChatContainer'
import { ChatInput } from '../components/chat/ChatInput'
import { ConnectionStatus } from '../components/common/ConnectionStatus'
import { useChatContext } from '../contexts/ChatContext'
import { useState, useEffect } from 'react'
import { API_URL } from '../config/constants'

/**
 * Página principal del chat
 */
export function ChatPage() {
  const { messages, sendMessage, isLoading, clearMessages, error } = useChat()
  const { setClearChatAction, setHasMessages } = useChatContext()
  const [isConnected, setIsConnected] = useState(true)

  // Conectar el botón de limpiar con el contexto
  useEffect(() => {
    setClearChatAction(() => clearMessages)
    setHasMessages(messages.length > 0)
  }, [clearMessages, messages.length, setClearChatAction, setHasMessages])

  // Verificar conexión con el servidor
  useEffect(() => {
    const checkConnection = async () => {
      try {
        const controller = new AbortController()
        const timeoutId = setTimeout(() => controller.abort(), 30000) // 30 segundos timeout (más tiempo para respuestas lentas)
        
        const response = await fetch(`${API_URL}/`, {
          signal: controller.signal,
          method: 'GET',
        })
        clearTimeout(timeoutId)
        setIsConnected(response.ok)
      } catch (err) {
        if (err.name === 'AbortError') {
          // No marcar como desconectado si es timeout, puede ser normal
          return
        }
        setIsConnected(false)
      }
    }

    checkConnection()
    const interval = setInterval(checkConnection, 60000) // Verificar cada 60 segundos

    return () => clearInterval(interval)
  }, [])

  return (
    <>
      <div className="flex flex-col h-full max-w-4xl mx-auto w-full relative overflow-x-hidden min-w-0">
        {/* Notificación de error de conexión debajo del header */}
        <div className="px-3 sm:px-4 pt-2 sm:pt-3 pb-2 sm:pb-3 w-full max-w-full min-w-0 overflow-hidden">
          <ConnectionStatus 
            isConnected={isConnected && !error} 
            message={error || 'No se pudo conectar con el servidor'}
          />
        </div>

        {/* Chat Container con padding bottom para el input fijo */}
        <div className="flex-1 overflow-hidden min-h-0 overflow-x-hidden w-full max-w-full" style={{ paddingBottom: '80px' }}>
          <ChatContainer messages={messages} isLoading={isLoading} />
        </div>
      </div>

      {/* Chat Input fijo en la parte inferior de la ventana */}
      <div className="fixed bottom-0 left-0 right-0 bg-dark-bg-primary/95 backdrop-blur-sm pt-3 sm:pt-4 pb-3 sm:pb-4 z-50 shadow-gemini-lg overflow-x-hidden w-full min-w-0">
        <div className="max-w-4xl mx-auto px-3 sm:px-4 w-full min-w-0">
          <ChatInput
            onSend={sendMessage}
            isLoading={isLoading}
            disabled={!isConnected}
          />
        </div>
      </div>
    </>
  )
}

export default ChatPage

