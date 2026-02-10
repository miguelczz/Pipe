"""
Schemas Pydantic para validación de datos y serialización
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


# ============================================================================
# Schemas de Mensajes y Estado del Agente
# ============================================================================

class Message(BaseModel):
    """Modelo para mensajes en el contexto de conversación"""
    role: str  # "user", "agent", "system"
    content: str


class AgentState(BaseModel):
    """Estado del agente con contexto y variables"""
    session_id: str = "default-session"
    user_id: Optional[str] = None
    context_window: List[Message] = Field(default_factory=list)
    variables: Dict[str, Any] = Field(default_factory=dict)
    results: Dict[str, Any] = Field(default_factory=dict)
    report_id: Optional[str] = None

    def add_message(self, role: str, content: str):
        """Agrega un mensaje al contexto, limitando a 20 mensajes"""
        self.context_window.append(Message(role=role, content=content))
        if len(self.context_window) > 20:
            self.context_window = self.context_window[-20:]


# ============================================================================
# Schemas de API
# ============================================================================

class AgentQuery(BaseModel):
    """Schema para consultas al agente"""
    session_id: str = "default-session"
    user_id: Optional[str] = None
    messages: List[Message] = Field(
        ..., 
        min_length=1, 
        description="Lista de mensajes, debe incluir al menos un mensaje del usuario"
    )
    # Configuración opcional
    max_context_messages: Optional[int] = Field(
        default=None,
        description="Número máximo de mensajes de contexto a usar (por defecto: todos)"
    )
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Temperatura para generación (0.0-2.0, por defecto: usa configuración del sistema)"
    )
    include_thought_chain: Optional[bool] = Field(
        default=None,
        description="Incluir cadena de pensamiento en la respuesta (por defecto: según configuración)"
    )
    report_id: Optional[str] = Field(default=None, description="ID del reporte cuando el chat es sobre un análisis concreto")
    selected_text: Optional[str] = Field(default=None, description="Texto seleccionado por el usuario en el reporte")


class SimpleQuery(BaseModel):
    """Schema simplificado para consultas - solo el prompt del usuario"""
    prompt: str = Field(..., min_length=1, description="El mensaje del usuario")
    session_id: Optional[str] = Field(default="default-session", description="ID de sesión (opcional)")
    user_id: Optional[str] = Field(default=None, description="ID de usuario (opcional)")


class FileUploadResponse(BaseModel):
    """Respuesta al subir un archivo"""
    document_id: str
    filename: str
    status: str
    uploaded_at: Optional[datetime] = None


class FileListResponse(BaseModel):
    """Respuesta al listar archivos"""
    document_id: str
    filename: str
    uploaded_at: Optional[datetime] = None


class DocumentMetadata(BaseModel):
    """Metadatos de un documento"""
    document_id: str
    filename: str
    source: str
    chunk_count: Optional[int] = None
    uploaded_at: Optional[datetime] = None

