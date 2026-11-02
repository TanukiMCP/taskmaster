"""Loads the library texts: the procedure, the method, and the design guidance.

The text files are the authority. This module only finds them and hands out the
pieces a step needs; it never rewrites their wording.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Each aspect a point can name, and the design procedure step that guides it.
ASPECTS: dict[str, int] = {
    "question": 0,
    "content": 1,
    "order": 2,
    "components": 3,
    "research": 4,
    "typography": 5,
    "imagery": 6,
    "color": 7,
    "layout": 8,
    "behavior": 9,
    "verify": 10,
}

_STEP_HEADING = re.compile(r"^(\d{1,2})\. (.+)$")


class LibraryError(RuntimeError):
    """The library is missing or malformed."""


@dataclass(frozen=True)
class Library:
    root: Path
    procedure: str
    method: str
    design: str
    design_steps: dict[int, str]

    def guidance(self, aspect: str) -> str:
        """The design procedure step for an aspect, verbatim, or '' for no aspect."""
        return self.design_steps[ASPECTS[aspect]] if aspect in ASPECTS else ""

    def read(self, ref: str) -> str | None:
        ref = ref.strip().strip("/")
        if ref == "":
            return INDEX
        if ref == "procedure":
            return self.procedure
        if ref == "method":
            return self.method
        if ref == "design":
            return self.design
        if ref.startswith("design/") and ref.removeprefix("design/") in ASPECTS:
            return self.guidance(ref.removeprefix("design/"))
        return None


INDEX = (
    "Library references:\n"
    "- procedure: how CoherenceMCP works and how every point is answered.\n"
    "- method: the dependency-ordered composition the procedure carries out.\n"
    "- design: the design procedure for interfaces, steps 0 to 10.\n"
    "- design/<aspect>: one step of it. Aspects: " + ", ".join(ASPECTS)
)


def library_dir() -> Path:
    """Find the library: an explicit override, the installed copy, or the repository copy."""
    override = os.environ.get("COHERENCE_LIBRARY_DIR")
    candidates = [Path(override)] if override else []
    here = Path(__file__).resolve().parent
    candidates += [here / "_library", here.parent / "library"]
    for candidate in candidates:
        if (candidate / "procedure.txt").is_file():
            return candidate
    raise LibraryError("No library found. Looked for procedure.txt in: " + ", ".join(str(c) for c in candidates))


def _read(path: Path) -> str:
    if not path.is_file():
        raise LibraryError(f"Missing library file: {path}")
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()


def parse_steps(text: str) -> dict[int, str]:
    """Split the design procedure into steps 0 to 10, each ending where the next begins."""
    lines = text.split("\n")
    starts: list[tuple[int, int]] = []
    end = len(lines)
    for i, line in enumerate(lines):
        match = _STEP_HEADING.match(line)
        if match and int(match.group(1)) == len(starts):
            starts.append((i, len(starts)))
        elif line.strip() == "Remaining limits" and starts:
            end = i
    if [n for _, n in starts] != list(range(11)):
        raise LibraryError("design/process.txt must contain step headings 0. through 10. in order")
    steps = {}
    for index, (line_no, number) in enumerate(starts):
        stop = starts[index + 1][0] if index + 1 < len(starts) else end
        steps[number] = "\n".join(lines[line_no:stop]).strip()
    return steps


@lru_cache(maxsize=4)
def _load(root: str) -> Library:
    base = Path(root)
    design = _read(base / "design" / "process.txt")
    return Library(
        root=base,
        procedure=_read(base / "procedure.txt"),
        method=_read(base / "method.txt"),
        design=design,
        design_steps=parse_steps(design),
    )


def load_library(root: Path | None = None) -> Library:
    return _load(str((root or library_dir()).resolve()))
