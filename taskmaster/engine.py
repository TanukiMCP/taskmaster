"""The step engine: sessions, matrix entries, plans, and SOP steps.

A session holds the end goal and an ordered list of matrix entries. Each entry
follows its situation's SOP: the agent first writes a plan with one item per
SOP step, then Taskmaster issues the steps in order. Each step finishes with
results that cite the earlier results they build on. The engine never judges
the work: a verify step ends at "ready", and only the user's verdict marks it
done or returns it to a step.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .library import FIRST_STEP, SCOPES, SITUATIONS, VERIFY_STEP, Library, SopStep

Situation = Literal["create", "extend", "redesign", "fix", "review"]
Scope = Literal["element", "component", "section", "page", "flow", "product", "shared-styles"]
CaptureKind = Literal["result", "comparison", "before"]

# The rungs an entry may escalate to, from the matrix's Parent column.
PARENTS: dict[str, tuple[str, ...]] = {
    "element": ("component", "section"),
    "component": ("section", "page"),
    "section": ("page",),
    "page": ("flow", "product"),
    "flow": ("product",),
    "product": (),
    "shared-styles": ("product",),
}

CAPTURE_WIDTHS = (1440, 820, 390)


class EngineError(ValueError):
    """The requested move does not fit the session's current position."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _words(text: str) -> str:
    text = text.lower()
    for chars, plain in (("‘’‛`", "'"), ("“”", '"'), ("–—", "-")):
        text = re.sub(f"[{chars}]", plain, text)
    return re.sub(r"\s+", " ", text).strip()


def quote_found(quote: str, words: str) -> bool:
    """A quote counts when it is at least three words and appears in the user's words."""
    q = _words(quote).strip("\"' .")
    return len(q.split(" ")) >= 3 and q in _words(words)


class EntryInput(BaseModel):
    situation: Situation = Field(description="create, extend, redesign, fix, or review — chosen with the matrix selector questions")
    scope: Scope = Field(description="element, component, section, page, flow, product, or shared-styles — the smallest unit containing every decision to change")
    goal: str = Field(description="What this entry must achieve, worked backward from the session's end goal")


class ConstraintInput(BaseModel):
    constraint: str = Field(description="What must be kept or followed, such as keeping the existing typography")
    quote: str = Field(description="The user's own words that say so, copied exactly from the request (at least three words)")


class ResultInput(BaseModel):
    statement: str = Field(description="One result of this step: a decision, a finding, or what is kept and why")
    based_on: list[str] = Field(default_factory=list, description="IDs of the earlier results, constraints (C1…), or 'request' this result builds on")


class DropInput(BaseModel):
    id: str = Field(description="ID of an earlier result that no later step will use")
    reason: str = Field(description="Why it is not carried further")


class Constraint(BaseModel):
    id: str
    text: str
    quote: str


class Handoff(BaseModel):
    sop_step: int
    iteration: int
    text: str
    at: str = Field(default_factory=_now)


class Result(BaseModel):
    id: str
    sop_step: int
    iteration: int
    statement: str
    based_on: list[str]
    at: str = Field(default_factory=_now)


class Verification(BaseModel):
    sop_step: int
    iteration: int
    outcome: str
    findings: str = ""
    at: str = Field(default_factory=_now)


class Capture(BaseModel):
    kind: CaptureKind
    label: str
    url: str
    selector: str | None = None
    taken_by: Literal["taskmaster", "agent"]
    taken_at: str = Field(default_factory=_now)
    widths: list[dict] = Field(default_factory=list)


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
    results: list[Result] = Field(default_factory=list)
    dropped: dict[str, str] = Field(default_factory=dict)
    captures: list[Capture] = Field(default_factory=list)
    verifications: list[Verification] = Field(default_factory=list)
    awaiting_user: bool = False
    last_completed_at: str = ""
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
    constraints: list[Constraint] = Field(default_factory=list)
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


def needs_verdict(entry: Entry) -> bool:
    """Every situation except Review ends its verify step with the user's verdict."""
    return entry.situation != "review"


def new_session(
    request: str,
    end_goal: str,
    entries: list[EntryInput],
    conditions: str = "",
    constraints: list[ConstraintInput] | None = None,
) -> Session:
    if not entries:
        raise EngineError("A session needs at least one matrix entry. Use get_matrix to choose situation and scope.")
    if not request.strip():
        raise EngineError("request is the user's own words, copied exactly.")
    recorded: list[Constraint] = []
    problems: list[str] = []
    for n, item in enumerate(constraints or [], 1):
        if not item.constraint.strip():
            problems.append(f"Constraint {n} doesn't say what must be kept or followed.")
        elif not quote_found(item.quote, request):
            problems.append(
                f'Constraint {n} ("{item.constraint.strip()}") has no quote from the request of at least three words. '
                "Without the user's own words it is not a constraint; leave that decision open."
            )
        else:
            recorded.append(Constraint(id=f"C{n}", text=item.constraint.strip(), quote=item.quote.strip()))
    if problems:
        raise EngineError(" ".join(problems))
    session = Session(
        request=request.strip(),
        end_goal=end_goal.strip(),
        conditions=conditions.strip(),
        constraints=recorded,
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
    entry.awaiting_user = False


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


def _waiting(entry: Entry) -> None:
    if entry.awaiting_user:
        raise EngineError(
            "The work is ready for the user's review. Only the user marks it done or returns it to a step; "
            "show them the captures and wait for their verdict."
        )


def _require_running(library: Library, session: Session) -> tuple[Entry, SopStep]:
    entry = _require_entry(session)
    if entry.phase == "plan":
        count = len(sop_steps(library, entry))
        raise EngineError(f"Write the plan first: call submit_plan with {count} items, one per SOP step of {entry.label}.")
    _waiting(entry)
    return entry, current_sop_step(library, entry)


def submit_plan(library: Library, session: Session, plan: list[str]) -> bool:
    """Record the plan for the current entry. Returns True when this starts the entry's work."""
    entry = _require_entry(session)
    _waiting(entry)
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


def latest_results(entry: Entry) -> dict[str, Result]:
    """The current results of the entry, by ID; a rerun step replaces its earlier results."""
    return {r.id: r for r in entry.results}


def _citable(session: Session, entry: Entry, step_number: int) -> set[str]:
    earlier = {r.id for r in entry.results if r.sop_step < step_number}
    return earlier | {c.id for c in session.constraints} | {"request"}


def complete_step(
    library: Library,
    session: Session,
    handoff: str = "",
    responsible_step: int | None = None,
    results: list[ResultInput] | None = None,
    dropped: list[DropInput] | None = None,
) -> None:
    entry, step = _require_running(library, session)
    if step.kind == "verify":
        raise EngineError(
            "This is a verify step. Finish it with report_verification: outcome 'ready', or the number of the "
            "procedure step responsible for a discrepancy."
        )
    if not handoff.strip():
        raise EngineError("handoff is required: name the actual result and how the next step uses it.")
    if step.kind == "trace" and (responsible_step is None or not FIRST_STEP <= responsible_step < VERIFY_STEP):
        raise EngineError("This trace step needs responsible_step: the procedure step (0–9) where the cause lies.")

    items = [r for r in (results or []) if r.statement.strip()]
    first_step = step.number == sop_steps(library, entry)[0].number
    citable = _citable(session, entry, step.number)
    earlier = {r.id for r in entry.results if r.sop_step < step.number}
    problems: list[str] = []
    if not items:
        problems.append("results are required: each result of this step as a statement with the IDs it is based on.")
    for n, item in enumerate(items, 1):
        cited = [c.strip() for c in item.based_on if c.strip()]
        unknown = [c for c in cited if c not in citable]
        if unknown:
            problems.append(f"Result {n} cites {', '.join(unknown)}, which are not earlier results, constraints, or 'request'.")
        if not cited:
            problems.append(f"Result {n} cites nothing. Name the earlier results it builds on.")
        elif not first_step and not any(c in earlier for c in cited):
            problems.append(f"Result {n} cites no earlier result. Every step after the first builds on an earlier step's results.")
    drops: dict[str, str] = {}
    for d in dropped or []:
        if d.id not in earlier:
            problems.append(f"Dropped {d.id} is not an earlier result.")
        elif not d.reason.strip():
            problems.append(f"Dropping {d.id} needs a reason.")
        else:
            drops[d.id] = d.reason.strip()
    if problems:
        raise EngineError(" ".join(problems))

    if step.kind == "trace":
        entry.k = responsible_step
    entry.results = [r for r in entry.results if r.sop_step != step.number]
    for n, item in enumerate(items, 1):
        entry.results.append(
            Result(
                id=f"{step.number}.{n}",
                sop_step=step.number,
                iteration=entry.iteration,
                statement=item.statement.strip(),
                based_on=[c.strip() for c in item.based_on if c.strip()],
            )
        )
    entry.dropped.update(drops)
    entry.handoffs.append(Handoff(sop_step=step.number, iteration=entry.iteration, text=handoff.strip()))
    entry.last_completed_at = _now()
    _advance(session, library, entry)
    session.updated = _now()


def unused_results(library: Library, entry: Entry) -> list[Result]:
    """Results no later step cites and that were not dropped, apart from the last step before verification."""
    steps = sop_steps(library, entry)
    verify_at = next((s.number for s in steps if s.kind == "verify"), None)
    before_verify = max((s.number for s in steps if verify_at is not None and s.number < verify_at), default=None)
    cited = {c for r in entry.results for c in r.based_on}
    return [
        r
        for r in entry.results
        if r.id not in cited and r.id not in entry.dropped and r.sop_step != before_verify
    ]


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


def _rerun(library: Library, entry: Entry, step: SopStep, k: int, outcome: str, findings: str) -> None:
    entry.verifications.append(Verification(sop_step=step.number, iteration=entry.iteration, outcome=outcome, findings=findings))
    if any(s.uses_k for s in sop_steps(library, entry)):
        entry.k = k
    entry.index = _return_target(library, entry, k)
    entry.resume_at = k
    entry.iteration += 1


def _parse_step(value: str) -> int:
    try:
        k = int(value)
    except ValueError:
        raise EngineError("outcome must be 'ready' or a procedure step number from 0 to 9.") from None
    if not FIRST_STEP <= k < VERIFY_STEP:
        raise EngineError("A responsible step is a procedure step number from 0 to 9; step 10 itself cannot be the cause.")
    return k


def report_verification(library: Library, session: Session, outcome: str, findings: str = "") -> str:
    """Record a verify step's result. Returns 'ready', 'done' (Review only), or 'rerun'."""
    entry, step = _require_running(library, session)
    if step.kind != "verify":
        raise EngineError(
            f"report_verification belongs to a verify step; SOP step {step.number} ({step.title}) finishes with complete_step."
        )
    value = outcome.strip().lower()

    if not needs_verdict(entry):
        if value in ("done", "ready"):
            entry.verifications.append(Verification(sop_step=step.number, iteration=entry.iteration, outcome="done", findings=findings.strip()))
            _advance(session, library, entry)
            session.updated = _now()
            return "done"
        _parse_step(value)
        raise EngineError(
            "Review stops before implementation. Record each finding with its responsible step and report outcome 'done'; "
            "acting on findings needs the user's authorization and a Fix or Redesign entry (add_entries)."
        )

    if value in ("ready", "done"):
        problems: list[str] = []
        unused = unused_results(library, entry)
        if unused:
            listed = "; ".join(f"{r.id} ({r.statement[:60]})" for r in unused)
            problems.append(
                f"These results are not used by any later step: {listed}. Use them, or drop them with a reason "
                "(complete_step's dropped) on a rerun."
            )
        fresh = [c for c in entry.captures if c.kind == "result" and c.taken_at >= entry.last_completed_at]
        if not fresh:
            problems.append("Capture the result first (capture with kind 'result'), after the last change to the work.")
        if not any(c.kind in ("comparison", "before") for c in entry.captures):
            problems.append("Capture what the result is compared with: its references or accepted views (kind 'comparison'), or the work before (kind 'before').")
        if problems:
            raise EngineError(" ".join(problems))
        entry.verifications.append(Verification(sop_step=step.number, iteration=entry.iteration, outcome="ready", findings=findings.strip()))
        entry.awaiting_user = True
        session.updated = _now()
        return "ready"

    k = _parse_step(value)
    _rerun(library, entry, step, k, str(k), findings.strip())
    session.updated = _now()
    return "rerun"


def record_verdict(library: Library, session: Session, verdict: str, step: int | None = None, reason: str = "") -> str:
    """The user's verdict on work that is ready for review: 'done', or 'return' to a procedure step with a reason."""
    entry = _require_entry(session)
    if not entry.awaiting_user:
        raise EngineError(f"Session {session.id} has no work waiting for a verdict.")
    sop_step = current_sop_step(library, entry)
    value = verdict.strip().lower()
    if value == "done":
        entry.awaiting_user = False
        entry.verifications.append(Verification(sop_step=sop_step.number, iteration=entry.iteration, outcome="done (user)", findings=reason.strip()))
        _advance(session, library, entry)
        session.updated = _now()
        return "done"
    if value == "return":
        if step is None:
            raise EngineError("Say which procedure step (0–9) the work returns to.")
        if not reason.strip():
            raise EngineError("Give the reason the work is returned.")
        k = _parse_step(str(step))
        entry.awaiting_user = False
        _rerun(library, entry, sop_step, k, f"returned by the user to step {k}", reason.strip())
        session.updated = _now()
        return "return"
    raise EngineError("verdict is 'done' or 'return'.")


def add_capture(
    session: Session,
    kind: CaptureKind,
    label: str,
    manifest: dict,
    taken_by: Literal["taskmaster", "agent"],
) -> Capture:
    """Record one capture from the capture script's manifest. A capture that failed at any width is refused."""
    entry = _require_entry(session)
    _waiting(entry)
    if entry.phase == "plan":
        raise EngineError("Write the plan first.")
    widths = manifest.get("widths") if isinstance(manifest, dict) else None
    if not isinstance(widths, list) or sorted(w.get("width") for w in widths if isinstance(w, dict)) != sorted(CAPTURE_WIDTHS):
        raise EngineError(f"A capture covers {', '.join(map(str, CAPTURE_WIDTHS))} pixels wide; this manifest doesn't.")
    failed = [f"{w['width']}: {w.get('error', 'did not render')}" for w in widths if not w.get("ok")]
    if failed:
        raise EngineError(f"The capture of {manifest.get('url')} failed at {'; '.join(failed)}. Fix the page or the selector and capture it again.")
    capture = Capture(
        kind=kind,
        label=label.strip() or kind,
        url=str(manifest.get("url", "")),
        selector=manifest.get("selector") or None,
        taken_by=taken_by,
        widths=widths,
    )
    entry.captures.append(capture)
    session.updated = _now()
    return capture


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
    _waiting(entry)
    if to_scope is None and to_situation is None:
        raise EngineError("Escalate to a scope, a situation, or both.")
    if not reason.strip():
        raise EngineError("Say why the decision belongs elsewhere.")
    if to_scope is not None and to_scope != entry.scope and to_scope not in PARENTS[entry.scope]:
        parents = ", ".join(PARENTS[entry.scope]) or "none"
        raise EngineError(f"An entry escalates to its parent scope. The parent of {entry.scope} is: {parents}.")
    if entry.situation == "review" and to_situation not in (None, "review"):
        raise EngineError(
            "A Review doesn't turn into changes on its own. Acting on findings needs the user's authorization and a Fix or "
            "Redesign entry (add_entries)."
        )
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
