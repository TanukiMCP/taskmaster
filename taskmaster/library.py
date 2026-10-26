"""Loads the design library: the procedure, the matrix, and the situation and scope prompts.

The text files are the authority. This module only splits them into the pieces
Taskmaster hands out one step at a time; it never rewrites their wording.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

SITUATIONS: dict[str, str] = {
    "create": "Create",
    "extend": "Extend",
    "improve": "Improve",
    "fix": "Fix",
    "review": "Review",
}

SCOPES: dict[str, str] = {
    "component": "Component",
    "page": "Page or view",
    "flow": "Flow",
    "shared-styles": "Shared styles and assets",
    "product": "Product",
}

FIRST_STEP = 0
VERIFY_STEP = 10

_STEP_HEADING = re.compile(r"^(\d{1,2})\. (.+)$")
_NUMBERED_RULE = re.compile(r"^(\d{1,2})(?:–(\d{1,2}))?(?: [A-Za-z][A-Za-z ]*)?: (.+)$")


class LibraryError(RuntimeError):
    """The design library is missing or malformed."""


@dataclass(frozen=True)
class Step:
    number: int
    name: str
    text: str


@dataclass(frozen=True)
class Procedure:
    preamble: str
    steps: dict[int, Step]
    limits: str
    full_text: str


@dataclass(frozen=True)
class SituationPrompt:
    key: str
    title: str
    header: str
    diagnosis: str
    rules: dict[int, str]
    before_k: str
    at_k: str
    after_k: str
    completion: str
    full_text: str

    def rule_for(self, step: int, k: int | None) -> str:
        if k is not None and self.at_k:
            if step < k:
                return self.before_k
            if step == k:
                return self.at_k
            if step != VERIFY_STEP:
                return self.after_k
        return self.rules.get(step, "")


@dataclass(frozen=True)
class ScopePrompt:
    key: str
    title: str
    header: str
    limits: dict[int, str]
    expansion: str
    full_text: str


@dataclass(frozen=True)
class Library:
    root: Path
    procedure: Procedure
    matrix: str
    situations: dict[str, SituationPrompt] = field(default_factory=dict)
    scopes: dict[str, ScopePrompt] = field(default_factory=dict)


def design_dir() -> Path:
    """Find the design folder: an explicit override, the installed copy, or the repository copy."""
    override = os.environ.get("TASKMASTER_DESIGN_DIR")
    candidates = [Path(override)] if override else []
    here = Path(__file__).resolve().parent
    candidates += [here / "design", here.parent / "design"]
    for candidate in candidates:
        if (candidate / "process.txt").is_file():
            return candidate
    searched = ", ".join(str(c) for c in candidates)
    raise LibraryError(f"No design library found. Looked for process.txt in: {searched}")


def _read(path: Path) -> str:
    if not path.is_file():
        raise LibraryError(f"Missing design file: {path}")
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def parse_procedure(text: str) -> Procedure:
    lines = text.split("\n")
    starts: list[tuple[int, int, str]] = []
    limits_at = len(lines)
    for i, line in enumerate(lines):
        match = _STEP_HEADING.match(line)
        if match and int(match.group(1)) == len(starts):
            starts.append((i, int(match.group(1)), match.group(2).strip()))
        elif line.strip() == "Remaining limits" and starts:
            limits_at = i
    if [n for _, n, _ in starts] != list(range(FIRST_STEP, VERIFY_STEP + 1)):
        raise LibraryError("process.txt must contain step headings 0. through 10. in order")

    steps: dict[int, Step] = {}
    for index, (line_no, number, name) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else limits_at
        body = "\n".join(lines[line_no:end]).strip()
        steps[number] = Step(number=number, name=name, text=body)

    preamble = "\n".join(lines[: starts[0][0]]).strip()
    limits = "\n".join(lines[limits_at:]).strip()
    return Procedure(preamble=preamble, steps=steps, limits=limits, full_text=text.strip())


def _sections(text: str, names: tuple[str, ...]) -> dict[str, str]:
    """Split a prompt into its header and the named sections that follow it."""
    lines = text.split("\n")
    found: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in lines:
        if line.strip() in names:
            current = line.strip()
            found[current] = []
            continue
        found[current].append(line)
    return {key: "\n".join(value).strip() for key, value in found.items()}


def _pull_line(text: str, prefix: str) -> tuple[str, str]:
    """Remove the first line starting with prefix and return (line, remaining text)."""
    kept, pulled = [], ""
    for line in text.split("\n"):
        if not pulled and line.startswith(prefix):
            pulled = line[len(prefix):].strip()
            continue
        kept.append(line)
    return pulled, "\n".join(kept).strip()


def parse_situation(key: str, text: str) -> SituationPrompt:
    parts = _sections(text, ("Diagnosis", "Step rules"))
    rules_text = parts.get("Step rules", "")
    completion, rules_text = _pull_line(rules_text, "Completion:")

    rules: dict[int, str] = {}
    before_k = at_k = after_k = ""
    for line in rules_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("Steps before k:"):
            before_k = line.split(":", 1)[1].strip()
        elif line.startswith("Step k and every later step:"):
            at_k = after_k = line.split(":", 1)[1].strip()
        elif line.startswith("Step k:"):
            at_k = line.split(":", 1)[1].strip()
        elif line.startswith("Steps after k:"):
            after_k = line.split(":", 1)[1].strip()
        else:
            match = _NUMBERED_RULE.match(line)
            if not match:
                raise LibraryError(f"Unreadable step rule in situation '{key}': {line}")
            first = int(match.group(1))
            last = int(match.group(2) or first)
            for step in range(first, last + 1):
                rules[step] = match.group(3).strip()

    if not at_k:
        missing = [s for s in range(FIRST_STEP, VERIFY_STEP + 1) if s not in rules]
        if missing:
            raise LibraryError(f"Situation '{key}' has no rule for steps {missing}")
    elif FIRST_STEP not in rules or VERIFY_STEP not in rules:
        raise LibraryError(f"Situation '{key}' needs rules for steps 0 and 10")

    return SituationPrompt(
        key=key,
        title=SITUATIONS[key],
        header=parts["header"],
        diagnosis=parts.get("Diagnosis", ""),
        rules=rules,
        before_k=before_k,
        at_k=at_k,
        after_k=after_k,
        completion=completion,
        full_text=text.strip(),
    )


def parse_scope(key: str, text: str) -> ScopePrompt:
    parts = _sections(text, ("Step limits",))
    limits_text = parts.get("Step limits", "")
    expansion, limits_text = _pull_line(limits_text, "Expansion:")
    limits: dict[int, str] = {}
    notes: list[str] = []
    for line in limits_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = _NUMBERED_RULE.match(line)
        if match:
            limits[int(match.group(1))] = match.group(3).strip()
        else:
            # A paragraph after the numbered limits applies to the whole scope.
            notes.append(line)
    missing = [s for s in range(FIRST_STEP, VERIFY_STEP + 1) if s not in limits]
    if missing:
        raise LibraryError(f"Scope '{key}' has no limit for steps {missing}")
    return ScopePrompt(
        key=key,
        title=SCOPES[key],
        header="\n\n".join([parts["header"], *notes]).strip(),
        limits=limits,
        expansion=expansion,
        full_text=text.strip(),
    )


@lru_cache(maxsize=4)
def _load(root: str) -> Library:
    base = Path(root)
    procedure = parse_procedure(_read(base / "process.txt"))
    matrix = _read(base / "matrix.txt").strip()
    situations = {
        key: parse_situation(key, _read(base / "prompts" / "situations" / f"{key}.txt"))
        for key in SITUATIONS
    }
    scopes = {
        key: parse_scope(key, _read(base / "prompts" / "scopes" / f"{key}.txt"))
        for key in SCOPES
    }
    return Library(root=base, procedure=procedure, matrix=matrix, situations=situations, scopes=scopes)


def load_library(root: Path | None = None) -> Library:
    return _load(str((root or design_dir()).resolve()))
