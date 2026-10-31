"""Loads the Taskmaster library: the working method and the design library.

The text files are the authority. This module splits them into the pieces
Taskmaster hands out with each operation; it never rewrites their wording.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace
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

MODIFIERS = ("full", "keep", "produces")
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

_STEP_HEADING = re.compile(r"^(\d{1,2})\. (.+)$")
_SOP_HEADING = re.compile(r"^(\d{1,2})\. (.+?) \[process ([^\]]+)\](?: \((diagnose|trace|verify)\))?$")
_PREAMBLE_SECTIONS = ("Purpose and working method", "The chain", "Running with Taskmaster", "Applying the methods", "Observable execution")
_ENTRY_REF = re.compile(r"^design/([a-z]+)/([a-z-]+)(?:#([a-z0-9._-]+))?$")
_STEP_REF = re.compile(r"^design/process/(\d{1,2})$")


class LibraryError(RuntimeError):
    """The library is missing or malformed."""


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
        """The rules every design operation repeats: decide and keep, and how to announce work."""
        chain = self.sections.get("The chain", "")
        decide_keep = "\n\n".join(b for b in chain.split("\n\n") if b.startswith(("Decide:", "Keep:")))
        return "\n\n".join(p for p in (decide_keep, self.sections.get("Observable execution", "")) if p)


@dataclass(frozen=True)
class SopStep:
    number: int
    id: str
    title: str
    refs: tuple[str, ...]
    modifier: str
    kind: str
    needs: tuple[str, ...]
    produces: str
    instruction: str

    @property
    def steps(self) -> list[int]:
        """The procedure steps this SOP step works in. The responsible step k is named by a trace at run time."""
        found: list[int] = []
        for ref in self.refs:
            if ref in ("k", "k+"):
                continue
            if "–" in ref:
                first, last = (int(x) for x in ref.split("–"))
                found.extend(range(first, last + 1))
            else:
                found.append(int(ref))
        return found

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

    def step(self, step_id: str) -> SopStep | None:
        return next((s for s in self.steps if s.id == step_id), None)


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
    method: str
    procedure: Procedure
    matrix: str
    situations: dict[str, SituationSop] = field(default_factory=dict)
    scopes: dict[str, ScopeSheet] = field(default_factory=dict)

    def composition(self, situation: str, scope: str) -> list[dict]:
        """A matrix entry's ready composition: one operation per SOP step, for compose."""
        return [
            {"id": s.id, "needs": list(s.needs), "does": "", "produces": s.produces, "guide": f"design/{situation}/{scope}#{s.id}"}
            for s in self.situations[situation].steps
        ]

    def read(self, ref: str) -> str | None:
        """The text a library reference names, or None when it names nothing."""
        ref = ref.strip().strip("/")
        if ref == "":
            return INDEX
        if ref == "method":
            return self.method
        if ref == "design":
            return f"{self.matrix}\n\n{DESIGN_INDEX}"
        if ref == "design/process":
            return self.procedure.full_text
        match = _STEP_REF.match(ref)
        if match:
            step = self.procedure.steps.get(int(match.group(1)))
            return step.text if step else None
        match = _ENTRY_REF.match(ref)
        if not match or match.group(1) not in SITUATIONS or match.group(2) not in SCOPES:
            return None
        situation, scope, step_id = match.groups()
        if step_id is None:
            return self._entry(situation, scope)
        step = self.situations[situation].step(step_id)
        return self._guide(situation, scope, step) if step else None

    def _entry(self, situation: str, scope: str) -> str:
        ops = self.composition(situation, scope)
        listing = "[\n" + ",\n".join("  " + json.dumps(op, ensure_ascii=False, separators=(",", ":")) for op in ops) + "\n]"
        return "\n\n".join([
            f"# {SITUATIONS[situation]} × {SCOPES[scope]}",
            f"## Situation SOP: {SITUATIONS[situation]}",
            self.situations[situation].full_text,
            f"## Scope: {SCOPES[scope]}",
            self.scopes[scope].full_text,
            "## Ready composition",
            COMPOSITION_NOTE,
            listing,
        ])

    def _guide(self, situation: str, scope: str, step: SopStep) -> str:
        sop, sheet = self.situations[situation], self.scopes[scope]
        numbers = step.steps
        tag = "" if step.kind == "work" else f" ({step.kind})"
        if step.uses_k:
            where = "the step the trace named" + (", then each later step" if "k+" in step.refs else "")
        else:
            where = ", ".join(f"{n} ({self.procedure.steps[n].name})" for n in numbers)
        parts = [
            f"### {sop.title} × {sheet.title}, SOP step {step.number} of {len(sop.steps)}: {step.title}{tag}",
            f"Works in procedure step: {where}\nMay change: {sop.may_change}\nMust preserve: {sop.must_preserve}",
            "### SOP step",
            step.instruction,
        ]
        scope_lines = [f"Boundary: {sheet.fields.get('Boundary', '')}"]
        scope_lines += [f"{label}: {text}" for label, text in sheet.lines_for(list(range(VERIFY_STEP + 1)) if step.uses_k else numbers)]
        parts += [f"### Scope: {sheet.title}", "\n".join(scope_lines)]
        for n in numbers:
            proc = self.procedure.steps[n]
            if step.modifier == "keep":
                parts += [f"### Procedure step {n}: {proc.name}, Keep rule (library('design/process/{n}') for the full step)", proc.paragraph("Keep:")]
            elif step.modifier == "produces":
                parts += [f"### Procedure step {n}: {proc.name}, what it produces (library('design/process/{n}') for the full step)", proc.paragraph("Produces:")]
            else:
                parts += [f"### Procedure step {n}: {proc.name} (verbatim)", proc.text]
        parts += ["### Working rules", self.procedure.working_rules]
        if step is sop.steps[0]:
            parts += ["### Design working method (process.txt; read it once and keep it as the authority)", self.procedure.preamble]
        if step is sop.steps[-1]:
            parts += ["### Completion", sop.completion]
        return "\n\n".join(p for p in parts if p)


INDEX = """\
Library references, for library(ref) and for an operation's guide:
- method: the working method Taskmaster runs.
- design: the design library's matrix, for choosing a situation and scope.
- design/<situation>/<scope>: that entry's SOP, scope sheet, and ready composition to adopt with compose.
- design/<situation>/<scope>#<id>: one operation's guide in that composition.
- design/process: the whole design procedure; design/process/<n>: one step of it (0–10)."""

DESIGN_INDEX = (
    "Reading the design library\n\n"
    "Choose the situation and the smallest scope with the selector above, then read library('design/<situation>/<scope>') "
    "for that entry's SOP, scope sheet, and ready composition. library('design/process/<n>') returns one procedure step in full.\n\n"
    "Situations: " + ", ".join(SITUATIONS) + "\nScopes: " + ", ".join(SCOPES)
)

COMPOSITION_NOTE = (
    "Adopt this with compose. Write each operation's \"does\" for this assignment: the specific work it will do, the questions "
    "it must answer, and the result that will show it is complete. Make \"produces\" specific where you can. Keep the ids, needs, "
    "and guides unless the task needs a different derivation. For a request that spans several entries, prefix each entry's ids "
    "with its name (pricing.question) and have the first operation of a later entry also need the last operation of the one before."
)


def library_dir() -> Path:
    """Find the library folder: an explicit override, the installed copy, or the repository copy."""
    override = os.environ.get("TASKMASTER_LIBRARY_DIR")
    candidates = [Path(override)] if override else []
    here = Path(__file__).resolve().parent
    candidates += [here / "_library", here.parent / "library"]
    for candidate in candidates:
        if (candidate / "method.txt").is_file():
            return candidate
    searched = ", ".join(str(c) for c in candidates)
    raise LibraryError(f"No library found. Looked for method.txt in: {searched}")


def _read(path: Path) -> str:
    if not path.is_file():
        raise LibraryError(f"Missing library file: {path}")
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


def parse_situation(key: str, text: str, procedure: Procedure) -> SituationSop:
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
            current = {
                "number": int(match.group(1)),
                "id": "",
                "title": match.group(2).strip(),
                "refs": tuple(r.strip() for r in refs_text.split(",") if r.strip()),
                "modifier": modifier,
                "kind": match.group(4) or "work",
                "needs": (),
                "produces": "",
            }
            body = []
        elif current is not None and not body and line.startswith(("Id:", "Needs:", "Produces:")):
            name, _, value = line.partition(":")
            if name == "Id":
                current["id"] = value.strip()
            elif name == "Needs":
                current["needs"] = tuple(n.strip() for n in value.split(",") if n.strip())
            else:
                current["produces"] = value.strip()
        elif current is not None:
            body.append(line)
    close()

    if [s.number for s in steps] != list(range(1, len(steps) + 1)):
        raise LibraryError(f"Situation '{key}' SOP steps must be numbered 1..n in order")
    seen: set[str] = set()
    for i, s in enumerate(steps):
        if not ID_PATTERN.match(s.id) or s.id in seen:
            raise LibraryError(f"Situation '{key}' step {s.number} needs a unique Id")
        if not s.produces:
            # A step that works fully in one procedure step produces what that step produces.
            if s.kind != "work" or s.modifier != "full" or len(s.steps) != 1 or s.uses_k:
                raise LibraryError(f"Situation '{key}' step {s.number} needs a Produces line")
            produces = procedure.steps[s.steps[0]].paragraph("Produces:").removeprefix("Produces:").strip()
            steps[i] = s = replace(s, produces=produces)
        missing = [n for n in s.needs if n not in seen]
        if missing:
            raise LibraryError(f"Situation '{key}' step {s.number} needs {missing}, which are not earlier steps")
        seen.add(s.id)
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
    design = base / "design"
    procedure = parse_procedure(_read(design / "process.txt"))
    situations = {key: parse_situation(key, _read(design / "situations" / f"{key}.txt"), procedure) for key in SITUATIONS}
    scopes = {key: parse_scope(key, _read(design / "scopes" / f"{key}.txt")) for key in SCOPES}
    return Library(
        root=base,
        method=_read(base / "method.txt").strip(),
        procedure=procedure,
        matrix=_read(design / "matrix.txt").strip(),
        situations=situations,
        scopes=scopes,
    )


def load_library(root: Path | None = None) -> Library:
    return _load(str((root or library_dir()).resolve()))
