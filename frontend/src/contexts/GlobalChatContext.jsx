import React, { createContext, useContext, useState } from 'react'

const GlobalChatContext = createContext({
    messages: [],
    isLoading: false,
    disabled: false,
    chatMode: 'docs',
    highlightedContext: null,
    selectionLockActive: false,
    
    setMessages: () => {},
    setIsLoading: () => {},
    setDisabled: () => {},
    setChatMode: () => {},
    setHighlightedContext: () => {},
    setSelectionLockActive: () => {},
    
    onSend: null,
    onClearMessages: null,
    onSaveEditedMessage: null,
    
    // Referencia directa al sendMessage del useChat global (para inyectar extras)
    sendMessageRef: { current: null },
    
    setCallbacks: () => {},
    clearCallbacks: () => {},
})

export function GlobalChatProvider({ children }) {
    const [messages, setMessages] = useState([])
    const [isLoading, setIsLoading] = useState(false)
    const [disabled, setDisabled] = useState(false)
    const [chatMode, setChatMode] = useState('docs')
    const [highlightedContext, setHighlightedContext] = useState(null)
    const [selectionLockActive, setSelectionLockActive] = useState(false)
    
    const [callbacks, setCallbacksState] = useState({
        onSend: null,
        onClearMessages: null,
        onSaveEditedMessage: null,
    })

    const setCallbacks = React.useCallback((newCallbacks) => {
        setCallbacksState(prev => ({ ...prev, ...newCallbacks }))
    }, [])

    const clearCallbacks = React.useCallback(() => {
        setCallbacksState({
            onSend: null,
            onClearMessages: null,
            onSaveEditedMessage: null,
        })
    }, [])

    // Ref al sendMessage del useChat global (el Layout lo configura)
    const sendMessageRef = React.useRef(null)

    const value = React.useMemo(
        () => ({
            messages,
            isLoading,
            disabled,
            chatMode,
            highlightedContext,
            selectionLockActive,
            
            setMessages,
            setIsLoading,
            setDisabled,
            setChatMode,
            setHighlightedContext,
            setSelectionLockActive,
            
            onSend: callbacks.onSend,
            onClearMessages: callbacks.onClearMessages,
            onSaveEditedMessage: callbacks.onSaveEditedMessage,
            
            sendMessageRef,
            
            setCallbacks,
            clearCallbacks,
        }),
        [
            messages, 
            isLoading, 
            disabled, 
            chatMode, 
            highlightedContext, 
            selectionLockActive, 
            callbacks.onSend,
            callbacks.onClearMessages,
            callbacks.onSaveEditedMessage
        ]
    )

    return (
        <GlobalChatContext.Provider value={value}>
            {children}
        </GlobalChatContext.Provider>
    )
}

export function useGlobalChat() {
    const context = useContext(GlobalChatContext)
    if (!context) {
        throw new Error('useGlobalChat must be used within GlobalChatProvider')
    }
    return context
}
