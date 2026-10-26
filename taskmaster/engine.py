"""The step engine: sessions, matrix entries, plans, and SOP steps.

A session holds the end goal and an ordered list of matrix entries. Each entry
follows its situation's SOP: the agent first writes a plan with one item per
SOP step, then Taskmaster issues the steps in order. The engine only sequences;
it never judges the work.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .library import FIRST_STEP, SCOPES, SITUATIONS, VERIFY_STEP, Library, SopStep

Situation = Literal["create", "extend", "redesign", "fix", "review"]
Scope = Literal["element", "component", "section", "page", "flow", "product", "shared-styles"]


class EngineError(ValueError):
    """The requested move does not fit the session's current position."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EntryInput(BaseModel):
    situation: Situation = Field(description="create, extend, redesign, fix, or review — chosen with the matrix selector questions")
    scope: Scope = Field(description="element, component, section, page, flow, product, or shared-styles — the smallest unit containing every decision to change")
    goal: str = Field(description="What this entry must achieve, worked backward from the session's end goal")


class Handoff(BaseModel):
    sop_step: int
    iteration: int
    text: str
    at: str = Field(default_factory=_now)


class Verification(BaseModel):
    sop_step: int
    iteration: int
    outcome: str
    findings: str = ""
    at: str = Field(default_factory=_now)


class Entry(BaseModel):
    situation: Situation
    scope: Scope
    goal: str
    status: Literal["pending", "active", "done", "escalated"] = "pending"
    phase: Literal["plan", "run"] = "plan"
    index: int = 0
    k: int | None = None
    resume_at: int | None = None
    iteration: int = 0
    plan: list[str] = Field(default_factory=list)
    plan_revisions: int = 0
    handoffs: list[Handoff] = Field(default_factory=list)
    verifications: list[Verification] = Field(default_factory=list)
    note: str = ""

    @property
    def label(self) -> str:
        return f"{SITUATIONS[self.situation]} × {SCOPES[self.scope]}"

    def latest_handoffs(self) -> dict[int, Handoff]:
        latest: dict[int, Handoff] = {}
        for handoff in self.handoffs:
            latest[handoff.sop_step] = handoff
        return dict(sorted(latest.items()))


class Session(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    created: str = Field(default_factory=_now)
    updated: str = Field(default_factory=_now)
    request: str
    end_goal: str
    conditions: str = ""
    entries: list[Entry]
    current: int = 0
    status: Literal["active", "complete", "ended"] = "active"
    summary: str = ""

    @property
    def entry(self) -> Entry | None:
        if self.status != "active" or not (0 <= self.current < len(self.entries)):
            return None
        return self.entries[self.current]


def sop_steps(library: Library, entry: Entry) -> tuple[SopStep, ...]:
    return library.situations[entry.situation].steps


def current_sop_step(library: Library, entry: Entry) -> SopStep:
    return sop_steps(library, entry)[entry.index]


def new_session(request: str, end_goal: str, entries: list[EntryInput], conditions: str = "") -> Session:
    if not entries:
        raise EngineError("A session needs at least one matrix entry. Use get_matrix to choose situation and scope.")
    session = Session(
        request=request.strip(),
        end_goal=end_goal.strip(),
        conditions=conditions.strip(),
        entries=[Entry(**e.model_dump()) for e in entries],
    )
    _activate(session, 0)
    return session


def _activate(session: Session, index: int) -> None:
    session.current = index
    entry = session.entries[index]
    entry.status = "active"
    entry.phase = "plan"
    entry.index = 0
    entry.k = None
    entry.resume_at = None
    entry.iteration = 1
    entry.plan = []


def _finish_entry(session: Session) -> None:
    entry = session.entries[session.current]
    if entry.status == "active":
        entry.status = "done"
    following = [i for i, e in enumerate(session.entries) if e.status == "pending"]
    if following:
        _activate(session, following[0])
    else:
        session.status = "complete"


def _require_entry(session: Session) -> Entry:
    entry = session.entry
    if entry is None:
        raise EngineError(f"Session {session.id} is {session.status}; there is no current step.")
    return entry


def _require_running(library: Library, session: Session) -> tuple[Entry, SopStep]:
    entry = _require_entry(session)
    if entry.phase == "plan":
        count = len(sop_steps(library, entry))
        raise EngineError(f"Write the plan first: call submit_plan with {count} items, one per SOP step of {entry.label}.")
    return entry, current_sop_step(library, entry)


def submit_plan(library: Library, session: Session, plan: list[str]) -> bool:
    """Record the plan for the current entry. Returns True when this starts the entry's work."""
    entry = _require_entry(session)
    steps = sop_steps(library, entry)
    items = [item.strip() for item in plan]
    if len(items) != len(steps) or not all(items):
        titles = "; ".join(f"{s.number}. {s.title}" for s in steps)
        raise EngineError(
            f"The plan needs exactly {len(steps)} non-empty items, one per SOP step in order ({titles}). "
            f"Received {len(items)}."
        )
    starting = entry.phase == "plan"
    entry.plan = items
    if starting:
        entry.phase = "run"
        entry.index = 0
    else:
        entry.plan_revisions += 1
    session.updated = _now()
    return starting


def _advance(session: Session, library: Library, entry: Entry) -> None:
    entry.resume_at = None
    if entry.index + 1 < len(sop_steps(library, entry)):
        entry.index += 1
    else:
        _finish_entry(session)


def complete_step(library: Library, session: Session, handoff: str = "", responsible_step: int | None = None) -> None:
    entry, step = _require_running(library, session)
    if step.kind == "verify":
        raise EngineError(
            "This is a verify step. Finish it with report_verification: outcome 'done', or the number of the "
            "procedure step responsible for a discrepancy."
        )
    if step.kind == "trace":
        if responsible_step is None or not FIRST_STEP <= responsible_step < VERIFY_STEP:
            raise EngineError("This trace step needs responsible_step: the procedure step (0–9) where the cause lies.")
        entry.k = responsible_step
    if handoff.strip():
        entry.handoffs.append(Handoff(sop_step=step.number, iteration=entry.iteration, text=handoff.strip()))
    _advance(session, library, entry)
    session.updated = _now()


def _return_target(library: Library, entry: Entry, k: int) -> int:
    """The index of the first working SOP step that works in procedure step k."""
    steps = sop_steps(library, entry)
    for index, step in enumerate(steps):
        if step.kind == "work" and k in step.resolve(entry.k):
            return index
    for index, step in enumerate(steps):
        if step.kind == "work":
            return index
    return 0


def report_verification(library: Library, session: Session, outcome: str, findings: str = "") -> str:
    """Record a verify step's result and move. Returns 'done' or 'rerun'."""
    entry, step = _require_running(library, session)
    if step.kind != "verify":
        raise EngineError(
            f"report_verification belongs to a verify step; SOP step {step.number} ({step.title}) finishes with complete_step."
        )
    value = outcome.strip().lower()
    if value == "done":
        entry.verifications.append(Verification(sop_step=step.number, iteration=entry.iteration, outcome="done", findings=findings.strip()))
        _advance(session, library, entry)
        session.updated = _now()
        return "done"

    try:
        k = int(value)
    except ValueError:
        raise EngineError("outcome must be 'done' or a procedure step number from 0 to 9.") from None
    if not FIRST_STEP <= k < VERIFY_STEP:
        raise EngineError("A responsible step is a procedure step number from 0 to 9; step 10 itself cannot be the cause.")
    if entry.situation == "review":
        raise EngineError(
            "Review stops before implementation. Record each finding with its responsible step and report outcome 'done'; "
            "acting on findings needs the user's authorization and a Fix or Redesign entry (add_entries)."
        )
    entry.verifications.append(Verification(sop_step=step.number, iteration=entry.iteration, outcome=str(k), findings=findings.strip()))
    if any(s.uses_k for s in sop_steps(library, entry)):
        entry.k = k
    entry.index = _return_target(library, entry, k)
    entry.resume_at = k
    entry.iteration += 1
    session.updated = _now()
    return "rerun"


def add_entries(session: Session, entries: list[EntryInput], position: Literal["next", "end"] = "next") -> None:
    if not entries:
        raise EngineError("No entries to add.")
    if session.status == "ended":
        raise EngineError(f"Session {session.id} has ended; start a new session.")
    new = [Entry(**e.model_dump()) for e in entries]
    if session.status == "complete":
        session.entries.extend(new)
        session.status = "active"
        _activate(session, len(session.entries) - len(new))
    elif position == "end":
        session.entries.extend(new)
    else:
        at = session.current + 1
        session.entries[at:at] = new
    session.updated = _now()


def escalate(session: Session, reason: str, to_scope: Scope | None = None, to_situation: Situation | None = None) -> Entry:
    """End the current entry and start one for the parent scope or the right situation in its place."""
    entry = _require_entry(session)
    if to_scope is None and to_situation is None:
        raise EngineError("Escalate to a scope, a situation, or both.")
    if not reason.strip():
        raise EngineError("Say why the decision belongs elsewhere.")
    replacement = Entry(
        situation=to_situation or entry.situation,
        scope=to_scope or entry.scope,
        goal=entry.goal,
        note=f"Escalated from {entry.label}: {reason.strip()}",
    )
    entry.status = "escalated"
    entry.note = f"Escalated to {replacement.label}: {reason.strip()}"
    at = session.current + 1
    session.entries.insert(at, replacement)
    _activate(session, at)
    session.updated = _now()
    return replacement


def end_session(session: Session, summary: str = "") -> None:
    session.status = "ended"
    session.summary = summary.strip()
    session.updated = _now()
