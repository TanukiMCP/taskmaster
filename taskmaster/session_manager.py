import os
import json
import threading
import uuid
import asyncio
import aiofiles
from typing import Dict, Optional, List
from pathlib import Path
import logging
from .models import Session
from .config import get_config

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Thread-safe session manager that replaces global state management.
    
    Provides centralized session storage, retrieval, and persistence
    with proper concurrency control and error handling.
    """
    
    def __init__(self, state_directory: Optional[str] = None):
        """
        Initialize the session manager.
        
        Args:
            state_directory: Directory for session storage. If None, uses config.
        """
        self._sessions: Dict[str, Session] = {}
        self._current_session_id: Optional[str] = None
        self._lock = threading.RLock()
        
        # Set up state directory
        if state_directory:
            self._state_directory = Path(state_directory)
        else:
            config = get_config()
            self._state_directory = Path(config.get_state_directory())
        
        # Ensure state directory exists
        self._state_directory.mkdir(parents=True, exist_ok=True)
        
        # Load existing sessions on startup (run in background)
        asyncio.create_task(self._load_existing_sessions())
    
    async def _load_existing_sessions(self) -> None:
        """Load all existing sessions from disk."""
        try:
            # Load current session if it exists
            current_session_file = self._state_directory / "current_session.json"
            if current_session_file.exists():
                async with aiofiles.open(current_session_file, 'r') as f:
                    content = await f.read()
                    session_data = json.loads(content)
                session = Session(**session_data)
                with self._lock:
                    self._sessions[session.id] = session
                    self._current_session_id = session.id
                logger.info(f"Loaded current session: {session.id}")
        except Exception as e:
            logger.warning(f"Could not load existing sessions: {e}")
    
    async def create_session(self, session_name: Optional[str] = None) -> Session:
        """
        Create a new session with optional name.
        
        Args:
            session_name: Optional human-readable session name
            
        Returns:
            Session: The newly created session
        """
        session = Session()
        if session_name:
            session.session_name = session_name
        
        # Set basic environment context
        session.environment_context = {
            "created_at": str(uuid.uuid4()),
            "capabilities_declared": False,
            "llm_environment": "agentic_coding_assistant",
            "workflow_paused": False,
            "pause_reason": None,
            "validation_state": "none"
        }
        
        with self._lock:
            self._sessions[session.id] = session
            self._current_session_id = session.id
        
        # Persist the session
        await self._save_session(session)
        await self._save_current_session_reference(session.id)
        
        logger.info(f"Created new session: {session.id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """
        Get a session by ID.
        
        Args:
            session_id: The session ID to retrieve
            
        Returns:
            Session or None if not found
        """
        with self._lock:
            return self._sessions.get(session_id)
    
    def get_current_session(self) -> Optional[Session]:
        """
        Get the current active session.
        
        Returns:
            Session or None if no current session
        """
        with self._lock:
            if self._current_session_id:
                return self._sessions.get(self._current_session_id)
            return None
    
    def set_current_session(self, session_id: str) -> bool:
        """
        Set the current active session.
        
        Args:
            session_id: The session ID to make current
            
        Returns:
            bool: True if successful, False if session not found
        """
        with self._lock:
            if session_id in self._sessions:
                self._current_session_id = session_id
                self._save_current_session_reference(session_id)
                logger.info(f"Set current session to: {session_id}")
                return True
            return False
    
    async def update_session(self, session: Session) -> None:
        """
        Update an existing session.
        
        Args:
            session: The session to update
        """
        with self._lock:
            self._sessions[session.id] = session
        
        # Persist the updated session
        await self._save_session(session)
        logger.debug(f"Updated session: {session.id}")
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: The session ID to delete
            
        Returns:
            bool: True if deleted, False if not found
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                
                # If this was the current session, clear it
                if self._current_session_id == session_id:
                    self._current_session_id = None
                    self._clear_current_session_reference()
                
                # Remove session file
                session_file = self._state_directory / f"{session_id}.json"
                if session_file.exists():
                    session_file.unlink()
                
                logger.info(f"Deleted session: {session_id}")
                return True
            return False
    
    def list_sessions(self) -> List[Dict[str, str]]:
        """
        List all sessions with basic info.
        
        Returns:
            List of session info dictionaries
        """
        with self._lock:
            return [
                {
                    "id": session.id,
                    "name": getattr(session, 'session_name', None) or "Unnamed",
                    "task_count": len(session.tasks),
                    "is_current": session.id == self._current_session_id
                }
                for session in self._sessions.values()
            ]
    
    async def _save_session(self, session: Session) -> None:
        """Save a session to disk."""
        try:
            session_file = self._state_directory / f"{session.id}.json"
            async with aiofiles.open(session_file, 'w') as f:
                await f.write(json.dumps(session.model_dump(), indent=2))
        except Exception as e:
            logger.error(f"Failed to save session {session.id}: {e}")
            raise
    
    async def _save_current_session_reference(self, session_id: str) -> None:
        """Save reference to current session."""
        try:
            current_session_file = self._state_directory / "current_session.json"
            session = self._sessions[session_id]
            async with aiofiles.open(current_session_file, 'w') as f:
                await f.write(json.dumps(session.model_dump(), indent=2))
        except Exception as e:
            logger.error(f"Failed to save current session reference: {e}")
            raise
    
    def _clear_current_session_reference(self) -> None:
        """Clear the current session reference file."""
        try:
            current_session_file = self._state_directory / "current_session.json"
            if current_session_file.exists():
                current_session_file.unlink()
        except Exception as e:
            logger.error(f"Failed to clear current session reference: {e}")
    
    def get_session_file_path(self, session_id: str) -> Path:
        """
        Get the file path for a session.
        
        Args:
            session_id: The session ID
            
        Returns:
            Path: The session file path
        """
        return self._state_directory / f"{session_id}.json"
    
    def __len__(self) -> int:
        """Return the number of sessions."""
        with self._lock:
            return len(self._sessions)
    
    def __contains__(self, session_id: str) -> bool:
        """Check if a session exists."""
        with self._lock:
            return session_id in self._sessions 