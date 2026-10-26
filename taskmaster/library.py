"""Loads the design library: the procedure, the matrix, the situation SOPs, and the scope sheets.

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
    "redesign": "Redesign",
    "fix": "Fix",
    "review": "Review",
}

SCOPES: dict[str, str] = {
    "element": "Element",
    "component": "Component",
    "section": "Section",
    "page": "Page or view",
    "flow": "Flow",
    "product": "Product",
    "shared-styles": "Shared styles and assets",
}

FIRST_STEP = 0
VERIFY_STEP = 10

# Which procedure steps each "At this scope" line speaks to.
SCOPE_LABELS: dict[str, tuple[int, ...]] = {
    "Question": (0,),
    "Content and order": (1, 2),
    "Components": (3,),
    "Foundations": (4, 5, 6, 7),
    "Layout": (8,),
    "Behavior": (9,),
    "Verify": (10,),
}

STEP_KINDS = ("work", "diagnose", "trace", "verify")
MODIFIERS = ("full", "keep", "produces")

_STEP_HEADING = re.compile(r"^(\d{1,2})\. (.+)$")
_SOP_HEADING = re.compile(r"^(\d{1,2})\. (.+?) \[process ([^\]]+)\](?: \((diagnose|trace|verify)\))?$")
_PREAMBLE_SECTIONS = ("Purpose and working method", "The chain", "Running with Taskmaster", "Applying the methods", "Observable execution")


class LibraryError(RuntimeError):
    """The design library is missing or malformed."""


@dataclass(frozen=True)
class Step:
    number: int
    name: str
    text: str

    def paragraph(self, prefix: str) -> str:
        for block in self.text.split("\n\n"):
            if block.startswith(prefix):
                return block.strip()
        return ""


@dataclass(frozen=True)
class Procedure:
    preamble: str
    sections: dict[str, str]
    steps: dict[int, Step]
    limits: str
    full_text: str

    @property
    def working_rules(self) -> str:
        """The rules every step message repeats: decide and keep, and how to announce work."""
        chain = self.sections.get("The chain", "")
        decide_keep = "\n\n".join(b for b in chain.split("\n\n") if b.startswith(("Decide:", "Keep:")))
        return "\n\n".join(p for p in (decide_keep, self.sections.get("Observable execution", "")) if p)


@dataclass(frozen=True)
class SopStep:
    number: int
    title: str
    refs: tuple[str, ...]
    modifier: str
    kind: str
    instruction: str

    def resolve(self, k: int | None) -> list[int]:
        steps: list[int] = []
        for ref in self.refs:
            if ref == "k":
                if k is not None:
                    steps.append(k)
            elif ref == "k+":
                if k is not None:
                    steps.extend(range(k + 1, VERIFY_STEP))
            elif "–" in ref:
                first, last = (int(x) for x in ref.split("–"))
                steps.extend(range(first, last + 1))
            else:
                steps.append(int(ref))
        return steps

    @property
    def uses_k(self) -> bool:
        return any(ref in ("k", "k+") for ref in self.refs)


@dataclass(frozen=True)
class SituationSop:
    key: str
    title: str
    brief: str
    may_change: str
    must_preserve: str
    steps: tuple[SopStep, ...]
    completion: str
    full_text: str


@dataclass(frozen=True)
class ScopeSheet:
    key: str
    title: str
    brief: str
    fields: dict[str, str]
    at_scope: dict[str, str]
    expansion: str
    full_text: str

    def lines_for(self, steps: list[int]) -> list[tuple[str, str]]:
        wanted = set(steps)
        return [(label, text) for label, text in self.at_scope.items() if wanted & set(SCOPE_LABELS[label])]


@dataclass(frozen=True)
class Library:
    root: Path
    procedure: Procedure
    matrix: str
    situations: dict[str, SituationSop] = field(default_factory=dict)
    scopes: dict[str, ScopeSheet] = field(default_factory=dict)


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


def _split_sections(text: str, names: tuple[str, ...]) -> dict[str, str]:
    found: dict[str, list[str]] = {"": []}
    current = ""
    for line in text.split("\n"):
        if line.strip() in names:
            current = line.strip()
            found[current] = []
            continue
        found[current].append(line)
    return {key: "\n".join(value).strip() for key, value in found.items()}


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
        steps[number] = Step(number=number, name=name, text="\n".join(lines[line_no:end]).strip())

    preamble = "\n".join(lines[: starts[0][0]]).strip()
    return Procedure(
        preamble=preamble,
        sections=_split_sections(preamble, _PREAMBLE_SECTIONS),
        steps=steps,
        limits="\n".join(lines[limits_at:]).strip(),
        full_text=text.strip(),
    )


def _field(text: str, prefix: str) -> str:
    for line in text.split("\n"):
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def parse_situation(key: str, text: str) -> SituationSop:
    head, _, rest = text.partition("\nSOP\n")
    if not rest:
        raise LibraryError(f"Situation '{key}' has no SOP section")
    blocks = [b.strip() for b in head.split("\n\n") if b.strip()]
    brief = "\n\n".join(b for b in blocks[1:] if not b.startswith(("May change:", "Must preserve:")))
    sop_text, _, completion = rest.partition("\nCompletion:")

    steps: list[SopStep] = []
    current: dict | None = None
    body: list[str] = []

    def close() -> None:
        if current is not None:
            steps.append(SopStep(instruction="\n".join(body).strip(), **current))

    for line in sop_text.split("\n"):
        match = _SOP_HEADING.match(line.strip())
        if match:
            close()
            refs_text, _, modifier = match.group(3).partition(":")
            modifier = modifier.strip() or "full"
            if modifier not in MODIFIERS:
                raise LibraryError(f"Situation '{key}' step {match.group(1)} has unknown modifier '{modifier}'")
            refs = tuple(r.strip() for r in refs_text.split(",") if r.strip())
            current = {
                "number": int(match.group(1)),
                "title": match.group(2).strip(),
                "refs": refs,
                "modifier": modifier,
                "kind": match.group(4) or "work",
            }
            body = []
        elif current is not None:
            body.append(line)
    close()

    if [s.number for s in steps] != list(range(1, len(steps) + 1)):
        raise LibraryError(f"Situation '{key}' SOP steps must be numbered 1..n in order")
    if not any(s.kind == "verify" for s in steps):
        raise LibraryError(f"Situation '{key}' needs a verify step")
    if any(s.uses_k for s in steps) and not any(s.kind == "trace" for s in steps):
        raise LibraryError(f"Situation '{key}' refers to the responsible step k without a trace step")

    return SituationSop(
        key=key,
        title=SITUATIONS[key],
        brief=brief,
        may_change=_field(head, "May change:"),
        must_preserve=_field(head, "Must preserve:"),
        steps=tuple(steps),
        completion=completion.strip(),
        full_text=text.strip(),
    )


def parse_scope(key: str, text: str) -> ScopeSheet:
    head, _, rest = text.partition("\nAt this scope\n")
    if not rest:
        raise LibraryError(f"Scope '{key}' has no 'At this scope' section")
    blocks = [b.strip() for b in head.split("\n\n") if b.strip()]
    field_block = next((b for b in blocks if b.startswith("Parent:")), "")
    brief = "\n\n".join(b for b in blocks[1:] if b is not field_block)
    fields = {}
    for line in field_block.split("\n"):
        name, sep, value = line.partition(":")
        if sep:
            fields[name.strip()] = value.strip()

    at_text, _, expansion = rest.partition("\nExpansion:")
    at_scope: dict[str, str] = {}
    for line in at_text.split("\n"):
        name, sep, value = line.partition(":")
        if sep and name.strip() in SCOPE_LABELS:
            at_scope[name.strip()] = value.strip()
    missing = [label for label in SCOPE_LABELS if label not in at_scope]
    if missing:
        raise LibraryError(f"Scope '{key}' is missing 'At this scope' lines: {missing}")
    return ScopeSheet(
        key=key,
        title=SCOPES[key],
        brief=brief,
        fields=fields,
        at_scope=at_scope,
        expansion=expansion.strip(),
        full_text=text.strip(),
    )


@lru_cache(maxsize=4)
def _load(root: str) -> Library:
    base = Path(root)
    procedure = parse_procedure(_read(base / "process.txt"))
    matrix = _read(base / "matrix.txt").strip()
    situations = {key: parse_situation(key, _read(base / "prompts" / "situations" / f"{key}.txt")) for key in SITUATIONS}
    scopes = {key: parse_scope(key, _read(base / "prompts" / "scopes" / f"{key}.txt")) for key in SCOPES}
    return Library(root=base, procedure=procedure, matrix=matrix, situations=situations, scopes=scopes)


def load_library(root: Path | None = None) -> Library:
    return _load(str((root or design_dir()).resolve()))
