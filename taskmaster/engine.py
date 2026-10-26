"""The step engine: sessions, matrix entries, and how each situation walks the chain.

A session holds the end goal and an ordered plan of matrix entries. Each entry
runs the procedure's steps 0–10 for one situation × scope. The engine only
sequences: it hands out the next step and moves where the agent's reports say.
It does not judge the work.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .library import FIRST_STEP, SCOPES, SITUATIONS, VERIFY_STEP, Library

Situation = Literal["create", "extend", "improve", "fix", "review"]
Scope = Literal["component", "page", "flow", "shared-styles", "product"]

# Situations that inspect the existing work before changing it.
DIAGNOSE_FIRST = {"improve", "fix"}


class EngineError(ValueError):
    """The requested move does not fit the session's current position."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EntryInput(BaseModel):
    situation: Situation = Field(description="create, extend, improve, fix, or review — chosen with the matrix selector questions")
    scope: Scope = Field(description="component, page, flow, shared-styles, or product — the smallest unit containing every decision to change")
    goal: str = Field(description="What this entry must achieve, worked backward from the session's end goal")


class Handoff(BaseModel):
    step: int
    iteration: int
    text: str
    at: str = Field(default_factory=_now)


class Verification(BaseModel):
    iteration: int
    phase: Literal["diagnosis", "verify"]
    outcome: str
    findings: str = ""
    at: str = Field(default_factory=_now)


class Entry(BaseModel):
    situation: Situation
    scope: Scope
    goal: str
    status: Literal["pending", "active", "done"] = "pending"
    phase: Literal["chain", "diagnosis"] = "chain"
    step: int | None = None
    k: int | None = None
    iteration: int = 0
    handoffs: list[Handoff] = Field(default_factory=list)
    verifications: list[Verification] = Field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{SITUATIONS[self.situation]} × {SCOPES[self.scope]}"

    def latest_handoffs(self, before: int) -> dict[int, Handoff]:
        latest: dict[int, Handoff] = {}
        for handoff in self.handoffs:
            if handoff.step < before:
                latest[handoff.step] = handoff
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
    entry.phase = "chain"
    entry.step = FIRST_STEP
    entry.k = None
    entry.iteration = 1


def _finish_entry(session: Session) -> None:
    entry = session.entries[session.current]
    entry.status = "done"
    entry.step = None
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


def complete_step(session: Session, handoff: str = "") -> None:
    entry = _require_entry(session)
    if entry.step == VERIFY_STEP:
        raise EngineError(
            "Step 10 ends with report_verification: outcome 'done', or the number of the step "
            "responsible for a discrepancy."
        )
    if handoff.strip():
        entry.handoffs.append(Handoff(step=entry.step, iteration=entry.iteration, text=handoff.strip()))
    if entry.step == FIRST_STEP and entry.situation in DIAGNOSE_FIRST and entry.k is None:
        entry.phase = "diagnosis"
        entry.step = VERIFY_STEP
    else:
        entry.step += 1
    session.updated = _now()


def report_verification(session: Session, outcome: str, findings: str = "") -> str:
    """Record step 10's result and move. Returns 'done' or 'rerun'."""
    entry = _require_entry(session)
    if entry.step != VERIFY_STEP:
        raise EngineError(
            f"report_verification belongs to step 10; the current step is {entry.step}. "
            "Finish this step with complete_step."
        )
    value = outcome.strip().lower()
    phase = "diagnosis" if entry.phase == "diagnosis" else "verify"
    if value == "done":
        entry.verifications.append(Verification(iteration=entry.iteration, phase=phase, outcome="done", findings=findings.strip()))
        _finish_entry(session)
        session.updated = _now()
        return "done"

    try:
        k = int(value)
    except ValueError:
        raise EngineError("outcome must be 'done' or a step number from 0 to 9.") from None
    if not FIRST_STEP <= k < VERIFY_STEP:
        raise EngineError("A responsible step is a number from 0 to 9; step 10 itself cannot be the cause.")
    if entry.situation == "review":
        raise EngineError(
            "Review stops before implementation. Record each finding with its responsible step and report "
            "outcome 'done'; acting on findings needs the user's authorization and a Fix or Improve entry (add_entries)."
        )

    entry.verifications.append(Verification(iteration=entry.iteration, phase=phase, outcome=str(k), findings=findings.strip()))
    entry.k = k
    entry.phase = "chain"
    entry.step = k
    entry.iteration += 1
    session.updated = _now()
    return "rerun"


def add_entries(session: Session, entries: list[EntryInput], position: Literal["next", "end"] = "next") -> None:
    if not entries:
        raise EngineError("No entries to add.")
    new = [Entry(**e.model_dump()) for e in entries]
    if session.status == "ended":
        raise EngineError(f"Session {session.id} has ended; start a new session.")
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


def end_session(session: Session, summary: str = "") -> None:
    session.status = "ended"
    session.summary = summary.strip()
    for entry in session.entries:
        if entry.status == "active":
            entry.step = None
    session.updated = _now()


def mode_for(library: Library, entry: Entry, step: int) -> str:
    """The decide or keep mark for a step, read from the situation rule and scope limit."""
    if entry.phase == "diagnosis":
        return "diagnose the existing work"
    rule = library.situations[entry.situation].rule_for(step, entry.k)
    first_sentence = rule.split(".")[0].lower()
    if first_sentence.startswith("record"):
        mode = "record"
    elif first_sentence.startswith("keep"):
        mode = "keep"
    elif " only " in f" {first_sentence} " or "otherwise keep" in rule.lower():
        mode = "decide or keep"
    else:
        mode = "decide"
    limit = library.scopes[entry.scope].limits[step].lower()
    if mode.startswith("decide"):
        if limit.startswith("keep"):
            mode = "keep"
        elif "otherwise keep" in limit:
            mode = "decide or keep"
    return mode
