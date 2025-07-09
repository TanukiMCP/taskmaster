import asyncio
import json
import os
import logging
from typing import Optional, Dict, Any, List
from .models import Session
from .exceptions import SessionError, ErrorCode
from .workflow_state_machine import WorkflowEvent
import aiofiles

logger = logging.getLogger(__name__)

class SessionManager:
    """
    Production-quality session manager with async support and proper error handling.
    
    Handles session creation, persistence, and lifecycle management with:
    - Async locks for thread safety
    - Proper error handling with structured exceptions
    - Efficient file-based storage
    - Current session tracking
    - Optional workflow state machine integration
    - Optional async persistence integration
    - Ultra-lazy initialization for Smithery compatibility
    """
    
    def __init__(self, state_dir: str = "taskmaster/state", persistence=None, workflow_state_machine=None):
        self.state_dir = state_dir
        self.current_session_file = os.path.join(state_dir, "current_session.json")
        self._lock = asyncio.Lock() # Use async lock for async environment
        self._current_session: Optional[Session] = None
        self._initialized = False
        
        # Optional enhanced components
        self.persistence = persistence # AsyncSessionPersistence if available
        self.workflow_state_machine = workflow_state_machine # WorkflowStateMachine if available
        
        # Defer directory creation and file operations until actually needed
        # This prevents file system operations during Smithery tool discovery
        logger.info(f"SessionManager created with deferred initialization for state directory: {state_dir}")
        
        if self.persistence:
            logger.info("SessionManager configured with async persistence")
        if self.workflow_state_machine:
            logger.info("SessionManager configured with workflow state machine")
    
    async def _ensure_initialized(self):
        """Ensure the session manager is properly initialized - called only when needed."""
        if not self._initialized:
            async with self._lock:
                if not self._initialized:
                    # Create state directory only when actually needed
                    os.makedirs(self.state_dir, exist_ok=True)
                    self._initialized = True
                    logger.info(f"SessionManager initialized with state directory: {self.state_dir}")
    
    async def create_session(self, session_name: Optional[str] = None) -> Session:
        """Create a new session and set it as current."""
        await self._ensure_initialized()
        
        if not self.persistence:
            raise SessionError("Async persistence handler not configured", error_code=ErrorCode.CONFIG_NOT_FOUND)

        async with self._lock:
            session = Session(name=session_name or "Default Session")
            
            if self.workflow_state_machine:
                try:
                    self.workflow_state_machine.context.session_id = session.id
                    self.workflow_state_machine.trigger_event(WorkflowEvent.CREATE_SESSION)
                except Exception as e:
                    logger.warning(f"Workflow state machine error during session creation: {e}")

            await self.persistence.save_session(session)
            await self._update_current_session_reference(session.id)
            self._current_session = session
            logger.info(f"Created new session: {session.id}")
            return session
    
    async def _update_current_session_reference(self, session_id: str) -> None:
        """Update current session reference file using async persistence."""
        await self._ensure_initialized()
        
        try:
            async with aiofiles.open(self.current_session_file, 'w') as f:
                await f.write(json.dumps({"current_session_id": session_id}, indent=2))
        except Exception as e:
            logger.error(f"Failed to update current session reference: {e}")
            raise SessionError(
                "Failed to update current session reference",
                error_code=ErrorCode.SESSION_PERSISTENCE_FAILED,
                cause=e
            )
    
    async def get_current_session(self) -> Optional[Session]:
        """Get the current active session."""
        if self._current_session:
            return self._current_session

        await self._ensure_initialized()

        if not os.path.exists(self.current_session_file):
            return None

        try:
            async with aiofiles.open(self.current_session_file, 'r') as f:
                content = await f.read()
                current_data = json.loads(content)
                
                session_id = current_data.get("current_session_id")
                if session_id:
                    session = await self.get_session_async(session_id)
                    if session:
                        self._current_session = session
                        return session
        except Exception:
            # File might be corrupted or empty, treat as no current session
            return None
        
        return None
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID (alias for async version)."""
        return await self.get_session_async(session_id)
    
    async def get_session_async(self, session_id: str) -> Optional[Session]:
        """Get a session by ID using async persistence."""
        await self._ensure_initialized()
        
        if not self.persistence:
            raise SessionError("Async persistence handler not configured", error_code=ErrorCode.CONFIG_NOT_FOUND)
        
        try:
            return await self.persistence.load_session(session_id)
        except Exception as e:
            logger.error(f"Failed to load session {session_id} with async persistence: {e}")
            raise SessionError(
                f"Failed to load session: {str(e)}",
                session_id=session_id,
                error_code=ErrorCode.SESSION_PERSISTENCE_FAILED,
                cause=e
            )
    
    async def update_session(self, session: Session) -> None:
        """Update an existing session."""
        await self._ensure_initialized()
        
        if not self.persistence:
            raise SessionError("Async persistence handler not configured", error_code=ErrorCode.CONFIG_NOT_FOUND)

        async with self._lock:
            try:
                await self.persistence.save_session(session)
                
                if self._current_session and self._current_session.id == session.id:
                    self._current_session = session
                
                logger.debug(f"Updated session: {session.id}")
                
            except Exception as e:
                raise SessionError(
                    f"Failed to update session: {str(e)}", 
                    session_id=session.id,
                    error_code=ErrorCode.SESSION_PERSISTENCE_FAILED,
                    cause=e
                )
    
    async def end_session(self, session_id: str) -> None:
        """End a session and clear it as current if it's the active one."""
        await self._ensure_initialized()
        
        if not self.persistence:
            raise SessionError("Async persistence handler not configured", error_code=ErrorCode.CONFIG_NOT_FOUND)

        async with self._lock:
            session = await self.get_session_async(session_id)
            
            if not session:
                raise SessionError(
                    f"Session {session_id} not found", 
                    session_id=session_id,
                    error_code=ErrorCode.SESSION_NOT_FOUND
                )
            
            if self.workflow_state_machine:
                try:
                    self.workflow_state_machine.context.session_id = session_id
                    # Note: No specific end session event defined in current workflow
                    logger.info(f"Session {session_id} ended - workflow state machine updated")
                except Exception as e:
                    logger.warning(f"Workflow state machine error during session end: {e}")
            
            # Clear current session reference if this is the current session
            if self._current_session and self._current_session.id == session_id:
                self._current_session = None
                if os.path.exists(self.current_session_file):
                    try:
                        await asyncio.to_thread(os.remove, self.current_session_file)
                    except Exception as e:
                        logger.error(f"Failed to remove current session file: {e}")
            
            logger.info(f"Ended session: {session_id}")
    
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions using async persistence."""
        await self._ensure_initialized()
        
        if not self.persistence:
            raise SessionError("Async persistence handler not configured", error_code=ErrorCode.CONFIG_NOT_FOUND)
        return await self.persistence.list_sessions()
    
    async def __len__(self) -> int:
        """Return the number of sessions."""
        if self.persistence:
            await self._ensure_initialized()
            sessions = await self.persistence.list_sessions()
            return len(sessions)
        return 0
    
    async def __contains__(self, session_id: str) -> bool:
        """Check if a session exists."""
        if self.persistence:
            await self._ensure_initialized()
            return await self.persistence.load_session(session_id) is not None
        return False 