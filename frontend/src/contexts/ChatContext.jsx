import { createContext, useContext, useState } from 'react'

const ChatContext = createContext(null)

/* eslint-disable react-refresh/only-export-components -- Contexto exporta Provider y hook por diseño */
export function ChatProvider({ children }) {
  const [clearChatAction, setClearChatAction] = useState(null)
  const [hasMessages, setHasMessages] = useState(false)

  return (
    <ChatContext.Provider value={{ clearChatAction, setClearChatAction, hasMessages, setHasMessages }}>
      {children}
    </ChatContext.Provider>
  )
}

export function useChatContext() {
  const context = useContext(ChatContext)
  if (!context) {
    throw new Error('useChatContext must be used within ChatProvider')
  }
  return context
}

