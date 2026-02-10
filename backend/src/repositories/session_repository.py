"""
Repositorio para gestión de sesiones en base de datos
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
    Repositorio para gestionar sesiones en la base de datos.
    Permite persistir el estado de las sesiones del agente.
    """
    
    def create_session(
        self,
        db: SQLSession,
        session_id: str,
        user_id: Optional[str] = None,
        initial_state: Optional[AgentState] = None
    ) -> Session:
        """
        Crea una nueva sesión en la base de datos.
        
        Args:
            db: Sesión de base de datos
            session_id: ID único de la sesión
            user_id: ID del usuario (opcional)
            initial_state: Estado inicial del agente (opcional)
        
        Returns:
            Instancia de Session creada
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
        Obtiene una sesión por su session_id.
        
        Args:
            db: Sesión de base de datos
            session_id: ID de la sesión
        
        Returns:
            Instancia de Session o None
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
        Actualiza el estado de una sesión.
        
        Args:
            db: Sesión de base de datos
            session_id: ID de la sesión
            state: Nuevo estado del agente
        
        Returns:
            Instancia de Session actualizada o None
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
        Convierte un modelo Session a AgentState.
        
        Args:
            session: Instancia de Session
        
        Returns:
            Instancia de AgentState
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
        Elimina una sesión de la base de datos.
        
        Args:
            db: Sesión de base de datos
            session_id: ID de la sesión
        
        Returns:
            True si se eliminó correctamente
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
        Lista sesiones, opcionalmente filtradas por user_id.
        
        Args:
            db: Sesión de base de datos
            user_id: Filtrar por user_id (opcional)
            skip: Número de sesiones a saltar
            limit: Número máximo de sesiones a retornar
        
        Returns:
            Lista de sesiones
        """
        query = db.query(Session)
        if user_id:
            query = query.filter(Session.user_id == user_id)
        return query.order_by(Session.last_activity.desc()).offset(skip).limit(limit).all()

