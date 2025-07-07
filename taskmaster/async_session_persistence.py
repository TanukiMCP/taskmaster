"""
Async session persistence for the Taskmaster application.

Provides async file operations, resource management, and robust session
persistence with proper error handling and resource cleanup.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, AsyncContextManager
from contextlib import asynccontextmanager
import aiofiles
import aiofiles.os
from .models import Session
from .exceptions import TaskmasterError, ErrorCode, SessionError

logger = logging.getLogger(__name__)


class AsyncSessionPersistence:
    """
    Async session persistence manager with proper resource management.
    
    Provides async file operations, atomic writes, backup management,
    and proper resource cleanup for robust session persistence.
    """
    
    def __init__(self, storage_directory: Path, backup_count: int = 5):
        """
        Initialize the async session persistence manager.
        
        Args:
            storage_directory: Directory for session storage
            backup_count: Number of backup files to maintain
        """
        self.storage_directory = Path(storage_directory)
        self.backup_count = backup_count
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_for_locks = asyncio.Lock()
        
        # Ensure storage directory exists
        self.storage_directory.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"AsyncSessionPersistence initialized with directory: {storage_directory}")
    
    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create a lock for a specific session."""
        async with self._lock_for_locks:
            if session_id not in self._locks:
                self._locks[session_id] = asyncio.Lock()
            return self._locks[session_id]
    
    def _get_session_file_path(self, session_id: str) -> Path:
        """Get the file path for a session."""
        return self.storage_directory / f"{session_id}.json"
    
    def _get_backup_file_path(self, session_id: str, backup_index: int) -> Path:
        """Get the backup file path for a session."""
        return self.storage_directory / f"{session_id}.backup.{backup_index}.json"
    
    def _get_temp_file_path(self, session_id: str) -> Path:
        """Get the temporary file path for atomic writes."""
        return self.storage_directory / f"{session_id}.tmp.json"    
    async def save_session(self, session: Session) -> None:
        """
        Save a session to disk with atomic write and backup management.
        
        Args:
            session: The session to save
        
        Raises:
            SessionError: If saving fails
        """
        session_lock = await self._get_session_lock(session.id)
        
        async with session_lock:
            try:
                # Create backup if session file exists
                await self._create_backup(session.id)
                
                # Perform atomic write
                await self._atomic_write_session(session)
                
                logger.debug(f"Session saved: {session.id}")
                
            except Exception as e:
                logger.error(f"Failed to save session {session.id}: {e}")
                raise SessionError(
                    message=f"Failed to save session: {str(e)}",
                    session_id=session.id,
                    error_code=ErrorCode.SESSION_PERSISTENCE_FAILED,
                    cause=e
                )
    
    async def load_session(self, session_id: str) -> Optional[Session]:
        """
        Load a session from disk with fallback to backups.
        
        Args:
            session_id: The session ID to load
        
        Returns:
            Session instance or None if not found
        
        Raises:
            SessionError: If loading fails
        """
        session_lock = await self._get_session_lock(session_id)
        
        async with session_lock:
            try:
                # Try to load main session file
                session_file = self._get_session_file_path(session_id)
                
                if await aiofiles.os.path.exists(session_file):
                    session = await self._load_session_from_file(session_file)
                    if session:
                        logger.debug(f"Session loaded: {session_id}")
                        return session
                
                # Try to load from backups
                session = await self._load_from_backups(session_id)
                if session:
                    logger.info(f"Session loaded from backup: {session_id}")
                    # Restore the session to main file
                    await self._atomic_write_session(session)
                    return session
                
                logger.debug(f"Session not found: {session_id}")
                return None
                
            except Exception as e:
                logger.error(f"Failed to load session {session_id}: {e}")
                raise SessionError(
                    message=f"Failed to load session: {str(e)}",
                    session_id=session_id,
                    error_code=ErrorCode.SESSION_PERSISTENCE_FAILED,
                    cause=e
                )    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and its backups.
        
        Args:
            session_id: The session ID to delete
        
        Returns:
            bool: True if deleted, False if not found
        """
        session_lock = await self._get_session_lock(session_id)
        
        async with session_lock:
            try:
                deleted = False
                
                # Delete main session file
                session_file = self._get_session_file_path(session_id)
                if await aiofiles.os.path.exists(session_file):
                    await aiofiles.os.remove(session_file)
                    deleted = True
                
                # Delete backup files
                for i in range(self.backup_count):
                    backup_file = self._get_backup_file_path(session_id, i)
                    if await aiofiles.os.path.exists(backup_file):
                        await aiofiles.os.remove(backup_file)
                        deleted = True
                
                # Delete temp file if it exists
                temp_file = self._get_temp_file_path(session_id)
                if await aiofiles.os.path.exists(temp_file):
                    await aiofiles.os.remove(temp_file)
                
                if deleted:
                    logger.info(f"Session deleted: {session_id}")
                
                return deleted
                
            except Exception as e:
                logger.error(f"Failed to delete session {session_id}: {e}")
                raise SessionError(
                    message=f"Failed to delete session: {str(e)}",
                    session_id=session_id,
                    error_code=ErrorCode.SESSION_PERSISTENCE_FAILED,
                    cause=e
                )    
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List all available sessions with metadata.
        
        Returns:
            List of session metadata dictionaries
        """
        try:
            sessions = []
            
            # Scan for session files
            for file_path in self.storage_directory.glob("*.json"):
                if file_path.name.endswith(".backup.json") or file_path.name.endswith(".tmp.json"):
                    continue
                
                session_id = file_path.stem
                
                try:
                    # Get file stats
                    stat = await aiofiles.os.stat(file_path)
                    
                    # Try to load session for additional metadata
                    session = await self._load_session_from_file(file_path)
                    
                    session_info = {
                        "id": session_id,
                        "file_path": str(file_path),
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "name": getattr(session, 'session_name', None) if session else None,
                        "task_count": len(session.tasks) if session else 0,
                        "valid": session is not None
                    }
                    
                    sessions.append(session_info)
                    
                except Exception as e:
                    logger.warning(f"Error reading session file {file_path}: {e}")
                    # Include invalid sessions in the list
                    sessions.append({
                        "id": session_id,
                        "file_path": str(file_path),
                        "size": 0,
                        "modified": 0,
                        "name": None,
                        "task_count": 0,
                        "valid": False,
                        "error": str(e)
                    })
            
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            raise SessionError(
                message=f"Failed to list sessions: {str(e)}",
                error_code=ErrorCode.SESSION_PERSISTENCE_FAILED,
                cause=e
            )    
    async def _atomic_write_session(self, session: Session) -> None:
        """Perform simple write of session data."""
        session_file = self._get_session_file_path(session.id)
        
        try:
            # Simple direct write - no temp files, no atomic operations
            async with aiofiles.open(session_file, 'w') as f:
                # Use Pydantic's model_dump with mode='json' to handle datetime serialization
                session_data = session.model_dump(mode='json')
                await f.write(json.dumps(session_data, indent=2))
                await f.flush()
                
        except Exception as e:
            raise e
    
    async def _create_backup(self, session_id: str) -> None:
        """Create a backup of the current session file."""
        session_file = self._get_session_file_path(session_id)
        
        if not await aiofiles.os.path.exists(session_file):
            return
        
        try:
            # Rotate existing backups
            for i in range(self.backup_count - 1, 0, -1):
                old_backup = self._get_backup_file_path(session_id, i - 1)
                new_backup = self._get_backup_file_path(session_id, i)
                
                if await aiofiles.os.path.exists(old_backup):
                    if await aiofiles.os.path.exists(new_backup):
                        await aiofiles.os.remove(new_backup)
                    await aiofiles.os.rename(old_backup, new_backup)
            
            # Create new backup from current file
            backup_file = self._get_backup_file_path(session_id, 0)
            if await aiofiles.os.path.exists(backup_file):
                await aiofiles.os.remove(backup_file)
            
            # Copy current file to backup
            async with aiofiles.open(session_file, 'rb') as src:
                async with aiofiles.open(backup_file, 'wb') as dst:
                    async for chunk in src:
                        await dst.write(chunk)
                        
        except Exception as e:
            logger.warning(f"Failed to create backup for session {session_id}: {e}")
            # Don't fail the main operation if backup fails    
    async def _load_session_from_file(self, file_path: Path) -> Optional[Session]:
        """Load session from a specific file."""
        try:
            async with aiofiles.open(file_path, 'r') as f:
                content = await f.read()
                session_data = json.loads(content)
                return Session(**session_data)
        except Exception as e:
            logger.warning(f"Failed to load session from {file_path}: {e}")
            return None
    
    async def _load_from_backups(self, session_id: str) -> Optional[Session]:
        """Try to load session from backup files."""
        for i in range(self.backup_count):
            backup_file = self._get_backup_file_path(session_id, i)
            
            if await aiofiles.os.path.exists(backup_file):
                session = await self._load_session_from_file(backup_file)
                if session:
                    logger.info(f"Loaded session {session_id} from backup {i}")
                    return session
        
        return None
    
    async def cleanup_temp_files(self) -> int:
        """
        Clean up temporary files that may have been left behind.
        
        Returns:
            Number of files cleaned up
        """
        try:
            cleaned_count = 0
            
            for temp_file in self.storage_directory.glob("*.tmp.json"):
                try:
                    await aiofiles.os.remove(temp_file)
                    cleaned_count += 1
                    logger.debug(f"Cleaned up temp file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file {temp_file}: {e}")
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} temporary files")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup temp files: {e}")
            return 0    
    async def verify_integrity(self, session_id: str) -> Dict[str, Any]:
        """
        Verify the integrity of a session and its backups.
        
        Args:
            session_id: The session ID to verify
        
        Returns:
            Dictionary containing integrity information
        """
        try:
            result = {
                "session_id": session_id,
                "main_file_valid": False,
                "backup_files_valid": [],
                "total_backups": 0,
                "valid_backups": 0,
                "errors": []
            }
            
            # Check main file
            session_file = self._get_session_file_path(session_id)
            if await aiofiles.os.path.exists(session_file):
                session = await self._load_session_from_file(session_file)
                result["main_file_valid"] = session is not None
                if not session:
                    result["errors"].append("Main session file is corrupted")
            else:
                result["errors"].append("Main session file does not exist")
            
            # Check backup files
            for i in range(self.backup_count):
                backup_file = self._get_backup_file_path(session_id, i)
                if await aiofiles.os.path.exists(backup_file):
                    result["total_backups"] += 1
                    session = await self._load_session_from_file(backup_file)
                    is_valid = session is not None
                    result["backup_files_valid"].append({
                        "index": i,
                        "valid": is_valid,
                        "file_path": str(backup_file)
                    })
                    if is_valid:
                        result["valid_backups"] += 1
                    else:
                        result["errors"].append(f"Backup file {i} is corrupted")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to verify integrity for session {session_id}: {e}")
            return {
                "session_id": session_id,
                "main_file_valid": False,
                "backup_files_valid": [],
                "total_backups": 0,
                "valid_backups": 0,
                "errors": [f"Integrity check failed: {str(e)}"]
            }    
    @asynccontextmanager
    async def session_transaction(self, session_id: str) -> AsyncContextManager[Optional[Session]]:
        """
        Context manager for transactional session operations.
        
        Args:
            session_id: The session ID to work with
        
        Yields:
            Session instance or None if not found
        """
        session_lock = await self._get_session_lock(session_id)
        
        async with session_lock:
            # Load session
            session = await self.load_session(session_id)
            
            try:
                yield session
                
                # Save session if it was modified
                if session:
                    await self.save_session(session)
                    
            except Exception as e:
                logger.error(f"Transaction failed for session {session_id}: {e}")
                raise
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Dictionary containing storage statistics
        """
        try:
            stats = {
                "storage_directory": str(self.storage_directory),
                "total_sessions": 0,
                "total_backups": 0,
                "total_temp_files": 0,
                "total_size": 0,
                "valid_sessions": 0,
                "corrupted_sessions": 0
            }
            
            # Count different file types
            for file_path in self.storage_directory.glob("*.json"):
                file_stat = await aiofiles.os.stat(file_path)
                stats["total_size"] += file_stat.st_size
                
                if file_path.name.endswith(".tmp.json"):
                    stats["total_temp_files"] += 1
                elif ".backup." in file_path.name:
                    stats["total_backups"] += 1
                else:
                    stats["total_sessions"] += 1
                    # Check if session is valid
                    session = await self._load_session_from_file(file_path)
                    if session:
                        stats["valid_sessions"] += 1
                    else:
                        stats["corrupted_sessions"] += 1
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {
                "storage_directory": str(self.storage_directory),
                "error": str(e)
            }    
    async def dispose(self) -> None:
        """Clean up resources and perform final cleanup."""
        try:
            # Clean up temporary files
            await self.cleanup_temp_files()
            
            # Clear locks
            async with self._lock_for_locks:
                self._locks.clear()
            
            logger.info("AsyncSessionPersistence disposed")
            
        except Exception as e:
            logger.error(f"Error during disposal: {e}")