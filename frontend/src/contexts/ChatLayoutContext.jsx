import React from 'react'

const REPORT_CHAT_SIDE_KEY = 'pipe_report_chat_side'
const REPORT_CHAT_OPEN_KEY = 'pipe_report_chat_open'
const REPORT_CHAT_WIDTH_KEY = 'pipe_report_chat_width'
const CHAT_WIDTH_MIN = 280
const CHAT_WIDTH_MAX = 720
const CHAT_WIDTH_DEFAULT = 380

/**
 * Contexto para manejar el estado del chat lateral del reporte
 * Permite que el Layout y NetworkAnalysisPage compartan información sobre
 * el estado del chat para coordinar el desplazamiento del contenido
 */
const ChatLayoutContext = React.createContext({
    chatWidth: 0,
    chatSide: 'right',
    chatPanelOpen: false,
    setChatWidth: () => {},
    setChatSide: () => {},
    setChatPanelOpen: () => {}
})

export function ChatLayoutProvider({ children }) {
    // Inicializar desde localStorage
    const [chatWidth, setChatWidth] = React.useState(() => {
        try {
            const v = localStorage.getItem(REPORT_CHAT_WIDTH_KEY)
            if (v != null) {
                const n = parseInt(v, 10)
                if (!Number.isNaN(n) && n >= CHAT_WIDTH_MIN && n <= CHAT_WIDTH_MAX) {
                    return n
                }
            }
        } catch {
            // ignore
        }
        return CHAT_WIDTH_DEFAULT
    })
    
    const [chatSide, setChatSide] = React.useState(() => {
        try {
            return localStorage.getItem(REPORT_CHAT_SIDE_KEY) || 'right'
        } catch {
            return 'right'
        }
    })
    
    const [chatPanelOpen, setChatPanelOpen] = React.useState(() => {
        try {
            const v = localStorage.getItem(REPORT_CHAT_OPEN_KEY)
            return v !== 'false'
        } catch {
            return true
        }
    })

    // Guardar en localStorage cuando cambien los valores
    React.useEffect(() => {
        try {
            localStorage.setItem(REPORT_CHAT_SIDE_KEY, chatSide)
        } catch {
            // ignore
        }
    }, [chatSide])

    React.useEffect(() => {
        try {
            localStorage.setItem(REPORT_CHAT_OPEN_KEY, String(chatPanelOpen))
        } catch {
            // ignore
        }
    }, [chatPanelOpen])

    React.useEffect(() => {
        try {
            localStorage.setItem(REPORT_CHAT_WIDTH_KEY, String(chatWidth))
        } catch {
            // ignore
        }
    }, [chatWidth])

    const value = React.useMemo(
        () => ({
            chatWidth,
            chatSide,
            chatPanelOpen,
            setChatWidth,
            setChatSide,
            setChatPanelOpen
        }),
        [chatWidth, chatSide, chatPanelOpen]
    )

    return (
        <ChatLayoutContext.Provider value={value}>
            {children}
        </ChatLayoutContext.Provider>
    )
}

export function useChatLayout() {
    const context = React.useContext(ChatLayoutContext)
    if (!context) {
        throw new Error('useChatLayout debe usarse dentro de ChatLayoutProvider')
    }
    return context
}

export default ChatLayoutContext
