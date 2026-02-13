"""
Repository for session management in database
"""
import json
import uuid
from typing import Optional, List
from sqlalchemy.orm import Session as SQLSession
from ..models.database import Session
from ..models.schemas import AgentState, Message
from datetime import datetime


class SessionRepository:
    """
    Repository for managing sessions in the database.
    Allows persisting the state of agent sessions.
    """
    
    def create_session(
        self,
        db: SQLSession,
        session_id: str,
        user_id: Optional[str] = None,
        initial_state: Optional[AgentState] = None
    ) -> Session:
        """
        Creates a new session in the database.
        
        Args:
            db: Database session
            session_id: Unique session ID
            user_id: User ID (optional)
            initial_state: Initial agent state (optional)
        
        Returns:
            Created Session instance
        """
        context_json = None
        variables_json = None
        
        if initial_state:
            context_json = json.dumps([
                {"role": msg.role, "content": msg.content}
                for msg in initial_state.context_window
            ])
            variables_json = json.dumps(initial_state.variables)
        
        session = Session(
            id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
            context_json=context_json,
            variables_json=variables_json
        )
        
        db.add(session)
        db.commit()
        db.refresh(session)
        return session
    
    def get_session(
        self,
        db: SQLSession,
        session_id: str
    ) -> Optional[Session]:
        """
        Gets a session by its session_id.
        
        Args:
            db: Database session
            session_id: Session ID
        
        Returns:
            Session instance or None
        """
        return db.query(Session).filter(
            Session.session_id == session_id
        ).first()
    
    def update_session_state(
        self,
        db: SQLSession,
        session_id: str,
        state: AgentState
    ) -> Optional[Session]:
        """
        Updates the state of a session.
        
        Args:
            db: Database session
            session_id: Session ID
            state: New agent state
        
        Returns:
            Updated Session instance or None
        """
        session = self.get_session(db, session_id)
        if not session:
            return None
        
        session.context_json = json.dumps([
            {"role": msg.role, "content": msg.content}
            for msg in state.context_window
        ])
        session.variables_json = json.dumps(state.variables)
        session.user_id = state.user_id
        session.last_activity = datetime.utcnow()
        
        db.commit()
        db.refresh(session)
        return session
    
    def session_to_agent_state(self, session: Session) -> AgentState:
        """
        Converts a Session model to AgentState.
        
        Args:
            session: Session instance
        
        Returns:
            AgentState instance
        """
        context_window = []
        if session.context_json:
            try:
                context_data = json.loads(session.context_json)
                context_window = [
                    Message(role=item["role"], content=item["content"])
                    for item in context_data
                ]
            except (json.JSONDecodeError, KeyError):
                pass
        
        variables = {}
        if session.variables_json:
            try:
                variables = json.loads(session.variables_json)
            except json.JSONDecodeError:
                pass
        
        return AgentState(
            session_id=session.session_id,
            user_id=session.user_id,
            context_window=context_window,
            variables=variables
        )
    
    def delete_session(
        self,
        db: SQLSession,
        session_id: str
    ) -> bool:
        """
        Deletes a session from the database.
        
        Args:
            db: Database session
            session_id: Session ID
        
        Returns:
            True if deleted successfully
        """
        session = self.get_session(db, session_id)
        if session:
            db.delete(session)
            db.commit()
            return True
        return False
    
    def list_sessions(
        self,
        db: SQLSession,
        user_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Session]:
        """
        Lists sessions, optionally filtered by user_id.
        
        Args:
            db: Database session
            user_id: Filter by user_id (optional)
            skip: Number of sessions to skip
            limit: Maximum number of sessions to return
        
        Returns:
            List of sessions
        """
        query = db.query(Session)
        if user_id:
            query = query.filter(Session.user_id == user_id)
        return query.order_by(Session.last_activity.desc()).offset(skip).limit(limit).all()

