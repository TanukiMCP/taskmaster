"""The composition engine: operations, what each one needs, and whether its output is current.

A session holds what the task starts from, the result it must produce, and the value
that makes that result worth having. The agent derives the operations. The engine
keeps their outputs, refuses work whose inputs are missing or stale, and marks
everything built on a revised output as stale. It never judges the work itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .library import ID_PATTERN


class EngineError(ValueError):
    """The requested move does not fit the session's current state."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _names(ids: list[str]) -> str:
    return ", ".join(f"'{i}'" for i in ids)


class OperationInput(BaseModel):
    id: str = Field(description="Short lowercase name, unique in the session, such as 'question' or 'pricing.layout'")
    needs: list[str] | None = Field(
        default=None, description="Ids of the operations whose outputs this one consumes; each must be listed before it"
    )
    does: str = Field(default="", description="What this operation does for this task: the specific work and the questions it must answer")
    produces: str = Field(default="", description="The concrete output it produces for the operations that need it")
    guide: str = Field(default="", description="Optional library reference whose text comes with the operation, such as design/redesign/page#research")


class Note(BaseModel):
    text: str
    at: str = Field(default_factory=_now)


class Result(BaseModel):
    version: int
    output: str
    preserves: str
    assumptions: list[str] = Field(default_factory=list)
    evidence: str = ""
    inputs: dict[str, int] = Field(default_factory=dict)  # each needed operation's version this result was built on
    purpose: int = 1  # the session's purpose version this result was built for
    at: str = Field(default_factory=_now)


class Operation(BaseModel):
    id: str
    needs: list[str] = Field(default_factory=list)
    does: str
    produces: str
    guide: str = ""
    open: bool = True
    results: list[Result] = Field(default_factory=list)
    notes: list[Note] = Field(default_factory=list)

    @property
    def result(self) -> Result | None:
        return self.results[-1] if self.results else None

    @property
    def version(self) -> int:
        return self.results[-1].version if self.results else 0


class Session(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    created: str = Field(default_factory=_now)
    updated: str = Field(default_factory=_now)
    request: str
    result: str
    value: str
    starting: str = ""
    purpose: int = 1
    operations: list[Operation] = Field(default_factory=list)
    retired: list[Operation] = Field(default_factory=list)
    log: list[Note] = Field(default_factory=list)
    status: Literal["active", "finished"] = "active"
    delivered: str = ""
    evidence: str = ""
    limitations: str = ""

    def operation(self, op_id: str) -> Operation:
        for op in self.operations:
            if op.id == op_id.strip():
                return op
        known = ", ".join(op.id for op in self.operations) or "none yet; call compose"
        raise EngineError(f"No operation '{op_id}' in this session. Operations: {known}.")

    def touch(self) -> None:
        self.updated = _now()


State = Literal["current", "stale", "open"]


def states(session: Session) -> dict[str, State]:
    """Each operation's state. Current: recorded on inputs that are themselves current and unchanged.
    Stale: recorded, but something it was built on has changed. Open: not recorded, or reopened."""
    versions = {op.id: op.version for op in session.operations}
    state: dict[str, State] = {}
    for op in session.operations:  # every operation comes after what it needs
        latest = op.result
        if op.open or latest is None:
            state[op.id] = "open"
        elif latest.purpose == session.purpose and all(
            state[n] == "current" and latest.inputs.get(n) == versions[n] for n in op.needs
        ):
            state[op.id] = "current"
        else:
            state[op.id] = "stale"
    return state


def ready(session: Session, state: dict[str, State] | None = None) -> list[Operation]:
    """Operations that are not current and whose needs all are, in composition order."""
    state = state or states(session)
    return [op for op in session.operations if state[op.id] != "current" and all(state[n] == "current" for n in op.needs)]


def upstream(session: Session, op_id: str) -> list[Operation]:
    """Everything an operation builds on, directly or through other operations, in composition order."""
    ops = {op.id: op for op in session.operations}
    found: set[str] = set()
    pending = list(ops[op_id].needs)
    while pending:
        n = pending.pop()
        if n not in found:
            found.add(n)
            pending.extend(ops[n].needs)
    return [op for op in session.operations if op.id in found]


def downstream(session: Session, op_id: str) -> list[Operation]:
    """Everything built on an operation, directly or through other operations, in composition order."""
    found = {op_id}
    built_on: list[Operation] = []
    for op in session.operations:
        if any(n in found for n in op.needs):
            found.add(op.id)
            built_on.append(op)
    return built_on


def changed_inputs(session: Session, op: Operation) -> list[str]:
    """Why a stale operation is stale."""
    latest = op.result
    if latest is None:
        return []
    state = states(session)
    reasons = []
    if latest.purpose != session.purpose:
        reasons.append("the value or the requested result changed")
    for n in op.needs:
        dep = session.operation(n)
        was = latest.inputs.get(n, 0)
        if was != dep.version:
            reasons.append(f"'{n}' changed (v{was} → v{dep.version})")
        elif state[n] != "current":
            reasons.append(f"'{n}' is {state[n]}")
    return reasons


def new_session(request: str, result: str, value: str, starting: str = "") -> Session:
    for name, text in (("request", request), ("result", result), ("value", value)):
        if not text.strip():
            raise EngineError(f"start needs {name}.")
    return Session(request=request.strip(), result=result.strip(), value=value.strip(), starting=starting.strip())


def compose(session: Session, items: list[OperationInput], reason: str = "") -> tuple[list[str], list[str]]:
    """Set or revise the operations. Returns the ids reopened by the revision and any warnings.

    An item with only an id keeps that existing operation as it is. A recorded operation
    whose needs or output change is reopened; one that is left out is retired.
    """
    if not items:
        raise EngineError("A composition needs at least one operation.")
    existing = {op.id: op for op in session.operations}
    if existing and not reason.strip():
        raise EngineError("This session already has a composition. Say why it changes: reason.")

    listed = {item.id.strip() for item in items}
    placed: dict[str, Operation] = {}
    reopened: list[str] = []
    for item in items:
        op_id = item.id.strip()
        if not ID_PATTERN.match(op_id):
            raise EngineError(f"'{item.id}' is not a usable id: use lowercase letters, digits, '.', '-', and '_'.")
        if op_id in placed:
            raise EngineError(f"'{op_id}' appears twice.")
        old = existing.get(op_id)
        if item.needs is None and not (item.does.strip() or item.produces.strip() or item.guide.strip()):
            if old is None:
                raise EngineError(f"'{op_id}' is new, so it needs does and produces.")
            op = old.model_copy(deep=True)
        else:
            needs = [n.strip() for n in item.needs or []]
            does, produces = item.does.strip(), item.produces.strip()
            if not does:
                raise EngineError(f"'{op_id}' needs does: the specific work it does for this task and the questions it must answer.")
            if not produces:
                raise EngineError(f"'{op_id}' needs produces: the concrete output the operations after it use.")
            if len(set(needs)) != len(needs):
                raise EngineError(f"'{op_id}' lists the same need twice.")
            if old is None:
                op = Operation(id=op_id, needs=needs, does=does, produces=produces, guide=item.guide.strip())
            else:
                op = old.model_copy(deep=True)
                if op.results and not op.open and (set(needs) != set(op.needs) or produces != op.produces):
                    op.open = True
                    op.notes.append(Note(text=f"Reopened by recomposition: {reason.strip()}"))
                    reopened.append(op_id)
                op.needs, op.does, op.produces, op.guide = needs, does, produces, item.guide.strip()
        for n in op.needs:
            if n == op_id:
                raise EngineError(f"'{op_id}' can't need itself.")
            if n not in placed:
                where = "is listed after it" if n in listed else "is not in the composition"
                raise EngineError(f"'{op_id}' needs '{n}', which {where}. List every operation after the operations it needs.")
        placed[op_id] = op

    for op_id, op in existing.items():
        if op_id not in placed:
            op.notes.append(Note(text=f"Removed from the composition: {reason.strip()}"))
            session.retired.append(op)
    session.operations = list(placed.values())
    session.log.append(Note(text=f"Recomposed: {reason.strip()}" if existing else f"Composed {len(placed)} operations"))
    if session.status == "finished":
        session.status = "active"
    session.touch()

    used = {n for op in session.operations for n in op.needs}
    loose = [op.id for op in session.operations[:-1] if op.id not in used]
    warnings = []
    if loose:
        warnings.append(
            f"Nothing needs the output of {_names(loose)}. Every operation should feed later work or be the requested result; "
            "connect it or drop it."
        )
    return reopened, warnings


def _require_active(session: Session) -> None:
    if session.status == "finished":
        raise EngineError(f"Session {session.id} is finished. Call compose with a reason to reopen it, or start a new session.")
    if not session.operations:
        raise EngineError("There are no operations yet. Derive them and call compose.")


def record(
    session: Session,
    op_id: str,
    output: str = "",
    preserves: str = "",
    assumptions: list[str] | None = None,
    evidence: str = "",
    still_holds: str = "",
) -> Literal["recorded", "confirmed"]:
    """Store an operation's output, or confirm that a stale output still holds."""
    _require_active(session)
    op = session.operation(op_id)
    state = states(session)
    waiting = [n for n in op.needs if state[n] != "current"]
    if waiting:
        first = ready(session, state)[0].id
        raise EngineError(
            f"'{op.id}' can't be recorded yet: it needs {_names(waiting)}, which {'is' if len(waiting) == 1 else 'are'} not current. "
            f"Work on '{first}' first."
        )
    if still_holds.strip():
        latest = op.result
        if latest is None:
            raise EngineError(f"'{op.id}' has no earlier output to confirm. Record its output.")
        if state[op.id] == "current":
            raise EngineError(f"'{op.id}' is already current; there is nothing to confirm.")
        latest.inputs = {n: session.operation(n).version for n in op.needs}
        latest.purpose = session.purpose
        op.open = False
        op.notes.append(Note(text=f"Confirmed v{latest.version} still holds: {still_holds.strip()}"))
        session.touch()
        return "confirmed"
    if state[op.id] == "current":
        raise EngineError(f"'{op.id}' is already current. If its output has to change, revise it first and say why.")
    if not output.strip():
        raise EngineError(f"Record the actual output of '{op.id}': {op.produces}")
    if not preserves.strip():
        raise EngineError(
            f"Say how this output still serves the value: {session.value} "
            "If it doesn't, change the work, or revise the value itself and say why."
        )
    op.results.append(
        Result(
            version=op.version + 1,
            output=output.strip(),
            preserves=preserves.strip(),
            assumptions=[a.strip() for a in assumptions or [] if a.strip()],
            evidence=evidence.strip(),
            inputs={n: session.operation(n).version for n in op.needs},
            purpose=session.purpose,
        )
    )
    op.open = False
    session.touch()
    return "recorded"


def revise(session: Session, reason: str, op_id: str = "", value: str = "", result: str = "") -> list[str]:
    """Reopen an operation, or change the purpose itself. Returns the ids that were current and are now stale."""
    if not reason.strip():
        raise EngineError("Say what observation undermines it: reason.")
    before = states(session)
    if op_id.strip():
        if value.strip() or result.strip():
            raise EngineError("Revise one thing at a time: an operation, or the value and result.")
        op = session.operation(op_id)
        if op.open:
            raise EngineError(f"'{op.id}' is already open; record its output.")
        op.open = True
        op.notes.append(Note(text=f"Revised: {reason.strip()}"))
    elif value.strip() or result.strip():
        changes = []
        if value.strip():
            changes.append(f"value was: {session.value}")
            session.value = value.strip()
        if result.strip():
            changes.append(f"result was: {session.result}")
            session.result = result.strip()
        session.purpose += 1
        session.log.append(Note(text=f"Purpose changed ({'; '.join(changes)}): {reason.strip()}"))
    else:
        raise EngineError("Name the operation to reopen, or give the new value or result.")
    session.status = "active"
    session.touch()
    after = states(session)
    return [op.id for op in session.operations if before[op.id] == "current" and after[op.id] != "current" and op.id != op_id.strip()]


def finish(session: Session, delivered: str, evidence: str, limitations: str = "") -> list[str]:
    """Close the session. Returns the operations that were not current when it closed."""
    if session.status == "finished":
        raise EngineError(f"Session {session.id} is already finished.")
    if not delivered.strip():
        raise EngineError("Say what was delivered and how to reach it: delivered.")
    if not evidence.strip():
        raise EngineError("Say what was actually checked: that the result works as built, and separately that it achieves its purpose.")
    state = states(session)
    unfinished = [op.id for op in session.operations if state[op.id] != "current"]
    if unfinished and not limitations.strip():
        raise EngineError(
            f"{_names(unfinished)} {'is' if len(unfinished) == 1 else 'are'} not current. "
            "Finish them, or say in limitations why the session ends without them."
        )
    session.delivered, session.evidence, session.limitations = delivered.strip(), evidence.strip(), limitations.strip()
    session.status = "finished"
    session.log.append(Note(text="Finished" + (f" with {_names(unfinished)} not current" if unfinished else "")))
    session.touch()
    return unfinished
