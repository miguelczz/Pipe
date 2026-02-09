import React from 'react'
import { Trash2, PanelLeft, PanelRight, X } from 'lucide-react'
import { Button } from '../ui/Button'
import { ChatContainer } from './ChatContainer'
import { ChatInput } from './ChatInput'
import { useChatLayout } from '../../contexts/ChatLayoutContext'
import { useGlobalChat } from '../../contexts/GlobalChatContext'

const CHAT_WIDTH_MIN = 280
const CHAT_WIDTH_MAX = 720

/**
 * Panel de chat global que aparece en todas las páginas
 * Se renderiza desde el Layout y consume datos del GlobalChatContext
 */
export function GlobalChatPanel() {
    const { chatWidth, setChatWidth, chatSide, setChatSide, chatPanelOpen, setChatPanelOpen, availableModes } = useChatLayout()
    const {
        messages,
        isLoading,
        disabled,
        chatMode,
        highlightedContext,
        selectionLockActive,
        setChatMode,
        setHighlightedContext,
        setSelectionLockActive,
        onSend,
        onClearMessages,
        onSaveEditedMessage,
    } = useGlobalChat()

    const [isResizing, setIsResizing] = React.useState(false)
    const isResizingRef = React.useRef(false)

    // Validar que el modo actual esté disponible
    React.useEffect(() => {
        if (availableModes && availableModes.length > 0 && !availableModes.includes(chatMode)) {
            // Si el modo actual no está disponible, cambiar al primer modo disponible
            setChatMode(availableModes[0])
        }
    }, [availableModes, chatMode, setChatMode])

    const handleResizeStart = React.useCallback((e) => {
        e.preventDefault()
        isResizingRef.current = true
        setIsResizing(true)
    }, [])

    React.useEffect(() => {
        if (!chatPanelOpen) return
        const onMove = (e) => {
            if (!isResizingRef.current) return
            const clientX = e.clientX ?? 0
            if (chatSide === 'right') {
                const w = Math.round(Math.max(CHAT_WIDTH_MIN, Math.min(CHAT_WIDTH_MAX, window.innerWidth - clientX)))
                setChatWidth(w)
            } else {
                const w = Math.round(Math.max(CHAT_WIDTH_MIN, Math.min(CHAT_WIDTH_MAX, clientX)))
                setChatWidth(w)
            }
        }
        const onUp = () => {
            isResizingRef.current = false
            setIsResizing(false)
        }
        document.addEventListener('mousemove', onMove)
        document.addEventListener('mouseup', onUp)
        return () => {
            document.removeEventListener('mousemove', onMove)
            document.removeEventListener('mouseup', onUp)
        }
    }, [chatPanelOpen, chatSide, setChatWidth])

    React.useEffect(() => {
        if (isResizing) {
            document.body.style.cursor = 'col-resize'
            document.body.style.userSelect = 'none'
        }
        return () => {
            document.body.style.cursor = ''
            document.body.style.userSelect = ''
        }
    }, [isResizing])

    return (
        <aside
            className={`fixed top-0 bottom-0 z-50 flex flex-col h-screen rounded-none border border-dark-border-primary/50 bg-dark-bg-primary overflow-hidden print:hidden shadow-lg min-w-0 ${chatSide === 'left' ? 'left-0' : 'right-0'}`}
            aria-label="Chat global"
            style={{
                width: chatPanelOpen ? chatWidth : 0,
                transition: 'width 0.45s cubic-bezier(0.4, 0, 0.2, 1)',
                pointerEvents: chatPanelOpen ? 'auto' : 'none'
            }}
            onWheel={(e) => e.stopPropagation()}
        >
            {/* Handle de redimensionamiento */}
            <div
                role="separator"
                aria-label="Redimensionar ancho del chat"
                className={`absolute top-0 bottom-0 w-2 cursor-col-resize flex-shrink-0 z-10 flex items-center justify-center hover:bg-dark-border-primary/20 ${chatSide === 'left' ? 'right-0' : 'left-0'}`}
                onMouseDown={handleResizeStart}
                style={{ [chatSide === 'left' ? 'right' : 'left']: 0 }}
            >
                <div className="w-0.5 h-12 rounded-full bg-dark-border-primary/50" />
            </div>

            {/* Header */}
            <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-dark-border-primary/50 bg-dark-surface-primary/50 flex-shrink-0">
                <span className="text-sm font-medium text-dark-text-primary truncate">
                    Pipechat
                </span>
                <div className="flex items-center gap-1 flex-shrink-0">
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="p-1.5 text-dark-text-muted hover:text-dark-accent-primary"
                        onClick={() => onClearMessages?.()}
                        title="Limpiar chat"
                    >
                        <Trash2 className="w-4 h-4" />
                    </Button>
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="p-1.5 text-dark-text-muted hover:text-dark-accent-primary"
                        onClick={() => setChatSide(chatSide === 'left' ? 'right' : 'left')}
                        title={chatSide === 'left' ? 'Mover chat a la derecha' : 'Mover chat a la izquierda'}
                    >
                        {chatSide === 'left' ? <PanelRight className="w-4 h-4" /> : <PanelLeft className="w-4 h-4" />}
                    </Button>
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="p-1.5 text-dark-text-muted hover:text-dark-accent-primary"
                        onClick={() => setChatPanelOpen(false)}
                        title="Cerrar chat"
                    >
                        <X className="w-4 h-4" />
                    </Button>
                </div>
            </div>

            {/* Chat Container */}
            <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
                <ChatContainer
                    messages={messages}
                    isLoading={isLoading}
                    onSaveEditedMessage={onSaveEditedMessage}
                    mode={chatMode}
                    onModeChange={setChatMode}
                    modeLocked={selectionLockActive}
                />
            </div>

            {/* Chat Input */}
            <div className="p-2 border-t border-dark-border-primary/50 flex-shrink-0 bg-dark-bg-primary">
                <ChatInput
                    onSend={onSend}
                    isLoading={isLoading}
                    disabled={disabled}
                    mode={chatMode}
                    modeLocked={selectionLockActive}
                    onModeChange={setChatMode}
                    contextText={highlightedContext}
                    onClearContext={() => {
                        setHighlightedContext(null)
                        setSelectionLockActive(false)
                    }}
                />
            </div>
        </aside>
    )
}
