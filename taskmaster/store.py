"""Session storage: one JSON file per session, addressed by its session_id."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .engine import Session


def state_dir() -> Path:
    """TASKMASTER_STATE_DIR, or .taskmaster in the folder the server was started from."""
    override = os.environ.get("TASKMASTER_STATE_DIR")
    return Path(override) if override else Path.cwd() / ".taskmaster"


class Store:
    def __init__(self, root: Path | None = None):
        self.root = root or state_dir()
        self.sessions = self.root / "sessions"

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def save(self, session: Session) -> None:
        self._write(self.sessions / f"{session.id}.json", session.model_dump_json(indent=2))

    def load(self, session_id: str) -> Session | None:
        path = self.sessions / f"{session_id}.json"
        if not path.is_file():
            return None
        return Session.model_validate_json(path.read_text(encoding="utf-8"))

    def recent(self, limit: int = 10) -> list[Session]:
        if not self.sessions.is_dir():
            return []
        files = sorted(self.sessions.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        found = []
        for path in files[:limit]:
            try:
                found.append(Session.model_validate_json(path.read_text(encoding="utf-8")))
            except ValueError:
                continue
        return found
