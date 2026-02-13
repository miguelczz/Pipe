"""
Pydantic schemas for data validation and serialization
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


# ============================================================================
# Message Schemas and Agent State
# ============================================================================

class Message(BaseModel):
    """Model for messages in conversation context"""
    role: str  # "user", "agent", "system"
    content: str


class AgentState(BaseModel):
    """Agent state with context and variables"""
    session_id: str = "default-session"
    user_id: Optional[str] = None
    context_window: List[Message] = Field(default_factory=list)
    variables: Dict[str, Any] = Field(default_factory=dict)
    results: Dict[str, Any] = Field(default_factory=dict)
    report_id: Optional[str] = None

    def add_message(self, role: str, content: str):
        """Adds a message to context, limiting to 20 messages"""
        self.context_window.append(Message(role=role, content=content))
        if len(self.context_window) > 20:
            self.context_window = self.context_window[-20:]


# ============================================================================
# API Schemas
# ============================================================================

class AgentQuery(BaseModel):
    """Schema for agent queries"""
    session_id: str = "default-session"
    user_id: Optional[str] = None
    messages: List[Message] = Field(
        ..., 
        min_length=1, 
        description="List of messages, must include at least one user message"
    )
    # Optional configuration
    max_context_messages: Optional[int] = Field(
        default=None,
        description="Maximum number of context messages to use (default: all)"
    )
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Temperature for generation (0.0-2.0, default: uses system config)"
    )
    include_thought_chain: Optional[bool] = Field(
        default=None,
        description="Include thought chain in response (default: according to configuration)"
    )
    report_id: Optional[str] = Field(default=None, description="Report ID when the chat is about a specific analysis")
    selected_text: Optional[str] = Field(default=None, description="Text selected by the user in the report")


class SimpleQuery(BaseModel):
    """Simplified schema for queries - only user prompt"""
    prompt: str = Field(..., min_length=1, description="The user message")
    session_id: Optional[str] = Field(default="default-session", description="Session ID (optional)")
    user_id: Optional[str] = Field(default=None, description="User ID (optional)")


class FileUploadResponse(BaseModel):
    """Response when uploading a file"""
    document_id: str
    filename: str
    status: str
    uploaded_at: Optional[datetime] = None


class FileListResponse(BaseModel):
    """Response when listing files"""
    document_id: str
    filename: str
    uploaded_at: Optional[datetime] = None


class DocumentMetadata(BaseModel):
    """Metadata of a document"""
    document_id: str
    filename: str
    source: str
    chunk_count: Optional[int] = None
    uploaded_at: Optional[datetime] = None

