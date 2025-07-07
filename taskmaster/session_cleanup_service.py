"""
Session cleanup service for managing session lifecycle and cleanup operations.

Provides automated cleanup of expired sessions, backup management,
and integrity checking for robust session management.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
from .async_session_persistence import AsyncSessionPersistence
from .config import Config
from .exceptions import SessionError, ErrorCode

logger = logging.getLogger(__name__)


class SessionCleanupService:
 """
 Service for managing session cleanup and maintenance operations.
 
 Provides automated cleanup of expired sessions, backup management,
 and integrity checking for robust session management.
 """
 
 def __init__(self, persistence: AsyncSessionPersistence, config: Config):
 """
 Initialize the session cleanup service.
 
 Args:
 persistence: Session persistence manager
 config: Application configuration
 """
 self.persistence = persistence
 self.config = config
 self.cleanup_interval = config.get('session_cleanup_interval_hours', 24)
 self.session_ttl_days = config.get('session_ttl_days', 30)
 self.backup_retention_days = config.get('backup_retention_days', 7)
 self._cleanup_task: Optional[asyncio.Task] = None
 self._running = False
 
 logger.info("SessionCleanupService initialized")
 
 async def start_cleanup_scheduler(self) -> None:
 """Start the automated cleanup scheduler."""
 if self._running:
 logger.warning("Cleanup scheduler is already running")
 return
 
 self._running = True
 self._cleanup_task = asyncio.create_task(self._cleanup_loop())
 logger.info("Session cleanup scheduler started")
 
 async def stop_cleanup_scheduler(self) -> None:
 """Stop the automated cleanup scheduler."""
 if not self._running:
 return
 
 self._running = False
 if self._cleanup_task:
 self._cleanup_task.cancel()
 try:
 await self._cleanup_task
 except asyncio.CancelledError:
 pass
 
 logger.info("Session cleanup scheduler stopped")
 
 async def _cleanup_loop(self) -> None:
 """Main cleanup loop that runs periodically."""
 while self._running:
 try:
 await self.cleanup_expired_sessions()
 await self.cleanup_old_backups()
 await self.verify_session_integrity()
 
 # Wait for next cleanup cycle
 await asyncio.sleep(self.cleanup_interval * 3600) # Convert hours to seconds
 
 except asyncio.CancelledError:
 break
 except Exception as e:
 logger.error(f"Error in cleanup loop: {e}")
 # Wait a bit before retrying to avoid tight error loops
 await asyncio.sleep(300) # 5 minutes
 
 async def cleanup_expired_sessions(self) -> Dict[str, Any]:
 """
 Clean up expired sessions based on TTL configuration.
 
 Returns:
 Cleanup statistics
 """
 try:
 sessions = await self.persistence.list_sessions()
 expired_sessions = []
 cutoff_date = datetime.now() - timedelta(days=self.session_ttl_days)
 
 for session_info in sessions:
 # Parse creation date (assuming ISO format)
 try:
 created_at = datetime.fromisoformat(session_info.get('created_at', '').replace('Z', '+00:00'))
 if created_at < cutoff_date:
 expired_sessions.append(session_info['session_id'])
 except (ValueError, KeyError):
 # Skip sessions with invalid dates
 continue
 
 # Delete expired sessions
 deleted_count = 0
 for session_id in expired_sessions:
 try:
 await self.persistence.delete_session(session_id)
 deleted_count += 1
 logger.info(f"Deleted expired session: {session_id}")
 except Exception as e:
 logger.error(f"Failed to delete expired session {session_id}: {e}")
 
 stats = {
 "total_sessions": len(sessions),
 "expired_sessions": len(expired_sessions),
 "deleted_sessions": deleted_count,
 "cleanup_date": datetime.now().isoformat()
 }
 
 if deleted_count > 0:
 logger.info(f"Cleaned up {deleted_count} expired sessions")
 
 return stats
 
 except Exception as e:
 logger.error(f"Failed to cleanup expired sessions: {e}")
 raise SessionError(
 message="Failed to cleanup expired sessions",
 error_code=ErrorCode.SESSION_PERSISTENCE_FAILED,
 cause=e
 )
 
 async def cleanup_old_backups(self) -> Dict[str, Any]:
 """
 Clean up old backup files based on retention policy.
 
 Returns:
 Cleanup statistics
 """
 try:
 storage_dir = Path(self.persistence.storage_directory)
 backup_files = list(storage_dir.glob("*.backup.*.json"))
 
 cutoff_date = datetime.now() - timedelta(days=self.backup_retention_days)
 old_backups = []
 
 for backup_file in backup_files:
 try:
 # Get file modification time
 mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
 if mtime < cutoff_date:
 old_backups.append(backup_file)
 except OSError:
 continue
 
 # Delete old backups
 deleted_count = 0
 for backup_file in old_backups:
 try:
 backup_file.unlink()
 deleted_count += 1
 logger.debug(f"Deleted old backup: {backup_file.name}")
 except OSError as e:
 logger.error(f"Failed to delete backup {backup_file.name}: {e}")
 
 stats = {
 "total_backups": len(backup_files),
 "old_backups": len(old_backups),
 "deleted_backups": deleted_count,
 "cleanup_date": datetime.now().isoformat()
 }
 
 if deleted_count > 0:
 logger.info(f"Cleaned up {deleted_count} old backup files")
 
 return stats
 
 except Exception as e:
 logger.error(f"Failed to cleanup old backups: {e}")
 return {"error": str(e)}
 
 async def verify_session_integrity(self) -> Dict[str, Any]:
 """
 Verify integrity of all sessions and report any issues.
 
 Returns:
 Integrity check results
 """
 try:
 sessions = await self.persistence.list_sessions()
 integrity_issues = []
 
 for session_info in sessions:
 session_id = session_info.get('session_id')
 if not session_id:
 continue
 
 try:
 integrity_result = await self.persistence.verify_integrity(session_id)
 if not integrity_result.get('valid', True):
 integrity_issues.append({
 "session_id": session_id,
 "issues": integrity_result.get('issues', [])
 })
 except Exception as e:
 integrity_issues.append({
 "session_id": session_id,
 "issues": [f"Integrity check failed: {str(e)}"]
 })
 
 stats = {
 "total_sessions": len(sessions),
 "sessions_with_issues": len(integrity_issues),
 "integrity_issues": integrity_issues,
 "check_date": datetime.now().isoformat()
 }
 
 if integrity_issues:
 logger.warning(f"Found integrity issues in {len(integrity_issues)} sessions")
 
 return stats
 
 except Exception as e:
 logger.error(f"Failed to verify session integrity: {e}")
 return {"error": str(e)}
 
 async def cleanup_temp_files(self) -> Dict[str, Any]:
 """
 Clean up temporary files left by incomplete operations.
 
 Returns:
 Cleanup statistics
 """
 try:
 temp_files_cleaned = await self.persistence.cleanup_temp_files()
 
 stats = {
 "temp_files_cleaned": temp_files_cleaned,
 "cleanup_date": datetime.now().isoformat()
 }
 
 if temp_files_cleaned > 0:
 logger.info(f"Cleaned up {temp_files_cleaned} temporary files")
 
 return stats
 
 except Exception as e:
 logger.error(f"Failed to cleanup temp files: {e}")
 return {"error": str(e)}
 
 async def get_cleanup_stats(self) -> Dict[str, Any]:
 """
 Get current cleanup service statistics.
 
 Returns:
 Service statistics
 """
 try:
 storage_stats = await self.persistence.get_storage_stats()
 
 return {
 "service_status": "running" if self._running else "stopped",
 "cleanup_interval_hours": self.cleanup_interval,
 "session_ttl_days": self.session_ttl_days,
 "backup_retention_days": self.backup_retention_days,
 "storage_stats": storage_stats
 }
 
 except Exception as e:
 logger.error(f"Failed to get cleanup stats: {e}")
 return {"error": str(e)}
 
 async def dispose(self) -> None:
 """Clean up resources and stop the service."""
 await self.stop_cleanup_scheduler()
 logger.info("SessionCleanupService disposed") 